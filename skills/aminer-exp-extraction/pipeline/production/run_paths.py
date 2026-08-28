"""Centralized run output path helpers for bulk production.

Layout (new):
  runs/{session_run_id}/bulk_session.json
  runs/{session_run_id}/{job_batch_id}/predictions/...

Legacy flat layout (pre-nested):
  runs/prod-bulk-YYYYMMDD-jobNNN/predictions/...
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from pipeline.production.config import RUNS_DIR

LEGACY_FLAT_RUN_RE = re.compile(r"^prod-bulk-\d{8}-job\d+$")
JOB_BATCH_DIR_RE = re.compile(r"^job_batch_\d+$|^job_batch_smoke$")


def session_run_dir(session_run_id: str) -> Path:
    """Top-level session directory under runs/."""
    return RUNS_DIR / session_run_id


def job_batch_run_dir(session_run_id: str, job_batch_id: str) -> Path:
    """Per job_batch output directory nested under a session run."""
    return RUNS_DIR / session_run_id / job_batch_id


def format_job_run_id(session_run_id: str, job_batch_id: str) -> str:
    """Logical run_id stored in prediction JSON metadata."""
    return f"{session_run_id}/{job_batch_id}"


def export_tag_from_run_id(run_id: str) -> str:
    """Filesystem-safe export filename tag from a logical run_id."""
    return run_id.replace("/", "_")


def is_legacy_flat_run_dir(name: str) -> bool:
    """True if name matches the old flat prod-bulk-*-job* top-level run dir."""
    return bool(LEGACY_FLAT_RUN_RE.match(name))


def is_job_batch_dir(name: str) -> bool:
    """True if name is a job_batch subfolder under a session run."""
    return bool(JOB_BATCH_DIR_RE.match(name))


def resolve_run_dir(run_id: str, run_dir: Path | None = None) -> Path:
    """Resolve the filesystem run directory for writers/monitors."""
    if run_dir is not None:
        return run_dir
    if is_legacy_flat_run_dir(run_id):
        return RUNS_DIR / run_id
    if "/" in run_id:
        session, jb = run_id.split("/", 1)
        return job_batch_run_dir(session, jb)
    return RUNS_DIR / run_id


def prediction_ok(session_run_id: str, job_batch_id: str, paper_id: str) -> bool:
    """True when a completed, non-errored prediction exists on disk.

    Errored predictions carry a top-level ``error`` field (written by
    ``post_llm.finalize_paper``) and must be re-run on resume. Legacy files
    written before that field existed keep the old semantics: absent/corrupt
    file -> retry; present without ``error`` -> ok (EXT-02: empty experiments
    is a valid ok outcome, so experiment count is NOT used here).

    TODO-V07-11 ledger fallback: when the file is absent/unreadable (the
    normal state after compaction deleted it), the session completion
    ledger's LAST row decides — ok -> skip, error/missing -> retry. A file
    that exists and parses is always authoritative, including its error
    marker (an errored file is never overridden by an older ok row).
    """
    path = job_batch_run_dir(session_run_id, job_batch_id) / "predictions" / f"{paper_id}.json"
    if path.exists() and path.stat().st_size != 0:
        try:
            pred = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return _ledger_ok_fallback(session_run_id, paper_id)
        return not pred.get("error")
    return _ledger_ok_fallback(session_run_id, paper_id)


def _ledger_ok_fallback(session_run_id: str, paper_id: str) -> bool:
    from pipeline.production.completion_ledger import ledger_ok

    try:
        return ledger_ok(session_run_id, paper_id)
    except Exception:  # noqa: BLE001
        return False
