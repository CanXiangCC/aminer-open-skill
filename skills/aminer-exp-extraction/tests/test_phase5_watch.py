"""v0.7 Phase 5 watch/dynamic-discovery tests (TODO-V07-06).

Two layers:
  1. _ManifestFeeder unit tests — queue-tail ordering, once vs watch, idle
     timeout, unreadable new files, STOP, no rescan in once mode.
  2. run_bulk.main() integration with a fake scheduler (Phase 3 harness
     pattern): watch discovers a batch published mid-run and processes it in
     tail order for BOTH scheduler branches; once mode exits after the
     startup snapshot; the currently-running batch file is never modified;
     flat merge over the resulting run has no duplicates.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

PROD_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROD_ROOT))

import pipeline.production.config as config_mod  # noqa: E402
import pipeline.production.monitor as monitor_mod  # noqa: E402
import pipeline.production.post_llm as post_llm  # noqa: E402
import pipeline.production.run_paths as run_paths  # noqa: E402
import pipeline.production.staged_pipeline_wf4 as staged_mod  # noqa: E402

WF = "prod-wf4-llm-datasets-experiment"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


run_bulk = _load("run_bulk_phase5w", PROD_ROOT / "scripts" / "run_bulk.py")
mfe = _load("mfe_phase5w", PROD_ROOT / "scripts" / "merge_flat_experiments.py")


def _batch_file(mdir: Path, idx: int, pids: list[str]) -> Path:
    p = mdir / f"job_batch_{idx:03d}.json"
    p.write_text(
        json.dumps(
            {
                "job_batch_id": f"job_batch_{idx:03d}",
                "batch_index": idx,
                "size": len(pids),
                "papers": [
                    {"paper_id": pid, "md_url": f"http://local/{pid}.md"} for pid in pids
                ],
            }
        ),
        encoding="utf-8",
    )
    return p


# --------------------------------------------------------- feeder unit tests


def _feeder(mdir: Path, batches, **kw):
    defaults = dict(
        manifest_dir=mdir,
        session_run_id="s",
        watch=False,
        poll_interval=0.05,
        idle_timeout=0.3,
    )
    defaults.update(kw)
    return run_bulk._ManifestFeeder(batches, **defaults)


def test_once_mode_returns_snapshot_then_none_without_rescan(tmp_path: Path):
    mdir = tmp_path / "m"
    mdir.mkdir()
    _batch_file(mdir, 0, ["a"])
    f = _feeder(mdir, [("job_batch_000", ["a"], "s")])
    assert f.next_batch() == ("job_batch_000", ["a"], "s", 1)
    assert f.next_batch() is None
    assert f.rescans == 0  # legacy behavior: never re-globs
    # a batch published afterwards is NOT picked up in once mode
    _batch_file(mdir, 1, ["b"])
    assert f.next_batch() is None


def test_watch_discovers_new_batch_at_tail(tmp_path: Path):
    mdir = tmp_path / "m"
    mdir.mkdir()
    _batch_file(mdir, 0, ["a"])
    f = _feeder(mdir, [("job_batch_000", ["a"], "s")], watch=True)
    assert f.next_batch()[0] == "job_batch_000"
    _batch_file(mdir, 2, ["c"])  # published while watching
    _batch_file(mdir, 1, ["b"])
    got = [f.next_batch()[0] for _ in range(2)]
    assert got == ["job_batch_001", "job_batch_002"]  # sorted order => queue tail
    t0 = time.perf_counter()
    assert f.next_batch() is None  # idle timeout reached, bounded exit
    assert time.perf_counter() - t0 >= 0.25


def test_watch_skips_unreadable_new_file(tmp_path: Path):
    mdir = tmp_path / "m"
    mdir.mkdir()
    _batch_file(mdir, 0, ["a"])
    f = _feeder(mdir, [("job_batch_000", ["a"], "s")], watch=True, idle_timeout=0.2)
    assert f.next_batch()[0] == "job_batch_000"
    (mdir / "job_batch_001.json").write_text("{not json", encoding="utf-8")
    assert f.next_batch() is None  # bad file ignored, run still finishes
    assert f.rescans >= 1


def test_watch_never_readds_startfrom_filtered_batches(tmp_path: Path):
    """Batches skipped past via --start-from must not re-enter via rescan."""
    mdir = tmp_path / "m"
    mdir.mkdir()
    _batch_file(mdir, 0, ["a"])
    _batch_file(mdir, 1, ["b"])
    # startup snapshot == only job_batch_001 (as after --start-from 001)
    f = _feeder(mdir, [("job_batch_001", ["b"], "s")], watch=True, idle_timeout=0.2)
    assert f.next_batch()[0] == "job_batch_001"
    assert f.next_batch() is None  # job_batch_000 on disk but NOT re-added
    f2 = _feeder(mdir, [("job_batch_001", ["b"], "s")], watch=True, idle_timeout=0.2)
    assert f2.next_batch()[0] == "job_batch_001"
    _batch_file(mdir, 2, ["c"])  # published AFTER f2 started watching
    assert f2.next_batch()[0] == "job_batch_002"  # genuinely new file is added


def test_watch_stop_event_ends_polling(tmp_path: Path):
    mdir = tmp_path / "m"
    mdir.mkdir()
    f = _feeder(mdir, [], watch=True, idle_timeout=10.0)
    run_bulk.STOP.set()
    t0 = time.perf_counter()
    assert f.next_batch() is None
    assert time.perf_counter() - t0 < 0.5  # did not wait for the 10s timeout
    run_bulk.STOP.clear()


# ------------------------------------------------- main() integration harness


class _FakeSched:
    constructed: list["_FakeSched"] = []

    def __init__(self, paper_ids, md_paths, run_id, spec, **kwargs) -> None:
        self.paper_ids = list(paper_ids)
        self.run_id = run_id
        self.batch_monitor = {"pipeline_mode": "fake"}
        _FakeSched.constructed.append(self)

    def run(self) -> list:
        # the REAL schedulers commit predictions during run(); the fake must too
        session, jid = self.run_id.split("/", 1)
        pred_dir = run_paths.job_batch_run_dir(session, jid) / "predictions"
        pred_dir.mkdir(parents=True, exist_ok=True)
        results = []
        for pid in self.paper_ids:
            (pred_dir / f"{pid}.json").write_text(
                json.dumps(
                    {
                        "paper_id": pid,
                        "run_id": self.run_id,
                        "workflow_id": WF,
                        "experiments": [{"experiment_name": "E1"}],
                    }
                ),
                encoding="utf-8",
            )
            results.append(
                SimpleNamespace(
                    paper_id=pid, error=None, monitor={}, experiments=[{"experiment_name": "E1"}]
                )
            )
        return results


class _MainEnv:
    """Hermetic run_bulk.main(): all writes under tmp_path, no network."""

    def __init__(self, monkeypatch, tmp_path: Path, scheduler_mode: str) -> None:
        monkeypatch.setattr(post_llm, "RUNS_DIR", tmp_path)
        monkeypatch.setattr(config_mod, "RUNS_DIR", tmp_path)
        monkeypatch.setattr(run_paths, "RUNS_DIR", tmp_path)
        monkeypatch.setattr(config_mod, "PARTIALS_DIR", tmp_path / "partials")
        monkeypatch.setattr(monitor_mod, "RUN_HISTORY_PATH", tmp_path / "history.jsonl")
        monkeypatch.setattr(run_bulk, "EVAL_MD_CACHE_DIR", tmp_path / "md_cache")
        monkeypatch.setattr(run_bulk, "PROD_ROOT", tmp_path)
        monkeypatch.setattr(run_bulk, "LOGS_ROOT", tmp_path / "logs")
        monkeypatch.setattr(run_bulk, "_merge_exports", lambda *a, **k: None)
        monkeypatch.setattr(run_bulk, "_load_vendor_meta", lambda: {})
        _FakeSched.constructed = []
        if scheduler_mode == "staged":
            monkeypatch.setattr(staged_mod, "StagedPipelineWf4", _FakeSched)
        else:
            monkeypatch.setattr(run_bulk, "BatchBertPipelineSchedulerWf4", _FakeSched)
        run_bulk.STOP.clear()

        self.cfg = tmp_path / "cfg.yaml"
        self.cfg.write_text(
            "\n".join(
                [
                    f"workflow: {WF}",
                    f"scheduler_mode: {scheduler_mode}",
                    f"bert_pipeline_mode: {'global_batch' if scheduler_mode == 'staged' else 'chunked_overlap'}",
                    "md_prefetch_window: 50",
                    "merge_every_n_job_batches: 0",
                    "md_cache_cleanup_on_batch_done: false",
                    "write_per_paper_monitor: false",
                    "md_fetch_concurrency: 2",
                    "md_fetch_retries: 1",
                ]
            ),
            encoding="utf-8",
        )

    def seed_md(self, tmp_path: Path, pids: list[str]) -> None:
        cache = tmp_path / "md_cache"
        cache.mkdir(parents=True, exist_ok=True)
        for pid in pids:
            (cache / f"{pid}.md").write_text("cached md body", encoding="utf-8")


def _run_main(monkeypatch, tmp_path: Path, *, scheduler_mode: str, argv: list[str], seed_pids: list[str]):
    env = _MainEnv(monkeypatch, tmp_path, scheduler_mode)
    env.seed_md(tmp_path, seed_pids)  # md cache pre-seeded: zero network in tests
    monkeypatch.setattr(
        sys,
        "argv",
        ["run_bulk.py", "--config", str(env.cfg), "--run-id", "watchrun",
         "--session-id", "watchsess", "--no-gate", *argv],
    )
    run_bulk.main()
    return env


def _pids_in_run(tmp_path: Path) -> dict[str, list[str]]:
    out = {}
    for bdir in sorted((tmp_path / "watchrun").glob("job_batch_*")):
        out[bdir.name] = sorted(p.stem for p in (bdir / "predictions").glob("*.json"))
    return out


@pytest.mark.parametrize("scheduler_mode", ["default", "staged"])
def test_watch_discovers_midrun_batch_and_merges_clean(
    tmp_path: Path, monkeypatch, scheduler_mode: str
) -> None:
    mdir = tmp_path / "m"
    mdir.mkdir()
    b0 = _batch_file(mdir, 0, ["p1", "p2"])
    b0_sha = hashlib.sha256(b0.read_bytes()).hexdigest()

    def publish_later() -> None:
        time.sleep(0.15)
        _batch_file(mdir, 1, ["p3"])

    timer = threading.Timer(0.15, publish_later)
    timer.start()
    _run_main(
        monkeypatch,
        tmp_path,
        scheduler_mode=scheduler_mode,
        argv=[
            "--manifest-dir", str(mdir),
            "--watch-manifest", "--poll-interval", "0.05",
            "--watch-idle-timeout", "0.5",
        ],
        seed_pids=["p1", "p2", "p3"],
    )

    # both batches processed, new one AFTER the running one (queue tail)
    assert [c.run_id for c in _FakeSched.constructed] == [
        "watchrun/job_batch_000",
        "watchrun/job_batch_001",
    ]
    preds = _pids_in_run(tmp_path)
    assert preds == {"job_batch_000": ["p1", "p2"], "job_batch_001": ["p3"]}
    # currently-running batch manifest file untouched (ingest only appends new files)
    assert hashlib.sha256(b0.read_bytes()).hexdigest() == b0_sha
    state = json.loads(
        (tmp_path / "pipeline_output" / "production" / "bulk_state.json").read_text(encoding="utf-8")
    )
    assert state["status"] == "done" and state["jobs_done"] == 2

    # flat merge over the whole run: every paper exactly once, no duplicates
    monkeypatch.setattr(mfe, "RUNS_DIR", tmp_path)
    monkeypatch.setattr(mfe, "OUT_DIR", tmp_path / "exports")
    out = tmp_path / "exports" / "flat.json"
    monkeypatch.setattr(
        sys, "argv",
        ["mfe", "--session-run-id", "watchrun", "--out", str(out)],
    )
    mfe.main()
    flat = json.loads(out.read_text(encoding="utf-8"))
    assert sorted(e["paper_id"] for e in flat) == ["p1", "p2", "p3"]  # no dup entries


def test_once_mode_ignores_midrun_publish_and_exits(tmp_path: Path, monkeypatch) -> None:
    mdir = tmp_path / "m"
    mdir.mkdir()
    _batch_file(mdir, 0, ["p1", "p2"])
    # job_batch_001 is published 0.1s AFTER main() starts — once mode must
    # ignore it (no re-scan) and exit normally after the startup snapshot.
    def publish_later() -> None:
        time.sleep(0.1)
        _batch_file(mdir, 1, ["p3"])

    threading.Timer(0.1, publish_later).start()
    _run_main(
        monkeypatch,
        tmp_path,
        scheduler_mode="default",
        argv=["--manifest-dir", str(mdir)],  # NO --watch-manifest
        seed_pids=["p1", "p2"],
    )

    assert [c.run_id for c in _FakeSched.constructed] == ["watchrun/job_batch_000"]
    assert set(_pids_in_run(tmp_path)) == {"job_batch_000"}  # p3 NOT processed
    state = json.loads(
        (tmp_path / "pipeline_output" / "production" / "bulk_state.json").read_text(encoding="utf-8")
    )
    assert state["status"] == "done" and state["jobs_done"] == 1  # normal exit


if __name__ == "__main__":
    raise SystemExit("run via pytest")
