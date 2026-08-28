"""Per-session completion ledger (TODO-V07-11) — append-only jsonl.

One row per durable prediction commit, appended by
``post_llm.commit_paper_finalization`` immediately AFTER the prediction file
is atomically published. The order is **file-first-then-ledger**: a crash
between the two leaves a file without a ledger row, which is safe (resume
trusts the file; compaction backfills missing rows before deleting). The
reverse order could mark a paper done whose file was never written.

Purposes:
  1. resume fallback — ``run_paths.prediction_ok`` treats "file missing but
     last ledger row ok" as done; this is what makes prediction-file
     compaction (deletion) safe for same-run-id resumes.
  2. compaction reconciliation — before deleting per-paper files, missing
     rows are backfilled from files so a paper is never "deleted but
     unrecorded".

Row shape (one json line; last row per paper_id wins):

  {ts, session_run_id, job_batch_id, run_id, paper_id,
   status: "ok"|"error", error_class?, experiments,
   prediction_sha256, workflow_version}

Legacy runs without a ledger keep working: the file alone stays
authoritative. Appends are thread-safe (window mode commits from multiple
llm workers) and best-effort at the call site — a failed append never
fails the paper commit.
"""

from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pipeline.production import run_paths

LEDGER_NAME = "ledger.jsonl"

_append_lock = threading.Lock()
_cache_lock = threading.Lock()
# ledger path -> (mtime_ns, size, {paper_id: last_status}); mtime+size key
# avoids re-reading the whole ledger on every prediction_ok fallback probe.
_index_cache: dict[Path, tuple[int, int, dict[str, str]]] = {}


def ledger_path(session_run_id: str) -> Path:
    return run_paths.RUNS_DIR / session_run_id / LEDGER_NAME


def split_run_id(run_id: str) -> tuple[str, str | None]:
    """"sess/job_batch_000" -> ("sess", "job_batch_000"); legacy flat -> (run_id, None)."""
    if "/" in run_id:
        session, jb = run_id.split("/", 1)
        return session, jb
    return run_id, None


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def append_row(
    session_run_id: str,
    job_batch_id: str | None,
    run_id: str,
    paper_id: str,
    status: str,
    *,
    error_class: str | None = None,
    experiments: int = 0,
    prediction_payload: str | None = None,
    workflow_version: Any = None,
) -> dict[str, Any]:
    """Append one completion row; returns the row as written."""
    row: dict[str, Any] = {
        "ts": utc_now(),
        "session_run_id": session_run_id,
        "job_batch_id": job_batch_id,
        "run_id": run_id,
        "paper_id": paper_id,
        "status": status,
    }
    if error_class is not None:
        row["error_class"] = error_class
    row["experiments"] = experiments
    if prediction_payload is not None:
        row["prediction_sha256"] = hashlib.sha256(
            prediction_payload.encode("utf-8")
        ).hexdigest()
    row["workflow_version"] = workflow_version

    path = ledger_path(session_run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(row, ensure_ascii=False) + "\n"
    with _append_lock:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line)
    return row


def read_rows(session_run_id: str) -> list[dict[str, Any]]:
    """All valid rows, in order; a corrupt/partial tail line is skipped."""
    path = ledger_path(session_run_id)
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:  # noqa: BLE001
            continue
    return rows


def last_status_index(session_run_id: str) -> dict[str, str]:
    """paper_id -> last status, cached on (mtime_ns, size) of the ledger."""
    path = ledger_path(session_run_id)
    try:
        st = path.stat()
        key = (st.st_mtime_ns, st.st_size)
    except OSError:
        with _cache_lock:
            _index_cache.pop(path, None)
        return {}
    with _cache_lock:
        cached = _index_cache.get(path)
        if cached is not None and (cached[0], cached[1]) == key:
            return dict(cached[2])
    index: dict[str, str] = {}
    for row in read_rows(session_run_id):
        pid = row.get("paper_id")
        status = row.get("status")
        if isinstance(pid, str) and isinstance(status, str):
            index[pid] = status
    with _cache_lock:
        _index_cache[path] = (*key, index)
    return dict(index)


def ledger_ok(session_run_id: str, paper_id: str) -> bool:
    """True iff the paper's LAST ledger row is status=="ok"."""
    return last_status_index(session_run_id).get(paper_id) == "ok"


def reset_cache() -> None:
    """Test helper — drop the stat-keyed index cache."""
    with _cache_lock:
        _index_cache.clear()
