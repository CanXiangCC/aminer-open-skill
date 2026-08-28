#!/usr/bin/env python3
"""Manual / offline compaction CLI (TODO-V07-11).

Compacts a session run NOW regardless of ``compaction_every_n_papers``
(the run_bulk hook stays threshold-gated). Same state machine and safety
invariant as the batch-boundary hook: merge into an audit window ->
dual verify -> publish stable flat -> only then delete sources.

Usage:
    python scripts/compact_run.py --session-run-id prod-bulk-20260821
    python scripts/compact_run.py --session-run-id X --dry-run   # report only
    python scripts/compact_run.py --session-run-id X --runs-dir /backup/runs

Exit 0 = compacted (or dry-run / nothing to do); 2 = verification failed
(originals kept).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROD_ROOT = Path(__file__).resolve().parents[1]
if str(PROD_ROOT) not in sys.path:
    sys.path.insert(0, str(PROD_ROOT))

from pipeline.production import compaction  # noqa: E402
from pipeline.production import run_paths  # noqa: E402


def _dry_run(session_run_id: str) -> int:
    papers = compaction.select_papers(session_run_id)
    registered = compaction.registered_paper_count(session_run_id)
    if not papers:
        print(f"{session_run_id}: nothing to compact "
              f"(on-disk=0, already-compacted={registered})")
        return 0
    batches: dict[str, int] = {}
    bytes_on_disk = 0
    for p in papers:
        batches[p.job_batch_id] = batches.get(p.job_batch_id, 0) + 1
        try:
            bytes_on_disk += p.pred_path.stat().st_size
        except OSError:
            pass
    stable = compaction.stable_flat_path(session_run_id)
    print(f"{session_run_id} DRY-RUN:")
    print(f"  would compact {len(papers)} papers across {len(batches)} batch(es): "
          + ", ".join(f"{k}={v}" for k, v in sorted(batches.items())))
    print(f"  prediction bytes on disk: {bytes_on_disk / 1024:.1f} KiB")
    print(f"  already-compacted papers: {registered}")
    print(f"  stable flat: {stable}"
          + (" (exists)" if stable.exists() else " (would be created)"))
    print("  no files written, nothing deleted")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--session-run-id", action="append", required=True,
                    help="runs/<session-run-id> to compact (repeatable)")
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would be compacted; zero writes")
    ap.add_argument("--runs-dir", type=Path, default=None,
                    help="override runs root (offline operations on a copy)")
    args = ap.parse_args()

    if args.runs_dir is not None:
        run_paths.RUNS_DIR = args.runs_dir

    for session_run_id in args.session_run_id:
        if args.dry_run:
            rc = _dry_run(session_run_id)
            if rc:
                return rc
            continue
        result = compaction.maybe_compact(session_run_id, 0, force=True)
        if result is None:
            print(f"{session_run_id}: nothing to compact (no on-disk predictions)")
        elif result.get("status") == "error":
            print(f"{session_run_id}: COMPACTION FAILED: {result.get('reason')}",
                  file=sys.stderr)
            return 2
        else:
            print(f"{session_run_id}: {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
