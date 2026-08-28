"""sample_size conditional policy (WIP — interface first).

Logic (模型+规则工程pipeline梳理.txt L51-54):
  has_dataset = len(paper_datasets) > 0  OR  any assigned experiment.datasets non-empty
  if has_dataset: top-level sample_size = null   (subfield policy WIP)
  else:           top-level sample_size = SampleSizeRule.extract(md)  (pack skeleton, may be None)

Runs in Wave-4 (after datasets extract/assign). The branch taken is recorded
in the FieldResult metadata + monitor.
"""

from __future__ import annotations

from typing import Any

from pipeline.production.adapters.rule_pack import PackImportError, get_sample_size_rule
from pipeline.production.context import PaperContext
from pipeline.production.extractors.base import FieldExtractor
from pipeline.production.schema import FieldResult


class SampleSizePolicyExtractor(FieldExtractor):
    extractor_id = "rules.sample_size_policy"
    version = "0.1.0"
    produces = ("sample_size",)
    depends_on = ("rules.datasets.extract", "rules.datasets.assign")

    def _extract(self, ctx: PaperContext) -> FieldResult:
        extract_partial = ctx.get("rules.datasets.extract")
        paper_datasets: list[dict[str, Any]] = (
            extract_partial.value if extract_partial and extract_partial.status == "ok" else []
        )
        assign_partial = ctx.get("rules.datasets.assign")
        assigned: list[dict[str, Any]] = (
            assign_partial.value if assign_partial and assign_partial.status == "ok" else []
        )

        has_dataset = len(paper_datasets) > 0 or any(
            (exp.get("datasets") if isinstance(exp, dict) else None) for exp in assigned
        )

        if has_dataset:
            return FieldResult(
                extractor_id=self.extractor_id,
                version=self.version,
                status="ok",
                value=None,
                fields=list(self.produces),
                metadata={
                    "branch": "has_dataset",
                    "reason": "datasets detected; top-level sample_size null (subfield policy WIP)",
                    "paper_dataset_count": len(paper_datasets),
                },
            )

        # No datasets -> rule match for true sample_size (medicine/biology etc.).
        try:
            SampleSizeRule = get_sample_size_rule()
        except PackImportError as exc:
            return FieldResult(
                extractor_id=self.extractor_id,
                version=self.version,
                status="error",
                value=None,
                error=str(exc),
                fields=list(self.produces),
                metadata={"branch": "no_dataset"},
            )

        sample_size = SampleSizeRule.extract(ctx.raw_md, section_filter=True)
        return FieldResult(
            extractor_id=self.extractor_id,
            version=self.version,
            status="ok",
            value=sample_size,
            fields=list(self.produces),
            metadata={
                "branch": "no_dataset",
                "rule_result": sample_size,
                "note": "SampleSizeRule is a pack skeleton; may return None",
            },
        )
