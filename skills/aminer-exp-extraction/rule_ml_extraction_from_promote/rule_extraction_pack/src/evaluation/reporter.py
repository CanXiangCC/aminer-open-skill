"""Generate lightweight Markdown reports for evaluation runs."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _format_float(value: object) -> str:
    return f"{float(value):.4f}" if isinstance(value, (int, float)) else "n/a"


def render_report(
    metrics: dict[str, Any],
    *,
    run_id: str,
    batch: str,
    strategies: list[str],
    failures: list[dict[str, str]] | None = None,
) -> str:
    """Render a concise Markdown report for one evaluation run."""
    failures = failures or []
    global_metrics = metrics.get("global_metrics") or {}
    strategy_metrics = metrics.get("per_strategy_metrics") or []
    paper_metrics = metrics.get("per_paper_metrics") or []
    accuracy_available = global_metrics.get("accuracy_available_count", 0)
    accuracy_unavailable = global_metrics.get("accuracy_unavailable_count", 0)

    lines = [
        f"# Evaluation Report: {run_id}",
        "",
        f"- Batch: `{batch}`",
        f"- Strategies: `{', '.join(strategies)}`",
        f"- Paper metrics: `{len(paper_metrics)}`",
        f"- Failed inputs: `{len(failures)}`",
        f"- Accuracy available: `{accuracy_available}`",
        f"- Accuracy unavailable: `{accuracy_unavailable}`",
        f"- Global total score: `{_format_float(global_metrics.get('total_score'))}`",
        "",
        "## Per Strategy Metrics",
        "",
        "| Strategy | Papers | Accuracy Coverage | Accuracy | Latency Score | Token Score | Total Score | Latency Mean ms | Token Sum |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in strategy_metrics:
        coverage = "{}/{}".format(
            item.get("accuracy_available_count", 0),
            item.get("paper_count", 0),
        )
        lines.append(
            "| {strategy} | {paper_count} | {coverage} | {accuracy} | "
            "{latency_score} | {token_score} | {total_score} | "
            "{latency_mean} | {token_sum} |".format(
                strategy=item.get("strategy", ""),
                paper_count=item.get("paper_count", 0),
                coverage=coverage,
                accuracy=_format_float(item.get("accuracy_score")),
                latency_score=_format_float(item.get("latency_score")),
                token_score=_format_float(item.get("token_score")),
                total_score=_format_float(item.get("total_score")),
                latency_mean=_format_float(item.get("latency_mean_ms")),
                token_sum=item.get("token_sum", 0),
            )
        )

    if failures:
        lines.extend(["", "## Failed Inputs", ""])
        for failure in failures:
            lines.append(
                "- `{paper_id}` / `{strategy}`: {reason}".format(
                    paper_id=failure.get("paper_id", ""),
                    strategy=failure.get("strategy", ""),
                    reason=failure.get("reason", ""),
                )
            )

    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- Accuracy is computed from Prediction vs Gold.",
            "- If Gold is missing, accuracy and total score are reported as unavailable for that paper.",
            "- Latency and token metrics are computed from Stage trace.",
            "- Gold files must not contain latency, tokens, or evaluation scores.",
        ]
    )
    return "\n".join(lines) + "\n"


def generate_report(
    metrics: dict,
    run_batch_id: str,
    strategies: list,
) -> dict:
    """Backward-compatible report helper for older skeleton callers."""
    report = render_report(
        metrics,
        run_id=run_batch_id,
        batch="unknown",
        strategies=list(strategies),
    )
    return {"ok": True, "report": report}


def write_report(
    output_dir: str | Path,
    metrics: dict[str, Any],
    *,
    run_id: str,
    batch: str,
    strategies: list[str],
    failures: list[dict[str, str]] | None = None,
) -> Path:
    """Write report.md into an evaluation output directory."""
    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    report_path = target_dir / "report.md"
    report_path.write_text(
        render_report(
            metrics,
            run_id=run_id,
            batch=batch,
            strategies=strategies,
            failures=failures,
        ),
        encoding="utf-8",
    )
    return report_path
