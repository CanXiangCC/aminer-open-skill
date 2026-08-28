"""Token usage trace normalization and aggregation."""

from __future__ import annotations

from statistics import mean

from src.evaluation.schemas import StageTrace, TokenTrace


def normalize_token_trace(tokens: TokenTrace) -> TokenTrace:
    """Ensure total_tokens equals input + output when missing."""
    return tokens.normalized()


def total_tokens(trace: StageTrace) -> int:
    """Return normalized total tokens for a stage trace."""
    return trace.tokens.normalized().total_tokens


def aggregate_tokens(traces: list[StageTrace]) -> dict:
    """Aggregate token usage values for one strategy."""
    totals = [total_tokens(trace) for trace in traces]
    return {
        "token_mean": mean(totals) if totals else 0.0,
        "token_sum": sum(totals),
        "llm_call_count_sum": sum(trace.tokens.llm_call_count for trace in traces),
        "paper_count": len(totals),
    }
