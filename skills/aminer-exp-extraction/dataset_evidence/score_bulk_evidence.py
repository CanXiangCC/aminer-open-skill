#!/usr/bin/env python3
"""Add MSWR evidence to bulk pipeline predictions.

Post-processes existing prediction JSON files to add evidence fields
without re-running the extraction pipeline.

Usage:
    cd ai2000_bulk_pipeline
    python -m dataset_evidence.score_bulk_evidence \\
        --session-run-id prod-bulk-20260717 \\
        [--job-batch job_batch_000] \\
        [--concurrency 8] \\
        [--retries 3] \\
        [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from pipeline.evaluation.md_resolver import ensure_cached
from pipeline.production.adapters.rule_pack import PackImportError, get_evidence_v4
from pipeline.production.run_paths import (
    format_job_run_id,
    is_job_batch_dir,
    is_legacy_flat_run_dir,
    job_batch_run_dir,
)
from pipeline.production.schema import LLM_FIELDS

# Project root paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
MANIFESTS_DIR = PROJECT_ROOT / "manifests" / "job_batches"
PREDICTIONS_BASE = PROJECT_ROOT / "pipeline_output" / "production" / "runs"
MD_CACHE_DIR = PROJECT_ROOT / "pipeline_output" / "md_cache"
PROGRESS_EVERY = 50


def _extract_job_batch_id(run_id: str) -> str:
    """Extract job batch ID from legacy flat run_id (prod-bulk-YYYYMMDD-jobNNN)."""
    match = re.search(r"job(\d+)$", run_id)
    if not match:
        raise ValueError(f"Cannot extract job batch ID from run_id: {run_id}")
    job_num = match.group(1).zfill(3)
    return f"job_batch_{job_num}"


def _resolve_run_targets(
    *,
    run_id: str | None = None,
    session_run_id: str | None = None,
    job_batch: str | None = None,
) -> list[dict[str, Any]]:
    """Resolve one or more run targets to filesystem paths.

    Supports:
      - Legacy: --run-id prod-bulk-20260717-job000
      - Nested: --session-run-id prod-bulk-20260717 --job-batch job_batch_000
      - Nested (all batches): --session-run-id prod-bulk-20260717
    """
    targets: list[dict[str, Any]] = []

    if run_id:
        if is_legacy_flat_run_dir(run_id):
            job_batch_id = _extract_job_batch_id(run_id)
            targets.append({
                "logical_run_id": run_id,
                "job_batch_id": job_batch_id,
                "run_dir": PREDICTIONS_BASE / run_id,
                "predictions_dir": PREDICTIONS_BASE / run_id / "predictions",
            })
            return targets
        if "/" in run_id:
            session, jb = run_id.split("/", 1)
            targets.append({
                "logical_run_id": run_id,
                "job_batch_id": jb,
                "run_dir": job_batch_run_dir(session, jb),
                "predictions_dir": job_batch_run_dir(session, jb) / "predictions",
            })
            return targets

    if not session_run_id:
        raise ValueError("Provide --run-id or --session-run-id")

    session_dir = PREDICTIONS_BASE / session_run_id
    if not session_dir.is_dir():
        raise FileNotFoundError(f"Session run directory not found: {session_dir}")

    if job_batch:
        targets.append({
            "logical_run_id": format_job_run_id(session_run_id, job_batch),
            "job_batch_id": job_batch,
            "run_dir": job_batch_run_dir(session_run_id, job_batch),
            "predictions_dir": job_batch_run_dir(session_run_id, job_batch) / "predictions",
        })
        return targets

    for jb_dir in sorted(session_dir.iterdir()):
        if jb_dir.is_dir() and is_job_batch_dir(jb_dir.name):
            targets.append({
                "logical_run_id": format_job_run_id(session_run_id, jb_dir.name),
                "job_batch_id": jb_dir.name,
                "run_dir": jb_dir,
                "predictions_dir": jb_dir / "predictions",
            })
    if not targets:
        raise FileNotFoundError(
            f"No job_batch_* directories under session run: {session_dir}"
        )
    return targets


def _load_manifest(manifests_dir: Path, job_batch_id: str) -> dict[str, str]:
    """Load manifest and build paper_id -> md_url mapping.

    Args:
        manifests_dir: Directory containing job_batch_*.json files
        job_batch_id: e.g., "job_batch_000"

    Returns:
        {paper_id: md_url, ...}
    """
    manifest_path = manifests_dir / f"{job_batch_id}.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")

    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    papers = data.get("papers", [])
    return {p["paper_id"]: p["md_url"] for p in papers}


def _ensure_md_cache(
    papers: list[str],
    manifest: dict[str, str],
    cache_dir: Path,
    concurrency: int,
    retries: int,
) -> tuple[dict[str, Path], dict[str, str]]:
    """Ensure MD files are cached, downloading missing ones.

    Args:
        papers: List of paper_ids
        manifest: {paper_id: md_url, ...}
        cache_dir: MD cache directory
        concurrency: Thread pool size
        retries: Download retry attempts

    Returns:
        (md_paths: {paper_id: path, ...}, errors: {paper_id: error, ...})
    """
    md_paths: dict[str, Path] = {}
    errors: dict[str, str] = {}

    def fetch_one(paper_id: str) -> tuple[str, Path | None, str | None]:
        """Fetch MD for a single paper."""
        md_url = manifest.get(paper_id, "")
        if not md_url:
            return paper_id, None, "no_md_url_in_manifest"

        for attempt in range(max(1, retries)):
            try:
                path, err = ensure_cached(paper_id, md_url, cache_dir)
                if path and path.exists() and path.stat().st_size > 0:
                    return paper_id, path, None
                if err:
                    last_err = err
            except Exception as exc:
                last_err = f"{type(exc).__name__}: {exc}"
            if attempt < retries - 1:
                time.sleep(min(2**attempt, 8))

        return paper_id, None, last_err or "md_fetch_failed"

    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as executor:
        futures = [executor.submit(fetch_one, pid) for pid in papers]
        for future in as_completed(futures):
            paper_id, path, err = future.result()
            if path:
                md_paths[paper_id] = path
            elif err:
                errors[paper_id] = err

    return md_paths, errors


def _build_experiments_stripped(experiments: list[dict]) -> list[dict]:
    """Build experiments_stripped from full experiments (7 LLM fields)."""
    return [{f: exp.get(f) for f in LLM_FIELDS} for exp in experiments]


def _write_prediction_atomic(pred_path: Path, prediction: dict) -> None:
    """Write prediction JSON atomically (same pattern as post_llm.py)."""
    payload = json.dumps(prediction, indent=2, ensure_ascii=False, default=str)
    tmp_path = pred_path.with_suffix(pred_path.suffix + ".tmp")
    tmp_path.write_text(payload, encoding="utf-8")
    os.replace(tmp_path, pred_path)


def _score_prediction(
    prediction: dict,
    md_path: Path,
    EvidenceRuleV4: type,
    force: bool,
) -> tuple[dict, dict]:
    """Extract evidence for a prediction.

    Args:
        prediction: Prediction dict with experiments
        md_path: Path to MD file
        EvidenceRuleV4: The evidence rule class
        force: Force overwrite existing non-empty evidence

    Returns:
        (modified_prediction, status_dict) where status_dict has:
        - success: bool
        - error: str | None
        - evidence_count: int (total evidence sentences across ALL experiments)
    """
    raw_md = md_path.read_text(encoding="utf-8")
    experiments = prediction.get("experiments", [])

    if not experiments:
        return prediction, {"success": False, "error": "no_experiments", "evidence_count": 0}

    # Skip only when EVERY experiment already has non-empty evidence.
    if not force and all(exp.get("evidence") for exp in experiments):
        return prediction, {
            "success": True,
            "error": None,
            "evidence_count": sum(len(exp.get("evidence", [])) for exp in experiments),
            "skipped": True,
        }

    # Build experiments_stripped (7 LLM fields only)
    experiments_stripped = _build_experiments_stripped(experiments)

    # Extract evidence
    try:
        results = EvidenceRuleV4.extract_for_paper(
            raw_md,
            experiments_stripped,
            input_mode="full_text",
        )
    except Exception as exc:
        return prediction, {
            "success": False,
            "error": f"{type(exc).__name__}: {exc}",
            "evidence_count": 0,
        }

    # results[i]["evidence"] maps 1:1 to experiments[i] (extractor preserves
    # input order); write back per experiment instead of only experiments[0].
    for i, exp in enumerate(experiments):
        if results and i < len(results) and isinstance(results[i], dict):
            exp["evidence"] = results[i].get("evidence", [])
        else:
            exp["evidence"] = []

    return prediction, {
        "success": True,
        "error": None,
        "evidence_count": sum(len(exp.get("evidence", [])) for exp in experiments),
    }


def _score_one_prediction_file(
    pred_file: Path,
    md_path: Path,
    EvidenceRuleV4: type,
    *,
    force: bool,
    dry_run: bool,
) -> tuple[str, dict[str, Any]]:
    """Score one prediction file; returns (paper_id, outcome dict for stats merge)."""
    paper_id = pred_file.stem
    try:
        pred = json.loads(pred_file.read_text(encoding="utf-8"))
        scored, status = _score_prediction(pred, md_path, EvidenceRuleV4, force)

        outcome: dict[str, Any] = {"paper_id": paper_id, **status}

        if status.get("skipped"):
            outcome["action"] = "skipped"
        elif status.get("success"):
            outcome["action"] = "processed"
            if not dry_run:
                _write_prediction_atomic(pred_file, scored)
        else:
            outcome["action"] = "failed"
            outcome["error"] = status.get("error", "unknown")

        return paper_id, outcome
    except Exception as exc:
        return paper_id, {
            "paper_id": paper_id,
            "action": "failed",
            "success": False,
            "error": f"{type(exc).__name__}: {exc}",
            "evidence_count": 0,
        }


def _merge_outcome(stats: dict[str, Any], outcome: dict[str, Any]) -> None:
    """Apply one worker outcome into run stats."""
    action = outcome.get("action")
    count = int(outcome.get("evidence_count", 0) or 0)
    paper_id = outcome["paper_id"]

    if action == "skipped":
        stats["skipped"] += 1
        if count > 0:
            stats["papers_with_evidence"] += 1
        stats["total_evidence_count"] += count
    elif action == "processed":
        stats["processed"] += 1
        stats["total_evidence_count"] += count
        if count > 0:
            stats["papers_with_evidence"] += 1
    else:
        stats["failed"] += 1
        stats["failures"][paper_id] = outcome.get("error", "unknown")


def _generate_report(stats: dict) -> str:
    """Generate evidence report in markdown.

    Args:
        stats: Statistics dict from _process_run

    Returns:
        Markdown report string
    """
    lines = [
        "# Evidence Report",
        "",
        "## Processing Statistics",
        f"- Total papers: {stats['total_papers']}",
        f"- Processed (success): {stats['processed']}",
        f"- Skipped (existing evidence): {stats['skipped']}",
        f"- Failed: {stats['failed']}",
        f"- Papers with evidence: {stats['papers_with_evidence']}",
        f"- Total evidence items: {stats['total_evidence_count']}",
        "",
    ]

    if stats['processed'] > 0:
        lines.extend([
            "## Evidence Distribution",
            f"- Avg evidence per paper: {stats['avg_evidence']:.2f}",
            f"- Non-empty evidence: {stats['papers_with_evidence']}/{stats['processed']} "
            f"({stats['pct_with_evidence']:.1f}%)",
            "",
        ])

    if stats["md_cache_hits"]:
        lines.extend([
            "## MD Cache",
            f"- Cache hits: {stats['md_cache_hits']}",
            f"- Downloads: {stats['md_downloads']}",
            f"- Download failures: {stats['md_failures']}",
            "",
        ])

    if stats["failures"]:
        lines.extend([
            "## Failures",
            "",
            f"Failed to process {len(stats['failures'])} papers.",
        ])
        for pid, err in list(stats["failures"].items())[:50]:
            lines.append(f"- {pid}: {err}")
        if len(stats["failures"]) > 50:
            lines.append(f"... and {len(stats['failures']) - 50} more")
        lines.append("")

    return "\n".join(lines)


def _process_run(
    target: dict[str, Any],
    concurrency: int,
    retries: int,
    dry_run: bool,
    force: bool,
    manifests_dir: Path | None = None,
) -> dict[str, Any]:
    """Process a single job-batch run target.

    manifests_dir: directory holding this run's job_batch_*.json. Defaults to
    the legacy ``manifests/job_batches`` layout (TODO-EV-02); per-corpus
    layouts (``manifests/<corpus>/``) must pass their own directory.
    """
    logical_run_id = target["logical_run_id"]
    job_batch_id = target["job_batch_id"]
    predictions_dir: Path = target["predictions_dir"]
    run_dir: Path = target["run_dir"]
    if manifests_dir is None:
        manifests_dir = MANIFESTS_DIR

    print(f"\n{'='*60}")
    print(f"Processing run: {logical_run_id}")
    print(f"{'='*60}")
    print(f"Job batch ID: {job_batch_id}")

    manifest = _load_manifest(manifests_dir, job_batch_id)
    print(f"Manifest loaded: {len(manifest)} papers")

    if not predictions_dir.exists():
        print(f"ERROR: Predictions directory not found: {predictions_dir}")
        return {"run_id": logical_run_id, "error": "predictions_dir_not_found"}

    # Scan prediction files
    prediction_files = list(predictions_dir.glob("*.json"))
    paper_ids = [f.stem for f in prediction_files]
    print(f"Found {len(paper_ids)} prediction files")

    if not paper_ids:
        print("WARNING: No prediction files found")
        return {"run_id": logical_run_id, "error": "no_predictions"}

    # Check MD cache
    existing_md = [pid for pid in paper_ids if (MD_CACHE_DIR / f"{pid}.md").exists()]
    missing_md = [pid for pid in paper_ids if pid not in existing_md]

    print(f"MD cache hits: {len(existing_md)}")
    print(f"MD cache misses: {len(missing_md)}")

    stats = {
        "run_id": logical_run_id,
        "total_papers": len(paper_ids),
        "processed": 0,
        "skipped": 0,
        "failed": 0,
        "papers_with_evidence": 0,
        "total_evidence_count": 0,
        "avg_evidence": 0.0,
        "pct_with_evidence": 0.0,
        "md_cache_hits": len(existing_md),
        "md_downloads": 0,
        "md_failures": 0,
        "failures": {},
    }

    # Download missing MD files
    md_paths: dict[str, Path] = {}
    if missing_md and not dry_run:
        print(f"Downloading {len(missing_md)} missing MD files...")
        downloaded, errors = _ensure_md_cache(missing_md, manifest, MD_CACHE_DIR, concurrency, retries)

        stats["md_downloads"] = len(downloaded)
        stats["md_failures"] = len(errors)
        stats["failures"].update(errors)

        print(f"Downloaded: {len(downloaded)}, Failed: {len(errors)}")
        if errors:
            print(f"Sample errors: {list(errors.items())[:3]}")

        md_paths.update(downloaded)
    elif missing_md and dry_run:
        print(f"DRY RUN: Would download {len(missing_md)} missing MD files")
        stats["md_failures"] = len(missing_md)

    # Build full md_paths dict
    for pid in existing_md:
        md_paths[pid] = MD_CACHE_DIR / f"{pid}.md"

    # Get EvidenceRuleV4
    try:
        EvidenceRuleV4 = get_evidence_v4()
        print(f"EvidenceRuleV4 loaded: {EvidenceRuleV4}")
    except PackImportError as exc:
        print(f"ERROR: {exc}")
        return {"run_id": logical_run_id, "error": f"pack_import_error: {exc}"}

    # Process predictions (parallel evidence scoring)
    to_process = [f for f in prediction_files if f.stem in md_paths]
    total = len(to_process)
    workers = max(1, concurrency)
    print(
        f"Scoring evidence for {total} papers "
        f"(concurrency={workers}, progress every {PROGRESS_EVERY})...",
        flush=True,
    )

    done = 0
    stats_lock = threading.Lock()

    def _on_outcome(outcome: dict[str, Any]) -> None:
        nonlocal done
        with stats_lock:
            _merge_outcome(stats, outcome)
            done += 1
            if done % PROGRESS_EVERY == 0 or done == total:
                print(
                    f"  progress {done}/{total}  "
                    f"processed={stats['processed']} skipped={stats['skipped']} "
                    f"failed={stats['failed']}",
                    flush=True,
                )

    if workers == 1:
        for pred_file in to_process:
            _, outcome = _score_one_prediction_file(
                pred_file,
                md_paths[pred_file.stem],
                EvidenceRuleV4,
                force=force,
                dry_run=dry_run,
            )
            _on_outcome(outcome)
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [
                executor.submit(
                    _score_one_prediction_file,
                    pred_file,
                    md_paths[pred_file.stem],
                    EvidenceRuleV4,
                    force=force,
                    dry_run=dry_run,
                )
                for pred_file in to_process
            ]
            for future in as_completed(futures):
                try:
                    _, outcome = future.result()
                except Exception as exc:
                    outcome = {
                        "paper_id": "?",
                        "action": "failed",
                        "success": False,
                        "error": f"{type(exc).__name__}: {exc}",
                        "evidence_count": 0,
                    }
                    print(f"ERROR in worker: {exc}", flush=True)
                _on_outcome(outcome)

    # Compute averages
    processed_count = stats["processed"] + stats["skipped"]
    if processed_count > 0:
        stats["avg_evidence"] = stats["total_evidence_count"] / processed_count
        stats["pct_with_evidence"] = stats["papers_with_evidence"] / processed_count * 100

    print(f"Processed: {stats['processed']}, Skipped: {stats['skipped']}, Failed: {stats['failed']}")
    print(f"Papers with evidence: {stats['papers_with_evidence']}/{processed_count} ({stats['pct_with_evidence']:.1f}%)")

    # Generate report
    report = _generate_report(stats)
    report_path = run_dir / "evidence_report.md"

    if not dry_run:
        report_path.write_text(report, encoding="utf-8")
        print(f"Report written to: {report_path}")

    return stats


def _demo():
    """Self-check demo."""
    print("Running demo...")

    # Mock prediction
    mock_pred = {
        "paper_id": "demo123",
        "paper_title": "Demo Paper",
        "experiments": [
            {
                "experiment_name": "Demo Experiment",
                "research_problem": "Image classification accuracy",
                "research_goal": "Improve ImageNet accuracy",
                "experiment_subject": "ImageNet dataset",
                "method": "Our proposed method with attention and residual connections",
                "key_results": ["Accuracy: 95%"],
                "metrics": ["accuracy"],
            }
        ],
    }

    # Mock MD text
    mock_md = """
# Demo Paper

## Abstract
We propose DemoNet which achieves 95% accuracy on ImageNet.

## Methods
Our method uses attention mechanisms and residual connections.

## Results
As shown in Table 1, DemoNet outperforms all baselines.
The accuracy of 95% is a significant improvement.
"""

    import tempfile

    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
        f.write(mock_md)
        temp_md = Path(f.name)

    try:
        # Get EvidenceRuleV4
        EvidenceRuleV4 = get_evidence_v4()
        print(f"EvidenceRuleV4 loaded: {EvidenceRuleV4}")

        # Score
        scored, status = _score_prediction(mock_pred, temp_md, EvidenceRuleV4, force=False)

        # Verify
        assert "evidence" in scored["experiments"][0], "evidence field missing"
        assert status["success"], f"scoring failed: {status.get('error')}"
        print("Demo passed!")
        print(f"Evidence count: {status['evidence_count']}")
        print(f"Evidence: {scored['experiments'][0]['evidence'][:2]}...")  # Show first 2

    finally:
        temp_md.unlink()


def main():
    parser = argparse.ArgumentParser(
        description="Add MSWR evidence to bulk pipeline predictions.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Nested session (single job batch)
  python -m dataset_evidence.score_bulk_evidence \\
      --session-run-id prod-bulk-20260717 --job-batch job_batch_000

  # Nested session (all job batches)
  python -m dataset_evidence.score_bulk_evidence \\
      --session-run-id prod-bulk-20260717

  # Dry run
  python -m dataset_evidence.score_bulk_evidence \\
      --session-run-id prod-bulk-20260717 --job-batch job_batch_000 --dry-run

  # Force overwrite existing evidence
  python -m dataset_evidence.score_bulk_evidence \\
      --session-run-id prod-bulk-20260717 --job-batch job_batch_000 --force

  # Per-corpus manifest layout (TODO-EV-02): manifests live in manifests/<corpus>/
  python -m dataset_evidence.score_bulk_evidence \\
      --session-run-id prod-lilaoshi-smoke10-llm-enums-20260814 \\
      --manifests-dir manifests/lilaoshi_aminer_smoke10 --force
        """,
    )
    parser.add_argument(
        "--run-id",
        action="append",
        help="Legacy flat run ID (prod-bulk-YYYYMMDD-jobNNN) or nested "
             "session/job (prod-bulk-YYYYMMDD/job_batch_NNN). Can be repeated.",
    )
    parser.add_argument(
        "--session-run-id",
        type=str,
        default=None,
        help="Session run ID (parent folder under runs/)",
    )
    parser.add_argument(
        "--job-batch",
        type=str,
        default=None,
        help="Job batch subfolder (e.g. job_batch_000); omit to process all under session",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=8,
        help="Thread pool size for MD downloads and evidence scoring (default: 8)",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=3,
        help="Download retry attempts (default: 3)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scan and compute without modifying files",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force overwrite existing non-empty evidence",
    )
    parser.add_argument(
        "--manifests-dir",
        type=Path,
        default=MANIFESTS_DIR,
        help="Directory containing job_batch_*.json manifests. Default: "
             "manifests/job_batches (legacy layout). Per-corpus runs must pass "
             "their own directory, e.g. manifests/<corpus> (TODO-EV-02).",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run self-check demo",
    )

    args = parser.parse_args()

    if args.demo:
        _demo()
        return

    if not args.run_id and not args.session_run_id:
        parser.error("--run-id or --session-run-id is required (unless using --demo)")

    all_targets: list[dict[str, Any]] = []
    if args.run_id:
        for rid in args.run_id:
            all_targets.extend(
                _resolve_run_targets(run_id=rid)
            )
    if args.session_run_id:
        all_targets.extend(
            _resolve_run_targets(
                session_run_id=args.session_run_id,
                job_batch=args.job_batch,
            )
        )

    # Process each target
    all_stats = []
    for target in all_targets:
        try:
            stats = _process_run(
                target,
                args.concurrency,
                args.retries,
                args.dry_run,
                args.force,
                manifests_dir=args.manifests_dir,
            )
            all_stats.append(stats)
        except Exception as e:
            print(f"\nERROR processing {target.get('logical_run_id')}: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()

    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    total_processed = sum(s.get("processed", 0) for s in all_stats)
    total_skipped = sum(s.get("skipped", 0) for s in all_stats)
    total_failed = sum(s.get("failed", 0) for s in all_stats)
    total_evidence = sum(s.get("total_evidence_count", 0) for s in all_stats)
    total_with_evidence = sum(s.get("papers_with_evidence", 0) for s in all_stats)

    print(f"Total runs processed: {len(all_stats)}")
    print(f"Total processed: {total_processed}")
    print(f"Total skipped: {total_skipped}")
    print(f"Total failed: {total_failed}")
    print(f"Total evidence items: {total_evidence}")
    print(f"Papers with evidence: {total_with_evidence}")

    if args.dry_run:
        print("\nDRY RUN: No files were modified")


if __name__ == "__main__":
    main()