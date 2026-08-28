"""Online CSV -> manifest incremental ingest (v0.7 Phase 5, TODO-V07-06).

Safe manifest ingest for a running production line:

  new CSV
    -> read/validate (row order preserved, raw line numbers kept)
    -> classify rows: new / duplicate / invalid / retry / conflict
    -> publish NEW papers as job_batch_{next:03d}.json (tmp + json re-validate
       + os.replace, never touching existing batch files)
    -> append an ingest ledger entry + return a full report dict

Dedup identity (stable, explainable; see docs/V07_PHASE45_REPORT.md §7):
  - paper_id: exact string after whitespace strip
  - md_url:   strip + scheme/host lowercased + trailing slash removed;
              the query string IS part of the identity (conservative for OSS
              signed URLs — differing queries surface as conflicts, never
              silent merges)

Existing-task universe for duplicate detection:
  - every job_batch_*.json already in the target manifest dir
    (incl. previously published ingest batches — they use the same schema)
  - successful predictions under the given run ids (paper_id with a
    prediction file carrying no top-level ``error``)

Retry semantics: rows whose paper_id only has an *error* prediction are
classified ``retry`` and are re-queued ONLY when include_retry=True. Without
the flag they are counted in the report and skipped, matching the production
contract (same-run-id resume already retries error papers).

This module never modifies an existing manifest file and never writes outside
the manifest dir (+ its ingest_log.jsonl).
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.production.config import RUNS_DIR  # noqa: E402

JOB_BATCH_RE = re.compile(r"^job_batch_(\d+)\.json$")
LEDGER_NAME = "ingest_log.jsonl"

ID_COLUMNS = ("paper_id", "id", "publication_id")
ROW_STATUSES = ("new", "duplicate", "invalid", "retry", "conflict")


@dataclass
class IngestRow:
    """One CSV row with its classification outcome."""

    line_no: int  # 1-based raw CSV line number (header = line 1)
    paper_id: str | None = None
    publication_id: str | None = None
    md_url: str | None = None
    status: str = "new"  # one of ROW_STATUSES
    reason: str = ""
    matched_by: str = ""  # which key matched (paper_id / md_url)


@dataclass
class IngestReport:
    counts: dict = field(default_factory=lambda: {s: 0 for s in ROW_STATUSES})
    rows: list[IngestRow] = field(default_factory=list)
    published: list[str] = field(default_factory=list)  # batch file names
    ingest_id: str = ""
    ingest_sequence: int = 0
    csv_sha256: str = ""
    created_at: str = ""
    manifest_dir: str = ""

    def to_dict(self) -> dict:
        return {
            "ingest_id": self.ingest_id,
            "ingest_sequence": self.ingest_sequence,
            "manifest_dir": self.manifest_dir,
            "csv_sha256": self.csv_sha256,
            "created_at": self.created_at,
            "counts": dict(self.counts),
            "published_batches": list(self.published),
            "rows": [vars(r) for r in self.rows],
        }


def normalize_md_url(url: str) -> str:
    """Identity form of an md_url: strip, lowercase scheme+host, drop trailing /."""
    u = url.strip()
    try:
        parts = urlsplit(u)
    except ValueError:
        return u
    if not parts.scheme or not parts.netloc:
        return u
    host = parts.netloc.lower()
    path = parts.path.rstrip("/")
    return urlunsplit((parts.scheme.lower(), host, path, parts.query, parts.fragment))


def _is_valid_md_url(url: str) -> bool:
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    return bool(parts.scheme and parts.netloc and parts.scheme in ("http", "https"))


def read_csv_rows(csv_path: Path) -> list[IngestRow]:
    """Read the CSV preserving original row order and raw line numbers.

    Field contract: ``md_url`` required; at least one of paper_id/id/publication_id
    required (paper_id falls back to publication_id, mirroring the prepare
    script's paper_id == publication_id convention). Anything else stays on the
    row and is classified later — parsing itself never drops rows.
    """
    rows: list[IngestRow] = []
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for line_no, raw in enumerate(reader, start=2):  # header is line 1
            row = IngestRow(line_no=line_no)
            row.md_url = (raw.get("md_url") or "").strip() or None
            row.paper_id = (raw.get("paper_id") or "").strip() or None
            row.publication_id = (
                (raw.get("publication_id") or "").strip()
                or (raw.get("id") or "").strip()
                or row.paper_id
            )
            rows.append(row)
    return rows


def _key_maps_from_manifest_dir(manifest_dir: Path) -> tuple[dict[str, str], dict[str, str]]:
    """(paper_id -> md_url, normalized md_url -> paper_id) across all batches."""
    pids: dict[str, str] = {}
    urls: dict[str, str] = {}
    for bf in sorted(manifest_dir.glob("job_batch_*.json")):
        try:
            data = json.loads(bf.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — corrupt batch files are not ours to fix
            continue
        for item in data.get("papers") or []:
            pid = (item.get("paper_id") or "").strip()
            url = (item.get("md_url") or "").strip()
            if pid:
                pids.setdefault(pid, url)
            if url:
                urls.setdefault(normalize_md_url(url), pid)
    return pids, urls


def _prediction_states(run_ids: list[str]) -> dict[str, str]:
    """paper_id -> 'ok' | 'error' from prediction files under the given runs."""
    states: dict[str, str] = {}
    for run_id in run_ids:
        session_dir = RUNS_DIR / run_id
        if not session_dir.is_dir():
            continue
        for pred_path in session_dir.glob("*/predictions/*.json"):
            pid = pred_path.stem
            try:
                pred = json.loads(pred_path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                states.setdefault(pid, "error")  # corrupt file -> retryable
                continue
            states[pid] = "error" if pred.get("error") else "ok"
    return states


def classify_rows(
    rows: list[IngestRow],
    *,
    manifest_dir: Path,
    run_ids: list[str] | None = None,
    include_retry: bool = False,
) -> list[IngestRow]:
    """Classify every row in place (new/duplicate/invalid/retry/conflict)."""
    known_pids, known_urls = _key_maps_from_manifest_dir(manifest_dir)
    pred_states = _prediction_states(run_ids or [])

    seen_pids: dict[str, str] = {}  # pid -> md_url (first occurrence in this CSV)
    seen_urls: dict[str, str] = {}  # norm url -> pid

    for row in rows:
        pid = row.paper_id or row.publication_id
        # --- invalid ---
        if not row.md_url:
            row.status, row.reason = "invalid", "missing md_url"
            continue
        if not pid:
            row.status, row.reason = "invalid", "missing paper_id/id/publication_id"
            continue
        if not _is_valid_md_url(row.md_url):
            row.status, row.reason = "invalid", f"md_url has no http(s) scheme: {row.md_url[:80]}"
            continue
        row.paper_id = pid  # resolved id becomes the task paper_id
        norm = normalize_md_url(row.md_url)

        # --- conflict: same id pointing at a different url, or url already
        #     owned by a different id (never silently pick a winner) ---
        if pid in known_pids and known_pids[pid] and normalize_md_url(known_pids[pid]) != norm:
            row.status = "conflict"
            row.reason = f"paper_id already mapped to different md_url (manifest)"
            row.matched_by = "paper_id"
            continue
        if norm in known_urls and known_urls[norm] and known_urls[norm] != pid:
            row.status = "conflict"
            row.reason = "md_url already mapped to different paper_id (manifest)"
            row.matched_by = "md_url"
            continue
        if pid in seen_pids and seen_pids[pid] and normalize_md_url(seen_pids[pid]) != norm:
            row.status = "conflict"
            row.reason = "paper_id appears twice in this CSV with different md_url"
            row.matched_by = "paper_id"
            continue
        if norm in seen_urls and seen_urls[norm] and seen_urls[norm] != pid:
            row.status = "conflict"
            row.reason = "md_url appears twice in this CSV with different paper_id"
            row.matched_by = "md_url"
            continue

        # --- duplicate: id or url already known (manifest / prior ingest /
        #     successful prediction / earlier row in this CSV) ---
        dup_src = ""
        if pid in known_pids:
            dup_src = "manifest"
        elif norm in known_urls:
            dup_src, row.matched_by = "manifest", "md_url"
        elif pred_states.get(pid) == "ok":
            dup_src = "success_prediction"
        elif pid in seen_pids or norm in seen_urls:
            dup_src = "csv"
        if dup_src:
            row.status, row.reason = "duplicate", f"already present ({dup_src})"
            if not row.matched_by:
                row.matched_by = "paper_id" if pid in known_pids or pid in seen_pids else "md_url"
            seen_pids.setdefault(pid, row.md_url)
            seen_urls.setdefault(norm, pid)
            continue

        # --- retry: only an error prediction exists ---
        if pred_states.get(pid) == "error":
            if include_retry:
                row.status, row.reason = "retry", "error prediction re-queued (--include-retry)"
            else:
                row.status, row.reason = "retry", "error prediction present; pass --include-retry to re-queue"
                seen_pids.setdefault(pid, row.md_url)
                seen_urls.setdefault(norm, pid)
                continue
        else:
            row.status = "new"

        # this row enters (or re-enters) the queue — remember it for later rows
        # (seen_* only, so later internal dups report "csv", not "manifest")
        seen_pids.setdefault(pid, row.md_url)
        seen_urls.setdefault(norm, pid)

    return rows


def next_batch_index(manifest_dir: Path) -> int:
    """One past the highest existing numeric job_batch index (never reused)."""
    highest = -1
    for f in manifest_dir.glob("job_batch_*.json"):
        m = JOB_BATCH_RE.match(f.name)
        if m:
            highest = max(highest, int(m.group(1)))
    return highest + 1


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _write_json_atomic(path: Path, payload: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        json.loads(tmp.read_text(encoding="utf-8"))  # read-back validation
        os.replace(tmp, path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def _ledger_count(manifest_dir: Path) -> int:
    ledger = manifest_dir / LEDGER_NAME
    if not ledger.exists():
        return 0
    return sum(1 for line in ledger.read_text(encoding="utf-8").splitlines() if line.strip())


def ingest_csv(
    csv_path: Path,
    manifest_dir: Path,
    *,
    run_ids: list[str] | None = None,
    include_retry: bool = False,
    size: int = 500,
    source_name: str | None = None,
) -> IngestReport:
    """Full ingest pipeline. Returns the report; raises on IO/validation errors."""
    manifest_dir.mkdir(parents=True, exist_ok=True)
    rows = read_csv_rows(csv_path)
    rows = classify_rows(rows, manifest_dir=manifest_dir, run_ids=run_ids, include_retry=include_retry)

    queued = [r for r in rows if r.status == "new" or (r.status == "retry" and include_retry)]
    report = IngestReport(
        rows=rows,
        csv_sha256=_sha256_file(csv_path),
        ingest_sequence=_ledger_count(manifest_dir) + 1,
        ingest_id=f"ingest-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{report_seq(manifest_dir)}",
        created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        manifest_dir=str(manifest_dir),
    )
    for r in rows:
        report.counts[r.status] += 1

    if queued:
        start = next_batch_index(manifest_dir)
        for i in range(0, len(queued), size):
            chunk = queued[i : i + size]
            idx = start + i // size
            batch_id = f"job_batch_{idx:03d}"
            payload = {
                "job_batch_id": batch_id,
                "batch_index": idx,
                "size": len(chunk),
                "machine": None,
                "machine_index": None,
                "machine_count": None,
                "papers": [{"paper_id": r.paper_id, "md_url": r.md_url} for r in chunk],
                "ingest": {
                    "source_name": source_name or Path(csv_path).name,
                    "ingest_id": report.ingest_id,
                    "ingest_sequence": report.ingest_sequence,
                    "csv_sha256": report.csv_sha256,
                    "row_count": len(rows),
                    "new_count": report.counts["new"],
                    "duplicate_count": report.counts["duplicate"],
                    "invalid_count": report.counts["invalid"],
                    "retry_count": report.counts["retry"],
                    "conflict_count": report.counts["conflict"],
                    "created_at": report.created_at,
                },
            }
            out = manifest_dir / f"{batch_id}.json"
            if out.exists():  # never overwrite an existing batch
                raise RuntimeError(f"refusing to overwrite existing manifest batch {out}")
            _write_json_atomic(out, payload)
            report.published.append(out.name)

    ledger = manifest_dir / LEDGER_NAME
    with open(ledger, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(report.to_dict(), ensure_ascii=False) + "\n")
    return report


def report_seq(manifest_dir: Path) -> str:
    """Short discriminator so ingest ids stay unique within the same second."""
    return f"{_ledger_count(manifest_dir) + 1:03d}"
