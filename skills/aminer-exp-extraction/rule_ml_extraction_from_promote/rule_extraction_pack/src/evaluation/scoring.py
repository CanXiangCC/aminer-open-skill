"""Stable benchmark score formulas for evaluation metrics."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from statistics import mean

from src.evaluation.schemas import PaperMetrics


@dataclass(frozen=True)
class ScoreWeights:
    """Default score weights. Keep defaults fixed for comparable benchmarks."""

    accuracy: float = 0.60
    latency: float = 0.20
    token: float = 0.20


DEFAULT_WEIGHTS = ScoreWeights()


def cost_ratio(actual: float | int | None, reference: float | int | None) -> float | None:
    """Return actual/reference when both values are positive."""
    if not isinstance(actual, (int, float)) or not isinstance(reference, (int, float)):
        return None
    if actual <= 0 or reference <= 0:
        return None
    return float(actual) / float(reference)


def cost_score(actual: float | int | None, reference: float | int | None) -> float | None:
    """Stable lower-is-better score: min(1, reference / actual)."""
    ratio = cost_ratio(actual, reference)
    if ratio is None:
        return None
    return min(1.0, 1.0 / ratio)


def total_score(
    accuracy_score: float | None,
    latency_score: float | None,
    token_score: float | None,
    *,
    weights: ScoreWeights = DEFAULT_WEIGHTS,
) -> float | None:
    """Compute weighted total only when all components are available."""
    if accuracy_score is None or latency_score is None or token_score is None:
        return None
    return (
        weights.accuracy * accuracy_score
        + weights.latency * latency_score
        + weights.token * token_score
    )


def apply_paper_scores(
    paper_metrics: list[PaperMetrics],
    *,
    weights: ScoreWeights = DEFAULT_WEIGHTS,
) -> list[PaperMetrics]:
    """Fill stable latency/token/total scores in paper metrics."""
    for metric in paper_metrics:
        metric.accuracy_score = metric.paper_accuracy if metric.accuracy_available else None
        metric.latency_ratio = cost_ratio(
            metric.latency_total_ms,
            metric.reference_latency_total_ms,
        )
        metric.latency_score = cost_score(
            metric.latency_total_ms,
            metric.reference_latency_total_ms,
        )
        metric.token_ratio = cost_ratio(
            metric.total_tokens,
            metric.reference_total_tokens,
        )
        metric.token_score = cost_score(
            metric.total_tokens,
            metric.reference_total_tokens,
        )
        metric.reference_cost_available = (
            metric.latency_score is not None and metric.token_score is not None
        )
        metric.total_score = total_score(
            metric.accuracy_score,
            metric.latency_score,
            metric.token_score,
            weights=weights,
        )
    return paper_metrics


def mean_score(values: Sequence[float | None]) -> float | None:
    """Return the mean of available scores, or None when none are available."""
    available = [value for value in values if value is not None]
    return mean(available) if available else None


def mean_score_or_zero(values: Sequence[float]) -> float:
    """Return mean or 0.0 for raw latency/token sequences."""
    return mean(values) if values else 0.0
