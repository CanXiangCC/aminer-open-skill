"""Evidence extractor — pack v4_clean_mswr (experimental optimal).

Builds MSWR evidence per experiment from the full markdown + experiment
metadata (experiment_name / key_results / method). Runs in Wave-2 alongside
datasets assign (both depend only on the LLM partial).
"""

from __future__ import annotations

from typing import Any

from pipeline.production.adapters.rule_pack import PackImportError, get_evidence_v4
from pipeline.production.context import PaperContext
from pipeline.production.extractors.base import FieldExtractor
from pipeline.production.schema import FieldResult


class EvidenceExtractor(FieldExtractor):
    extractor_id = "rules.evidence"
    version = "v4_clean_mswr"
    produces = ("evidence",)
    depends_on = ("llm.wf4_dev20_v2_wash_datasets",)

    def _extract(self, ctx: PaperContext) -> FieldResult:
        if not ctx.experiments_stripped:
            return FieldResult(
                extractor_id=self.extractor_id,
                version=self.version,
                status="error",
                error="experiments_stripped not built (LLM partial missing?)",
                fields=list(self.produces),
            )

        try:
            EvidenceRuleV4 = get_evidence_v4()
        except PackImportError as exc:
            return FieldResult(
                extractor_id=self.extractor_id,
                version=self.version,
                status="error",
                error=str(exc),
                fields=list(self.produces),
            )

        results: list[dict[str, Any]] = EvidenceRuleV4.extract_for_paper(
            ctx.raw_md,
            ctx.experiments_stripped,
            input_mode="full_text",
        )
        return FieldResult(
            extractor_id=self.extractor_id,
            version=self.version,
            status="ok",
            value=results,  # list[dict] each with `evidence`
            fields=list(self.produces),
            metadata={"experiment_count": len(results)},
        )
