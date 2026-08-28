"""
Per-experiment assignment evaluator.

Evaluates assignment quality at (paper_id, experiment_index) granularity by
reusing shared.dataset_evaluator.evaluate_paper_datasets on each experiment's
assigned vs gold datasets. Aggregates overall P/R/F1 plus a multi_experiment
subset and reports broadcast-trigger / field_study empty-hit stats.
"""

from __future__ import annotations

from typing import Any

from experiments.rule_extraction.datasets.shared.dataset_evaluator import (
    aggregate_evaluations,
    evaluate_paper_datasets,
)


def _exp_dataset_count(exp: dict[str, Any]) -> int:
    ds = exp.get("datasets")
    return len(ds) if isinstance(ds, list) else 0


def _flatten_experiments(
    by_paper: dict[str, list[dict[str, Any]]],
) -> list[tuple[str, int, dict[str, Any]]]:
    """Flatten to (paper_id, experiment_index, experiment) tuples in stable order."""
    flat: list[tuple[str, int, dict[str, Any]]] = []
    for paper_id in sorted(by_paper.keys()):
        for idx, exp in enumerate(by_paper[paper_id]):
            flat.append((paper_id, idx, exp))
    return flat


def evaluate_assignment(
    assigned_experiments_by_paper: dict[str, list[dict[str, Any]]],
    gold_experiments_by_paper: dict[str, list[dict[str, Any]]],
    *,
    eval_modes: list[str] | None = None,
    multi_experiment_paper_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Evaluate assignment at experiment granularity.

    Args:
        assigned_experiments_by_paper: {paper_id: [exp with assigned `datasets`]}
        gold_experiments_by_paper: {paper_id: [exp with gold `datasets`]}
        eval_modes: subset of ["strict","fuzzy","semantic"]; defaults to
            ["strict","fuzzy"].
        multi_experiment_paper_ids: papers with >1 experiment to report
            separately (dev_20's 5 multi-experiment papers).

    Returns:
        dict with overall / multi_experiment summaries per mode + per-experiment
        breakdown + broadcast / field_study stats.
    """
    if eval_modes is None:
        eval_modes = ["strict", "fuzzy"]
    multi_set = set(multi_experiment_paper_ids or [])

    per_exp_records: list[dict[str, Any]] = []
    raw_evals: list[dict[str, Any]] = []  # shape compatible with aggregate_evaluations
    multi_raw_evals: list[dict[str, Any]] = []
    multi_records: list[dict[str, Any]] = []
    broadcast_papers: set[str] = set()
    broadcast_trigger_count = 0
    field_study_total = 0
    field_study_empty_hit = 0  # assigned [] and gold [] both empty

    for paper_id, gold_exps in gold_experiments_by_paper.items():
        assigned_exps = assigned_experiments_by_paper.get(paper_id) or []
        # Pair by experiment index; if counts mismatch, pair up to min length
        # and report extras as errors.
        n = max(len(gold_exps), len(assigned_exps))
        is_multi = paper_id in multi_set
        for idx in range(n):
            gold_exp = gold_exps[idx] if idx < len(gold_exps) else {}
            assigned_exp = assigned_exps[idx] if idx < len(assigned_exps) else {}
            gold_ds = gold_exp.get("datasets") or []
            assigned_ds = assigned_exp.get("datasets") or []
            evaluation = evaluate_paper_datasets(gold_ds, assigned_ds)
            raw_evals.append(evaluation)
            if is_multi:
                multi_raw_evals.append(evaluation)

            trace = assigned_exp.get("assignment_trace") or {}
            if trace.get("broadcast_triggered"):
                broadcast_trigger_count += 1
                broadcast_papers.add(paper_id)
            klass = trace.get("experiment_class") or ""
            if klass == "field_study":
                field_study_total += 1
                if not gold_ds and not assigned_ds:
                    field_study_empty_hit += 1

            rec = {
                "paper_id": paper_id,
                "experiment_index": idx,
                "experiment_name": gold_exp.get("experiment_name") or assigned_exp.get("experiment_name"),
                "is_multi_experiment_paper": is_multi,
                "gold_count": len(gold_ds),
                "rule_count": len(assigned_ds),
                "evaluation": {m: evaluation[m] for m in eval_modes if m in evaluation},
                "match_pairs": evaluation.get("match_pairs", []),
                "broadcast_triggered": bool(trace.get("broadcast_triggered")),
                "experiment_class": klass,
                "fallback_used": trace.get("fallback_used", "none"),
                "rule_hits": trace.get("rule_hits", []),
            }
            per_exp_records.append(rec)
            if is_multi:
                multi_records.append(rec)

    overall: dict[str, Any] = {}
    multi: dict[str, Any] = {}
    for mode in eval_modes:
        overall[mode] = aggregate_evaluations(raw_evals, mode)
        multi[mode] = aggregate_evaluations(multi_raw_evals, mode) if multi_raw_evals else {
            "total_papers": 0, "total_gold_datasets": 0, "total_rule_datasets": 0,
            "total_matched": 0, "total_missed": 0, "total_extra": 0,
            "recall": 0.0, "precision": 0.0, "f1": 0.0,
        }

    field_study_empty_rate = (
        field_study_empty_hit / field_study_total if field_study_total else 0.0
    )

    return {
        "eval_modes": eval_modes,
        "overall": overall,
        "multi_experiment": multi,
        "stats": {
            "total_papers": len(gold_experiments_by_paper),
            "total_experiments": len(per_exp_records),
            "multi_experiment_papers": sorted(multi_set),
            "multi_experiment_count": sum(1 for r in per_exp_records if r["is_multi_experiment_paper"]),
            "broadcast_trigger_count": broadcast_trigger_count,
            "broadcast_papers": sorted(broadcast_papers),
            "field_study_total": field_study_total,
            "field_study_empty_hit": field_study_empty_hit,
            "field_study_empty_rate": field_study_empty_rate,
        },
        "per_experiment": per_exp_records,
    }
