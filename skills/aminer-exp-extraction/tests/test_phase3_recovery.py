"""v0.7 Phase 3 recovery tests (TODO-V07-04) — resume/skip/tmp/retry-chain.

Covers (see docs/V07_PHASE3_REPORT.md §recovery):
  1. prediction_ok boundaries beyond test_prediction_ok.py: a leftover
     ``.tmp`` is never a success; no ``.tmp`` residue after real commits.
  2. run_bulk-level resume skip with request counters: already-ok papers
     never reach the scheduler (=> zero BERT/LLM calls); error/missing
     papers are re-run — for BOTH the staged branch (function-level import:
     patch the source module) and the default branch (top-level import:
     patch the run_bulk attribute).
  3. duplicate start == full skip: with every prediction ok on disk the
     scheduler is never even constructed.
  4. error-retry chain across a simulated restart (new scheduler instance,
     same run_id): error prediction -> not skipped -> re-run succeeds ->
     disk keeps exactly one final success prediction.
  5. Three-mode non-regression is enforced by the full suite (staged /
     global_batch / chunked tests all run together).
"""

from __future__ import annotations

import importlib.util
import json
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

PROD_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROD_ROOT))

import pipeline.production.config as config_mod  # noqa: E402
import pipeline.production.monitor as monitor_mod  # noqa: E402
import pipeline.production.post_llm as post_llm  # noqa: E402
import pipeline.production.run_paths as run_paths  # noqa: E402
import pipeline.production.staged_pipeline_wf4 as staged_mod  # noqa: E402
from pipeline.production.batch_llm_common import PaperBatchState  # noqa: E402
from pipeline.production.post_llm import PaperFinalization  # noqa: E402
from pipeline.production.staged_pipeline_wf4 import StagedPipelineWf4  # noqa: E402
from pipeline.production.workflows.spec import get_workflow  # noqa: E402

WF = "prod-wf4-llm-datasets-experiment"
SESSION = "phase3rc"
RUN_ID = f"{SESSION}/job_batch_000"

_spec = importlib.util.spec_from_file_location("run_bulk_phase3rc", PROD_ROOT / "scripts" / "run_bulk.py")
run_bulk = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(run_bulk)


class _Env:
    def __init__(self, monkeypatch, tmp_path: Path) -> None:
        monkeypatch.setattr(post_llm, "RUNS_DIR", tmp_path)
        monkeypatch.setattr(config_mod, "RUNS_DIR", tmp_path)
        monkeypatch.setattr(run_paths, "RUNS_DIR", tmp_path)
        monkeypatch.setattr(config_mod, "PARTIALS_DIR", tmp_path / "partials")
        monkeypatch.setattr(monitor_mod, "RUN_HISTORY_PATH", tmp_path / "history.jsonl")
        monkeypatch.setenv("PROD_SKIP_PAPER_MONITOR", "1")
        # md cache root used by _run_window -> _window_prefetch
        monkeypatch.setattr(run_bulk, "EVAL_MD_CACHE_DIR", tmp_path / "md_cache")


def _fin(tmp_path: Path, pid: str, error: str | None = None) -> PaperFinalization:
    pred = {
        "paper_id": pid,
        "run_id": RUN_ID,
        "workflow_id": WF,
        "experiments": [] if error else [{"experiment_name": "E1"}],
    }
    if error:
        pred["error"] = error
    base = tmp_path / RUN_ID
    return PaperFinalization(
        paper_id=pid,
        run_id=RUN_ID,
        workflow_id=WF,
        dry_run=False,
        prediction=pred,
        monitor={"paper_id": pid},
        pred_path=base / "predictions" / f"{pid}.json",
        mon_path=base / "monitors" / f"{pid}_monitor.json",
        experiments=pred["experiments"],
        provenance=[],
        error=error,
        history_record={
            "run_id": RUN_ID, "paper_id": pid, "workflow_id": WF,
            "dry_run": False, "experiment_count": len(pred["experiments"]),
            "error": error,
        },
    )


def _make_pipe(tmp_path: Path, pids: list[str], **overrides) -> StagedPipelineWf4:
    spec = get_workflow(WF)
    params = dict(
        llm_concurrency=2,
        bert_pipeline_mode="global_batch",
        scheduler_mode="staged",
        prep_workers=2,
        post_workers=2,
        prep_queue_maxsize=16,
        llm_queue_maxsize=16,
        post_queue_maxsize=16,
        write_queue_maxsize=16,
        bert_batch_max_papers=16,
        bert_batch_max_wait_ms=200,
    )
    params.update(overrides)
    return StagedPipelineWf4(
        pids, {pid: Path("dummy.md") for pid in pids}, RUN_ID, spec, **params
    )


def _install(pipe: StagedPipelineWf4, tmp_path: Path, *, llm_raise_pid: str | None = None) -> None:
    def prep(pid: str) -> None:
        job = pipe.jobs[pid]
        job.paper_start_perf = time.perf_counter()
        job.ctx = SimpleNamespace(
            paper_id=pid, md_path=Path("dummy.md"), run_id=RUN_ID, workflow_id=WF,
            dry_run=False, raw_md="text", partials={}, set=lambda r: None,
        )
        job.prepared = SimpleNamespace(
            english_sentences=["sentence one two three"] * 3, clean_stats={}
        )

    def bert(prepared_map: dict) -> dict:
        return {
            pid: SimpleNamespace(timings={"bert_amortized_sec": 0.01})
            for pid in prepared_map
        }

    def llm(job, **kw):
        if llm_raise_pid is not None and job.paper_id == llm_raise_pid:
            raise TimeoutError(f"llm timed out for {job.paper_id}")
        return None

    def post(job, **kw):
        return _fin(tmp_path, job.paper_id)

    pipe._prep_paper = prep
    pipe._global_batch_fn = bert
    staged_mod.run_qwen_http_stage = llm
    staged_mod.run_post_stage = post


# ------------------------------------------------- 1. prediction_ok + .tmp semantics


def test_tmp_file_is_never_a_success_and_commits_leave_no_tmp(
    tmp_path: Path, monkeypatch
) -> None:
    _Env(monkeypatch, tmp_path)
    pred_dir = tmp_path / SESSION / "job_batch_000" / "predictions"
    pred_dir.mkdir(parents=True)
    # a leftover .tmp (kill between write and replace) must NOT count as done
    (pred_dir / "t1.json.tmp").write_text('{"paper_id": "t1"}', encoding="utf-8")
    assert run_paths.prediction_ok(SESSION, "job_batch_000", "t1") is False
    (pred_dir / "t1.json.tmp").unlink()  # restart would rewrite it via tmp+replace

    # a full staged run leaves no .tmp residue behind
    pids = ["a", "b", "c"]
    pipe = _make_pipe(tmp_path, pids)
    _install(pipe, tmp_path)
    pipe.run()
    assert all(pipe.jobs[p].state == PaperBatchState.COMMITTED_SUCCESS for p in pids)
    assert list(pred_dir.glob("*.tmp")) == []
    assert sorted(p.name for p in pred_dir.glob("*.json")) == ["a.json", "b.json", "c.json"]


# ------------------------------------ 2. run_bulk resume skip with request counters


class _FakeSched:
    """Records the papers that reached the scheduler (= would call BERT/LLM)."""

    constructed: list["_FakeSched"] = []

    def __init__(self, paper_ids, md_paths, run_id, spec, **kwargs) -> None:
        self.paper_ids = list(paper_ids)
        self.run_id = run_id
        self.batch_monitor = {"pipeline_mode": "fake"}
        _FakeSched.constructed.append(self)

    def run(self) -> list:
        return [
            SimpleNamespace(paper_id=pid, error=None, monitor={}, experiments=[{"experiment_name": "E1"}])
            for pid in self.paper_ids
        ]


def _seed_predictions(tmp_path: Path, ok: list[str], errored: list[str]) -> None:
    pred_dir = tmp_path / SESSION / "job_batch_000" / "predictions"
    pred_dir.mkdir(parents=True, exist_ok=True)
    for pid in ok:
        (pred_dir / f"{pid}.json").write_text(
            json.dumps({"paper_id": pid, "experiments": [{"experiment_name": "E"}]}),
            encoding="utf-8",
        )
    for pid in errored:
        (pred_dir / f"{pid}.json").write_text(
            json.dumps({"paper_id": pid, "experiments": [], "error": "llm/post: ReadTimeout: boom"}),
            encoding="utf-8",
        )


def _seed_md_cache(tmp_path: Path, pids: list[str]) -> None:
    cache = tmp_path / "md_cache"
    cache.mkdir(parents=True, exist_ok=True)
    for pid in pids:
        (cache / f"{pid}.md").write_text("cached md body", encoding="utf-8")


def _paper_items(pids: list[str]) -> list[dict]:
    return [{"paper_id": pid, "md_url": f"http://local/{pid}.md"} for pid in pids]


def _run_window(monkeypatch, tmp_path: Path, *, scheduler_mode: str) -> dict:
    pids = ["done1", "done2", "failed1", "missing1"]
    _seed_predictions(tmp_path, ok=["done1", "done2"], errored=["failed1"])
    _seed_md_cache(tmp_path, ["failed1", "missing1"])
    _FakeSched.constructed = []
    if scheduler_mode == "staged":
        # staged branch imports StagedPipelineWf4 INSIDE _run_window ->
        # patch the source module attribute.
        monkeypatch.setattr(staged_mod, "StagedPipelineWf4", _FakeSched)
    else:
        # default branch uses the top-level import -> patch run_bulk's binding.
        monkeypatch.setattr(run_bulk, "BatchBertPipelineSchedulerWf4", _FakeSched)
    cfg = {
        "md_fetch_concurrency": 2,
        "md_fetch_retries": 1,
        "workflow": WF,
        "scheduler_mode": scheduler_mode,
        "bert_pipeline_mode": "global_batch" if scheduler_mode == "staged" else "chunked_overlap",
    }
    return run_bulk._run_window(
        paper_items=_paper_items(pids),
        session_run_id=SESSION,
        job_batch_id="job_batch_000",
        cfg=cfg,
        force=False,
    )


def test_resume_skip_staged_branch_zero_calls_for_ok_papers(tmp_path: Path, monkeypatch) -> None:
    _Env(monkeypatch, tmp_path)
    st = _run_window(monkeypatch, tmp_path, scheduler_mode="staged")

    assert st["skipped"] == 2          # done1/done2 skipped before the scheduler
    assert st["attempted"] == 2        # failed1 (error prediction) + missing1
    assert st["ok"] == 2 and st["error"] == 0
    # the scheduler (= the only path to BERT/LLM) saw exactly the retry pids
    assert len(_FakeSched.constructed) == 1
    assert sorted(_FakeSched.constructed[0].paper_ids) == ["failed1", "missing1"]
    # progress.jsonl only records attempted papers; skips are silent
    rows = [
        json.loads(line)
        for line in (tmp_path / SESSION / "job_batch_000" / "progress.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    assert sorted(r["paper_id"] for r in rows) == ["failed1", "missing1"]


def test_resume_skip_default_branch_patched_at_run_bulk(tmp_path: Path, monkeypatch) -> None:
    _Env(monkeypatch, tmp_path)
    st = _run_window(monkeypatch, tmp_path, scheduler_mode="default")

    assert st["skipped"] == 2 and st["attempted"] == 2
    assert sorted(_FakeSched.constructed[0].paper_ids) == ["failed1", "missing1"]


def test_duplicate_start_all_ok_scheduler_never_constructed(tmp_path: Path, monkeypatch) -> None:
    _Env(monkeypatch, tmp_path)
    _seed_predictions(tmp_path, ok=["done1", "done2", "failed1", "missing1"], errored=[])
    _FakeSched.constructed = []
    monkeypatch.setattr(staged_mod, "StagedPipelineWf4", _FakeSched)
    st = run_bulk._run_window(
        paper_items=_paper_items(["done1", "done2", "failed1", "missing1"]),
        session_run_id=SESSION,
        job_batch_id="job_batch_000",
        cfg={"md_fetch_concurrency": 2, "md_fetch_retries": 1, "workflow": WF,
             "scheduler_mode": "staged", "bert_pipeline_mode": "global_batch"},
        force=False,
    )
    assert st["skipped"] == 4 and st["attempted"] == 0
    assert _FakeSched.constructed == []  # zero BERT/LLM work on duplicate start


# -------------------------------------------- 4. error-retry chain across restart


def test_barrier_hook_noop_without_env_and_blocks_with_env(
    tmp_path: Path, monkeypatch
) -> None:
    """The Phase 3 deterministic kill-point hook: zero effect unless armed."""
    import pipeline.production.test_hooks as hooks

    # no env -> immediate return (production path)
    monkeypatch.delenv("WF4_BARRIER_STAGE", raising=False)
    hooks.reset_counts()
    t0 = time.perf_counter()
    hooks.barrier("prep")
    assert time.perf_counter() - t0 < 0.1

    # armed on a different stage -> still immediate
    monkeypatch.setenv("WF4_BARRIER_STAGE", "llm")
    hooks.reset_counts()
    t0 = time.perf_counter()
    hooks.barrier("prep")
    assert time.perf_counter() - t0 < 0.1

    # armed on THIS stage, item < N -> passes through and counts
    monkeypatch.setenv("WF4_BARRIER_STAGE", "prep")
    monkeypatch.setenv("WF4_BARRIER_N", "3")
    monkeypatch.setenv("WF4_BARRIER_TIMEOUT", "2")
    hooks.reset_counts()
    t0 = time.perf_counter()
    hooks.barrier("prep")  # item 1 < 3
    hooks.barrier("prep")  # item 2 < 3
    assert time.perf_counter() - t0 < 0.1
    # item 3 == N: signal file touched, blocks until release appears
    release = tmp_path / "rel"
    monkeypatch.setenv("WF4_BARRIER_RELEASE", str(release))
    signal_p = tmp_path / "sig"
    monkeypatch.setenv("WF4_BARRIER_SIGNAL", str(signal_p))
    threading.Timer(0.3, lambda: release.write_text("go", encoding="utf-8")).start()
    t0 = time.perf_counter()
    hooks.barrier("prep")  # item 3 -> trips
    blocked = time.perf_counter() - t0
    assert blocked >= 0.25  # it really parked until the release file appeared
    assert signal_p.exists() and signal_p.read_text(encoding="utf-8").startswith("prep:3")


def test_error_prediction_retried_after_simulated_restart(tmp_path: Path, monkeypatch) -> None:
    _Env(monkeypatch, tmp_path)
    pids = ["r1", "r2"]

    # --- first "process": r1 fails with a llm timeout -> error prediction
    pipe1 = _make_pipe(tmp_path, pids)
    _install(pipe1, tmp_path, llm_raise_pid="r1")
    pipe1.run()
    pred = json.loads(
        (tmp_path / RUN_ID / "predictions" / "r1.json").read_text(encoding="utf-8")
    )
    assert pred["error"].startswith("llm/post: TimeoutError:")
    assert run_paths.prediction_ok(SESSION, "job_batch_000", "r1") is False
    assert run_paths.prediction_ok(SESSION, "job_batch_000", "r2") is True

    # --- restart: skip decision keeps r2 out, r1 goes through a NEW instance
    retry = [p for p in pids if not run_paths.prediction_ok(SESSION, "job_batch_000", p)]
    assert retry == ["r1"]
    pipe2 = _make_pipe(tmp_path, retry)  # fresh instance, same run_id
    _install(pipe2, tmp_path)            # this time llm succeeds
    pipe2.run()

    # disk keeps exactly ONE final artifact for r1 — now a success
    pred = json.loads(
        (tmp_path / RUN_ID / "predictions" / "r1.json").read_text(encoding="utf-8")
    )
    assert "error" not in pred
    assert pred["experiments"] == [{"experiment_name": "E1"}]
    assert run_paths.prediction_ok(SESSION, "job_batch_000", "r1") is True
    assert pipe2.jobs["r1"].state == PaperBatchState.COMMITTED_SUCCESS
    # r2's prediction was never touched by the second run
    assert run_paths.prediction_ok(SESSION, "job_batch_000", "r2") is True
    # history records both attempts; the LAST terminal for r1 is the success
    hist = [
        json.loads(line)
        for line in (tmp_path / "history.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    r1_rows = [h for h in hist if h["paper_id"] == "r1"]
    assert len(r1_rows) == 2
    assert r1_rows[-1]["error"] is None
    # a THIRD start now skips everything
    assert not [p for p in pids if not run_paths.prediction_ok(SESSION, "job_batch_000", p)]


if __name__ == "__main__":
    raise SystemExit("run via pytest")
