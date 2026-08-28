"""Datasets assign — pack v2_type_aware.

Maps ``paper_datasets[]`` onto the LLM-produced experiments. Runs in Wave-2
after the LLM partial is available (needs ``experiments_stripped`` — the LLM
experiments with the datasets field removed).

Returns experiments with a ``datasets`` key per experiment (+ assignment_trace).
"""

from __future__ import annotations

from typing import Any

from pipeline.production.adapters.rule_pack import PackImportError, get_assign_v2_type_aware
from pipeline.production.context import PaperContext
from pipeline.production.extractors.base import FieldExtractor
from pipeline.production.schema import FieldResult


class DatasetsAssignExtractor(FieldExtractor):
    extractor_id = "rules.datasets.assign"
    version = "v2_type_aware"
    produces = ("datasets",)  # per-experiment assignment
    depends_on = ("llm.wf8_dev20_v2_wash", "rules.datasets.extract")

    def _extract(self, ctx: PaperContext) -> FieldResult:
        extract_partial = ctx.get("rules.datasets.extract")
        paper_datasets: list[dict[str, Any]] = (
            extract_partial.value if extract_partial and extract_partial.status == "ok" else []
        )

        if not ctx.experiments_stripped:
            return FieldResult(
                extractor_id=self.extractor_id,
                version=self.version,
                status="error",
                error="experiments_stripped not built (LLM partial missing?)",
                fields=list(self.produces),
            )

        try:
            AssignCls = get_assign_v2_type_aware()
        except PackImportError as exc:
            return FieldResult(
                extractor_id=self.extractor_id,
                version=self.version,
                status="error",
                error=str(exc),
                fields=list(self.produces),
            )

        assigned = AssignCls().assign(
            paper_datasets,
            ctx.experiments_stripped,
            ctx.raw_md,
            paper_id=ctx.paper_id,
        )
        return FieldResult(
            extractor_id=self.extractor_id,
            version=self.version,
            status="ok",
            value=assigned,  # list[dict] each with `datasets`
            fields=list(self.produces),
            metadata={
                "paper_dataset_count": len(paper_datasets),
                "experiment_count": len(assigned),
            },
        )
