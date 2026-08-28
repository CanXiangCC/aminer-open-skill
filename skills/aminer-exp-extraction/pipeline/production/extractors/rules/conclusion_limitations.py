"""Conclusion + Limitations extractor — pack v5_layered + vK_enhanced_filter.

Both rules take the full ``paper_md`` and do their own section detection
internally (v5 three-layer fallback; vK enhanced filter). Runs in Wave-1, in
parallel with the LLM call — text2 slicing is unnecessary (see ARCHITECTURE.md
D2).
"""

from __future__ import annotations

from pipeline.production.adapters.rule_pack import (
    PackImportError,
    get_conclusion_v5,
    get_limitations_vk,
)
from pipeline.production.context import PaperContext
from pipeline.production.extractors.base import FieldExtractor
from pipeline.production.schema import FieldResult


class ConclusionLimitationsExtractor(FieldExtractor):
    extractor_id = "rules.conclusion_limitations"
    version = "v5_layered+vK_enhanced_filter"
    produces = ("conclusion", "limitations")
    depends_on: tuple[str, ...] = ()

    def _extract(self, ctx: PaperContext) -> FieldResult:
        try:
            ConclusionRuleV5 = get_conclusion_v5()
            LimitationsRuleK = get_limitations_vk()
        except PackImportError as exc:
            return FieldResult(
                extractor_id=self.extractor_id,
                version=self.version,
                status="error",
                error=str(exc),
                fields=list(self.produces),
            )

        conclusion = ConclusionRuleV5.extract(ctx.raw_md, max_sentences=3)
        limitations = LimitationsRuleK.extract(ctx.raw_md, max_sentences=2)
        return FieldResult(
            extractor_id=self.extractor_id,
            version=self.version,
            status="ok",
            value={
                "conclusion": conclusion or "",
                "limitations": limitations or "",
            },
            fields=list(self.produces),
            metadata={
                "conclusion_strategy": "v5_layered",
                "limitations_strategy": "vK_enhanced_filter",
                "conclusion_found": bool(conclusion),
                "limitations_found": bool(limitations),
            },
        )
