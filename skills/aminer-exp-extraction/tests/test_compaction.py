"""Compaction core (TODO-V07-11 c2) — state machine, crash windows A–F,
conservation gate, resume semantics, CLI.

The pre-registered crash windows (plan POSTV0708 §4):
  A  记账后选窗前      — nothing on disk yet; next trigger redoes (covered by
                        threshold test)
  B  选窗后合并中      — stale unregistered window dir; finalize deletes it,
                        originals untouched, redo succeeds
  C  合并后发布前      — same as B (window not registered)
  D  发布后注册前      — stable flat may hold the rows; republish converges
                        (old − window pids ∪ window rows = same set)
  E  注册后删源中      — registered window; finalize completes deletion
                        idempotently
  F  history 重写前后  — extraction/rewrite converge on re-run; window
                        history.jsonl is write-once
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

PROD_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROD_ROOT))

import pipeline.production.compaction as cmp_mod  # noqa: E402
import pipeline.production.config as config_mod  # noqa: E402
import pipeline.production.monitor as monitor_mod  # noqa: E402
import pipeline.production.run_paths as run_paths  # noqa: E402
from pipeline.production import completion_ledger as cl  # noqa: E402
from pipeline.production.schema import empty_experiment  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "compact_run_cli", PROD_ROOT / "scripts" / "compact_run.py"
)
compact_run_cli = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(compact_run_cli)

SESSION = "cmp1"


class _Env:
    def __init__(self, monkeypatch, tmp_path: Path, session: str = SESSION) -> Path:
        self.session = session
        self.runs = tmp_path / "runs"
        monkeypatch.setattr(run_paths, "RUNS_DIR", self.runs)
        monkeypatch.setattr(config_mod, "RUNS_DIR", self.runs)
        monkeypatch.setattr(config_mod, "PARTIALS_DIR", tmp_path / "partials")
        monkeypatch.setattr(config_mod, "RUN_HISTORY_PATH", tmp_path / "history.jsonl")
        monkeypatch.setattr(monitor_mod, "RUN_HISTORY_PATH", tmp_path / "history.jsonl")
        cl.reset_cache()

    # -- fixture builders ---------------------------------------------------

    def write_prediction(
        self,
        pid: str,
        jb: str = "job_batch_000",
        n_exp: int = 1,
        error: str | None = None,
        title: str | None = None,
    ) -> Path:
        exps = []
        for j in range(n_exp):
            e = empty_experiment(pid)
            e.pop("research_problem", None)  # paper-level; MergerWf4 pops it
            e["experiment_name"] = f"E{j}"
            exps.append(e)
        pred = {
            "paper_id": pid,
            "run_id": f"{self.session}/{jb}",
            "workflow_id": "prod-wf4-llm-datasets-experiment",
            "workflow_version": "0.7.0",
            "paper_title": title or f"Title {pid}",
            "research_problem": "RP",
            "research_problem_description": "RPD",
            "research_problem_aliases": [],
            "experiments": exps,
        }
        if error:
            pred["error"] = error
        d = self.runs / self.session / jb / "predictions"
        d.mkdir(parents=True, exist_ok=True)
        p = d / f"{pid}.json"
        p.write_text(json.dumps(pred, indent=2) + "\n", encoding="utf-8")
        return p

    def write_monitor(self, pid: str, jb: str = "job_batch_000", prompt_chars: int = 123) -> None:
        d = self.runs / self.session / jb / "monitors"
        d.mkdir(parents=True, exist_ok=True)
        mon = {
            "paper_id": pid,
            "run_id": f"{self.session}/{jb}",
            "extractors": [
                {
                    "extractor_id": "llm.wf4_dev20_v2_wash_datasets",
                    "metadata": {"prompt_chars": prompt_chars},
                }
            ],
        }
        (d / f"{pid}_monitor.json").write_text(json.dumps(mon), encoding="utf-8")

    def write_partial(self, pid: str, run_id: str | None = None, eid: str = "llm.wf4_dev20_v2_wash_datasets") -> None:
        d = config_mod.PARTIALS_DIR / eid
        d.mkdir(parents=True, exist_ok=True)
        payload = {"paper_id": pid, "run_id": run_id or f"{self.session}/job_batch_000",
                   "status": "ok", "value": None}
        (d / f"{pid}.json").write_text(json.dumps(payload), encoding="utf-8")

    def append_history_line(self, pid: str, run_id: str) -> None:
        config_mod.RUN_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        with config_mod.RUN_HISTORY_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"ts": "2026-08-21T00:00:00Z", "run_id": run_id,
                                 "paper_id": pid, "error": None}) + "\n")

    def history_lines(self) -> list[dict]:
        if not config_mod.RUN_HISTORY_PATH.exists():
            return []
        return [json.loads(x) for x in
                config_mod.RUN_HISTORY_PATH.read_text(encoding="utf-8").splitlines() if x.strip()]

    def on_disk_preds(self) -> list[Path]:
        return [p for _jb, p in cmp_mod.iter_on_disk_predictions(self.session)]

    def make_standard_run(self) -> None:
        """6 papers / 2 batches: 4 single-exp ok, 1 multi-exp (2 exp), 1 error."""
        self.write_prediction("p000", n_exp=1)
        self.write_prediction("p001", n_exp=1)
        self.write_prediction("p002", jb="job_batch_001", n_exp=2)  # multi-exp
        self.write_prediction("p003", jb="job_batch_001", n_exp=1)
        self.write_prediction("p004", jb="job_batch_001", n_exp=1, error="llm_timeout")
        self.write_prediction("p005", jb="job_batch_001", n_exp=1)
        for pid, jb in [("p000", "job_batch_000"), ("p001", "job_batch_000"),
                        ("p002", "job_batch_001"), ("p003", "job_batch_001"),
                        ("p005", "job_batch_001")]:  # p004: monitor intentionally absent
            self.write_monitor(pid, jb=jb)
        self.write_partial("p000")
        self.write_partial("p002")
        self.write_partial("p003", run_id="other-session/job_batch_000")  # run_id guard case
        for pid, jb in [("p000", "job_batch_000"), ("p001", "job_batch_000"),
                        ("p002", "job_batch_001"), ("p003", "job_batch_001"),
                        ("p004", "job_batch_001"), ("p005", "job_batch_001")]:
            self.append_history_line(pid, f"{self.session}/{jb}")
        self.append_history_line("zzz", "other-session/job_batch_000")


# ---------------------------------------------------------------------------
# happy path
# ---------------------------------------------------------------------------

def test_full_compaction_happy_path(tmp_path: Path, monkeypatch) -> None:
    env = _Env(monkeypatch, tmp_path)
    env.make_standard_run()
    assert len(env.on_disk_preds()) == 6

    res = cmp_mod.compact_session(SESSION)

    assert res["status"] == "compacted"
    assert res["papers"] == 6
    assert res["flat_rows"] == 7  # 1+1+2+1+0(error)+1
    assert res["freed"]["predictions"] == 6
    assert res["freed"]["monitors"] == 5
    assert res["freed"]["partials"] == 2  # p000 + p002 only (p003 guarded)
    assert res["freed"]["history_rows"] == 6

    # sources gone
    assert env.on_disk_preds() == []
    wdir = cmp_mod.compaction_dir(SESSION) / res["window_id"]
    mon_dir = env.runs / SESSION / "job_batch_000" / "monitors"
    assert not mon_dir.exists() or not list(mon_dir.glob("*_monitor.json"))

    # window audit artifacts
    wjson = json.loads((wdir / "window.json").read_text(encoding="utf-8"))
    assert wjson["status"] == "sources_deleted"
    assert wjson["papers_count"] == 6
    assert wjson["monitors_missing"] == 1  # p004
    preds_lines = (wdir / "predictions.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(preds_lines) == 6
    mons = [json.loads(x) for x in
            (wdir / "monitors.jsonl").read_text(encoding="utf-8").splitlines()]
    assert {m["paper_id"] for m in mons} == {"p000", "p001", "p002", "p003", "p005"}
    hist = [json.loads(x) for x in
            (wdir / "history.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(hist) == 6
    part = wdir / "partials" / "llm.wf4_dev20_v2_wash_datasets.jsonl"
    assert {json.loads(x)["paper_id"] for x in part.read_text(encoding="utf-8").splitlines()} == {
        "p000", "p002"}

    # stable flat published + registered
    stable = cmp_mod.stable_flat_path(SESSION)
    rows = json.loads(stable.read_text(encoding="utf-8"))
    assert len(rows) == 7
    assert stable.read_bytes() and res["stable_flat_sha256"]
    state = cmp_mod.load_state(SESSION)
    assert len(state["windows"]) == 1
    assert state["windows"][0]["status"] == "sources_deleted"
    assert state["windows"][0]["papers_count"] == 6

    # global history rewritten: only other-session remains
    assert [(h["paper_id"], h["run_id"]) for h in env.history_lines()] == [
        ("zzz", "other-session/job_batch_000")
    ]
    # guarded partial survives
    assert (config_mod.PARTIALS_DIR / "llm.wf4_dev20_v2_wash_datasets" / "p003.json").exists()

    # ledger complete
    idx = cl.last_status_index(SESSION)
    assert idx["p000"] == "ok" and idx["p004"] == "error"


def test_resume_semantics_after_compaction(tmp_path: Path, monkeypatch) -> None:
    """关键场景：跑 → compaction → 同 run-id 重跑判定——ok 篇全 skip（账本），
    error 篇重试。"""
    env = _Env(monkeypatch, tmp_path)
    env.make_standard_run()
    cmp_mod.compact_session(SESSION)

    ok = lambda pid, jb: run_paths.prediction_ok(SESSION, jb, pid)  # noqa: E731
    assert ok("p000", "job_batch_000") is True   # ledger ok -> skip
    assert ok("p002", "job_batch_001") is True
    assert ok("p004", "job_batch_001") is False  # ledger error -> retry
    assert on_disk_count(SESSION) == 0


def on_disk_count(session: str) -> int:
    return cmp_mod.on_disk_prediction_count(session)


def test_rerun_after_compaction_reselects_and_converges(tmp_path: Path, monkeypatch) -> None:
    """Error paper re-run after compaction: new file reappears, next window
    re-compacts it; stable flat replaces its (zero) old rows."""
    env = _Env(monkeypatch, tmp_path)
    env.make_standard_run()
    r1 = cmp_mod.compact_session(SESSION)

    env.write_prediction("p004", jb="job_batch_001", n_exp=3, error=None)  # retry succeeded
    r2 = cmp_mod.compact_session(SESSION)
    assert r2["papers"] == 1 and r2["flat_rows"] == 3
    assert r2["window_id"] > r1["window_id"]

    stable = json.loads(cmp_mod.stable_flat_path(SESSION).read_text(encoding="utf-8"))
    assert len(stable) == 9  # 7 − p004's old 1 row + 3 new rows
    assert run_paths.prediction_ok(SESSION, "job_batch_001", "p004") is True


# ---------------------------------------------------------------------------
# threshold hook
# ---------------------------------------------------------------------------

def test_maybe_compact_threshold_gating(tmp_path: Path, monkeypatch) -> None:
    env = _Env(monkeypatch, tmp_path)
    for i in range(5):
        env.write_prediction(f"p{i:03d}", n_exp=1)

    assert cmp_mod.maybe_compact(SESSION, 10) is None       # below threshold
    assert cmp_mod.maybe_compact(SESSION, 0) is None        # disabled
    res = cmp_mod.maybe_compact(SESSION, 5)                 # at threshold
    assert res["status"] == "compacted"


def test_maybe_compact_counter_includes_registered(tmp_path: Path, monkeypatch) -> None:
    env = _Env(monkeypatch, tmp_path)
    for i in range(5):
        env.write_prediction(f"p{i:03d}", n_exp=1)
    assert cmp_mod.maybe_compact(SESSION, 5)["status"] == "compacted"
    for i in range(5, 11):
        env.write_prediction(f"p{i:03d}", jb="job_batch_001", n_exp=1)
    res = cmp_mod.maybe_compact(SESSION, 10)  # 6 on-disk + 5 registered = 11 >= 10
    assert res is not None and res["status"] == "compacted"
    assert res["papers"] == 6


def test_maybe_compact_noop_when_nothing_on_disk(tmp_path: Path, monkeypatch) -> None:
    env = _Env(monkeypatch, tmp_path)
    assert cmp_mod.maybe_compact(SESSION, 1, force=True) is None


# ---------------------------------------------------------------------------
# conservation gate / zero deletion
# ---------------------------------------------------------------------------

def test_verify_fail_keeps_all_originals(tmp_path: Path, monkeypatch) -> None:
    """守恒破坏注入 → 零删除 + status=error + 告警。"""
    env = _Env(monkeypatch, tmp_path)
    env.make_standard_run()

    def injected_verify(*a, **kw):
        raise cmp_mod.CompactionError("injected conservation break")

    monkeypatch.setattr(cmp_mod, "_verify_window", injected_verify)

    res = cmp_mod.maybe_compact(SESSION, 1, force=True)
    assert res["status"] == "error"
    assert len(env.on_disk_preds()) == 6                     # zero deletion
    assert not cmp_mod.stable_flat_path(SESSION).exists()
    assert cmp_mod.load_state(SESSION)["windows"] == []
    assert env.history_lines()  # history untouched
    wdirs = [d for d in cmp_mod.compaction_dir(SESSION).iterdir()
             if d.name.startswith("window_")]
    assert len(wdirs) == 1  # left for inspection, unregistered


def test_schema_violation_blocked_by_real_validator(tmp_path: Path, monkeypatch) -> None:
    """权威 schema 门（非 mock）：score 类型非法的实验 → CompactionError，
    原件保留。"""
    env = _Env(monkeypatch, tmp_path)
    p = env.write_prediction("p000", n_exp=1)
    pred = json.loads(p.read_text(encoding="utf-8"))
    pred["experiments"][0]["score"] = "0.9"  # must be number/null
    p.write_text(json.dumps(pred, indent=2), encoding="utf-8")

    res = cmp_mod.maybe_compact(SESSION, 1, force=True)
    assert res["status"] == "error"
    assert "score" in res["reason"]
    assert p.exists()


def test_corrupt_prediction_left_on_disk(tmp_path: Path, monkeypatch) -> None:
    env = _Env(monkeypatch, tmp_path)
    env.write_prediction("p000", n_exp=1)
    bad = env.runs / SESSION / "job_batch_000" / "predictions" / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    res = cmp_mod.maybe_compact(SESSION, 1, force=True)
    assert res["papers"] == 1
    assert bad.exists()  # corrupt file never enters a window


def test_tmp_files_not_selected(tmp_path: Path, monkeypatch) -> None:
    env = _Env(monkeypatch, tmp_path)
    p = env.write_prediction("p000", n_exp=1)
    leftover = p.with_name("p999.json.tmp")
    leftover.write_text("{}", encoding="utf-8")
    res = cmp_mod.maybe_compact(SESSION, 1, force=True)
    assert res["papers"] == 1
    assert leftover.exists()


# ---------------------------------------------------------------------------
# crash windows B–F
# ---------------------------------------------------------------------------

def _crash_after(name: str):
    """Wrap a compaction step to raise once it has been entered."""
    def wrapper(*a, **kw):
        raise RuntimeError(f"simulated crash inside {name}")
    return wrapper


class _patch_step:
    """Targeted step replacement with restore — unlike monkeypatch.undo()
    this never reverts the _Env directory redirections."""

    def __init__(self, step_name: str, fake) -> None:
        self.attr = step_name
        self.fake = fake

    def __enter__(self):
        self.real = getattr(cmp_mod, self.attr)
        setattr(cmp_mod, self.attr, self.fake)
        return self

    def __exit__(self, *exc):
        setattr(cmp_mod, self.attr, self.real)
        return False


def test_crash_B_mid_copy_stale_window_removed_and_redo(tmp_path: Path, monkeypatch) -> None:
    env = _Env(monkeypatch, tmp_path)
    env.make_standard_run()

    with _patch_step("_copy_partials", _crash_after("_copy_partials")):
        with pytest.raises(RuntimeError):
            cmp_mod.compact_session(SESSION)

    assert len(env.on_disk_preds()) == 6            # originals untouched
    assert cmp_mod.load_state(SESSION)["windows"] == []

    out = cmp_mod.finalize_compaction(SESSION)
    assert out["status"] == "finalized"
    wdirs = [d for d in cmp_mod.compaction_dir(SESSION).iterdir()
             if d.name.startswith("window_")]
    assert wdirs == []                               # stale selection deleted whole

    res = cmp_mod.compact_session(SESSION)          # redo succeeds
    assert res["status"] == "compacted" and res["papers"] == 6


def test_crash_C_after_copies_before_publish(tmp_path: Path, monkeypatch) -> None:
    env = _Env(monkeypatch, tmp_path)
    env.make_standard_run()
    with _patch_step("_publish_stable_flat", _crash_after("_publish_stable_flat")):
        with pytest.raises(RuntimeError):
            cmp_mod.compact_session(SESSION)

    assert len(env.on_disk_preds()) == 6
    assert not cmp_mod.stable_flat_path(SESSION).exists()
    cmp_mod.finalize_compaction(SESSION)
    res = cmp_mod.compact_session(SESSION)
    assert res["papers"] == 6


def test_crash_D_after_publish_before_register(tmp_path: Path, monkeypatch) -> None:
    env = _Env(monkeypatch, tmp_path)
    env.make_standard_run()
    with _patch_step("_register_window", _crash_after("_register_window")):
        with pytest.raises(RuntimeError):
            cmp_mod.compact_session(SESSION)

    # stable flat already holds window rows; originals intact; unregistered.
    assert len(json.loads(cmp_mod.stable_flat_path(SESSION).read_text(encoding="utf-8"))) == 7
    assert len(env.on_disk_preds()) == 6

    cmp_mod.finalize_compaction(SESSION)            # deletes stale window dir
    res = cmp_mod.compact_session(SESSION)          # republish converges
    assert res["papers"] == 6
    rows = json.loads(cmp_mod.stable_flat_path(SESSION).read_text(encoding="utf-8"))
    assert len(rows) == 7                           # no duplication
    keys = {(r["paper_id"], r["experiment_name"]) for r in rows}
    assert len(keys) == 7


def test_crash_E_registered_deletion_interrupted(tmp_path: Path, monkeypatch) -> None:
    env = _Env(monkeypatch, tmp_path)
    env.make_standard_run()

    real_delete = cmp_mod._delete_sources

    def half_delete(session_run_id, window_dir, manifest, log):
        freed = real_delete(session_run_id, window_dir, manifest[:2], log)
        raise RuntimeError("simulated crash mid-deletion")

    with _patch_step("_delete_sources", half_delete):
        with pytest.raises(RuntimeError):
            cmp_mod.compact_session(SESSION)

    # window IS registered; some originals still on disk
    state = cmp_mod.load_state(SESSION)
    assert state["windows"] and state["windows"][0]["status"] == "published"
    remaining = len(env.on_disk_preds())
    assert 0 < remaining < 6

    out = cmp_mod.finalize_compaction(SESSION)
    assert out["status"] == "finalized"
    assert env.on_disk_preds() == []                # deletion completed
    state = cmp_mod.load_state(SESSION)
    assert state["windows"][0]["status"] == "sources_deleted"
    # resume semantics already valid
    assert run_paths.prediction_ok(SESSION, "job_batch_000", "p000") is True
    assert run_paths.prediction_ok(SESSION, "job_batch_001", "p004") is False


def test_crash_F_history_rewrite_lost_converges(tmp_path: Path, monkeypatch) -> None:
    """真实 F 窗口：窗口 history.jsonl 已写、全局重写丢失（崩溃）——finalize
    重提取（窗口文件 write-once 不动）并只重写全局，收敛。"""
    env = _Env(monkeypatch, tmp_path)
    env.make_standard_run()

    real_awj = cmp_mod._atomic_write_jsonl

    def fail_global_rewrite(path, lines):
        if Path(path) == config_mod.RUN_HISTORY_PATH:
            raise RuntimeError("simulated crash: global history rewrite lost")
        return real_awj(path, lines)

    with _patch_step("_atomic_write_jsonl", fail_global_rewrite):
        with pytest.raises(RuntimeError):
            cmp_mod.compact_session(SESSION)

    # window registered (deletion ran up to the history rewrite), window
    # history.jsonl already written, global log still holds the 6 lines.
    state = cmp_mod.load_state(SESSION)
    assert state["windows"][0]["status"] == "published"
    wdir = cmp_mod.compaction_dir(SESSION) / state["windows"][0]["window_id"]
    assert len((wdir / "history.jsonl").read_text(encoding="utf-8").splitlines()) == 6
    assert len([h for h in env.history_lines() if h["paper_id"] != "zzz"]) == 6

    cmp_mod.finalize_compaction(SESSION)
    # converged: only the other-session line remains in the global log
    assert [h["paper_id"] for h in env.history_lines()] == ["zzz"]
    # window history.jsonl write-once: still the original 6 lines, no dup
    lines = (wdir / "history.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 6
    assert cmp_mod.load_state(SESSION)["windows"][0]["status"] == "sources_deleted"


def test_finalize_noop_without_dir(tmp_path: Path, monkeypatch) -> None:
    _Env(monkeypatch, tmp_path)
    assert cmp_mod.finalize_compaction(SESSION) == {"status": "noop",
                                                    "reason": "no compaction dir"}


# ---------------------------------------------------------------------------
# ledger backfill & misc
# ---------------------------------------------------------------------------

def test_ledger_backfill_for_legacy_runs(tmp_path: Path, monkeypatch) -> None:
    env = _Env(monkeypatch, tmp_path)
    env.make_standard_run()
    assert cl.read_rows(SESSION) == []  # legacy run, no ledger

    res = cmp_mod.compact_session(SESSION)
    assert res["status"] == "compacted"
    rows = cl.read_rows(SESSION)
    assert len(rows) == 6               # all backfilled at reconcile step
    by_pid = {r["paper_id"]: r for r in rows}
    assert by_pid["p000"]["status"] == "ok"
    assert by_pid["p004"]["status"] == "error"
    assert by_pid["p004"]["error_class"] == "llm_timeout"


def test_window_ids_monotonic_and_state_accumulates(tmp_path: Path, monkeypatch) -> None:
    env = _Env(monkeypatch, tmp_path)
    env.write_prediction("a", n_exp=1)
    r1 = cmp_mod.compact_session(SESSION)
    env.write_prediction("b", jb="job_batch_001", n_exp=2)
    r2 = cmp_mod.compact_session(SESSION)
    assert (r1["window_id"], r2["window_id"]) == ("window_0001", "window_0002")
    state = cmp_mod.load_state(SESSION)
    assert [w["papers_count"] for w in state["windows"]] == [1, 1]
    assert len(json.loads(cmp_mod.stable_flat_path(SESSION).read_text(encoding="utf-8"))) == 3


def test_monitors_all_missing_is_not_fatal(tmp_path: Path, monkeypatch) -> None:
    env = _Env(monkeypatch, tmp_path)
    env.write_prediction("p000", n_exp=1)  # no monitor anywhere
    res = cmp_mod.compact_session(SESSION)
    assert res["status"] == "compacted"
    wdir = cmp_mod.compaction_dir(SESSION) / res["window_id"]
    wjson = json.loads((wdir / "window.json").read_text(encoding="utf-8"))
    assert wjson["monitors_missing"] == 1 and wjson["monitors_copied"] == 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _run_cli(monkeypatch, argv: list[str]) -> int:
    monkeypatch.setattr(sys, "argv", ["compact_run.py", *argv])
    try:
        return int(compact_run_cli.main() or 0)
    except SystemExit as e:
        return int(e.code or 0)


def test_cli_dry_run_zero_writes(tmp_path: Path, monkeypatch, capsys) -> None:
    env = _Env(monkeypatch, tmp_path)
    env.write_prediction("p000", n_exp=1)
    rc = _run_cli(monkeypatch, ["--session-run-id", SESSION, "--dry-run"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "would compact 1 papers" in out
    assert not cmp_mod.compaction_dir(SESSION).exists()   # zero writes
    assert len(env.on_disk_preds()) == 1


def test_cli_force_compacts_and_exit_codes(tmp_path: Path, monkeypatch, capsys) -> None:
    env = _Env(monkeypatch, tmp_path)
    env.write_prediction("p000", n_exp=1)
    rc = _run_cli(monkeypatch, ["--session-run-id", SESSION])
    assert rc == 0
    assert env.on_disk_preds() == []
    assert "compacted" in capsys.readouterr().out

    # verify-failure path exits 2 with originals kept
    env.write_prediction("p001", n_exp=1)

    def injected_verify(*a, **kw):
        raise cmp_mod.CompactionError("injected verify failure")

    monkeypatch.setattr(cmp_mod, "_verify_window", injected_verify)
    rc = _run_cli(monkeypatch, ["--session-run-id", SESSION])
    assert rc == 2
    assert (env.runs / SESSION / "job_batch_000" / "predictions" / "p001.json").exists()


if __name__ == "__main__":
    raise SystemExit("run via pytest")
