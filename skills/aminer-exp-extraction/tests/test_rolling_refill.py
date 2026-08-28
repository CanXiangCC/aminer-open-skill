"""TODO-V07-10 rolling refill invariants — fake-injected, no HTTP.

Three layers, mirroring the production wiring:
  1. scheduler rolling API (StagedPipelineWf4 rolling=True): incremental
     admit_paper, credit release at EVERY durable terminal class (writer
     commit / writer_error->defensive / no_result_set->defensive), heavy-field
     stripping, flat rolling monitor, batch_index monotonicity;
  2. run_bulk._RollingBatchController: single-source stats, progress-once,
     md-failure credit return, credit gating;
  3. _run_window_rolling end-to-end: skips / md errors / llm errors /
     conservation, with the SAME fakes as tests/test_staged_pipeline.py.
"""

from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

PROD_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROD_ROOT))
sys.path.insert(0, str(PROD_ROOT / "scripts"))

import pipeline.production.config as config_mod  # noqa: E402
import pipeline.production.monitor as monitor_mod  # noqa: E402
import pipeline.production.post_llm as post_llm  # noqa: E402
import pipeline.production.run_paths as run_paths  # noqa: E402
import pipeline.production.staged_pipeline_wf4 as staged_mod  # noqa: E402
import run_bulk  # noqa: E402
from pipeline.production.batch_llm_common import PaperBatchState  # noqa: E402
from pipeline.production.post_llm import PaperFinalization  # noqa: E402
from pipeline.production.staged_pipeline_wf4 import StagedPipelineWf4  # noqa: E402
from pipeline.production.workflows.spec import get_workflow  # noqa: E402

WF = "prod-wf4-llm-datasets-experiment"
RUN_ID = "rolltest/job_batch_000"


def _make_rolling_pipe(
    tmp_path: Path,
    *,
    target: int,
    on_terminal=None,
    heartbeat_cb=None,
    **overrides,
) -> StagedPipelineWf4:
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
        bert_batch_max_wait_ms=200,
        rolling=True,
        rolling_target=target,
    )
    if on_terminal is not None:
        params["on_paper_terminal"] = on_terminal
    if heartbeat_cb is not None:
        params["rolling_heartbeat_cb"] = heartbeat_cb
    params.update(overrides)
    return StagedPipelineWf4([], {}, RUN_ID, spec, **params)


def _install_fakes(pipe: StagedPipelineWf4, tmp_path: Path, *, llm_fn=None, post_fn=None) -> None:
    def default_prep(pid: str) -> None:
        job = pipe.jobs[pid]
        job.paper_start_perf = time.perf_counter()
        job.ctx = SimpleNamespace(
            paper_id=pid,
            md_path=Path("dummy.md"),
            run_id=RUN_ID,
            workflow_id=WF,
            dry_run=False,
            raw_md="heavy markdown payload " * 100,
            partials={},
            set=lambda r: None,
        )
        job.prepared = SimpleNamespace(
            english_sentences=["sentence one two three"] * 3,
            clean_stats={},
            heavy=["x" * 1000],
        )

    def default_bert(prepared_map: dict) -> dict:
        return {
            pid: SimpleNamespace(
                timings={"bert_amortized_sec": 0.01, "bert_batch_chunk": 0},
                heavy=["y" * 1000],
            )
            for pid in prepared_map
        }

    def default_qwen(job, **kwargs):
        t0 = time.perf_counter()
        if llm_fn is not None:
            llm_fn(job, **kwargs)
        job.timings["llm_wait_sec"] = 0.0
        job.timings["llm_elapsed_sec"] = round(time.perf_counter() - t0, 4)

    def default_post(job, **kwargs):
        if post_fn is not None:
            ret = post_fn(job, **kwargs)
        else:
            ret = _fin(pipe, tmp_path, job.paper_id)
        job.timings["post_llm_elapsed_sec"] = 0.001
        job.timings["paper_wall_sec"] = round(time.perf_counter() - job.paper_start_perf, 4)
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
        monitor={"paper_id": pid, "pipeline_stages": {}},
        pred_path=base / "predictions" / f"{pid}.json",
        mon_path=base / "monitors" / f"{pid}_monitor.json",
        experiments=pred["experiments"],
        provenance=[],
        error=error,
    )


class _Env:
    """Patch all output roots into tmp_path for one test (staged-test precedent)."""

    def __init__(self, monkeypatch, tmp_path: Path) -> None:
        monkeypatch.setattr(post_llm, "RUNS_DIR", tmp_path)
        monkeypatch.setattr(config_mod, "RUNS_DIR", tmp_path)
        monkeypatch.setattr(run_paths, "RUNS_DIR", tmp_path)
        monkeypatch.setattr(config_mod, "PARTIALS_DIR", tmp_path / "partials")
        monkeypatch.setattr(monitor_mod, "RUN_HISTORY_PATH", tmp_path / "history.jsonl")
        monkeypatch.setenv("PROD_SKIP_PAPER_MONITOR", "1")


# ------------------------------------------------------ 1. scheduler rolling API


def test_admit_paper_order_duplicate_and_prerequisites(tmp_path: Path, monkeypatch) -> None:
    _Env(monkeypatch, tmp_path)
    pipe = _make_rolling_pipe(tmp_path, target=4)
    _install_fakes(pipe, tmp_path)

    # admit before start_rolling is a programming error
    try:
        pipe.admit_paper("a", Path("dummy.md"))
        raise AssertionError("admit_paper before start_rolling must raise")
    except RuntimeError:
        pass

    pipe.start_rolling()
    pids = [f"p{i:02d}" for i in range(5)]
    for pid in pids:
        pipe.admit_paper(pid, Path("dummy.md"))

    # paper_ids mirrors the ADMISSION order (skipped/md-failed never appear)
    assert pipe.paper_ids == pids
    assert all(pipe.jobs[p].state == PaperBatchState.PREP_QUEUED for p in pids)
    try:
        pipe.admit_paper(pids[0], Path("dummy.md"))
        raise AssertionError("duplicate admission must raise")
    except ValueError:
        pass
    pipe.finish_rolling_input()


def test_every_terminal_class_releases_credit_exactly_once(tmp_path: Path, monkeypatch) -> None:
    """ok-commit, llm error-commit (writer durable), and defensive
    (writer_error -> defensive finalize) each fire the terminal callback
    exactly once; duplicate callbacks are counted, never re-fired."""
    _Env(monkeypatch, tmp_path)
    terminals: list[str] = []

    def on_terminal(pid, result):
        terminals.append(pid)

    pipe = _make_rolling_pipe(tmp_path, target=8, on_terminal=on_terminal)
    _install_fakes(
        pipe,
        tmp_path,
        llm_fn=lambda job, **kw: (_ for _ in ()).throw(TimeoutError("llm timed out"))
        if job.paper_id == "err1"
        else None,
    )
    real_commit = staged_mod.commit_paper_finalization
    failed_once: set[str] = set()

    def flaky_commit(fin):
        # fail exactly the FIRST commit per marked pid — the defensive pass's
        # retry then succeeds (same pattern as the window writer-error test)
        if fin.paper_id == "wfail" and fin.paper_id not in failed_once:
            failed_once.add(fin.paper_id)
            raise OSError("disk full")
        return real_commit(fin)

    monkeypatch.setattr(staged_mod, "commit_paper_finalization", flaky_commit)

    pipe.start_rolling()
    for pid in ["ok1", "err1", "wfail", "ok2"]:
        pipe.admit_paper(pid, Path("dummy.md"))
    pipe.finish_rolling_input()

    assert sorted(terminals) == ["err1", "ok1", "ok2", "wfail"]  # each exactly once
    assert pipe.commit_counts["success"] == 2
    assert pipe.commit_counts["error"] == 1
    assert pipe.commit_counts["writer_error"] == 1
    assert pipe.commit_counts["defensive"] == 1
    assert pipe._rolling_duplicate_terminals == 0
    # manual duplicate callback is deduped, not re-fired
    pipe._on_paper_terminal("ok1", None)
    assert pipe._rolling_duplicate_terminals == 1
    assert terminals.count("ok1") == 1


def test_rolling_strips_heavy_fields_after_terminal(tmp_path: Path, monkeypatch) -> None:
    """After the durable commit nothing heavy survives on the job shell:
    ctx/prepared/bert_result/md_path are None while timings/state/result stay."""
    _Env(monkeypatch, tmp_path)
    pipe = _make_rolling_pipe(tmp_path, target=2)
    _install_fakes(pipe, tmp_path)
    pids = [f"s{i}" for i in range(4)]
    pipe.start_rolling()
    for pid in pids:
        pipe.admit_paper(pid, Path("dummy.md"))
    pipe.finish_rolling_input()

    for pid in pids:
        job = pipe.jobs[pid]
        assert job.result is not None and job.result.error is None
        assert job.ctx is None
        assert job.prepared is None
        assert job.bert_result is None
        assert job.md_path is None
        assert job.timings.get("paper_wall_sec") is not None  # light shell survives
        assert job.state == PaperBatchState.COMMITTED_SUCCESS


def test_window_mode_never_strips_and_keeps_windows_monitor(tmp_path: Path, monkeypatch) -> None:
    """Byte-compat guard: rolling stripping/flat monitor are rolling-only."""
    _Env(monkeypatch, tmp_path)
    spec = get_workflow(WF)
    pids = [f"w{i}" for i in range(3)]
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
        bert_batch_max_wait_ms=200,
    )
    _install_fakes(pipe, tmp_path)
    results = pipe.run()
    assert all(r is not None and r.error is None for r in results)
    for pid in pids:
        job = pipe.jobs[pid]
        assert job.ctx is not None  # window mode: no stripping
        assert job.prepared is not None
        assert job.bert_result is not None
        assert job.md_path is not None
    mon_path = tmp_path / RUN_ID / "staged_pipeline_monitor.json"
    doc = json.loads(mon_path.read_text(encoding="utf-8"))
    assert "windows" in doc and doc["window_count"] == 1
    assert "admission_mode" not in doc["windows"][0]  # rolling keys never leak


def test_rolling_monitor_is_flat_admission_payload(tmp_path: Path, monkeypatch) -> None:
    _Env(monkeypatch, tmp_path)
    pipe = _make_rolling_pipe(tmp_path, target=3)
    _install_fakes(pipe, tmp_path)
    pids = [f"m{i}" for i in range(5)]
    pipe.start_rolling()
    for pid in pids:
        pipe.admit_paper(pid, Path("dummy.md"))
    pipe.finish_rolling_input()

    mon_path = tmp_path / RUN_ID / "staged_pipeline_monitor.json"
    doc = json.loads(mon_path.read_text(encoding="utf-8"))
    assert "windows" not in doc  # flat single payload, no pseudo-window
    assert doc["admission_mode"] == "rolling"
    adm = doc["admission"]
    assert adm["rolling_target"] == 3
    assert adm["admitted"] == 5
    assert adm["terminal_registry"] == 5
    assert adm["duplicate_terminal_callbacks"] == 0
    assert doc["paper_count"] == 5
    assert doc["terminal_states"]["success"] == 5
    assert doc["params"]["rolling_target"] == 3


def test_rolling_batch_index_monotonic_under_staggered_admission(tmp_path: Path, monkeypatch) -> None:
    """Admission is staggered (next paper only after the previous terminal
    fired) — the batcher's batch_index must still be strictly increasing,
    never reused."""
    _Env(monkeypatch, tmp_path)

    def on_terminal(pid, result):
        pass

    pipe = _make_rolling_pipe(tmp_path, target=1, on_terminal=on_terminal)
    _install_fakes(pipe, tmp_path)
    pids = [f"b{i}" for i in range(4)]
    pipe.start_rolling()
    for i, pid in enumerate(pids):
        if i > 0:
            deadline = time.monotonic() + 10.0
            while len(pipe._rolling_terminal_seen) < i:
                if time.monotonic() > deadline:
                    raise AssertionError(f"credit never released before admitting {pid}")
                time.sleep(0.01)
        pipe.admit_paper(pid, Path("dummy.md"))
    pipe.finish_rolling_input()

    indices = [b["batch_index"] for b in pipe.batch_monitor["batches"]]
    assert indices == sorted(indices)
    assert len(indices) == len(set(indices))


def test_rolling_overlaps_papers_within_target(tmp_path: Path, monkeypatch) -> None:
    """target=3 slots with 0.08s llm each: rolling wall must beat the serial
    6*0.08 bound — proof that freed credits are reused promptly."""
    _Env(monkeypatch, tmp_path)

    def slow_qwen(job, **kw):
        time.sleep(0.08)

    pipe = _make_rolling_pipe(
        tmp_path, target=3, llm_concurrency=3, on_terminal=lambda pid, result: None
    )
    _install_fakes(pipe, tmp_path, llm_fn=slow_qwen)
    pids = [f"o{i}" for i in range(6)]
    t0 = time.monotonic()
    pipe.start_rolling()
    admitted = 0
    while admitted < len(pids):
        # naive credit loop: hold in_flight <= target
        if len(pipe.paper_ids) - len(pipe._rolling_terminal_seen) < 3:
            pipe.admit_paper(pids[admitted], Path("dummy.md"))
            admitted += 1
        else:
            time.sleep(0.005)
    pipe.finish_rolling_input()
    wall = time.monotonic() - t0
    assert all(pipe.jobs[p].result is not None and pipe.jobs[p].result.error is None for p in pids)
    assert wall < 6 * 0.08  # serial bound; ~2 rounds of 3 slots


def test_rolling_sentinel_drain_leaves_no_unfinished_tasks(tmp_path: Path, monkeypatch) -> None:
    _Env(monkeypatch, tmp_path)
    pipe = _make_rolling_pipe(tmp_path, target=4)
    _install_fakes(pipe, tmp_path)
    pids = [f"d{i}" for i in range(5)]
    pipe.start_rolling()
    for pid in pids:
        pipe.admit_paper(pid, Path("dummy.md"))
    pipe.finish_rolling_input()
    for q in (pipe.prep_q, pipe.sq_qwen, pipe.sq_post, pipe.sq_write):
        assert q.qsize() == 0
        q.join()  # must not block


def test_rolling_empty_admission_drains_cleanly(tmp_path: Path, monkeypatch) -> None:
    _Env(monkeypatch, tmp_path)
    pipe = _make_rolling_pipe(tmp_path, target=4)
    _install_fakes(pipe, tmp_path)
    pipe.start_rolling()
    results = pipe.finish_rolling_input()
    assert results == []
    assert pipe.batch_monitor["batch_count"] == 0


def test_rolling_heartbeat_cb_receives_snapshots(tmp_path: Path, monkeypatch) -> None:
    _Env(monkeypatch, tmp_path)
    snaps: list[dict] = []

    def hb(snap):
        snaps.append(dict(snap))

    pipe = _make_rolling_pipe(tmp_path, target=2, heartbeat_cb=hb)

    def slow_qwen(job, **kw):
        time.sleep(0.05)

    _install_fakes(pipe, tmp_path, llm_fn=slow_qwen)
    pids = [f"h{i}" for i in range(4)]
    pipe.start_rolling()
    for pid in pids:
        pipe.admit_paper(pid, Path("dummy.md"))
    pipe.finish_rolling_input()
    # the sampler throttles beats to ~1s, but the first tick fires immediately
    # (last_hb starts at 0.0 against perf_counter) — at least one beat lands.
    assert snaps, "rolling heartbeat callback never fired"
    assert {"admitted", "rolling_target", "queue_depth_max", "stage_active_peak"} <= set(snaps[0])


# --------------------------------------------------- 2. _RollingBatchController


def _make_controller(tmp_path: Path, target: int = 4) -> run_bulk._RollingBatchController:
    return run_bulk._RollingBatchController(
        session_run_id="sess",
        job_batch_id="job_batch_000",
        job_run_id="sess/job_batch_000",
        progress_path=tmp_path / "progress.jsonl",
        target=target,
    )


def _fake_result(pid: str, *, error: str | None = None, parse_error: bool = False, ds_count: int | None = 1):
    mon = {
        "paper_id": pid,
        "pipeline_stages": {"llm_elapsed_sec": 0.42},
        "extractors": [
            {
                "extractor_id": "wf4_dev20_v2_datasets",
                "metadata": {"parse_error": parse_error, "datasets_count": ds_count},
            }
        ],
    }
    r = SimpleNamespace(
        paper_id=pid, monitor=mon, error=error, experiments=[] if error else [{"e": 1}]
    )
    return r


def test_controller_credit_gate_and_release(tmp_path: Path) -> None:
    ctrl = _make_controller(tmp_path, target=1)
    assert ctrl.in_flight() == 0
    assert ctrl.wait_for_credit() is True  # immediately
    ctrl.take_credit("a")
    assert ctrl.in_flight() == 1
    # full: wait_for_credit returns False once stop fires
    stop = threading.Event()
    threading.Timer(0.1, stop.set).start()
    t0 = time.monotonic()
    assert ctrl.wait_for_credit(stop=stop) is False
    assert time.monotonic() - t0 < 2.0
    # a durable terminal wakes a blocked credit waiter
    out: list[bool] = []
    th = threading.Thread(target=lambda: out.append(ctrl.wait_for_credit(poll=0.02)))
    th.start()
    time.sleep(0.05)
    assert not out  # still blocked at target
    ctrl.on_pipeline_terminal("a", _fake_result("a"))
    th.join(timeout=2)
    assert not th.is_alive()
    assert out == [True]
    assert ctrl.in_flight() == 0


def test_controller_md_failure_returns_credit_and_writes_progress_once(tmp_path: Path) -> None:
    ctrl = _make_controller(tmp_path, target=2)
    ctrl.record_md_failure("p1", "HTTPError: 404")
    snap = ctrl.snapshot()
    assert snap["admitted"] == 1 and snap["terminal"] == 1 and snap["in_flight"] == 0
    assert snap["attempted"] == 1 and snap["error"] == 1 and snap["md_failures"] == 1
    assert snap["error_classes"]["md_fetch"] == 1
    # duplicate md failure for the same pid is a no-op
    ctrl.record_md_failure("p1", "HTTPError: 404")
    assert ctrl.snapshot()["terminal"] == 1
    rows = [json.loads(x) for x in (tmp_path / "progress.jsonl").read_text().splitlines()]
    assert len(rows) == 1
    assert rows[0]["paper_id"] == "p1" and rows[0]["status"] == "error"
    assert rows[0]["error_class"] == "md_fetch"


def test_controller_pipeline_terminal_stats_single_source(tmp_path: Path) -> None:
    ctrl = _make_controller(tmp_path, target=8)
    ctrl.take_credit("ok1")
    ctrl.on_pipeline_terminal("ok1", _fake_result("ok1"))
    ctrl.take_credit("err1")
    ctrl.on_pipeline_terminal("err1", _fake_result("err1", error="llm/post: TimeoutError: x"))
    ctrl.take_credit("pe1")
    ctrl.on_pipeline_terminal("pe1", _fake_result("pe1", parse_error=True, ds_count=0))
    # duplicate terminal for the same pid: counted once
    ctrl.on_pipeline_terminal("ok1", _fake_result("ok1"))

    st = ctrl.stats()
    assert st["attempted"] == 3
    # window accounting: pe1 (parse_error metadata, no r.error) counts as ok
    # with parse_errors+zero_datasets — exactly like the legacy absorb loop
    assert st["ok"] == 2
    assert st["error"] == 1
    assert st["parse_errors"] == 1
    assert st["zero_datasets"] == 1
    assert st["skipped"] == 0
    assert st["error_classes"]["llm_timeout"] == 1
    assert st["error_classes"]["parse_error"] == 1
    adm = st["admission"]
    assert adm["admitted"] == 3 and adm["terminal"] == 3 and adm["in_flight"] == 0
    assert abs(st["rates"]["error_rate"] - 1 / 3) < 1e-9
    # progress rows: exactly one per terminal
    rows = [json.loads(x) for x in (tmp_path / "progress.jsonl").read_text().splitlines()]
    assert len(rows) == 3
    assert rows[0]["llm_elapsed_sec"] == 0.42
    # skip never writes a row
    ctrl.record_skip("done-before")
    assert ctrl.stats()["skipped"] == 1
    rows = [json.loads(x) for x in (tmp_path / "progress.jsonl").read_text().splitlines()]
    assert len(rows) == 3


def test_controller_stats_match_window_accounting(tmp_path: Path) -> None:
    """ok/error/attempted arithmetic must equal _run_window's: attempted =
    to_run count, error includes md failures, skipped separate."""
    ctrl = _make_controller(tmp_path, target=8)
    ctrl.record_skip("s1")
    ctrl.record_skip("s2")
    ctrl.record_md_failure("m1", "empty_or_missing_cache")
    for pid in ("a", "b", "c"):
        ctrl.take_credit(pid)
        ctrl.on_pipeline_terminal(pid, _fake_result(pid))
    ctrl.take_credit("e1")
    ctrl.on_pipeline_terminal("e1", _fake_result("e1", error="llm/post: ValueError: bad"))
    st = ctrl.stats()
    assert st["attempted"] == 5  # 4 pipeline + 1 md failure; skips excluded
    assert st["skipped"] == 2
    assert st["ok"] == 3
    assert st["error"] == 2  # 1 pipeline + 1 md
    assert abs(st["rates"]["error_rate"] - 2 / 5) < 1e-9


def test_controller_heartbeat_state_merges_scheduler_peaks(tmp_path: Path) -> None:
    ctrl = _make_controller(tmp_path, target=8)
    ctrl.take_credit("a")
    ctrl.on_pipeline_terminal("a", _fake_result("a"))
    state = ctrl.heartbeat_state(
        {
            "admitted": 1,
            "rolling_target": 8,
            "queue_depth_max": {"prep": 3},
            "stage_active_peak": {"llm_http": 2},
        }
    )
    assert state["queue_depth_max"] == {"prep": 3}
    assert state["stage_active_peak"] == {"llm_http": 2}
    assert state["admitted"] == 1 and state["terminal"] == 1 and state["in_flight"] == 0
    assert "pph_cum" in state


# --------------------------------------------------- 3. _run_window_rolling e2e


ROLL_CFG = {
    "scheduler_mode": "staged",
    "bert_pipeline_mode": "global_batch",
    "admission_mode": "rolling",
    "rolling_target": 4,
    "md_prefetch_lookahead": 8,
    "md_fetch_concurrency": 2,
    "md_fetch_retries": 1,
    "workflow": WF,
    "llm_concurrency": 2,
    "bert_batch_size": 32,
    "bert_batch_max_papers": 16,
    "bert_batch_max_sentences": 1500,
    "bert_batch_max_chars": 300000,
    "bert_batch_max_wait_ms": 50,
    "bert_endpoint_concurrency": 1,
    "prep_queue_maxsize": 8,
    "llm_queue_maxsize": 8,
    "post_queue_maxsize": 8,
    "write_queue_maxsize": 8,
    "prep_workers": 2,
    "post_workers": 2,
    "llm_timeout": 30,
}


def test_run_window_rolling_end_to_end(tmp_path: Path, monkeypatch) -> None:
    _Env(monkeypatch, tmp_path)
    monkeypatch.setattr(run_bulk, "EVAL_MD_CACHE_DIR", tmp_path / "mdcache")

    pre_done = {"skip1", "skip2"}
    md_fail = {"mdfail1", "mdfail2"}
    llm_fail = {"qerr1"}

    def fake_prediction_ok(session_run_id, job_batch_id, pid):
        return pid in pre_done

    def fake_ensure_cached(pid, url, cache_dir):
        if pid in md_fail:
            return None, "HTTPError: 404 not found"
        p = Path(cache_dir) / f"{pid}.md"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("markdown body", encoding="utf-8")
        return p, None

    monkeypatch.setattr(run_bulk, "_prediction_ok", fake_prediction_ok)
    monkeypatch.setattr(run_bulk, "ensure_cached", fake_ensure_cached)

    # scheduler fakes: reuse a rolling pipe we throw away just to bind stage fakes?
    # No — patch module seams directly (same as test_staged_pipeline).
    def fake_prep(self, pid: str) -> None:
        job = self.jobs[pid]
        job.paper_start_perf = time.perf_counter()
        job.ctx = SimpleNamespace(
            paper_id=pid, md_path=Path("d.md"), run_id="x", workflow_id=WF,
            dry_run=False, raw_md="md", partials={}, set=lambda r: None,
        )
        job.prepared = SimpleNamespace(english_sentences=["s1 s2"], clean_stats={})

    def fake_bert(self, prepared_map):
        return {pid: SimpleNamespace(timings={}) for pid in prepared_map}

    def fake_qwen(job, **kw):
        if job.paper_id in llm_fail:
            raise TimeoutError("llm timed out")
        job.timings["llm_wait_sec"] = 0.0
        job.timings["llm_elapsed_sec"] = 0.001

    def fake_post(job, **kw):
        return _fin(None, tmp_path, job.paper_id, error="llm/post: TimeoutError: llm timed out" if job.paper_id in llm_fail else None)

    monkeypatch.setattr(StagedPipelineWf4, "_prep_paper", fake_prep)
    monkeypatch.setattr(StagedPipelineWf4, "_global_batch_fn", fake_bert)
    monkeypatch.setattr(staged_mod, "run_qwen_http_stage", fake_qwen)
    monkeypatch.setattr(staged_mod, "run_post_stage", fake_post)

    papers = [
        {"paper_id": pid, "md_url": f"http://x/{pid}.md"}
        for pid in ["skip1", "skip2", "mdfail1", "mdfail2", "qerr1", "ok1", "ok2", "ok3", "ok4"]
    ]
    st = run_bulk._run_window_rolling(
        paper_items=papers,
        session_run_id="sess",
        job_batch_id="job_batch_000",
        cfg=dict(ROLL_CFG),
        force=False,
    )

    assert st["attempted"] == 7  # 9 - 2 skips
    assert st["skipped"] == 2
    assert st["ok"] == 4
    assert st["error"] == 3  # 2 md + 1 llm
    adm = st["admission"]
    assert adm["admitted"] == 7 and adm["terminal"] == 7 and adm["in_flight"] == 0
    assert adm["md_failures"] == 2
    assert st["error_classes"]["md_fetch"] == 2
    assert st["error_classes"]["llm_timeout"] == 1
    assert st["batch_monitor"]["scheduler_mode"] == "staged"

    # flat rolling monitor on disk. The scheduler's admitted is
    # admitted-pipeline-only (skips/MD failures never enter); the controller's
    # admitted additionally counts MD-failure credits (returned immediately).
    mon = json.loads((tmp_path / "sess/job_batch_000/staged_pipeline_monitor.json").read_text())
    assert mon["admission_mode"] == "rolling"
    assert mon["admission"]["admitted"] == 5
    assert mon["admission"]["terminal_registry"] == 5
    assert mon["paper_count"] == 5
    assert "windows" not in mon

    # progress rows: one per non-skipped paper (md rows + pipeline rows)
    rows = [json.loads(x) for x in (tmp_path / "sess/job_batch_000/progress.jsonl").read_text().splitlines()]
    assert len(rows) == 7
    assert sum(1 for r in rows if r.get("error_class") == "md_fetch") == 2
    assert sum(1 for r in rows if r["status"] == "ok") == 4
    # results order must follow admission order, not completion order
    assert st["rates"]["error_rate"] == 3 / 7


def test_run_window_rolling_stop_drains_safely(tmp_path: Path, monkeypatch) -> None:
    """STOP before any admission: loop exits, drain completes, stats balance."""
    _Env(monkeypatch, tmp_path)
    monkeypatch.setattr(run_bulk, "EVAL_MD_CACHE_DIR", tmp_path / "mdcache")
    monkeypatch.setattr(run_bulk, "_prediction_ok", lambda *a: False)
    monkeypatch.setattr(
        run_bulk, "ensure_cached", lambda pid, url, cd: (Path(cd) / f"{pid}.md", None)
    )
    # make the md files actually exist so a (never-reached) resolve would work
    (tmp_path / "mdcache").mkdir(parents=True, exist_ok=True)
    papers = [{"paper_id": "x1", "md_url": "u"}]
    stop_event = threading.Event()
    stop_event.set()
    monkeypatch.setattr(run_bulk, "STOP", stop_event)
    st = run_bulk._run_window_rolling(
        paper_items=papers,
        session_run_id="sess",
        job_batch_id="job_batch_000",
        cfg=dict(ROLL_CFG),
        force=False,
    )
    assert st["stopped"] is True
    assert st["attempted"] == 0 and st["admission"]["admitted"] == 0


def test_validate_admission_config() -> None:
    assert run_bulk._validate_admission_config({}) == {"admission_mode": "window"}
    assert run_bulk._validate_admission_config({"admission_mode": "window"}) == {
        "admission_mode": "window"
    }
    ok = run_bulk._validate_admission_config(
        {
            "admission_mode": "rolling",
            "scheduler_mode": "staged",
            "bert_pipeline_mode": "global_batch",
            "rolling_target": 128,
            "md_fetch_concurrency": 8,
        }
    )
    assert ok["md_prefetch_lookahead"] == 144  # target + 2*md_fetch_concurrency
    explicit = run_bulk._validate_admission_config(
        {
            "admission_mode": "rolling",
            "scheduler_mode": "staged",
            "bert_pipeline_mode": "global_batch",
            "rolling_target": 128,
            "md_fetch_concurrency": 8,
            "md_prefetch_lookahead": 200,
        }
    )
    assert explicit["md_prefetch_lookahead"] == 200

    for bad in (
        {"admission_mode": "yolo"},
        {"admission_mode": "rolling"},  # missing staged/global_batch/target
        {
            "admission_mode": "rolling",
            "scheduler_mode": "staged",
            "bert_pipeline_mode": "chunked_overlap",
            "rolling_target": 8,
        },
        {
            "admission_mode": "rolling",
            "scheduler_mode": "staged",
            "bert_pipeline_mode": "global_batch",
            "rolling_target": 0,
        },
        {
            "admission_mode": "rolling",
            "scheduler_mode": "staged",
            "bert_pipeline_mode": "global_batch",
            "rolling_target": 100,
            "md_prefetch_lookahead": 50,
        },
    ):
        try:
            run_bulk._validate_admission_config(bad)
            raise AssertionError(f"expected SystemExit for {bad}")
        except SystemExit:
            pass


def test_rolling_heavy_payload_peak_bounded_by_target(tmp_path: Path, monkeypatch) -> None:
    """Plan §6.1 memory bound: 500 synthetic papers, target=128 — the number
    of simultaneously LIVE heavy payloads must never exceed target (+ a small
    handoff slack), and after drain every heavy object must be collected.
    This is the unit-level proof that memory does not accumulate with the
    terminal count (the p500 RSS gate's mechanistic property)."""

    class _Heavy:
        _live = 0
        _peak = 0
        _lock = threading.Lock()

        def __init__(self, n: int) -> None:
            with _Heavy._lock:
                _Heavy._live += 1
                _Heavy._peak = max(_Heavy._peak, _Heavy._live)
            self.blob = bytearray(n)

        def __del__(self) -> None:
            with _Heavy._lock:
                _Heavy._live -= 1

    _Env(monkeypatch, tmp_path)

    def slow_qwen(job, **kw):
        time.sleep(0.02)

    pipe = _make_rolling_pipe(
        tmp_path, target=128, llm_concurrency=16,
        on_terminal=lambda pid, result: None,
    )
    _install_fakes(pipe, tmp_path, llm_fn=slow_qwen)

    def prep_with_heavy(pid: str) -> None:
        job = pipe.jobs[pid]
        job.paper_start_perf = time.perf_counter()
        job.ctx = SimpleNamespace(
            paper_id=pid, md_path=Path("dummy.md"), run_id=RUN_ID,
            workflow_id=WF, dry_run=False,
            raw_md="", partials={}, set=lambda r: None,
        )
        job.prepared = SimpleNamespace(
            english_sentences=["s"] * 3, clean_stats={},
            heavy=_Heavy(2048),
        )

    pipe._prep_paper = prep_with_heavy

    pids = [f"h{i}" for i in range(500)]
    pipe.start_rolling()
    admitted = 0
    while admitted < len(pids):
        if len(pipe.paper_ids) - len(pipe._rolling_terminal_seen) < 128:
            pipe.admit_paper(pids[admitted], Path("dummy.md"))
            admitted += 1
        else:
            time.sleep(0.002)
    pipe.finish_rolling_input()

    assert all(
        pipe.jobs[p].result is not None and pipe.jobs[p].result.error is None
        for p in pids
    ), "synthetic run must be all-ok for the strip points to be exercised"
    import gc
    gc.collect()
    assert _Heavy._peak <= 128 + 4, (
        f"live heavy payloads peaked at {_Heavy._peak}, exceeding target 128"
    )
    assert _Heavy._live == 0, (
        f"{_Heavy._live} heavy payloads still alive after drain"
    )
