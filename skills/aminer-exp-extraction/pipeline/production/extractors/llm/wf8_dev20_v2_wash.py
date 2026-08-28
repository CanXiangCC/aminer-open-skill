"""LLM extractor: thin wrapper over the wf8 adapter (frozen 板块 5)."""

from __future__ import annotations

from pipeline.production.adapters.wf8_llm import run_wf8_for_production
from pipeline.production.context import PaperContext
from pipeline.production.extractors.base import FieldExtractor
from pipeline.production.schema import FieldResult


class Wf8Dev20V2WashExtractor(FieldExtractor):
    extractor_id = "llm.wf8_dev20_v2_wash"
    version = "0.2.0-dev20-wash"
    produces = (
        "experiment_name",
        "research_problem",
        "research_goal",
        "experiment_subject",
        "method",
        "key_results",
        "metrics",
    )
    depends_on: tuple[str, ...] = ()

    def _extract(self, ctx: PaperContext) -> FieldResult:
        return run_wf8_for_production(
            paper_id=ctx.paper_id,
            md_path=ctx.md_path,
            run_id=ctx.run_id,
        )
