"""PaperContext: per-paper mutable state passed through the DAG.

Holds the raw markdown, the partial FieldResult of every Extractor that has
run, and inter-wave derived state (base experiments, etc.). Extractors read
``ctx.raw_md`` / ``ctx.partials`` and write only their own partial.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pipeline.production.schema import FieldResult


@dataclass
class PaperContext:
    paper_id: str
    md_path: Path
    run_id: str
    workflow_id: str
    dry_run: bool = False

    # Raw markdown (full, including references — pack rule extractors expect
    # the same full md the pack's own dev_10 runner feeds them; URL/DOI
    # matching in datasets v4.3 reads the reference section directly).
    raw_md: str = ""

    # Extractor partials: extractor_id -> FieldResult.
    partials: dict[str, FieldResult] = field(default_factory=dict)

    # Inter-wave derived state (set by orchestrator glue between waves).
    # Base single experiment built from the LLM 7-field output (no datasets).
    base_experiments: list[dict[str, Any]] = field(default_factory=list)
    # Same as base_experiments but with datasets stripped (input to assign).
    experiments_stripped: list[dict[str, Any]] = field(default_factory=list)

    # Timing / monitoring accumulators.
    wave_timings: list[dict[str, Any]] = field(default_factory=list)

    def get(self, extractor_id: str) -> FieldResult | None:
        return self.partials.get(extractor_id)

    def set(self, result: FieldResult) -> None:
        self.partials[result.extractor_id] = result
