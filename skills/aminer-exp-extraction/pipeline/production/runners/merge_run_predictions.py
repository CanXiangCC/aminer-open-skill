"""CLI: merge a prod-wf4 run's per-paper predictions into exportable arrays.

Reads ``pipeline_output/production/runs/<run_id>/predictions/*.json`` (each a
``ProductionResult`` written by ``finalize_paper``) and emits:

- ``extractions.<tag>.json``         — flat array; one entry PER experiment
  (papers carry 1..3 experiments in wf4) with ``paper_id / paper_title /
  workflow_id / run_id`` merged in (handoff-baseline-array
  shape, for comparison/import; llm_model_tag stays in run telemetry only).
- ``extractions.<tag>.papers.json``  — raw per-paper predictions as-is
  (full provenance / metadata preserved).
- ``merge_report.<tag>.md``          — coverage / parse_error / timing report.

This script only **reads + rewrites**; it does NOT touch MergerWf4 or any
pipeline logic. Multi-experiment-per-paper is the wf4 design (1..3); every
experiment is exported, not just ``experiments[0]``.

Examples:
  venv/Scripts/python.exe pipeline/production/runners/merge_run_predictions.py \\
    --run-id prod-dev500-wf4-qwen17-v0.1.0 \\
    --manifest pipeline/evaluation/fixtures/dev_500/manifest.json \\
    --out pipeline_output/production/exports/extractions.dev500.wf4_qwen17.json \\
    --format both
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.production.config import RUNS_DIR, WF4_LLM_EXTRACTOR_ID  # noqa: E402
from pipeline.production.schema import validate_wf4_experiment  # noqa: E402

DEFAULT_EXPORTS = PROJECT_ROOT / "pipeline_output" / "production" / "exports"


def _load_manifest_paper_ids(manifest_path: Path) -> list[str]:
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw = data.get("papers", data.get("paper_ids", [])) if isinstance(data, dict) else data
    ids: list[str] = []
    for item in raw:
        if isinstance(item, dict) and item.get("paper_id"):
            ids.append(str(item["paper_id"]))
        elif isinstance(item, str):
            ids.append(item)
    return ids


def _llm_model_tag_from_monitor(monitor: dict) -> str | None:
    for e in monitor.get("extractors") or []:
        if e.get("extractor_id") == WF4_LLM_EXTRACTOR_ID:
            meta = e.get("metadata") or {}
            if meta.get("llm_model_tag"):
                return meta["llm_model_tag"]
    return None


def _llm_meta(monitor: dict) -> dict:
    for e in monitor.get("extractors") or []:
        if e.get("extractor_id") == WF4_LLM_EXTRACTOR_ID:
            return e.get("metadata") or {}
    return {}


def _load_progress(jsonl_path: Path) -> list[dict]:
    if not jsonl_path.exists():
        return []
    rows = []
    for line in jsonl_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def merge_run(
    *,
    run_id: str,
    manifest_path: Path,
    out_flat: Path,
    out_papers: Path | None,
    report_path: Path,
    llm_model_tag_override: str | None = None,
    out_experiments: Path | None = None,
) -> dict[str, Any]:
    run_dir = RUNS_DIR / run_id
    pred_dir = run_dir / "predictions"
    mon_dir = run_dir / "monitors"

    manifest_ids = _load_manifest_paper_ids(Path(manifest_path))
    manifest_set = set(manifest_ids)

    # run-level llm_model_tag fallback (batch_summary)
    run_llm_model_tag = llm_model_tag_override
    if run_llm_model_tag is None:
        bs = run_dir / "batch_summary.json"
        if bs.exists():
            try:
                run_llm_model_tag = json.loads(bs.read_text(encoding="utf-8")).get("llm_model_tag")
            except Exception:  # noqa: BLE001
                run_llm_model_tag = None

    pred_files = sorted(pred_dir.glob("*.json")) if pred_dir.exists() else []
    flat: list[dict[str, Any]] = []
    papers: list[dict[str, Any]] = []
    experiments_pure: list[dict[str, Any]] = []  # every experiment as-is (18 fields, no run provenance)
    seen: set[str] = set()
    parse_error_count = 0
    llm_secs: list[float] = []
    datasets_counts: list[int] = []
    error_papers: list[tuple[str, str]] = []
    multi_exp_papers = 0
    schema_error_experiments = 0
    schema_error_samples: list[tuple[str, list[str]]] = []

    for pf in pred_files:
        try:
            pred = json.loads(pf.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            error_papers.append((pf.stem, f"prediction read error: {exc}"))
            continue
        paper_id = pred.get("paper_id") or pf.stem
        seen.add(paper_id)
        papers.append(pred)

        # monitor for llm_model_tag + llm meta
        monitor: dict = {}
        mon_path = mon_dir / f"{paper_id}_monitor.json"
        if mon_path.exists():
            try:
                monitor = json.loads(mon_path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                monitor = {}
        llm_meta = _llm_meta(monitor)
        if llm_meta.get("parse_error"):
            parse_error_count += 1
        ec = llm_meta.get("datasets_count")
        if ec is not None:
            datasets_counts.append(int(ec))
        ps = (monitor.get("pipeline_stages") or {}) if monitor else {}
        if ps.get("llm_elapsed_sec") is not None:
            llm_secs.append(float(ps["llm_elapsed_sec"]))

        llm_model_tag = _llm_model_tag_from_monitor(monitor) or run_llm_model_tag

        experiments = pred.get("experiments") or []
        if not experiments:
            error_papers.append((paper_id, "no experiments in prediction"))
            continue
        if len(experiments) > 1:
            multi_exp_papers += 1
        for exp in experiments:
            exp_schema_errors = validate_wf4_experiment(exp)
            if exp_schema_errors:
                schema_error_experiments += 1
                if len(schema_error_samples) < 10:
                    schema_error_samples.append((paper_id, exp_schema_errors[:3]))
            exp_flat = dict(exp)
            # pure experiment data: each experiment as-is (18 experiment_v1
            # fields, no run-level provenance like run_id/llm_model_tag/workflow_id/paper_title).
            experiments_pure.append(dict(exp_flat))
            # merge provenance fields (do not clobber experiment's own paper_id)
            exp_flat.setdefault("paper_id", paper_id)
            flat.append({
                **exp_flat,
                "paper_id": paper_id,
                "paper_title": pred.get("paper_title"),
                "workflow_id": pred.get("workflow_id"),
                "run_id": pred.get("run_id"),
            })

    missing = sorted(manifest_set - seen)
    success = len(flat)
    n = max(1, len(llm_secs))
    avg_qwen_sec = round(sum(llm_secs) / len(llm_secs), 4) if llm_secs else 0.0
    avg_datasets_count = round(sum(datasets_counts) / len(datasets_counts), 4) if datasets_counts else 0.0

    # progress-log skip/error rows (md_fetch failures, skipped_missing_md)
    progress_rows = _load_progress(run_dir / "extraction_progress.jsonl")
    skipped = [r for r in progress_rows if r.get("status") == "skipped_missing_md"]
    md_fetch_failures = {r["paper_id"]: r.get("error") for r in skipped}

    # write flat
    out_flat.parent.mkdir(parents=True, exist_ok=True)
    out_flat.write_text(json.dumps(flat, ensure_ascii=False, indent=2), encoding="utf-8")

    # write papers
    if out_papers is not None:
        out_papers.parent.mkdir(parents=True, exist_ok=True)
        out_papers.write_text(json.dumps(papers, ensure_ascii=False, indent=2), encoding="utf-8")

    # write pure experiments (every experiment as-is, 18 experiment_v1 fields, no run provenance)
    if out_experiments is not None:
        out_experiments.parent.mkdir(parents=True, exist_ok=True)
        out_experiments.write_text(
            json.dumps(experiments_pure, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # write report
    report_lines = [
        f"# Merge Report — `{run_id}`",
        "",
        f"- manifest paper_count: **{len(manifest_ids)}**",
        f"- predictions found: **{len(papers)}**",
        f"- papers with >1 experiment: **{multi_exp_papers}**",
        f"- flat experiment entries: **{success}**",
        f"- pure experiment entries: **{len(experiments_pure)}**",
        f"- parse_error count: **{parse_error_count}**",
        f"- schema-invalid experiments: **{schema_error_experiments}** (wf4_experiment_v1; non-fatal)",
        f"- avg llm sec: **{avg_qwen_sec}** (n={len(llm_secs)})",
        f"- avg datasets count: **{avg_datasets_count}** (n={len(datasets_counts)})",
        f"- llm_model_tag (run-level): `{run_llm_model_tag}`",
        "",
        f"## Coverage ({len(seen)}/{len(manifest_ids)} manifest papers have a prediction)",
        "",
    ]
    if missing:
        report_lines += [f"## Missing paper_ids ({len(missing)})", ""]
        report_lines += [f"- {pid}" for pid in missing]
        report_lines.append("")
    else:
        report_lines += ["All manifest paper_ids have a prediction. ✓", ""]
    if md_fetch_failures:
        report_lines += [f"## md_fetch / skipped_missing_md ({len(md_fetch_failures)})", ""]
        report_lines += [f"- {pid}: {err}" for pid, err in md_fetch_failures.items()]
        report_lines.append("")
    if error_papers:
        report_lines += [f"## Prediction errors ({len(error_papers)})", ""]
        report_lines += [f"- {pid}: {err}" for pid, err in error_papers]
        report_lines.append("")
    if schema_error_samples:
        report_lines += [f"## Schema errors ({schema_error_experiments} experiments)", ""]
        report_lines += [f"- {pid}: {'; '.join(errs)}" for pid, errs in schema_error_samples]
        report_lines.append("")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    return {
        "run_id": run_id,
        "manifest_paper_count": len(manifest_ids),
        "predictions_found": len(papers),
        "multi_exp_papers": multi_exp_papers,
        "flat_entries": success,
        "missing_count": len(missing),
        "missing": missing,
        "parse_error_count": parse_error_count,
        "schema_error_experiments": schema_error_experiments,
        "avg_qwen_sec": avg_qwen_sec,
        "avg_datasets_count": avg_datasets_count,
        "llm_model_tag": run_llm_model_tag,
        "skipped_missing_md": len(skipped),
        "out_flat": str(out_flat),
        "out_papers": str(out_papers) if out_papers else None,
        "out_experiments": str(out_experiments) if out_experiments else None,
        "report": str(report_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge a prod-wf4 run's predictions into export arrays")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--out", default=str(DEFAULT_EXPORTS / "extractions.dev500.wf4_qwen17.json"),
                        help="flat experiments array output path")
    parser.add_argument("--format", choices=["experiments_flat", "papers", "experiments_pure", "both", "all"], default="both")
    parser.add_argument(
        "--papers-out", default=None,
        help="raw per-paper predictions output path (default: <out>.papers.json when format includes papers)",
    )
    parser.add_argument(
        "--experiments-out", default=None,
        help="pure experiment data output path (every experiment as-is, 18 fields, no run provenance; "
             "default: <out>.experiments.json when format includes experiments_pure/all)",
    )
    parser.add_argument("--report-out", default=str(DEFAULT_EXPORTS / "merge_report.dev500.md"))
    parser.add_argument("--ollama-model", default=None, help="override run-level llm_model_tag fallback")
    args = parser.parse_args()

    out_flat = Path(args.out)
    do_papers = args.format in ("papers", "both", "all")
    do_experiments = args.format in ("experiments_pure", "all")
    out_papers = Path(args.papers_out) if args.papers_out else (
        out_flat.with_suffix("").with_name(out_flat.stem + ".papers.json") if do_papers else None
    )
    out_experiments = Path(args.experiments_out) if args.experiments_out else (
        out_flat.with_suffix("").with_name(out_flat.stem + ".experiments.json") if do_experiments else None
    )
    if args.format == "papers":
        # flat not requested; still write a stub? No — only papers.
        out_flat_to_write = out_flat  # will still write flat for report convenience
    else:
        out_flat_to_write = out_flat

    stats = merge_run(
        run_id=args.run_id,
        manifest_path=Path(args.manifest),
        out_flat=out_flat_to_write,
        out_papers=out_papers,
        report_path=Path(args.report_out),
        llm_model_tag_override=args.llm_model_tag,
        out_experiments=out_experiments,
    )
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
