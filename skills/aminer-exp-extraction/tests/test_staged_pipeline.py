"""Staged pipeline (v0.7 Phase 2) tests — fake-injected, no HTTP.

The staged scheduler is exercised end-to-end with fakes at the four stage
seams (``_prep_paper``, ``_global_batch_fn``, ``run_qwen_http_stage``,
``run_post_stage``) plus, where needed, ``commit_paper_finalization`` —
the same injection precedent as tests/test_bert_global_batch.py.

Coverage groups (see docs/V07_PHASE2 plan §6):
  B. backpressure      — bounded queues never exceed maxsize; producers block
                         and resume; everything completes
  C. llm slot release — event timeline: llm_end(A) < llm_start(B) <
                         post_end(A) with llm_concurrency=1 AND post_workers=1
  D. stage parallelism — concurrent PREP; cross-paper BERT batching; per-pid
                         result association
  E. lifecycle/drain   — sentinel cascade, queue.join() drain, empty window,
                         all threads exit, no unfinished tasks
  F. error isolation   — prep / bert batch / missing pid / llm http /
                         parse / post / writer failures; the rest continue;
                         error predictions are resume-retryable
  G. terminal conservation — exactly one commit per paper; commit_once
                         duplicates are counted, never written
"""

from __future__ import annotations

import json
import queue
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
RUN_ID = "stagedtest/job_batch_000"


def _make_pipe(tmp_path: Path, pids: list[str], **overrides) -> StagedPipelineWf4:
    spec = get_workflow(WF)
    params = dict(
        llm_concurrency=2,
        bert_pipeline_mode="global_batch",
        scheduler_mode="staged",
        prep_workers=2,
        post_workers=2,
        prep_queue_maxsize=8,
        llm_queue_maxsize=8,
        post_queue_maxsize=8,
        write_queue_maxsize=8,
        bert_batch_max_papers=16,
        bert_batch_max_wait_ms=200,  # let groups accumulate across papers
    )
    params.update(overrides)
    pipe = StagedPipelineWf4(
        pids,
        {pid: Path("dummy.md") for pid in pids},
        RUN_ID,
        spec,
        **params,
    )
    return pipe


def _install_fakes(
    pipe: StagedPipelineWf4,
    tmp_path: Path,
    *,
    llm_fn=None,
    post_fn=None,
    prep_fn=None,
    bert_fn=None,
    events: list | None = None,
) -> None:
    """Install default happy-path fakes; individual tests wrap/replace."""

    def default_prep(pid: str) -> None:
        job = pipe.jobs[pid]
        job.paper_start_perf = time.perf_counter()
        if prep_fn is not None:
            prep_fn(pid)
        job.ctx = SimpleNamespace(
            paper_id=pid,
            md_path=Path("dummy.md"),
            run_id=RUN_ID,
            workflow_id=WF,
            dry_run=False,
            raw_md="text",
            partials={},
            set=lambda r: None,
        )
        job.prepared = SimpleNamespace(english_sentences=["sentence one two three"] * 3, clean_stats={})

    def default_bert(prepared_map: dict) -> dict:
        if bert_fn is not None:
            return bert_fn(prepared_map)
        return {
            pid: SimpleNamespace(timings={"bert_amortized_sec": 0.01, "bert_batch_chunk": 0})
            for pid in prepared_map
        }

    def default_qwen(job, **kwargs):
        t0 = time.perf_counter()
        if events is not None:
            events.append(("llm_start", job.paper_id, t0))
        if llm_fn is not None:
            ret = llm_fn(job, **kwargs)
        else:
            ret = None
        job.timings["llm_wait_sec"] = 0.0
        job.timings["llm_elapsed_sec"] = round(time.perf_counter() - t0, 4)
        if events is not None:
            events.append(("llm_end", job.paper_id, time.perf_counter()))
        return ret

    def default_post(job, **kwargs):
        t0 = time.perf_counter()
        if post_fn is not None:
            ret = post_fn(job, **kwargs)
        else:
            ret = _fin(pipe, tmp_path, job.paper_id)
        job.timings["post_llm_elapsed_sec"] = round(time.perf_counter() - t0, 4)
        job.timings["paper_wall_sec"] = round(time.perf_counter() - job.paper_start_perf, 4)
        if events is not None:
            events.append(("post_end", job.paper_id, time.perf_counter()))
        return ret

    pipe._prep_paper = default_prep
    pipe._global_batch_fn = default_bert
    staged_mod.run_qwen_http_stage = default_qwen
    staged_mod.run_post_stage = default_post


def _fin(pipe: StagedPipelineWf4, tmp_path: Path, pid: str, error: str | None = None) -> PaperFinalization:
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
    )


class _Env:
    """Patch all output roots into tmp_path for one test."""

    def __init__(self, monkeypatch, tmp_path: Path) -> None:
        monkeypatch.setattr(post_llm, "RUNS_DIR", tmp_path)
        monkeypatch.setattr(config_mod, "RUNS_DIR", tmp_path)
        monkeypatch.setattr(run_paths, "RUNS_DIR", tmp_path)
        monkeypatch.setattr(config_mod, "PARTIALS_DIR", tmp_path / "partials")
        monkeypatch.setattr(monitor_mod, "RUN_HISTORY_PATH", tmp_path / "history.jsonl")
        monkeypatch.setenv("PROD_SKIP_PAPER_MONITOR", "1")


# ----------------------------------------------------------------- B. backpressure


def test_backpressure_bounded_queues_and_completion(tmp_path: Path, monkeypatch) -> None:
    _Env(monkeypatch, tmp_path)
    pids = [f"p{i:02d}" for i in range(12)]
    pipe = _make_pipe(
        tmp_path,
        pids,
        prep_queue_maxsize=2,
        llm_queue_maxsize=1,
        post_queue_maxsize=1,
        write_queue_maxsize=1,
        prep_workers=1,
        llm_concurrency=1,
        post_workers=1,
    )

    def slow_qwen(job, **kw):
        time.sleep(0.02)

    _install_fakes(pipe, tmp_path, llm_fn=slow_qwen)
    results = pipe.run()

    assert len(results) == 12
    assert all(r is not None and r.error is None for r in results)
    # bounded: observed depths never exceed maxsize (incl. sentinel puts)
    assert pipe.queue_depth_max["prep"] <= 2
    assert pipe.queue_depth_max["llm"] <= 1
    assert pipe.queue_depth_max["post"] <= 1
    assert pipe.queue_depth_max["write"] <= 1
    # after run: every queue fully drained
    for q in (pipe.prep_q, pipe.sq_qwen, pipe.sq_post, pipe.sq_write):
        assert q.qsize() == 0
        q.join()  # must not block


# ------------------------------------------------------- C. llm slot release timeline


def test_qwen_slot_released_before_post_completes(tmp_path: Path, monkeypatch) -> None:
    """llm_end(A) < llm_start(B) < post_end(A) with ONE dispatcher and ONE
    post worker: paper B's inference starts while A's POST is still running —
    proof that the inference slot does not cover POST."""
    _Env(monkeypatch, tmp_path)
    events: list[tuple[str, str, float]] = []
    pids = ["A", "B"]
    pipe = _make_pipe(
        tmp_path, pids, llm_concurrency=1, post_workers=1, prep_workers=1,
        bert_batch_max_wait_ms=500,  # both papers in ONE batch -> deterministic order
    )

    def slow_post_for_A(job, **kw):
        if job.paper_id == "A":
            time.sleep(0.6)
        return _fin(pipe, tmp_path, job.paper_id)

    _install_fakes(pipe, tmp_path, post_fn=slow_post_for_A, events=events)
    results = pipe.run()
    assert all(r is not None and r.error is None for r in results)

    def ev(name, pid):
        return [t for n, p, t in events if n == name and p == pid][0]

    assert ev("llm_end", "A") < ev("llm_start", "B") < ev("post_end", "A")
    # timings recorded per stage, POST time not inside llm HTTP time
    assert "llm_http_elapsed" in pipe.jobs["A"].timings
    assert "post_elapsed" in pipe.jobs["A"].timings
    assert "llm_queue_wait" in pipe.jobs["A"].timings
    assert "post_queue_wait" in pipe.jobs["A"].timings
    assert "write_queue_wait" in pipe.jobs["A"].timings


# ------------------------------------------------------------ D. stage parallelism


def test_prep_workers_run_concurrently(tmp_path: Path, monkeypatch) -> None:
    _Env(monkeypatch, tmp_path)
    pids = [f"c{i}" for i in range(2)]
    pipe = _make_pipe(tmp_path, pids, prep_workers=2, llm_concurrency=1, post_workers=1)
    barrier = threading.Barrier(2, timeout=5)

    def barrier_prep(pid: str) -> None:
        barrier.wait()  # only passes if BOTH prep workers run simultaneously

    _install_fakes(pipe, tmp_path, prep_fn=barrier_prep)
    results = pipe.run()
    assert all(r is not None and r.error is None for r in results)


def test_bert_batches_cross_paper_and_results_map_by_pid(tmp_path: Path, monkeypatch) -> None:
    _Env(monkeypatch, tmp_path)
    pids = [f"m{i}" for i in range(4)]
    pipe = _make_pipe(
        tmp_path, pids, bert_batch_max_papers=8, bert_batch_max_wait_ms=400,
        prep_workers=4, llm_concurrency=2, post_workers=2,
    )
    seen_batches: list[list[str]] = []

    def recording_bert(prepared_map: dict) -> dict:
        seen_batches.append(list(prepared_map.keys()))
        # deliberately return results keyed by pid in REVERSE order: mapping
        # must not depend on response order
        return {
            pid: SimpleNamespace(
                timings={"bert_amortized_sec": 0.02, "bert_batch_chunk": 0},
                marker=f"bert-for-{pid}",
            )
            for pid in reversed(list(prepared_map))
        }

    _install_fakes(pipe, tmp_path, bert_fn=recording_bert)
    results = pipe.run()

    assert all(r is not None and r.error is None for r in results)
    assert seen_batches and max(len(b) for b in seen_batches) >= 2  # cross-paper batch
    for pid in pids:
        assert pipe.jobs[pid].bert_result.marker == f"bert-for-{pid}"
    assert pipe.batch_monitor["scheduler_mode"] == "staged"


# --------------------------------------------------------------- E. lifecycle/drain


def test_lifecycle_drain_and_thread_exit(tmp_path: Path, monkeypatch) -> None:
    _Env(monkeypatch, tmp_path)
    pids = [f"d{i}" for i in range(5)]
    done_fired: list[str] = []
    lock = threading.Lock()

    def on_done(job) -> None:
        with lock:
            done_fired.append(job.paper_id)

    spec = get_workflow(WF)
    pipe = StagedPipelineWf4(
        pids,
        {pid: Path("dummy.md") for pid in pids},
        RUN_ID,
        spec,
        llm_concurrency=2,
        bert_pipeline_mode="global_batch",
        scheduler_mode="staged",
        prep_workers=2,
        post_workers=2,
        on_paper_done=on_done,
    )
    _install_fakes(pipe, tmp_path)
    results = pipe.run()

    assert len(results) == 5
    assert sorted(done_fired) == sorted(pids)  # each paper fired exactly once
    for q in (pipe.prep_q, pipe.sq_qwen, pipe.sq_post, pipe.sq_write):
        q.join()  # drain evidence: joins return immediately post-run


def test_empty_window_completes(tmp_path: Path, monkeypatch) -> None:
    _Env(monkeypatch, tmp_path)
    pipe = _make_pipe(tmp_path, [])
    _install_fakes(pipe, tmp_path)
    assert pipe.run() == []


# ---------------------------------------------------------------- F. error isolation


def _run_with_failures(
    tmp_path: Path,
    monkeypatch,
    pids: list[str],
    *,
    fail_prep: str | None = None,
    fail_bert_batches: bool = False,
    bert_missing: str | None = None,
    llm_raise: str | None = None,
    llm_parse_err: str | None = None,
    post_raise: str | None = None,
) -> StagedPipelineWf4:
    _Env(monkeypatch, tmp_path)
    pipe = _make_pipe(tmp_path, pids)

    class _PrepAbort(Exception):
        pass

    def prep(pid: str) -> None:
        if pid == fail_prep:
            job = pipe.jobs[pid]
            job.paper_start_perf = time.perf_counter()
            job.error = f"prep: FileNotFoundError: boom {pid}"
            pipe._fail_paper(job, source="prep")
            raise _PrepAbort

    def bert(prepared_map: dict) -> dict:
        if fail_bert_batches:
            raise ConnectionError("bert endpoint down")
        return {
            pid: SimpleNamespace(timings={"bert_amortized_sec": 0.01})
            for pid in prepared_map
            if pid != bert_missing  # HTTP 200 but this pid absent from response
        }

    def llm(job, **kw):
        if llm_raise is not None and job.paper_id == llm_raise:
            raise TimeoutError("llm timed out")
        if llm_parse_err is not None and job.paper_id == llm_parse_err:
            return "llm_parse_or_empty: ValueError: Expecting value"
        time.sleep(0.001)

    def post(job, **kw):
        if post_raise is not None and job.paper_id == post_raise:
            raise RuntimeError("post exploded")
        return _fin(pipe, tmp_path, job.paper_id)

    # prep failure: mimic base _prep_paper semantics (error + _fail_paper)
    def prep_wrapper(pid: str) -> None:
        try:
            prep(pid)
        except _PrepAbort:
            return
        job = pipe.jobs[pid]
        job.paper_start_perf = time.perf_counter()
        job.ctx = SimpleNamespace(paper_id=pid, partials={}, set=lambda r: None,
                                  md_path=Path("d.md"), run_id=RUN_ID,
                                  workflow_id=WF, dry_run=False, raw_md="t")
        job.prepared = SimpleNamespace(english_sentences=["s1 s2 s3"], clean_stats={})

    pipe._prep_paper = prep_wrapper
    pipe._global_batch_fn = bert
    staged_mod.run_qwen_http_stage = llm
    staged_mod.run_post_stage = post
    pipe.run()
    return pipe


def test_error_isolation_each_failure_class(tmp_path: Path, monkeypatch) -> None:
    cases = [
        ("prep", dict(fail_prep="e-prep", expect_error="prep: FileNotFoundError")),
        ("bert_batch", dict(fail_bert_batches=True, expect_error="bert_batch_failed")),
        ("bert_missing", dict(bert_missing="e-missing", expect_error="no result for paper")),
        ("llm_http", dict(llm_raise="e-llm", expect_error="llm/post: TimeoutError")),
        ("llm_parse", dict(llm_parse_err="e-parse", expect_error="llm_parse_or_empty")),
        ("post", dict(post_raise="e-post", expect_error="llm/post: RuntimeError")),
    ]
    for name, cfg in cases:
        expect_error = cfg.pop("expect_error")
        pids = ["ok1", "e-prep", "e-llm", "e-parse", "e-post", "e-missing", "ok2"]
        pipe = _run_with_failures(tmp_path, monkeypatch, pids, **cfg)
        failed = [p for p in pids if pipe.jobs[p].result is not None and pipe.jobs[p].result.error]
        # exactly the target class of paper failed (batch failure may hit more,
        # but never the papers of other classes and never silently)
        assert all(expect_error in pipe.jobs[p].result.error for p in failed), name
        if name != "bert_batch":
            target = {
                "prep": "e-prep", "llm_http": "e-llm", "llm_parse": "e-parse",
                "post": "e-post", "bert_missing": "e-missing",
            }[name]
            assert failed == [target], (name, failed)
        # every other paper succeeded and committed
        for p in pids:
            if p not in failed:
                assert pipe.jobs[p].result is not None and pipe.jobs[p].result.error is None
                assert run_paths.prediction_ok("stagedtest", "job_batch_000", p) is True
        # failed papers are retryable on resume
        for p in failed:
            assert run_paths.prediction_ok("stagedtest", "job_batch_000", p) is False


def test_writer_error_isolated_and_defensive_recovers(tmp_path: Path, monkeypatch) -> None:
    _Env(monkeypatch, tmp_path)
    pids = ["w1", "w2", "w3"]
    pipe = _make_pipe(tmp_path, pids)

    real_commit = staged_mod.commit_paper_finalization

    def flaky_commit(fin: PaperFinalization) -> None:
        if fin.paper_id == "w2":
            raise OSError("disk full")
        return real_commit(fin)

    _install_fakes(pipe, tmp_path)
    staged_mod.commit_paper_finalization = flaky_commit
    try:
        results = pipe.run()
    finally:
        staged_mod.commit_paper_finalization = real_commit

    # run survived; w1/w3 committed fine
    assert pipe.jobs["w1"].result is not None and pipe.jobs["w1"].result.error is None
    assert pipe.jobs["w3"].result is not None and pipe.jobs["w3"].result.error is None
    # writer error recorded
    assert [e["paper_id"] for e in pipe.writer_errors] == ["w2"]
    # defensive pass re-finalized the never-committed paper (sequentially)
    assert results[1] is not None
    assert pipe.commit_counts["writer_error"] == 1
    assert pipe.commit_counts["defensive"] == 1
    # w2 lands a retryable error prediction
    assert run_paths.prediction_ok("stagedtest", "job_batch_000", "w2") is False


# ------------------------------------------------------------ G. terminal conservation


def test_terminal_conservation_exactly_one_commit_per_paper(tmp_path: Path, monkeypatch) -> None:
    _Env(monkeypatch, tmp_path)
    pids = [f"g{i}" for i in range(6)]
    pipe = _make_pipe(tmp_path, pids, llm_concurrency=2)
    _install_fakes(pipe, tmp_path)
    results = pipe.run()

    assert len(results) == len(pids)
    assert pipe.commit_counts["success"] == len(pids)
    assert pipe.commit_counts["error"] == 0
    assert pipe.commit_counts["defensive"] == 0
    assert pipe.duplicate_commit_attempts == []
    # every paper reached its terminal state exactly once
    for pid in pids:
        assert pipe.jobs[pid].state == PaperBatchState.COMMITTED_SUCCESS
        pred = json.loads(pipe.jobs[pid].result.prediction_path.read_text(encoding="utf-8"))
        assert pred["paper_id"] == pid and "error" not in pred
    # staged monitor written with the conservation stats
    mon = json.loads((tmp_path / RUN_ID / "staged_pipeline_monitor.json").read_text(encoding="utf-8"))
    w = mon["windows"][-1]
    assert w["terminal_states"]["success"] == len(pids)
    assert w["duplicate_commit_attempts"] == []


def test_commit_once_duplicate_never_writes_or_overwrites(tmp_path: Path, monkeypatch) -> None:
    _Env(monkeypatch, tmp_path)
    pids = ["z1"]
    pipe = _make_pipe(tmp_path, pids)
    _install_fakes(pipe, tmp_path)
    pipe.run()

    # success already committed for z1
    assert pipe.commit_counts["success"] == 1
    fin_err = _fin(pipe, tmp_path, "z1", error="late_error: should never land")
    assert pipe._enqueue_commit("z1", fin_err, source="late_error") is False
    assert pipe._enqueue_commit("z1", fin_err, source="late_error_2") is False
    assert len(pipe.duplicate_commit_attempts) == 2
    # committed success prediction untouched by the duplicate attempts
    pred = json.loads(pipe.jobs["z1"].result.prediction_path.read_text(encoding="utf-8"))
    assert "error" not in pred
    assert pipe.jobs["z1"].result.error is None
    # error cannot overwrite success even via _fail_paper (routes the same gate)
    job = pipe.jobs["z1"]
    job.error = "late failure"
    pipe._fail_paper(job, source="late")
    assert len(pipe.duplicate_commit_attempts) == 3
    pred = json.loads(pipe.jobs["z1"].result.prediction_path.read_text(encoding="utf-8"))
    assert "error" not in pred


def test_queue_wait_timings_recorded(tmp_path: Path, monkeypatch) -> None:
    _Env(monkeypatch, tmp_path)
    pids = [f"t{i}" for i in range(3)]
    pipe = _make_pipe(tmp_path, pids)
    _install_fakes(pipe, tmp_path)
    pipe.run()
    for pid in pids:
        t = pipe.jobs[pid].timings
        for key in ("prep_queue_wait", "llm_queue_wait", "post_queue_wait", "write_queue_wait"):
            assert key in t and t[key] >= 0.0, key
        assert t["llm_http_elapsed"] >= 0.0
        assert t["post_elapsed"] >= 0.0


def test_bert_queue_wait_recorded_staged(tmp_path: Path, monkeypatch) -> None:
    """PREP submit -> batch HTTP start is stamped per paper by the batcher
    (it lands in job.timings -> pipeline_stages)."""
    _Env(monkeypatch, tmp_path)
    pids = [f"bq{i}" for i in range(3)]
    pipe = _make_pipe(tmp_path, pids)
    _install_fakes(pipe, tmp_path)
    pipe.run()
    for pid in pids:
        assert pipe.jobs[pid].timings.get("bert_queue_wait", -1.0) >= 0.0, pid


def test_write_queue_wait_excludes_commit_time(tmp_path: Path, monkeypatch) -> None:
    """write_queue_wait must be recorded at dequeue (pure queue time), and the
    commit's disk IO measured separately as write_elapsed_sec."""
    _Env(monkeypatch, tmp_path)
    pids = ["wq0"]
    pipe = _make_pipe(tmp_path, pids)
    seen: dict = {}

    def slow_commit(fin):
        seen["wqw_at_commit_entry"] = pipe.jobs["wq0"].timings.get("write_queue_wait")
        time.sleep(0.2)
        return SimpleNamespace(prediction={}, error=fin.error)

    monkeypatch.setattr(staged_mod, "commit_paper_finalization", slow_commit)
    _install_fakes(pipe, tmp_path)
    pipe.run()

    t = pipe.jobs["wq0"].timings
    # already present when commit started (old code computed it AFTER commit)
    assert seen["wqw_at_commit_entry"] is not None
    # the 0.2s commit did not inflate the wait
    assert t["write_queue_wait"] == seen["wqw_at_commit_entry"]
    assert t["write_queue_wait"] < 0.15  # single paper: dequeued right away
    assert t["write_elapsed_sec"] >= 0.2  # commit duration measured separately


def test_write_queue_wait_lands_in_paper_monitor(tmp_path: Path, monkeypatch) -> None:
    """The writer backfills write_queue_wait into the to-be-persisted monitor
    (the pipeline_stages snapshot predates enqueue), so the per-paper monitor
    carries it — collect_phase_metrics lists this key."""
    _Env(monkeypatch, tmp_path)
    monkeypatch.setenv("PROD_SKIP_PAPER_MONITOR", "0")  # _Env disables it; we want the file
    pids = ["wm0"]
    pipe = _make_pipe(tmp_path, pids)

    def post_with_stages(job, **kwargs):
        fin = _fin(pipe, tmp_path, job.paper_id)
        fin.monitor["pipeline_stages"] = {"paper_wall_sec": 0.0}
        return fin

    _install_fakes(pipe, tmp_path, post_fn=post_with_stages)
    pipe.run()

    mon = json.loads(
        (tmp_path / RUN_ID / "monitors" / "wm0_monitor.json").read_text(encoding="utf-8")
    )
    assert "write_queue_wait" in mon["pipeline_stages"]
    assert (
        mon["pipeline_stages"]["write_queue_wait"]
        == pipe.jobs["wm0"].timings["write_queue_wait"]
    )


if __name__ == "__main__":
    raise SystemExit("run via pytest")
