"""Datasets extract (paper-level) — pack v4.3 union strategy.

Produces ``paper_datasets[]`` (the raw, unassigned dataset list) from the full
markdown. Runs in Wave-1, in parallel with the LLM call.
"""

from __future__ import annotations

from typing import Any

from pipeline.production.adapters.rule_pack import PackImportError, get_dataset_v43
from pipeline.production.context import PaperContext
from pipeline.production.extractors.base import FieldExtractor
from pipeline.production.schema import FieldResult


class DatasetsExtractExtractor(FieldExtractor):
    extractor_id = "rules.datasets.extract"
    version = "v4_3_union"
    produces = ("datasets",)  # paper-level; assignment maps to experiments
    depends_on: tuple[str, ...] = ()

    def _extract(self, ctx: PaperContext) -> FieldResult:
        try:
            DatasetRuleV43 = get_dataset_v43()
        except PackImportError as exc:
            return FieldResult(
                extractor_id=self.extractor_id,
                version=self.version,
                status="error",
                error=str(exc),
                fields=list(self.produces),
            )

        result: dict[str, Any] = DatasetRuleV43.extract(ctx.raw_md, paper_id=ctx.paper_id)
        paper_datasets = result.get("datasets", []) if isinstance(result, dict) else []
        return FieldResult(
            extractor_id=self.extractor_id,
            version=self.version,
            status="ok",
            value=paper_datasets,
            fields=list(self.produces),
            metadata={
                "dataset_count": len(paper_datasets),
                "strategy": "v4_3_union",
            },
        )
