"""Shared helpers for writing per-paper stage and reference traces."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from src.config.settings import PROJECT_ROOT
from src.evaluation.schemas import write_json


def display_path(path: Path) -> str:
    try:
        return path.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def elapsed_ms(start: float) -> float:
    return (time.perf_counter() - start) * 1000


def extract_usage(payload: dict[str, Any]) -> dict[str, int]:
    usage = payload.get("usage") if isinstance(payload, dict) else None
    if not isinstance(usage, dict):
        return {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "llm_call_count": 1,
        }
    input_tokens = usage.get("input_tokens", usage.get("prompt_tokens", 0))
    output_tokens = usage.get("output_tokens", usage.get("completion_tokens", 0))
    total_tokens = usage.get("total_tokens", 0)
    input_tokens = input_tokens if isinstance(input_tokens, int) else 0
    output_tokens = output_tokens if isinstance(output_tokens, int) else 0
    total_tokens = total_tokens if isinstance(total_tokens, int) else input_tokens + output_tokens
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "llm_call_count": 1,
    }


def empty_usage() -> dict[str, int]:
    return {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "llm_call_count": 0,
    }


def write_stage_trace(
    *,
    trace_dir: Path,
    paper_id: str,
    strategy: str,
    model: str,
    status: str,
    prediction_path: Path | None,
    error: str | None,
    latency_ms: dict[str, float],
    tokens: dict[str, int],
    preprocess: dict[str, Any] | None = None,
) -> Path:
    """Write a StageTrace-compatible JSON file for evaluation or reference cost."""
    total = sum(float(latency_ms.get(key, 0.0)) for key in ("load", "chunk", "section_select", "process", "llm"))
    payload = {
        "paper_id": paper_id,
        "strategy": strategy,
        "model": model,
        "status": status,
        "prediction_path": display_path(prediction_path) if prediction_path else "",
        "error": error,
        "latency_ms": {
            "load": latency_ms.get("load", 0.0),
            "chunk": latency_ms.get("chunk", 0.0),
            "section_select": latency_ms.get("section_select", 0.0),
            "process": latency_ms.get("process", 0.0),
            "llm": latency_ms.get("llm", 0.0),
            "total": total,
        },
        "tokens": tokens,
    }
    if preprocess is not None:
        payload["preprocess"] = preprocess
    trace_path = trace_dir / f"{paper_id}.json"
    write_json(trace_path, payload)
    return trace_path
