"""v0.7 Phase 3 fault-injection tests (TODO-V07-04) — fake-injected, no HTTP.

Scenario matrix (see docs/V07_PHASE3_REPORT.md §fault matrix):
  A  PREP single-paper failure        — isolated, retryable, no empty success
  B  BERT whole-batch failure         — only that batch's papers fail, later
                                        batches continue
  C  BERT 200 missing paper_id        — missing paper explicit error, returned
                                        papers proceed with correct pid mapping
  D  LLM timeout/429/5xx/connection  — error commit + stable error classes +
                                        inference-slot release timeline
  D2 dense mixed timeout/5xx faults   — all papers reach a terminal state,
                                        conservation holds, no deadlock
  E  LLM parse error                 — POST never runs, explicit error
                                        prediction, no empty-experiment fake ok
  F  POST exception                   — error prediction, no success written
  G  writer single failure            — others commit, writer_errors recorded,
                                        defensive pass recovers, no overwrite
  H  six fault kinds in ONE run       — conservation: success+error == input,
                                        exactly one commit per paper
  I  schema-invalid experiment        — code-as-truth: exposed (counted) only
                                        in the offline merge, never a paper-level
                                        online error; not dropped from export
  K  BERT duplicate paper_id submit   — explicit batcher error

Injection seams are the same as tests/test_staged_pipeline.py (Phase 2):
``_prep_paper`` / ``_global_batch_fn`` / module-level ``run_qwen_http_stage``
/ ``run_post_stage`` / ``commit_paper_finalization``.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests

PROD_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROD_ROOT))

import pipeline.production.config as config_mod  # noqa: E402
import pipeline.production.monitor as monitor_mod  # noqa: E402
import pipeline.production.post_llm as post_llm  # noqa: E402
import pipeline.production.run_paths as run_paths  # noqa: E402
import pipeline.production.staged_pipeline_wf4 as staged_mod  # noqa: E402
from pipeline.production.batch_bert_pipeline_wf4 import BertGlobalBatcher  # noqa: E402
from pipeline.production.batch_llm_common import PaperBatchState  # noqa: E402
from pipeline.production.post_llm import PaperFinalization  # noqa: E402
from pipeline.production.staged_pipeline_wf4 import StagedPipelineWf4  # noqa: E402
from pipeline.production.workflows.spec import get_workflow  # noqa: E402

WF = "prod-wf4-llm-datasets-experiment"
SESSION = "phase3fi"
RUN_ID = f"{SESSION}/job_batch_000"

# scripts/ is not a package; load run_bulk.py by path for _classify_error.
_spec = importlib.util.spec_from_file_location("run_bulk_phase3fi", PROD_ROOT / "scripts" / "run_bulk.py")
run_bulk = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(run_bulk)


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
            "run_id": RUN_ID,
            "paper_id": pid,
            "workflow_id": WF,
            "dry_run": False,
            "experiment_count": len(pred["experiments"]),
            "error": error,
        },
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


def _history(tmp_path: Path) -> list[dict]:
    p = tmp_path / "history.jsonl"
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def _pred(tmp_path: Path, pid: str) -> dict:
    return json.loads(
        (tmp_path / RUN_ID / "predictions" / f"{pid}.json").read_text(encoding="utf-8")
    )


def _ok(pid: str) -> bool:
    return run_paths.prediction_ok(SESSION, "job_batch_000", pid)


def _install(
    pipe: StagedPipelineWf4,
    tmp_path: Path,
    *,
    fail_prep: str | None = None,
    bert_fn=None,
    bert_missing: str | None = None,
    llm_raise: dict[str, Exception] | None = None,
    llm_parse_err: str | None = None,
    post_raise: str | None = None,
    post_called: list[str] | None = None,
    commit_fail: str | None = None,
    events: list | None = None,
) -> None:
    """Happy-path fakes + per-stage failure hooks (Phase 3 scenario seams)."""

    def prep(pid: str) -> None:
        job = pipe.jobs[pid]
        job.paper_start_perf = time.perf_counter()
        if pid == fail_prep:
            job.error = f"prep: FileNotFoundError: boom {pid}"
            pipe._fail_paper(job, source="prep")
            return
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
        job.prepared = SimpleNamespace(
            english_sentences=["sentence one two three"] * 3, clean_stats={}
        )

    def bert(prepared_map: dict) -> dict:
        if bert_fn is not None:
            return bert_fn(prepared_map)
        return {
            pid: SimpleNamespace(
                timings={"bert_amortized_sec": 0.01, "bert_batch_chunk": 0},
                marker=f"bert-for-{pid}",
            )
            for pid in prepared_map
            if pid != bert_missing
        }

    def llm(job, **kw):
        t0 = time.perf_counter()
        if events is not None:
            events.append(("llm_start", job.paper_id, t0))
        exc = (llm_raise or {}).get(job.paper_id)
        if exc is not None:
            if events is not None:
                events.append(("llm_end", job.paper_id, time.perf_counter()))
            raise exc
        ret = None
        if job.paper_id == llm_parse_err:
            ret = "llm_parse_or_empty: ValueError: Expecting value"
        job.timings["llm_wait_sec"] = 0.0
        job.timings["llm_elapsed_sec"] = round(time.perf_counter() - t0, 4)
        if events is not None:
            events.append(("llm_end", job.paper_id, time.perf_counter()))
        return ret

    def post(job, **kw):
        if post_called is not None:
            post_called.append(job.paper_id)
        if job.paper_id == post_raise:
            raise RuntimeError(f"post exploded for {job.paper_id}")
        fin = _fin(tmp_path, job.paper_id)
        job.timings["post_llm_elapsed_sec"] = 0.0
        job.timings["paper_wall_sec"] = 0.0
        return fin

    pipe._prep_paper = prep
    pipe._global_batch_fn = bert
    staged_mod.run_qwen_http_stage = llm
    staged_mod.run_post_stage = post

    if commit_fail is not None:
        real_commit = staged_mod.commit_paper_finalization

        def flaky_commit(fin: PaperFinalization) -> None:
            if fin.paper_id == commit_fail:
                raise OSError("disk full")
            return real_commit(fin)

        staged_mod.commit_paper_finalization = flaky_commit


# ----------------------------------------------------------------- A. PREP failure


def test_A_prep_single_failure_isolated_and_retryable(tmp_path: Path, monkeypatch) -> None:
    _Env(monkeypatch, tmp_path)
    pids = ["ok1", "ok2", "e1", "ok3", "ok4"]
    pipe = _make_pipe(tmp_path, pids, prep_workers=1)
    _install(pipe, tmp_path, fail_prep="e1")
    results = pipe.run()

    assert len(results) == 5
    assert pipe.commit_counts == {"success": 4, "error": 1, "writer_error": 0, "defensive": 0}
    assert pipe.duplicate_commit_attempts == []
    # failed paper: explicit error prediction, no empty success, retryable
    assert pipe.jobs["e1"].state == PaperBatchState.COMMITTED_ERROR
    pred = _pred(tmp_path, "e1")
    assert pred["error"].startswith("prep:")
    assert pred["experiments"] == []
    assert _ok("e1") is False
    # others committed success and are skip-eligible
    for pid in ("ok1", "ok2", "ok3", "ok4"):
        assert pipe.jobs[pid].state == PaperBatchState.COMMITTED_SUCCESS
        assert "error" not in _pred(tmp_path, pid)
        assert _ok(pid) is True
    # history: exactly one terminal record per paper (5 papers -> 5 lines)
    hist = _history(tmp_path)
    assert sorted(h["paper_id"] for h in hist) == sorted(pids)
    assert sum(1 for h in hist if h["paper_id"] == "e1") == 1


# ------------------------------------------------------- B. BERT whole-batch failure


def test_B_bert_batch_failure_only_fails_that_batch(tmp_path: Path, monkeypatch) -> None:
    _Env(monkeypatch, tmp_path)
    # prep_workers=1 => FIFO submit order => deterministic 3+3 batches
    pids = ["b1", "b2", "b3", "g1", "g2", "g3"]
    pipe = _make_pipe(
        tmp_path, pids, prep_workers=1, bert_batch_max_papers=3, bert_batch_max_wait_ms=200
    )

    def failing_first_batch(prepared_map: dict) -> dict:
        if "b1" in prepared_map:  # the first flushed batch
            raise ConnectionError("bert endpoint down")
        return {
            pid: SimpleNamespace(timings={"bert_amortized_sec": 0.01})
            for pid in prepared_map
        }

    _install(pipe, tmp_path, bert_fn=failing_first_batch)
    pipe.run()

    # batch {b1,b2,b3} failed with the retryable batch-failed marker...
    for pid in ("b1", "b2", "b3"):
        pred = _pred(tmp_path, pid)
        assert pred["error"].startswith("bert_batch_failed:")
        assert _ok(pid) is False
    # ...and the SUBSEQUENT batch continued normally (no window abort, no silent skip)
    for pid in ("g1", "g2", "g3"):
        assert pipe.jobs[pid].state == PaperBatchState.COMMITTED_SUCCESS
        assert _ok(pid) is True
    assert pipe.commit_counts["success"] == 3
    assert pipe.commit_counts["error"] == 3


# -------------------------------------------------- C. BERT 200 missing paper_id


def test_C_bert_missing_paper_id_explicit_error_others_mapped(tmp_path: Path, monkeypatch) -> None:
    _Env(monkeypatch, tmp_path)
    pids = ["m0", "m1", "m2"]
    pipe = _make_pipe(tmp_path, pids)

    def reverse_bert(prepared_map: dict) -> dict:
        # 200 OK but m1 absent; mapping of returned papers must not depend
        # on response order (dict keyed by pid, built in reverse here).
        return {
            pid: SimpleNamespace(
                timings={"bert_amortized_sec": 0.01}, marker=f"bert-for-{pid}"
            )
            for pid in reversed(list(prepared_map))
            if pid != "m1"
        }

    _install(pipe, tmp_path, bert_fn=reverse_bert)
    pipe.run()

    pred = _pred(tmp_path, "m1")
    assert "bert_global_batch: no result for paper" in pred["error"]
    assert pred["experiments"] == []
    assert _ok("m1") is False
    for pid in ("m0", "m2"):
        assert pipe.jobs[pid].bert_result.marker == f"bert-for-{pid}"
        assert pipe.jobs[pid].state == PaperBatchState.COMMITTED_SUCCESS
        assert _ok(pid) is True


# ------------------------------------- D. LLM timeout / 429 / 5xx / connection error

# Real-form error strings (openai_chat backend): classification relies on
# substring ORDER in run_bulk._classify_error — e.g. "timeout" is checked
# before "http", so ReadTimeout: HTTPConnectionPool... -> llm_timeout.
_QWEN_HTTP_CASES = [
    pytest.param(
        requests.exceptions.ReadTimeout(
            "HTTPSConnectionPool(host='llm.internal.example', port=8000): "
            "Read timed out. (read timeout=30)"
        ),
        "ReadTimeout",
        "llm_timeout",
        id="timeout",
    ),
    pytest.param(
        requests.exceptions.HTTPError(
            "429 Too Many Requests for url: "
            "http://llm.internal.example:8000/qwen17b/v1/chat/completions"
        ),
        "HTTPError",
        "llm_http",
        id="429",
    ),
    pytest.param(
        requests.exceptions.HTTPError(
            "500 Internal Server Error for url: "
            "http://llm.internal.example:8000/qwen17b/v1/chat/completions"
        ),
        "HTTPError",
        "llm_http",
        id="5xx",
    ),
    pytest.param(
        requests.exceptions.ConnectionError(
            "HTTPConnectionPool(host='llm.internal.example', port=8000): Max retries "
            "exceeded with url: /qwen17b/v1/chat/completions"
        ),
        "ConnectionError",
        "llm_http",
        id="connection",
    ),
]


@pytest.mark.parametrize("exc,type_name,expect_class", _QWEN_HTTP_CASES)
def test_D_qwen_http_error_commit_slot_release_and_class(
    tmp_path: Path, monkeypatch, exc, type_name, expect_class
) -> None:
    _Env(monkeypatch, tmp_path)
    events: list[tuple[str, str, float]] = []
    pipe = _make_pipe(
        tmp_path, ["A", "B"], llm_concurrency=1, post_workers=1, prep_workers=1,
        bert_batch_max_wait_ms=400,  # both papers in ONE batch -> B follows A
    )
    _install(pipe, tmp_path, llm_raise={"A": exc}, events=events)
    pipe.run()

    # A: error commit with the legacy-identical string; retryable
    pred = _pred(tmp_path, "A")
    assert pred["error"].startswith(f"llm/post: {type_name}:")
    assert _ok("A") is False
    # B: unaffected, committed success
    assert pipe.jobs["B"].state == PaperBatchState.COMMITTED_SUCCESS
    assert _ok("B") is True
    # inference slot released on failure: B's HTTP starts only after A's ended
    def ev(name: str, pid: str) -> float:
        return [t for n, p, t in events if n == name and p == pid][0]

    assert ev("llm_end", "A") < ev("llm_start", "B")
    # stable error classification (run_bulk._classify_error, substring order)
    assert run_bulk._classify_error(pred["error"]) == expect_class


def test_D_classify_error_stable_mapping() -> None:
    """Classification table for every Phase 3 error family (real-form strings)."""
    cases = {
        "llm/post: ReadTimeout: HTTPSConnectionPool(host='h', port=1): Read timed out. (read timeout=30)": "llm_timeout",
        "llm/post: HTTPError: 429 Too Many Requests for url: http://h/v1": "llm_http",
        "llm/post: HTTPError: 500 Internal Server Error for url: http://h/v1": "llm_http",
        "llm/post: ConnectionError: HTTPConnectionPool(host='h', port=1): Max retries exceeded": "llm_http",
        "bert_batch_failed: ConnectionError: bert endpoint down": "bert",
        "bert_global_batch: no result for paper (batch 3)": "bert",
        "bert_global_batch: duplicate paper_id x": "bert",
        "llm_parse_or_empty: ValueError: Expecting value": "parse_error",
        "llm/post: RuntimeError: post exploded for q1": "post_llm",
        "prep: FileNotFoundError: boom e1": "other",
        "no_result_set": "other",
    }
    for err, expect in cases.items():
        assert run_bulk._classify_error(err) == expect, err


# ------------------------------------------------------------- D2. dense faults


def test_D2_dense_mixed_timeout_5xx_all_terminal(tmp_path: Path, monkeypatch) -> None:
    _Env(monkeypatch, tmp_path)
    pids = [f"d{i:02d}" for i in range(16)]
    # deterministic 50% failure mix: even idx -> 5xx, odd idx -> timeout
    raises = {
        pid: (
            requests.exceptions.HTTPError("500 Internal Server Error for url: http://h/v1")
            if i % 2 == 0
            else requests.exceptions.ReadTimeout(
                "HTTPSConnectionPool(host='h', port=8000): Read timed out. (read timeout=30)"
            )
        )
        for i, pid in enumerate(pids)
        if i % 3 != 2  # every 3rd paper survives -> ~50% failure density
    }
    pipe = _make_pipe(tmp_path, pids, llm_concurrency=3, post_workers=2)
    _install(pipe, tmp_path, llm_raise=raises)
    results = pipe.run()

    n_fail = len(raises)
    assert len(results) == len(pids)  # no deadlock: run drained fully
    assert pipe.commit_counts["success"] == len(pids) - n_fail
    assert pipe.commit_counts["error"] == n_fail
    assert pipe.commit_counts["defensive"] == 0
    assert pipe.duplicate_commit_attempts == []
    for pid in raises:
        assert _ok(pid) is False
    for pid in set(pids) - set(raises):
        assert _ok(pid) is True
    # classification split exactly along the injected mix
    errors = [pipe.jobs[p].result.error for p in raises]
    assert sum(run_bulk._classify_error(e) == "llm_timeout" for e in errors) == sum(
        1 for p in raises if p in [q for q, e in raises.items() if isinstance(e, requests.exceptions.ReadTimeout)]
    )


# ------------------------------------------------------------ E. LLM parse error


def test_E_parse_error_skips_post_no_fake_success(tmp_path: Path, monkeypatch) -> None:
    _Env(monkeypatch, tmp_path)
    post_called: list[str] = []
    pipe = _make_pipe(tmp_path, ["p1", "p2", "p3"])
    _install(pipe, tmp_path, llm_parse_err="p1", post_called=post_called)
    pipe.run()

    assert "p1" not in post_called  # parse-failed paper never reaches POST
    assert sorted(post_called) == ["p2", "p3"]
    pred = _pred(tmp_path, "p1")
    assert pred["error"].startswith("llm_parse_or_empty:")
    assert pred["experiments"] == []  # no empty-experiments fake success
    assert _ok("p1") is False
    assert _ok("p2") is True and _ok("p3") is True


# ------------------------------------------------------------- F. POST exception


def test_F_post_exception_error_prediction_no_success(tmp_path: Path, monkeypatch) -> None:
    _Env(monkeypatch, tmp_path)
    pipe = _make_pipe(tmp_path, ["q1", "q2"])
    _install(pipe, tmp_path, post_raise="q1")
    pipe.run()

    pred = _pred(tmp_path, "q1")
    assert pred["error"].startswith("llm/post: RuntimeError:")
    assert pred["experiments"] == []
    assert _ok("q1") is False
    assert pipe.jobs["q1"].state == PaperBatchState.COMMITTED_ERROR
    assert _ok("q2") is True


# ----------------------------------------------------------- G. writer failure


def test_G_writer_failure_isolated_defensive_recovers_no_overwrite(
    tmp_path: Path, monkeypatch
) -> None:
    _Env(monkeypatch, tmp_path)
    pipe = _make_pipe(tmp_path, ["w1", "w2", "w3"])
    _install(pipe, tmp_path, commit_fail="w2")
    try:
        pipe.run()
    finally:
        # _install patched the module symbol; restore the real commit here so
        # later tests in the same process see the pristine seam.
        staged_mod.commit_paper_finalization = post_llm.commit_paper_finalization

    # w1/w3 committed fine and stay untouched (no error overwrites success)
    assert _ok("w1") is True and _ok("w3") is True
    assert "error" not in _pred(tmp_path, "w1")
    assert "error" not in _pred(tmp_path, "w3")
    # writer error recorded; defensive pass re-finalized w2 (retryable)
    assert [e["paper_id"] for e in pipe.writer_errors] == ["w2"]
    assert pipe.commit_counts["writer_error"] == 1
    assert pipe.commit_counts["defensive"] == 1
    pred = _pred(tmp_path, "w2")
    assert pred["error"] == "no_result_set"
    assert _ok("w2") is False
    # history: exactly one terminal record per paper, no duplicate finals
    hist = _history(tmp_path)
    assert sorted(h["paper_id"] for h in hist) == ["w1", "w2", "w3"]


# ------------------------------------------------- H. six fault kinds in one run


def test_H_multi_fault_mixed_conservation(tmp_path: Path, monkeypatch) -> None:
    _Env(monkeypatch, tmp_path)
    pids = ["h-prep", "h-bert", "h-llm", "h-parse", "h-post", "h-writer", "ok1", "ok2"]
    # bert_batch_max_papers=1 => every paper is its own BERT batch, so the
    # injected batch failure hits exactly one paper.
    pipe = _make_pipe(tmp_path, pids, bert_batch_max_papers=1, prep_workers=1)

    def bert_fail_only_h_bert(prepared_map: dict) -> dict:
        if "h-bert" in prepared_map:
            raise ConnectionError("bert endpoint down")
        return {
            pid: SimpleNamespace(timings={"bert_amortized_sec": 0.01})
            for pid in prepared_map
        }

    _install(
        pipe,
        tmp_path,
        fail_prep="h-prep",
        bert_fn=bert_fail_only_h_bert,
        llm_raise={
            "h-llm": requests.exceptions.ReadTimeout(
                "HTTPSConnectionPool(host='h', port=8000): Read timed out. (read timeout=30)"
            )
        },
        llm_parse_err="h-parse",
        post_raise="h-post",
        commit_fail="h-writer",
    )
    try:
        results = pipe.run()
    finally:
        staged_mod.commit_paper_finalization = post_llm.commit_paper_finalization

    assert len(results) == len(pids)  # nobody silently dropped
    # exactly one commit per paper: 2 success + 5 error + 1 writer_error(defensive)
    assert pipe.commit_counts == {
        "success": 2, "error": 5, "writer_error": 1, "defensive": 1
    }
    assert pipe.duplicate_commit_attempts == []
    # every paper landed exactly one final artifact on disk
    expect_error = {"h-prep", "h-bert", "h-llm", "h-parse", "h-post", "h-writer"}
    for pid in pids:
        pred = _pred(tmp_path, pid)
        assert pred["paper_id"] == pid
        if pid in expect_error:
            assert pred.get("error"), pid
            assert _ok(pid) is False
        else:
            assert "error" not in pred, pid
            assert _ok(pid) is True
    hist = _history(tmp_path)
    assert sorted(h["paper_id"] for h in hist) == sorted(pids)
    assert len(hist) == len(pids)


# ------------------------------------------- I. schema-invalid: merge-layer only


def test_I_schema_invalid_counted_in_merge_not_dropped(tmp_path: Path, monkeypatch) -> None:
    """Code-as-truth: the ONLY online validation is the LLM JSON parse; wf4
    schema violations surface in the offline merge as counts/samples and the
    experiment is still exported (never dropped, never a paper-level error)."""
    import pipeline.production.runners.merge_run_predictions as mrp
    from pipeline.production.schema import empty_experiment

    monkeypatch.setattr(mrp, "RUNS_DIR", tmp_path)

    def exp(pid: str, **overrides) -> dict:
        e = empty_experiment(pid)
        e.pop("research_problem", None)
        e.update(overrides)
        return e

    pred_dir = tmp_path / "sess" / "predictions"
    pred_dir.mkdir(parents=True)
    good = exp("paper_ok")
    bad = exp("paper_bad", score="0.9")  # schema: score must be number|null
    (pred_dir / "paper_ok.json").write_text(
        json.dumps({"paper_id": "paper_ok", "experiments": [good]}), encoding="utf-8"
    )
    (pred_dir / "paper_bad.json").write_text(
        json.dumps({"paper_id": "paper_bad", "experiments": [bad]}), encoding="utf-8"
    )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps({"papers": [{"paper_id": "paper_ok"}, {"paper_id": "paper_bad"}]}),
        encoding="utf-8",
    )
    out_flat = tmp_path / "flat.json"
    stats = mrp.merge_run(
        run_id="sess",
        manifest_path=manifest,
        out_flat=out_flat,
        out_papers=None,
        report_path=tmp_path / "report.md",
    )

    assert stats["schema_error_experiments"] == 1
    flat = json.loads(out_flat.read_text(encoding="utf-8"))
    assert len(flat) == 2  # invalid experiment still exported, not dropped
    assert any(f["paper_id"] == "paper_bad" and f["score"] == "0.9" for f in flat)
    assert stats["predictions_found"] == 2  # no paper-level failure introduced


# ---------------------------------------------- K. BERT duplicate paper_id submit


def test_K_bert_duplicate_paper_id_explicit_error(tmp_path: Path) -> None:
    errors: list[tuple[list[str], str]] = []
    dispatched: list[list[str]] = []

    def batch_fn(prepared_map: dict) -> dict:
        dispatched.append(list(prepared_map))
        return {pid: SimpleNamespace(timings={}) for pid in prepared_map}

    batcher = BertGlobalBatcher(
        max_papers=8, max_wait_ms=10, batch_fn=batch_fn,
        error_fn=lambda pids, err: errors.append((pids, err)),
    )
    prepared = SimpleNamespace(english_sentences=["s1"], clean_stats={})
    batcher.submit("dup", prepared)
    batcher.submit("dup", prepared)  # duplicate pid -> explicit error, no batch entry
    batcher.end_of_input()
    t = threading.Thread(target=batcher.run, daemon=True)
    t.start()
    t.join(timeout=5)
    assert not t.is_alive()

    assert errors == [(["dup"], "bert_global_batch: duplicate paper_id dup")]
    assert dispatched == [["dup"]]  # the duplicate never entered a batch


if __name__ == "__main__":
    raise SystemExit("run via pytest")
