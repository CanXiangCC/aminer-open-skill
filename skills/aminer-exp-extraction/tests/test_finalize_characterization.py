"""Characterization tests for the v0.7 Phase 2 finalize_paper split.

``finalize_paper`` was split into ``build_paper_finalization`` (no filesystem
side effects) + ``commit_paper_finalization`` (durable write). These tests
lock the shared contract so wf1/wf2/chunked/global_batch callers — which keep
using the composed wrapper — cannot drift:

  - composed wrapper == build + commit (same prediction/monitor/result)
  - prediction write is tmp + os.replace (atomic), no .tmp residue
  - error predictions persist the error marker (prediction_ok -> False)
  - dry_run skips partials + run history; non-dry_run writes both
  - staged-only pieces (error finalization build, commit idempotence at the
    scheduler level) are covered in test_staged_pipeline.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

PROD_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROD_ROOT))

import pipeline.production.monitor as monitor_mod  # noqa: E402
import pipeline.production.post_llm as post_llm  # noqa: E402
import pipeline.production.run_paths as run_paths  # noqa: E402
from pipeline.production.context import PaperContext  # noqa: E402
from pipeline.production.post_llm import (  # noqa: E402
    build_paper_finalization,
    commit_paper_finalization,
    finalize_paper,
)
from pipeline.production.schema import FieldResult  # noqa: E402
from pipeline.production.workflows.spec import get_workflow  # noqa: E402

WF = "prod-wf4-llm-datasets-experiment"


def _ctx(paper_id: str, run_id: str, dry_run: bool = True) -> PaperContext:
    ctx = PaperContext(
        paper_id=paper_id,
        md_path=Path("dummy.md"),
        run_id=run_id,
        workflow_id=WF,
        dry_run=dry_run,
    )
    ctx.raw_md = "# title\nbody text."
    return ctx


def test_composed_wrapper_equals_build_plus_commit(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(post_llm, "RUNS_DIR", tmp_path)
    monkeypatch.setenv("PROD_SKIP_PAPER_MONITOR", "1")
    spec = get_workflow(WF)
    run_id = "char/job_batch_000"
    t0 = time.perf_counter()

    via_wrapper = finalize_paper(
        _ctx("paperA", run_id),
        spec,
        run_id=run_id,
        dry_run=True,
        waves_log=[{"wave": 2, "parallel": ["x"], "elapsed_sec": 0.01, "started_at": "t"}],
        overall_start=t0,
        error=None,
        pipeline_stages={"llm_elapsed_sec": 1.0},
    )
    fin = build_paper_finalization(
        _ctx("paperB", run_id),
        spec,
        run_id=run_id,
        dry_run=True,
        waves_log=[{"wave": 2, "parallel": ["x"], "elapsed_sec": 0.01, "started_at": "t"}],
        overall_start=t0,
        error=None,
        pipeline_stages={"llm_elapsed_sec": 1.0},
    )
    # build must NOT touch the filesystem
    assert not fin.pred_path.exists()
    via_split = commit_paper_finalization(fin)

    pa = json.loads(via_wrapper.prediction_path.read_text(encoding="utf-8"))
    pb = json.loads(via_split.prediction_path.read_text(encoding="utf-8"))
    assert pa["paper_id"] == "paperA" and pb["paper_id"] == "paperB"
    for key in (
        "workflow_id", "workflow_version", "run_id", "dry_run",
        "experiments", "provenance", "research_problem",
    ):
        assert pa[key] == pb[key], key
    assert via_wrapper.error == via_split.error is None
    assert via_split.prediction_path.name == "paperB.json"
    # monitor payload built identically (modulo ids)
    assert via_wrapper.monitor["waves"] == via_split.monitor["waves"]
    assert via_wrapper.monitor["pipeline_stages"] == via_split.monitor["pipeline_stages"]


def test_prediction_write_is_atomic_os_replace(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(post_llm, "RUNS_DIR", tmp_path)
    monkeypatch.setenv("PROD_SKIP_PAPER_MONITOR", "1")
    spec = get_workflow(WF)

    replaced: list[tuple[Path, Path]] = []
    real_replace = post_llm.os.replace
    monkeypatch.setattr(
        post_llm.os, "replace", lambda src, dst: (replaced.append((Path(src), Path(dst))), real_replace(src, dst))[1]
    )

    result = finalize_paper(
        _ctx("paperC", "char/job_batch_000"),
        spec,
        run_id="char/job_batch_000",
        dry_run=True,
        waves_log=[],
        overall_start=time.perf_counter(),
    )
    assert len(replaced) == 1
    src, dst = replaced[0]
    assert dst == result.prediction_path
    assert src.name == "paperC.json.tmp"
    assert not src.exists()  # no tmp residue after replace
    assert dst.exists()


def test_error_prediction_persists_marker_and_fails_prediction_ok(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(post_llm, "RUNS_DIR", tmp_path)
    monkeypatch.setattr(run_paths, "RUNS_DIR", tmp_path)
    monkeypatch.setenv("PROD_SKIP_PAPER_MONITOR", "1")
    spec = get_workflow(WF)

    fin = build_paper_finalization(
        _ctx("paperD", "char/job_batch_000"),
        spec,
        run_id="char/job_batch_000",
        dry_run=True,
        waves_log=[],
        overall_start=time.perf_counter(),
        error="bert_batch_failed: ConnectionError: refused",
    )
    result = commit_paper_finalization(fin)

    assert result.error == "bert_batch_failed: ConnectionError: refused"
    pred = json.loads(result.prediction_path.read_text(encoding="utf-8"))
    assert pred["error"] == "bert_batch_failed: ConnectionError: refused"
    assert pred["experiments"] == []
    assert run_paths.prediction_ok("char", "job_batch_000", "paperD") is False


def test_dry_run_skips_partials_and_history(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(post_llm, "RUNS_DIR", tmp_path)
    monkeypatch.setattr(monitor_mod, "RUN_HISTORY_PATH", tmp_path / "history.jsonl")
    monkeypatch.setattr(run_paths, "RUNS_DIR", tmp_path)
    import pipeline.production.config as config_mod

    monkeypatch.setattr(config_mod, "PARTIALS_DIR", tmp_path / "partials")
    monkeypatch.setenv("PROD_SKIP_PAPER_MONITOR", "1")
    spec = get_workflow(WF)

    ctx = _ctx("paperE", "char/job_batch_000", dry_run=True)
    ctx.set(FieldResult(extractor_id="llm.fake", version="1", status="ok", value={"a": 1}))
    commit_paper_finalization(
        build_paper_finalization(
            ctx, spec,
            run_id="char/job_batch_000", dry_run=True, waves_log=[],
            overall_start=time.perf_counter(),
        )
    )
    assert not (tmp_path / "history.jsonl").exists()
    assert not (tmp_path / "partials").exists()
    assert run_paths.prediction_ok("char", "job_batch_000", "paperE") is True


def test_non_dry_run_writes_partials_and_history(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(post_llm, "RUNS_DIR", tmp_path)
    monkeypatch.setattr(monitor_mod, "RUN_HISTORY_PATH", tmp_path / "history.jsonl")
    import pipeline.production.config as config_mod

    monkeypatch.setattr(config_mod, "PARTIALS_DIR", tmp_path / "partials")
    monkeypatch.setenv("PROD_SKIP_PAPER_MONITOR", "1")
    spec = get_workflow(WF)

    ctx = _ctx("paperF", "char/job_batch_000", dry_run=False)
    ctx.set(FieldResult(extractor_id="llm.fake", version="1", status="ok", value={"a": 1}))
    commit_paper_finalization(
        build_paper_finalization(
            ctx, spec,
            run_id="char/job_batch_000", dry_run=False, waves_log=[],
            overall_start=time.perf_counter(),
        )
    )
    partial = tmp_path / "partials" / "llm.fake" / "paperF.json"
    assert partial.is_file()
    payload = json.loads(partial.read_text(encoding="utf-8"))
    assert payload["paper_id"] == "paperF" and payload["value"] == {"a": 1}
    history_lines = (tmp_path / "history.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(history_lines) == 1
    row = json.loads(history_lines[0])
    assert row["paper_id"] == "paperF" and "ts" in row


def test_legacy_callers_still_use_composed_wrapper() -> None:
    """The legacy paths must keep finalizing through the composed wrapper
    (no staged-only build/commit usage outside the staged pipeline)."""
    wf4_src = (PROD_ROOT / "pipeline" / "production" / "batch_llm_common_wf4.py").read_text(
        encoding="utf-8"
    )
    sched_src = (
        PROD_ROOT / "pipeline" / "production" / "batch_bert_pipeline_wf4.py"
    ).read_text(encoding="utf-8")
    # process_llm_and_post_wf4 composes the split halves + immediate commit
    assert "commit_paper_finalization(fin)" in wf4_src
    assert "run_qwen_http_stage(" in wf4_src and "run_post_stage(" in wf4_src
    # the llm worker (legacy scheduling) still routes through the composed fn
    assert "process_llm_and_post_wf4(" in sched_src
    # base scheduler keeps inline error finalize (staged subclass overrides)
    assert "_fail_paper" in sched_src


def test_pipeline_started_at_passthrough_to_monitor(tmp_path: Path, monkeypatch) -> None:
    """P4: the new top-level field appears only when supplied (wf4 batch paths
    lift it from job.timings; wf8/legacy paths omit it unchanged)."""
    monkeypatch.setattr(post_llm, "RUNS_DIR", tmp_path)
    monkeypatch.setenv("PROD_SKIP_PAPER_MONITOR", "1")
    spec = get_workflow(WF)
    run_id = "char/job_batch_000"
    waves = [{"wave": 2, "parallel": ["x"], "elapsed_sec": 0.01, "started_at": "t"}]
    stamp = "2026-08-21T00:00:00+00:00"

    fin_with = build_paper_finalization(
        _ctx("paperC", run_id),
        spec,
        run_id=run_id,
        dry_run=True,
        waves_log=waves,
        overall_start=time.perf_counter(),
        pipeline_stages={"llm_elapsed_sec": 1.0},
        pipeline_started_at=stamp,
    )
    assert fin_with.monitor["pipeline_started_at"] == stamp

    fin_without = build_paper_finalization(
        _ctx("paperD", run_id),
        spec,
        run_id=run_id,
        dry_run=True,
        waves_log=waves,
        overall_start=time.perf_counter(),
        pipeline_stages={"llm_elapsed_sec": 1.0},
    )
    assert "pipeline_started_at" not in fin_without.monitor


def test_run_post_stage_lifts_pipeline_started_at(monkeypatch) -> None:
    """run_post_stage must lift the stamp from job.timings (set by
    _prep_paper) into the finalization build call."""
    from types import SimpleNamespace

    import pipeline.production.batch_llm_common_wf4 as wf4_common

    captured: dict = {}
    monkeypatch.setattr(
        wf4_common,
        "build_paper_finalization",
        lambda ctx, spec, **kw: captured.update(kw) or SimpleNamespace(sentinel=True),
    )
    stamp = "2026-08-21T00:00:00+00:00"
    job = SimpleNamespace(
        ctx=SimpleNamespace(partials={}),
        timings={"pipeline_started_at": stamp},
        paper_start_perf=time.perf_counter(),
        state=None,
    )
    spec = SimpleNamespace(
        waves=[["llm"]],  # spec.waves[1:] -> [] : no extractor execution needed
        tail=[],
        run_between_wave=lambda ctx, finished_wave: None,
    )
    wf4_common.run_post_stage(job, spec=spec, run_id="r", dry_run=True)
    assert captured["pipeline_started_at"] == stamp


if __name__ == "__main__":
    raise SystemExit("run via pytest")
