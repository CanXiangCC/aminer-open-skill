"""sample_size conditional policy — wf4 variant (LLM datasets source).

Mirrors ``rules.sample_size_policy`` but reads ``has_dataset`` from the wf4 LLM
partial's ``datasets[]`` instead of ``rules.datasets.extract`` / ``.assign``
(which do not run in wf4). ``depends_on=()`` — the LLM partial is set by
``process_llm_and_post_wf4`` before the tail runs, so ``ctx.get`` is enough.

Logic:
  has_dataset = any(len(exp.datasets) > 0 for exp in llm.experiments)
  if has_dataset: top-level sample_size = null  (branch="has_dataset_llm")
  else:           top-level sample_size = SampleSizeRule.extract(md)  (branch="no_dataset")
"""

from __future__ import annotations

from typing import Any

from pipeline.production.adapters.rule_pack import PackImportError, get_sample_size_rule
from pipeline.production.config import WF4_LLM_EXTRACTOR_ID
from pipeline.production.context import PaperContext
from pipeline.production.extractors.base import FieldExtractor
from pipeline.production.schema import FieldResult


def _collect_llm_datasets(llm_val: dict[str, Any]) -> list[dict[str, Any]]:
    """Aggregate datasets from multi-exp value (or old flat datasets key)."""
    out: list[dict[str, Any]] = []
    experiments = llm_val.get("experiments")
    if isinstance(experiments, list):
        for exp in experiments:
            if isinstance(exp, dict):
                ds = exp.get("datasets")
                if isinstance(ds, list):
                    out.extend(d for d in ds if isinstance(d, dict))
        return out
    ds = llm_val.get("datasets")
    if isinstance(ds, list):
        return [d for d in ds if isinstance(d, dict)]
    return []


class SampleSizePolicyWf4Extractor(FieldExtractor):
    extractor_id = "rules.sample_size_policy_wf4"
    version = "0.1.0-wf4"
    produces = ("sample_size",)
    depends_on: tuple[str, ...] = ()  # LLM partial set before tail; ctx.get is enough

    def _extract(self, ctx: PaperContext) -> FieldResult:
        llm = ctx.get(WF4_LLM_EXTRACTOR_ID)
        llm_datasets: list[dict[str, Any]] = []
        if llm and llm.status == "ok" and isinstance(llm.value, dict):
            llm_datasets = _collect_llm_datasets(llm.value)

        has_dataset = len(llm_datasets) > 0

        if has_dataset:
            return FieldResult(
                extractor_id=self.extractor_id,
                version=self.version,
                status="ok",
                value=None,
                fields=list(self.produces),
                metadata={
                    "branch": "has_dataset_llm",
                    "reason": "LLM datasets present; top-level sample_size null (subfield policy WIP)",
                    "llm_dataset_count": len(llm_datasets),
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
