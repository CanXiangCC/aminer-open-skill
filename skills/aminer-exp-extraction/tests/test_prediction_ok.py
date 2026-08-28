"""Failed predictions persist an error marker and resume logic retries them."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

PROD_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROD_ROOT))

import pipeline.production.post_llm as post_llm  # noqa: E402
import pipeline.production.run_paths as run_paths  # noqa: E402
from pipeline.production.context import PaperContext  # noqa: E402
from pipeline.production.workflows.spec import get_workflow  # noqa: E402


def _write_pred(tmp_path: Path, paper_id: str, payload) -> Path:
    pred_dir = tmp_path / "sess" / "job_batch_000" / "predictions"
    pred_dir.mkdir(parents=True, exist_ok=True)
    p = pred_dir / f"{paper_id}.json"
    if isinstance(payload, str):
        p.write_text(payload, encoding="utf-8")
    else:
        p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def test_prediction_ok_states(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(run_paths, "RUNS_DIR", tmp_path)
    ok = lambda pid: run_paths.prediction_ok("sess", "job_batch_000", pid)  # noqa: E731

    # Missing / empty / corrupt files -> retry.
    assert ok("missing") is False
    _write_pred(tmp_path, "empty", "")
    assert ok("empty") is False
    _write_pred(tmp_path, "corrupt", "{not json")
    assert ok("corrupt") is False

    # New-format failed prediction (error persisted by finalize_paper) -> retry.
    _write_pred(tmp_path, "failed", {"paper_id": "failed", "experiments": [], "error": "llm_timeout"})
    assert ok("failed") is False

    # Completed predictions -> skip (including EXT-02 empty-experiments).
    _write_pred(tmp_path, "done", {"paper_id": "done", "experiments": [{"experiment_name": "E"}]})
    assert ok("done") is True
    _write_pred(tmp_path, "done_empty", {"paper_id": "done_empty", "experiments": []})
    assert ok("done_empty") is True


def test_finalize_paper_persists_error(tmp_path: Path, monkeypatch) -> None:
    """Errored papers land a top-level `error` field in the prediction JSON."""
    monkeypatch.setattr(post_llm, "RUNS_DIR", tmp_path)
    monkeypatch.setenv("PROD_SKIP_PAPER_MONITOR", "1")

    ctx = PaperContext(
        paper_id="paperX",
        md_path=Path("dummy.md"),
        run_id="sess/job_batch_000",
        workflow_id="prod-wf4-llm-datasets-experiment",
        dry_run=True,
    )
    spec = get_workflow("prod-wf4-llm-datasets-experiment")

    result = post_llm.finalize_paper(
        ctx,
        spec,
        run_id="sess/job_batch_000",
        dry_run=True,
        waves_log=[],
        overall_start=time.perf_counter(),
        error="bert_batch_failed: connection refused",
    )

    assert result.error == "bert_batch_failed: connection refused"
    pred = json.loads(result.prediction_path.read_text(encoding="utf-8"))
    assert pred["error"] == "bert_batch_failed: connection refused"
    assert pred["experiments"] == []

    # And the persisted marker flips prediction_ok to False (resume retries it).
    monkeypatch.setattr(run_paths, "RUNS_DIR", tmp_path)
    assert run_paths.prediction_ok("sess", "job_batch_000", "paperX") is False


if __name__ == "__main__":
    raise SystemExit("run via pytest")
