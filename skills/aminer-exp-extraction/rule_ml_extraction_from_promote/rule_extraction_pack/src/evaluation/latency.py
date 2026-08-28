"""Latency trace normalization and aggregation."""

from __future__ import annotations

from statistics import mean

from src.evaluation.schemas import LatencyTrace, StageTrace


def normalize_latency_trace(latency: LatencyTrace) -> LatencyTrace:
    """Ensure latency total equals the segment sum when missing."""
    return latency.normalized()


def latency_total(trace: StageTrace) -> float:
    """Return normalized total latency for a stage trace."""
    return trace.latency_ms.normalized().total


def aggregate_latency(traces: list[StageTrace]) -> dict:
    """Aggregate latency values for one strategy."""
    totals = [latency_total(trace) for trace in traces]
    return {
        "latency_mean_ms": mean(totals) if totals else 0.0,
        "latency_sum_ms": sum(totals),
        "paper_count": len(totals),
    }
