"""Evaluation metrics entry points.

This module combines accuracy, latency, token, and stable benchmark scoring.
It does not call LLMs and does not write latency/token/score data back to Gold.
"""

from __future__ import annotations

from collections import defaultdict
from statistics import mean
from typing import Any

from src.evaluation.accuracy import paper_accuracy
from src.evaluation.latency import aggregate_latency, latency_total
from src.evaluation.scoring import ScoreWeights, apply_paper_scores, mean_score, mean_score_or_zero
from src.evaluation.schemas import (
    GlobalMetrics,
    PaperMetrics,
    StageTrace,
    StrategyMetrics,
    dataclass_to_dict,
)
from src.evaluation.semantic import SemanticScorer
from src.evaluation.token_usage import aggregate_tokens, total_tokens


ACCURACY_COMPONENT_FIELDS = (
    "domain_score",
    "datasets_score",
    "metrics_score",
    "key_results_score",
    "exp_semantic_score",
)


def accuracy_component_means(accuracy_details: dict[str, Any]) -> dict[str, float | None]:
    """Aggregate matched experiment component scores to paper-level fields."""
    matched = accuracy_details.get("matched_experiments") or []
    if not matched:
        return {field: None for field in ACCURACY_COMPONENT_FIELDS}
    means: dict[str, float | None] = {}
    for field in ACCURACY_COMPONENT_FIELDS:
        values = [
            item[field]
            for item in matched
            if isinstance(item, dict) and isinstance(item.get(field), (int, float))
        ]
        means[field] = mean(values) if values else None
    return means


def _reference_latency(reference_trace: StageTrace | None) -> float | None:
    if reference_trace is None:
        return None
    return latency_total(reference_trace)


def _reference_tokens(reference_trace: StageTrace | None) -> int | None:
    if reference_trace is None:
        return None
    return total_tokens(reference_trace)


def evaluate_paper(
    *,
    paper_id: str,
    strategy: str,
    gold_experiments: list[dict] | None,
    pred_experiments: list[dict],
    trace: StageTrace,
    reference_trace: StageTrace | None = None,
    semantic_scorer: SemanticScorer | None = None,
) -> PaperMetrics:
    """Compute per-paper metrics for one strategy."""
    reference_latency = _reference_latency(reference_trace)
    reference_tokens = _reference_tokens(reference_trace)
    if gold_experiments is None:
        return PaperMetrics(
            paper_id=paper_id,
            strategy=strategy,
            gold_status="missing_gold",
            accuracy_available=False,
            paper_accuracy=None,
            accuracy_score=None,
            latency_total_ms=latency_total(trace),
            reference_latency_total_ms=reference_latency,
            total_tokens=total_tokens(trace),
            reference_total_tokens=reference_tokens,
            details={
                "gold_status": "missing_gold",
                "accuracy": None,
                "trace_status": trace.status,
                "prediction_path": trace.prediction_path,
                "reference_trace_status": reference_trace.status if reference_trace else None,
            },
        )

    accuracy_details = paper_accuracy(
        gold_experiments,
        pred_experiments,
        semantic_scorer=semantic_scorer,
    )
    component_scores = accuracy_component_means(accuracy_details)
    return PaperMetrics(
        paper_id=paper_id,
        strategy=strategy,
        gold_status="available",
        accuracy_available=True,
        paper_accuracy=accuracy_details["paper_accuracy"],
        accuracy_score=accuracy_details["paper_accuracy"],
        domain_score=component_scores["domain_score"],
        datasets_score=component_scores["datasets_score"],
        metrics_score=component_scores["metrics_score"],
        key_results_score=component_scores["key_results_score"],
        exp_semantic_score=component_scores["exp_semantic_score"],
        latency_total_ms=latency_total(trace),
        reference_latency_total_ms=reference_latency,
        total_tokens=total_tokens(trace),
        reference_total_tokens=reference_tokens,
        details={
            "accuracy": accuracy_details,
            "reference_trace_status": reference_trace.status if reference_trace else None,
        },
    )


def aggregate_strategy_metrics(
    paper_metrics: list[PaperMetrics],
    traces: list[StageTrace],
) -> list[StrategyMetrics]:
    """Aggregate per-paper metrics by strategy."""
    metrics_by_strategy: dict[str, list[PaperMetrics]] = defaultdict(list)
    traces_by_strategy: dict[str, list[StageTrace]] = defaultdict(list)
    for metric in paper_metrics:
        metrics_by_strategy[metric.strategy].append(metric)
    for trace in traces:
        traces_by_strategy[trace.strategy].append(trace)

    strategy_metrics: list[StrategyMetrics] = []
    for strategy, metrics in sorted(metrics_by_strategy.items()):
        strategy_traces = traces_by_strategy.get(strategy, [])
        latency = aggregate_latency(strategy_traces)
        tokens = aggregate_tokens(strategy_traces)
        reference_latencies = [item.reference_latency_total_ms for item in metrics]
        reference_tokens = [float(item.reference_total_tokens) for item in metrics if item.reference_total_tokens is not None]
        strategy_metrics.append(
            StrategyMetrics(
                strategy=strategy,
                paper_count=len(metrics),
                accuracy_available_count=sum(1 for item in metrics if item.accuracy_available),
                accuracy_unavailable_count=sum(1 for item in metrics if not item.accuracy_available),
                accuracy_score=mean_score([item.accuracy_score for item in metrics]),
                reference_cost_available_count=sum(1 for item in metrics if item.reference_cost_available),
                reference_cost_unavailable_count=sum(1 for item in metrics if not item.reference_cost_available),
                latency_score=mean_score([item.latency_score for item in metrics]),
                token_score=mean_score([item.token_score for item in metrics]),
                total_score=mean_score([item.total_score for item in metrics]),
                latency_mean_ms=latency["latency_mean_ms"],
                latency_sum_ms=latency["latency_sum_ms"],
                reference_latency_mean_ms=mean_score(reference_latencies),
                latency_ratio_mean=mean_score([item.latency_ratio for item in metrics]),
                token_mean=tokens["token_mean"],
                token_sum=tokens["token_sum"],
                reference_token_mean=mean_score(reference_tokens),
                token_ratio_mean=mean_score([item.token_ratio for item in metrics]),
            )
        )
    return strategy_metrics


def aggregate_global_metrics(paper_metrics: list[PaperMetrics]) -> GlobalMetrics:
    """Aggregate global score across all selected strategy-paper metrics."""
    strategies = {metric.strategy for metric in paper_metrics}
    return GlobalMetrics(
        strategy_count=len(strategies),
        paper_metric_count=len(paper_metrics),
        accuracy_available_count=sum(1 for item in paper_metrics if item.accuracy_available),
        accuracy_unavailable_count=sum(1 for item in paper_metrics if not item.accuracy_available),
        reference_cost_available_count=sum(1 for item in paper_metrics if item.reference_cost_available),
        reference_cost_unavailable_count=sum(1 for item in paper_metrics if not item.reference_cost_available),
        total_score=mean_score([metric.total_score for metric in paper_metrics]),
    )


def compute_run_metrics(
    records: list[dict[str, Any]],
    *,
    semantic_scorer: SemanticScorer | None = None,
    weights: ScoreWeights | None = None,
) -> dict[str, Any]:
    """Compute run-level metrics from loaded gold/prediction/trace records."""
    paper_metrics = [
        evaluate_paper(
            paper_id=record["paper_id"],
            strategy=record["strategy"],
            gold_experiments=record["gold_experiments"],
            pred_experiments=record["pred_experiments"],
            trace=record["trace"],
            reference_trace=record.get("reference_trace"),
            semantic_scorer=semantic_scorer,
        )
        for record in records
    ]
    apply_paper_scores(paper_metrics, weights=weights or ScoreWeights())

    traces = [record["trace"] for record in records]
    strategy_metrics = aggregate_strategy_metrics(paper_metrics, traces)
    global_metrics = aggregate_global_metrics(paper_metrics)

    return {
        "per_paper_metrics": [dataclass_to_dict(metric) for metric in paper_metrics],
        "per_strategy_metrics": [
            dataclass_to_dict(metric) for metric in strategy_metrics
        ],
        "global_metrics": dataclass_to_dict(global_metrics),
    }


def compute_metrics(
    predictions: list,
    gold_labels: list,
    run_metadata: list,
) -> dict:
    """Backward-compatible wrapper for older skeleton callers.

    Prefer `compute_run_metrics(records)` for the new evaluation skeleton.
    """
    records: list[dict[str, Any]] = []
    for index, (prediction, gold, metadata) in enumerate(
        zip(predictions, gold_labels, run_metadata, strict=False)
    ):
        trace = metadata.get("trace") if isinstance(metadata, dict) else None
        if trace is None:
            continue
        records.append(
            {
                "paper_id": metadata.get("paper_id", f"paper_{index}"),
                "strategy": metadata.get("strategy", "unknown"),
                "gold_experiments": gold,
                "pred_experiments": prediction,
                "trace": trace,
                "reference_trace": metadata.get("reference_trace"),
            }
        )
    return compute_run_metrics(records)
