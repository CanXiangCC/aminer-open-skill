"""Extractor base class.

Every Task in the DAG is an Extractor: a swappable unit identified by
``extractor_id`` + ``version``. The orchestrator resolves extractors by id from
the registry and calls ``extract(ctx)``; swapping v4_3 -> v4_5 means changing
one registry line, never the orchestrator.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod

from pipeline.production.context import PaperContext
from pipeline.production.schema import FieldResult


class FieldExtractor(ABC):
    """Abstract Extractor."""

    extractor_id: str = "base"
    version: str = "0.0.0"
    produces: tuple[str, ...] = ()  # field paths this extractor contributes to
    depends_on: tuple[str, ...] = ()  # extractor_ids that must run first

    @abstractmethod
    def _extract(self, ctx: PaperContext) -> FieldResult:
        """Run the real extraction. Subclasses implement this."""
        ...

    def _stub(self, ctx: PaperContext) -> FieldResult:
        """Dry-run stub: return an ok-marked FieldResult with empty value."""
        return FieldResult(
            extractor_id=self.extractor_id,
            version=self.version,
            status="stub",
            value=None,
            fields=list(self.produces),
            metadata={"reason": "dry_run"},
        )

    def extract(self, ctx: PaperContext) -> FieldResult:
        """Public entry point: times the run, captures errors, never raises.

        On dry-run, returns the stub. On exception, returns a FieldResult with
        status="error" so the monitor records it and the Merger falls back to
        empty values — never a silent fallback to fake data.
        """
        if ctx.dry_run:
            return self._stub(ctx)

        start = time.perf_counter()
        try:
            result = self._extract(ctx)
            result.elapsed_sec = time.perf_counter() - start
            return result
        except Exception as exc:  # noqa: BLE001 — record, do not raise
            return FieldResult(
                extractor_id=self.extractor_id,
                version=self.version,
                status="error",
                value=None,
                elapsed_sec=time.perf_counter() - start,
                error=f"{type(exc).__name__}: {exc}",
                fields=list(self.produces),
            )
