#!/usr/bin/env python3
"""Merge one or more production run_ids into export JSON under pipeline_output/production/exports."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROD_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROD_ROOT))

from pipeline.production.runners.merge_run_predictions import merge_run  # noqa: E402
from pipeline.production.run_paths import resolve_run_dir, export_tag_from_run_id  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-id", action="append", required=True, help="repeatable")
    ap.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="optional job_batch or combined manifest; if omitted, use all preds in run",
    )
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=PROD_ROOT / "pipeline_output" / "production" / "exports",
    )
    ap.add_argument("--format", choices=("flat", "papers", "both"), default="both")
    ap.add_argument("--clean-md-cache", action="store_true", help="delete md_cache after merge")
    args = ap.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    for run_id in args.run_id:
        tag = export_tag_from_run_id(run_id)
        out_flat = args.out_dir / f"extractions.{tag}.json"
        out_papers = (
            args.out_dir / f"extractions.{tag}.papers.json"
            if args.format in ("papers", "both")
            else None
        )
        if args.format == "papers":
            out_flat = args.out_dir / f"extractions.{tag}.papers.json"
            out_papers = None

        manifest = args.manifest
        tmp_manifest = None
        if manifest is None:
            pred_dir = resolve_run_dir(run_id) / "predictions"
            ids = sorted(p.stem for p in pred_dir.glob("*.json")) if pred_dir.is_dir() else []
            tmp_manifest = args.out_dir / f"_manifest_{tag}.json"
            tmp_manifest.write_text(
                json.dumps({"papers": [{"paper_id": i} for i in ids]}, indent=2) + "\n",
                encoding="utf-8",
            )
            manifest = tmp_manifest

        merge_run(
            run_id=run_id,
            manifest_path=manifest,
            out_flat=out_flat,
            out_papers=out_papers if args.format == "both" else out_papers,
            report_path=args.out_dir / f"merge_report.{tag}.md",
            llm_model_tag_override=None,
        )
        print(f"merged {run_id} -> {out_flat}")
        if tmp_manifest and tmp_manifest.exists():
            tmp_manifest.unlink()

    if args.clean_md_cache:
        cache = PROD_ROOT / "pipeline_output" / "md_cache"
        n = 0
        if cache.is_dir():
            for p in cache.glob("*.md"):
                p.unlink()
                n += 1
        print(f"cleaned md_cache files={n}")


if __name__ == "__main__":
    main()
