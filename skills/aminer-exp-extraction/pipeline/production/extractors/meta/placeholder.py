"""Placeholder extractor for meta fields not produced by rules/ML/LLM.

Fills ``_id``, ``experiment_history``, ``score`` with type-correct empty
defaults so the merged experiment always satisfies experiment_v1.schema.json.
"""

from __future__ import annotations

from pipeline.production.context import PaperContext
from pipeline.production.extractors.base import FieldExtractor
from pipeline.production.schema import FieldResult


class PlaceholderExtractor(FieldExtractor):
    extractor_id = "meta.placeholder"
    version = "0.1.0"
    produces = ("_id", "experiment_history", "score")

    def _extract(self, ctx: PaperContext) -> FieldResult:
        return FieldResult(
            extractor_id=self.extractor_id,
            version=self.version,
            status="ok",
            value={
                "_id": "",
                "experiment_history": [],
                "score": None,
            },
            fields=list(self.produces),
        )

    # dry-run stub still produces the same empty defaults.
    def _stub(self, ctx: PaperContext) -> FieldResult:
        return self._extract(ctx)
