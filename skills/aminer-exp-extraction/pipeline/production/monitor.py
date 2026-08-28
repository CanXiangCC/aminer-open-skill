"""Per-paper monitor + run-level history (jsonl).

Extends the 板块 5 monitor shape with a ``waves`` array (parallel task list +
elapsed per wave) and an ``extractors`` array (status/elapsed/fields per
extractor), plus ``critical_path_sec`` and ``merge_conflicts``.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pipeline.production.context import PaperContext
from pipeline.production.config import RUN_HISTORY_PATH


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_paper_monitor(
    ctx: PaperContext,
    waves: list[dict[str, Any]],
    extractors: list[dict[str, Any]],
    critical_path_sec: float,
    merge_conflicts: list[dict[str, Any]],
    total_elapsed_sec: float,
    error: str | None = None,
    pipeline_stages: dict[str, Any] | None = None,
    pipeline_started_at: str | None = None,
) -> dict[str, Any]:
    monitor = {
        "paper_id": ctx.paper_id,
        "workflow_id": ctx.workflow_id,
        "run_id": ctx.run_id,
        "dry_run": ctx.dry_run,
        "started_at": waves[0]["started_at"] if waves else utc_now(),
        "finished_at": utc_now(),
        "waves": waves,
        "extractors": extractors,
        "critical_path_sec": round(critical_path_sec, 4),
        "total_elapsed_sec": round(total_elapsed_sec, 4),
        "merge_conflicts": merge_conflicts,
        "error": error,
    }
    if pipeline_stages is not None:
        monitor["pipeline_stages"] = pipeline_stages
    if pipeline_started_at is not None:
        # True paper entry (PREP start). "started_at" above is the first POST
        # wave's start in the batch/staged paths — see docs/MONITORING.md.
        monitor["pipeline_started_at"] = pipeline_started_at
    return monitor


def write_paper_monitor(monitor: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(monitor, indent=2, ensure_ascii=False), encoding="utf-8")


def append_history(entry: dict[str, Any]) -> None:
    RUN_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with RUN_HISTORY_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
