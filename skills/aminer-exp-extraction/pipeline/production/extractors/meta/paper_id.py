"""paper_id extractor: carries the input paper_id into the experiment."""

from __future__ import annotations

from pipeline.production.context import PaperContext
from pipeline.production.extractors.base import FieldExtractor
from pipeline.production.schema import FieldResult


class PaperIdExtractor(FieldExtractor):
    extractor_id = "meta.paper_id"
    version = "0.1.0"
    produces = ("paper_id",)

    def _extract(self, ctx: PaperContext) -> FieldResult:
        return FieldResult(
            extractor_id=self.extractor_id,
            version=self.version,
            status="ok",
            value=ctx.paper_id,
            fields=list(self.produces),
        )
