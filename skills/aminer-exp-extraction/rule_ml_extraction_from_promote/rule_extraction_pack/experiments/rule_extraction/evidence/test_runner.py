"""
Evidence field test runner — Gold build, v1/v2/v3 MSWR extract, evaluate, runs/{run_id}/.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

project_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from experiments.rule_extraction.evidence.scripts.build_gold_sets import (
    load_gold_experiments_stripped,
)
from experiments.rule_extraction.evidence.shared.evidence_evaluator import (
    BUCKET_NAMES,
    MULTI_EXPERIMENT_PAPER_IDS_DEV_20,
    PRODUCT_THRESHOLDS,
    aggregate_experiment_evals,
    aggregate_paper_evals,
    check_product_gates,
    evaluate_paper_evidence,
)
from experiments.rule_extraction.evidence.strategies.v1_field_backtrace_mswr import EvidenceRuleV1
from experiments.rule_extraction.evidence.strategies.v2_field_backtrace_mswr import EvidenceRuleV2
from experiments.rule_extraction.evidence.strategies.v3_field_backtrace_mswr import EvidenceRuleV3
from experiments.rule_extraction.evidence.strategies.v4_clean_mswr import EvidenceRuleV4

EVIDENCE_ROOT = Path(__file__).parent
STRATEGIES = {"v1": EvidenceRuleV1, "v2": EvidenceRuleV2, "v3": EvidenceRuleV3, "v4": EvidenceRuleV4}
STRATEGY_IDS = {
    "v1": EvidenceRuleV1.STRATEGY_ID,
    "v2": EvidenceRuleV2.STRATEGY_ID,
    "v3": EvidenceRuleV3.STRATEGY_ID,
    "v4": EvidenceRuleV4.STRATEGY_ID,
}
_DYNAMIC_STRATEGIES = frozenset({"v2", "v3", "v4"})

THRESHOLDS = {
    "semantic_recall_at_5_min": 0.45,
    "verbatim_rate_min": 0.85,
    "gold_substring_rate_min": 0.90,
}

# Engineering success criteria (automated gates). human_acceptable is manual review.
SUCCESS_CRITERIA = "product"
PRODUCT_GATES = PRODUCT_THRESHOLDS

V2_THRESHOLDS = {
    "verbatim_rate_min": 0.95,
    "verbatim_gold_recall_delta_min_pp": 10.0,
}

V3_THRESHOLDS = {
    "verbatim_rate_min": 0.95,
    "semantic_recall_at_5_min_vs_v1": 0.194,
    "semantic_recall_at_5_delta_min_pp": 3.0,
}

V4_THRESHOLDS = {
    "verbatim_rate_min": 0.95,
}


def _git_commit() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            cwd=project_root,
            timeout=5,
            check=False,
        )
        if out.returncode == 0:
            return out.stdout.strip()
    except Exception:
        pass
    return None


def _write_step(run_dir: Path, name: str, payload: dict[str, Any]) -> None:
    steps_dir = run_dir / "steps"
    steps_dir.mkdir(parents=True, exist_ok=True)
    with open(steps_dir / name, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def load_manifest(batch: str) -> list[dict[str, Any]]:
    manifest_path = project_root / "data" / "fixtures" / batch / "manifest.json"
    with open(manifest_path, encoding="utf-8") as f:
        return json.load(f)


def load_gold_experiments(batch: str, paper_id: str) -> list[dict]:
    gold_path = EVIDENCE_ROOT / "data" / "gold" / batch / "per_experiment" / f"{paper_id}.json"
    with open(gold_path, encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else [data]


def ensure_gold_built(batch: str, run_dir: Path, *, rebuild: bool = False) -> dict[str, Any]:
    stats_path = EVIDENCE_ROOT / "data" / "gold" / batch / "build_stats.json"
    if rebuild or not stats_path.exists():
        from experiments.rule_extraction.evidence.scripts.build_gold_sets import build_gold_sets

        stats = build_gold_sets(batch, project_root)
    else:
        with open(stats_path, encoding="utf-8") as f:
            stats = json.load(f)
    _write_step(run_dir, "01_build_gold.json", stats)
    return stats


def _load_v1_baseline(batch: str) -> tuple[dict[str, Any] | None, Path | None]:
    """Load v1 baseline manifest; return (manifest, run_dir)."""
    candidates = [
        EVIDENCE_ROOT / "runs" / "20260706_evidence_v1_dev10" / "run_manifest.json",
    ]
    for pattern in EVIDENCE_ROOT.glob("runs/*evidence_v1*"):
        p = pattern / "run_manifest.json"
        if p.exists() and p not in [c for c in candidates]:
            candidates.append(p)

    for path in candidates:
        if not path.exists():
            continue
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
        if doc.get("batch") == batch:
            return doc, path.parent
    return None, None


def _reevaluate_stored_results(
    results_dir: Path,
    batch: str,
    *,
    k: int | None = 5,
) -> dict[str, Any]:
    """Re-evaluate stored prediction JSON with enhanced evaluator."""
    paper_records: list[dict[str, Any]] = []
    gold_by_paper: dict[str, list[dict]] = {}
    k_used_list: list[int] = []

    for result_file in sorted(results_dir.glob("*.json")):
        paper_id = result_file.stem
        gold_path = EVIDENCE_ROOT / "data" / "gold" / batch / "per_experiment" / f"{paper_id}.json"
        if not gold_path.exists():
            continue
        manifest = load_manifest(batch)
        md_text = ""
        for item in manifest:
            if item.get("paper_id") == paper_id:
                md_path = item.get("md_path", "")
                md_text = (project_root / md_path).read_text(encoding="utf-8")
                break

        with open(result_file, encoding="utf-8") as f:
            pred_experiments = json.load(f)
        gold_experiments = load_gold_experiments(batch, paper_id)
        gold_by_paper[paper_id] = gold_experiments

        eval_k = k
        evaluation = evaluate_paper_evidence(
            gold_experiments, pred_experiments, md_text, k=eval_k,
        )
        for exp_ev in evaluation.get("experiments") or []:
            k_used_list.append(exp_ev.get("k_used", 0))

        paper_records.append({
            "paper_id": paper_id,
            "evaluation": evaluation,
            "success": True,
        })

    multi_ids = set()
    stats_path = EVIDENCE_ROOT / "data" / "gold" / batch / "build_stats.json"
    if stats_path.exists():
        with open(stats_path, encoding="utf-8") as f:
            stats = json.load(f)
        multi_ids = set(stats.get("multi_experiment_paper_ids") or [])

    agg = aggregate_paper_evals(
        [
            {"paper_id": r["paper_id"], "experiments": r.get("evaluation", {}).get("experiments") or []}
            for r in paper_records
        ],
        multi_paper_ids=multi_ids,
        gold_by_paper=gold_by_paper,
    )
    avg_k = sum(k_used_list) / len(k_used_list) if k_used_list else 0.0
    return {"agg": agg, "paper_records": paper_records, "avg_k_used": avg_k}


def _metrics_from_agg(agg: dict[str, Any], gold_sub_rate: float, *, avg_k_used: float = 0.0, k_mode: str = "fixed") -> dict[str, Any]:
    overall = agg["overall"]
    buckets = agg.get("buckets") or {}
    bucket_metrics = {}
    for name in BUCKET_NAMES:
        b = buckets.get(name, {})
        bucket_metrics[name] = {
            "semantic_recall_at_5": round(b.get("semantic_recall_at_k", 0), 4),
            "semantic_recall_at_5_verbatim_gold": round(b.get("semantic_recall_at_k_verbatim_gold", 0), 4),
            "verbatim_rate": round(b.get("verbatim_rate", 0), 4),
            "experiment_count": b.get("experiment_count", 0),
        }

    return {
        "success_criteria": SUCCESS_CRITERIA,
        "noise_rate": round(overall.get("noise_rate", 0), 4),
        "relevance_mean": round(overall.get("relevance_mean", 0), 4),
        "relevance_hit_rate": round(overall.get("relevance_hit_rate", 0), 4),
        "traceable_rate": round(overall.get("traceable_rate", overall.get("verbatim_rate", 0)), 4),
        "product_pass": overall.get("product_pass", False),
        "product_gates": overall.get("product_gates"),
        "human_acceptable": None,
        "semantic_recall_at_5": round(overall.get("semantic_recall_at_k", 0), 4),
        "semantic_recall_at_5_verbatim_gold": round(overall.get("semantic_recall_at_k_verbatim_gold", 0), 4),
        "semantic_recall_normalized_at_5": round(overall.get("semantic_recall_normalized", 0), 4),
        "recall_at_5_verbatim_gold": round(overall.get("recall_at_k_verbatim_gold", 0), 4),
        "verbatim_rate": round(overall.get("verbatim_rate", 0), 4),
        "micro_f1_at_5": round(overall.get("micro_f1_at_k", 0), 4),
        "gold_substring_rate": round(gold_sub_rate, 4),
        "gold_verbatim_count": overall.get("gold_verbatim_count", 0),
        "gold_non_verbatim_count": overall.get("gold_non_verbatim_count", 0),
        "multi_exp_semantic_recall_at_5": (
            round(agg["multi_experiment"]["semantic_recall_at_k"], 4)
            if agg.get("multi_experiment")
            else None
        ),
        "k_mode": k_mode,
        "avg_k_used": round(avg_k_used, 2),
        "buckets": bucket_metrics,
    }


def _compute_delta_vs_v1(
    current_metrics: dict[str, Any],
    v1_metrics: dict[str, Any],
    *,
    strategy_key: str = "v2",
) -> dict[str, Any]:
    delta: dict[str, Any] = {}
    for key in (
        "noise_rate",
        "relevance_mean",
        "traceable_rate",
        "semantic_recall_at_5",
        "semantic_recall_at_5_verbatim_gold",
        "verbatim_rate",
        "semantic_recall_normalized_at_5",
    ):
        cur_val = current_metrics.get(key, 0) or 0
        v1_val = v1_metrics.get(key, 0) or 0
        delta[key] = round(cur_val - v1_val, 4)
        delta[f"{key}_v1"] = v1_val
        delta[f"{key}_{strategy_key}"] = cur_val

    cur_buckets = current_metrics.get("buckets") or {}
    v1_buckets = v1_metrics.get("buckets") or {}
    bucket_delta: dict[str, Any] = {}
    for name in BUCKET_NAMES:
        curb = cur_buckets.get(name, {})
        v1b = v1_buckets.get(name, {})
        bucket_delta[name] = {
            "semantic_recall_at_5_verbatim_gold_delta": round(
                (curb.get("semantic_recall_at_5_verbatim_gold") or 0)
                - (v1b.get("semantic_recall_at_5_verbatim_gold") or 0),
                4,
            ),
        }
    delta["buckets"] = bucket_delta
    return delta


def _write_analysis(
    run_dir: Path,
    agg: dict[str, Any],
    paper_records: list[dict[str, Any]],
    *,
    pass_run: bool,
    gold_stats: dict[str, Any],
    thresholds: dict[str, float],
    strategy_key: str,
    metrics: dict[str, Any],
    delta_vs_v1: dict[str, Any] | None = None,
    v1_baseline_run_id: str | None = None,
) -> None:
    analysis_dir = run_dir / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)

    overall = agg["overall"]
    gold_sub = gold_stats.get("gold_substring_rate", 0.0)
    version = strategy_key if strategy_key in ("v2", "v3") else "v1"

    lines = [
        f"# Evidence {version} Run Summary",
        "",
        f"**PASS (product):** {'YES' if pass_run else 'NO'}",
        "",
        "## Product Success Criteria",
        "",
        "Engineering gates: **低噪声 + 高相关 + 可溯源**; **人工可接受** via manual spot-check (`human_acceptable`).",
        "",
        f"| Gate | Threshold | Actual | Status |",
        "|------|-----------|--------|--------|",
    ]
    gates = metrics.get("product_gates") or check_product_gates(metrics)
    checks = gates.get("checks") or {}
    gate_rows = [
        ("low_noise (noise_rate ≤ max)", f"≤ {PRODUCT_GATES['noise_rate_max']:.0%}", metrics.get("noise_rate", 0), "low_noise"),
        ("high_relevance (relevance_mean ≥ min)", f"≥ {PRODUCT_GATES['relevance_mean_min']:.0%}", metrics.get("relevance_mean", 0), "high_relevance"),
        ("traceable (traceable_rate ≥ min)", f"≥ {PRODUCT_GATES['traceable_rate_min']:.0%}", metrics.get("traceable_rate", 0), "traceable"),
    ]
    for label, thresh, actual, key in gate_rows:
        status = "PASS" if checks.get(key) else "FAIL"
        lines.append(f"| {label} | {thresh} | {actual:.2%} | {status} |")
    lines.extend([
        f"| human_acceptable | manual review | {metrics.get('human_acceptable', 'pending')} | — |",
        "",
        "## Benchmark Track (gold regression only)",
        "",
    ])

    if delta_vs_v1 and v1_baseline_run_id:
        lines.extend([
            f"## v1 vs {version} Delta",
            "",
            f"Baseline: `{v1_baseline_run_id}`",
            "",
            f"| Metric | v1 | {version} | Δ |",
            "|--------|----|----|---|",
        ])
        for key, label in [
            ("semantic_recall_at_5", "semantic_recall@5 (all gold)"),
            ("semantic_recall_at_5_verbatim_gold", "semantic_recall@5 (verbatim gold)"),
            ("verbatim_rate", "verbatim_rate"),
            ("semantic_recall_normalized_at_5", "semantic_recall_normalized"),
        ]:
            v1v = delta_vs_v1.get(f"{key}_v1", 0)
            curv = delta_vs_v1.get(f"{key}_{strategy_key}", delta_vs_v1.get(f"{key}_v2", 0))
            d = delta_vs_v1.get(key, 0)
            lines.append(f"| {label} | {v1v:.2%} | {curv:.2%} | {d:+.2%} |")
        lines.append("")

    lines.extend([
        "## Metrics — All Gold vs Verbatim Gold",
        "",
        "| Metric | All Gold | Verbatim Gold Only |",
        "|--------|----------|-------------------|",
        f"| semantic_recall@k | {overall.get('semantic_recall_at_k', 0):.2%} | {overall.get('semantic_recall_at_k_verbatim_gold', 0):.2%} |",
        f"| recall@k | {overall.get('recall_at_k', 0):.2%} | {overall.get('recall_at_k_verbatim_gold', 0):.2%} |",
        f"| gold count | {overall.get('gold_count', 0)} | {overall.get('gold_verbatim_count', 0)} |",
        f"| verbatim_rate (pred) | {overall.get('verbatim_rate', 0):.2%} | — |",
        f"| semantic_recall_normalized | {overall.get('semantic_recall_normalized', 0):.2%} | — |",
        f"| gold_substring_rate | {gold_sub:.2%} | — |",
        "",
    ])

    buckets = agg.get("buckets") or {}
    if buckets:
        lines.extend([
            "## Bucket Breakdown",
            "",
            "| Bucket | Exps | sem_recall (all) | sem_recall (verbatim gold) | verbatim_rate |",
            "|--------|------|------------------|---------------------------|---------------|",
        ])
        for name in BUCKET_NAMES:
            b = buckets.get(name, {})
            if b.get("experiment_count", 0) == 0:
                continue
            lines.append(
                f"| {name} | {b.get('experiment_count', 0)} "
                f"| {b.get('semantic_recall_at_k', 0):.2%} "
                f"| {b.get('semantic_recall_at_k_verbatim_gold', 0):.2%} "
                f"| {b.get('verbatim_rate', 0):.2%} |"
            )
        lines.append("")

    if strategy_key == "v2":
        v1_vg = (delta_vs_v1 or {}).get("semantic_recall_at_5_verbatim_gold_v1", 0)
        target = v1_vg + V2_THRESHOLDS["verbatim_gold_recall_delta_min_pp"] / 100
        v2_vg = metrics.get("semantic_recall_at_5_verbatim_gold", 0)
        lines.extend([
            "## v2 Benchmark Notes (non-gating)",
            "",
            f"- verbatim_gold recall vs v1+10pp target ({target:.2%}): {v2_vg:.2%}",
            "",
            "## Failure modes",
            "",
            "1. **Paraphrase miss** — gold evidence not in md; key_results paraphrase gap",
            "2. **Multi-exp misrouting** — wrong section despite scope routing",
            "3. **Survey / cross-lingual** — CJK queries vs English md",
            "",
        ])

    if strategy_key == "v3":
        v1_all = (delta_vs_v1 or {}).get("semantic_recall_at_5_v1", 0.194)
        v3_all = metrics.get("semantic_recall_at_5", 0)
        v3_vg = metrics.get("semantic_recall_at_5_verbatim_gold", 0)
        lines.extend([
            "## v3 Benchmark Notes (non-gating)",
            "",
            f"- semantic_recall@5 vs v1 ({v1_all:.2%}): {v3_all:.2%}",
            f"- verbatim_gold recall: {v3_vg:.2%}",
            "",
        ])

    if strategy_key == "v4":
        lines.extend([
            "## v4 Benchmark Notes (non-gating)",
            "",
            f"- sentence_clean enabled with R1-R4 filters",
            f"- Jaccard-only rerank (no embedding)",
            "",
        ])

    with open(analysis_dir / "summary.md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    breakdown_lines = [
        "# Per-paper Breakdown",
        "",
        "| paper_id | exps | pred | noise | relevance | traceable | product | sem_recall |",
        "|----------|------|------|-------|-----------|-----------|---------|------------|",
    ]
    for rec in paper_records:
        exps = rec.get("evaluation", {}).get("experiments") or []
        sub = aggregate_experiment_evals(exps)
        breakdown_lines.append(
            f"| {rec['paper_id']} | {len(exps)} | {sub['pred_count']} "
            f"| {sub.get('noise_rate', 0):.2%} | {sub.get('relevance_mean', 0):.2%} "
            f"| {sub.get('traceable_rate', 0):.2%} "
            f"| {'YES' if sub.get('product_pass') else 'NO'} "
            f"| {sub['semantic_recall_at_k']:.2%} |"
        )

    with open(analysis_dir / "per_paper_breakdown.md", "w", encoding="utf-8") as f:
        f.write("\n".join(breakdown_lines) + "\n")


def run_batch(
    *,
    strategy_key: str,
    batch: str,
    run_dir: Path,
    k: int,
    input_mode: str,
    rebuild_gold: bool,
    fixed_k: int | None = None,
    use_embedding: bool = False,
    compare_v1: bool = False,
) -> dict[str, Any]:
    strategy_class = STRATEGIES[strategy_key]
    started_at = datetime.now().isoformat()
    t_run = time.perf_counter()

    gold_stats = ensure_gold_built(batch, run_dir, rebuild=rebuild_gold)
    manifest = load_manifest(batch)

    paper_records: list[dict[str, Any]] = []
    extract_times: list[float] = []
    experiments_total = 0
    k_used_list: list[int] = []
    warnings: list[str] = []

    gold_sub_rate = gold_stats.get("gold_substring_rate", 0.0)
    if gold_sub_rate < THRESHOLDS["gold_substring_rate_min"]:
        warnings.append(
            f"gold_quality_warning: gold_substring_rate={gold_sub_rate:.2%} "
            f"< {THRESHOLDS['gold_substring_rate_min']:.0%}"
        )

    results_dir = run_dir / "results"
    traces_dir = run_dir / "traces"
    results_dir.mkdir(parents=True, exist_ok=True)
    traces_dir.mkdir(parents=True, exist_ok=True)

    gold_by_paper: dict[str, list[dict]] = {}
    eval_k: int | None = k if strategy_key == "v1" else None

    for item in manifest:
        paper_id = item["paper_id"]
        gold_path = EVIDENCE_ROOT / "data" / "gold" / batch / "per_experiment" / f"{paper_id}.json"
        if not gold_path.exists():
            continue

        try:
            md_path = item.get("md_path", "")
            md_text = (project_root / md_path).read_text(encoding="utf-8")
            gold_experiments = load_gold_experiments(batch, paper_id)
            gold_by_paper[paper_id] = gold_experiments
            input_experiments = load_gold_experiments_stripped(paper_id, batch)

            t0 = time.perf_counter()
            if strategy_key in _DYNAMIC_STRATEGIES:
                pred_experiments = strategy_class.extract_for_paper(
                    md_text,
                    input_experiments,
                    input_mode=input_mode,
                    fixed_k=fixed_k,
                    use_embedding=use_embedding,
                )
            else:
                pred_experiments = strategy_class.extract_for_paper(
                    md_text,
                    input_experiments,
                    k=k,
                    input_mode=input_mode,
                )
            extract_ms = round((time.perf_counter() - t0) * 1000, 2)
            extract_times.append(extract_ms)
            experiments_total += len(pred_experiments)

            traces = [p.get("evidence_trace") or {} for p in pred_experiments]
            for tr in traces:
                if tr.get("k_dynamic"):
                    k_used_list.append(tr["k_dynamic"])

            with open(traces_dir / f"{paper_id}.json", "w", encoding="utf-8") as f:
                json.dump({"paper_id": paper_id, "traces": traces}, f, indent=2, ensure_ascii=False)

            pred_out = []
            for p in pred_experiments:
                copy = {key: val for key, val in p.items() if key != "evidence_trace"}
                pred_out.append(copy)
            with open(results_dir / f"{paper_id}.json", "w", encoding="utf-8") as f:
                json.dump(pred_out, f, indent=2, ensure_ascii=False)

            evaluation = evaluate_paper_evidence(
                gold_experiments, pred_experiments, md_text, k=eval_k,
            )
            paper_records.append({
                "paper_id": paper_id,
                "extract_ms": extract_ms,
                "evaluation": evaluation,
                "success": True,
            })
        except Exception as e:
            paper_records.append({
                "paper_id": paper_id,
                "success": False,
                "error": str(e),
                "evaluation": {"experiments": []},
            })
            with open(traces_dir / f"{paper_id}.json", "w", encoding="utf-8") as f:
                json.dump({"paper_id": paper_id, "error": str(e), "traces": []}, f, indent=2)

    multi_ids = set(MULTI_EXPERIMENT_PAPER_IDS_DEV_20) if batch == "dev_20" else set(
        gold_stats.get("multi_experiment_paper_ids") or []
    )
    agg = aggregate_paper_evals(
        [
            {"paper_id": r["paper_id"], "experiments": r.get("evaluation", {}).get("experiments") or []}
            for r in paper_records
            if r.get("success")
        ],
        multi_paper_ids=multi_ids,
        gold_by_paper=gold_by_paper,
    )
    overall = agg["overall"]

    k_mode = "dynamic" if strategy_key in _DYNAMIC_STRATEGIES and fixed_k is None else "fixed"
    avg_k_used = sum(k_used_list) / len(k_used_list) if k_used_list else float(k)

    _write_step(run_dir, "02_extract.json", {
        "papers_processed": len(paper_records),
        "experiments_total": experiments_total,
        "extract_total_ms": round(sum(extract_times), 2),
        "extract_mean_ms": round(sum(extract_times) / len(extract_times), 2) if extract_times else 0,
        "extract_times_by_paper": {r["paper_id"]: r.get("extract_ms", 0) for r in paper_records if r.get("success")},
        "k_mode": k_mode,
        "avg_k_used": round(avg_k_used, 2),
        "use_embedding": use_embedding if strategy_key in _DYNAMIC_STRATEGIES else False,
    })

    _write_step(run_dir, "03_evaluate.json", {
        "overall": overall,
        "multi_experiment": agg.get("multi_experiment"),
        "buckets": agg.get("buckets"),
        "paper_count": len(paper_records),
    })

    finished_at = datetime.now().isoformat()
    wall_ms = round((time.perf_counter() - t_run) * 1000, 2)

    metrics = _metrics_from_agg(agg, gold_sub_rate, avg_k_used=avg_k_used, k_mode=k_mode)

    delta_vs_v1: dict[str, Any] | None = None
    v1_baseline_run_id: str | None = None

    if compare_v1 and strategy_key in _DYNAMIC_STRATEGIES:
        v1_manifest, v1_run_dir = _load_v1_baseline(batch)
        v1_metrics: dict[str, Any] = {}

        if v1_run_dir and (v1_run_dir / "results").exists():
            reeval = _reevaluate_stored_results(v1_run_dir / "results", batch, k=5)
            v1_metrics = _metrics_from_agg(
                reeval["agg"], gold_sub_rate, avg_k_used=5.0, k_mode="fixed",
            )
            v1_baseline_run_id = v1_manifest.get("run_id") if v1_manifest else v1_run_dir.name
        elif v1_manifest:
            v1_metrics = v1_manifest.get("metrics", {})
            v1_baseline_run_id = v1_manifest.get("run_id")

        if v1_metrics:
            delta_vs_v1 = _compute_delta_vs_v1(metrics, v1_metrics, strategy_key=strategy_key)
            delta_vs_v1["baseline_run_id"] = v1_baseline_run_id

    pass_run = bool(metrics.get("product_pass"))

    _write_analysis(
        run_dir, agg, paper_records,
        pass_run=pass_run,
        gold_stats=gold_stats,
        thresholds=PRODUCT_GATES,
        strategy_key=strategy_key,
        metrics=metrics,
        delta_vs_v1=delta_vs_v1,
        v1_baseline_run_id=v1_baseline_run_id,
    )

    manifest_doc: dict[str, Any] = {
        "run_id": run_dir.name,
        "started_at": started_at,
        "finished_at": finished_at,
        "git_commit": _git_commit(),
        "batch": batch,
        "strategy": STRATEGY_IDS[strategy_key],
        "k": k if strategy_key == "v1" else (fixed_k if fixed_k is not None else "dynamic"),
        "k_mode": k_mode,
        "avg_k_used": round(avg_k_used, 2),
        "input_mode": input_mode,
        "gold_set": "per_experiment",
        "use_embedding": use_embedding if strategy_key in _DYNAMIC_STRATEGIES else False,
        "success_criteria": SUCCESS_CRITERIA,
        "metrics": metrics,
        "thresholds": PRODUCT_GATES,
        "benchmark_thresholds_legacy": (
            V4_THRESHOLDS if strategy_key == "v4"
            else V3_THRESHOLDS if strategy_key == "v3"
            else V2_THRESHOLDS if strategy_key == "v2"
            else THRESHOLDS
        ),
        "pass": pass_run,
        "papers_total": len(paper_records),
        "experiments_total": experiments_total,
        "wall_ms": wall_ms,
        "warnings": warnings,
    }
    if delta_vs_v1:
        manifest_doc["delta_vs_v1"] = delta_vs_v1

    with open(run_dir / "run_manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest_doc, f, indent=2, ensure_ascii=False)

    return manifest_doc


def main() -> None:
    parser = argparse.ArgumentParser(description="Run evidence extraction tests")
    parser.add_argument("--strategy", choices=list(STRATEGIES.keys()), default="v1")
    parser.add_argument("--batch", default="dev_10")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--k", type=int, default=EvidenceRuleV1.DEFAULT_K)
    parser.add_argument("--fixed-k", type=int, default=None, help="Disable dynamic k for v2/v3")
    parser.add_argument("--input-mode", default="full_text", choices=["full_text", "section_union"])
    parser.add_argument("--rebuild-gold", action="store_true")
    parser.add_argument("--compare-v1", action="store_true", help="Compute delta vs v1 baseline run")
    parser.add_argument("--use-embedding", action="store_true", help="v2/v3: use embedding rerank (requires sentence-transformers)")
    args = parser.parse_args()

    default_prefix = f"evidence_{args.strategy}"
    run_id = args.run_id or datetime.now().strftime(f"%Y%m%d_{default_prefix}_%H%M%S")
    run_dir = EVIDENCE_ROOT / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    print(f"Evidence {args.strategy} run: {run_id} batch={args.batch}")
    manifest = run_batch(
        strategy_key=args.strategy,
        batch=args.batch,
        run_dir=run_dir,
        k=args.k,
        input_mode=args.input_mode,
        rebuild_gold=args.rebuild_gold,
        fixed_k=args.fixed_k,
        use_embedding=args.use_embedding,
        compare_v1=args.compare_v1,
    )

    m = manifest["metrics"]
    print(
        f"\nProduct: noise_rate={m.get('noise_rate', 0):.2%} "
        f"relevance_mean={m.get('relevance_mean', 0):.2%} "
        f"traceable_rate={m.get('traceable_rate', 0):.2%} "
        f"pass={manifest['pass']}"
    )
    print(
        f"Benchmark: semantic_recall_at_5={m['semantic_recall_at_5']:.2%} "
        f"verbatim_gold={m.get('semantic_recall_at_5_verbatim_gold', 0):.2%}"
    )
    if manifest.get("delta_vs_v1"):
        d = manifest["delta_vs_v1"]
        print(
            f"Delta vs v1: all_gold={d.get('semantic_recall_at_5', 0):+.2%} "
            f"verbatim_gold={d.get('semantic_recall_at_5_verbatim_gold', 0):+.2%}"
        )
    print(f"Run manifest: {run_dir / 'run_manifest.json'}")


if __name__ == "__main__":
    main()
