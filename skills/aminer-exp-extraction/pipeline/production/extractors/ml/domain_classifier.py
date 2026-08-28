"""domain ML classifier (paper-level).

Uses JSON features (research_problem / research_goal / experiment_subject /
method / conclusion / evidence) — NOT the predict.py MD path. Depends on
conclusion + evidence + LLM, so runs in Wave-3 (serialized after evidence;
monitor records ``domain_blocked_by=evidence``).
"""

from __future__ import annotations

from typing import Any

from pipeline.production.adapters.rule_pack import PackImportError
from pipeline.production.context import PaperContext
from pipeline.production.extractors.base import FieldExtractor
from pipeline.production.extractors.ml._util import predict_field
from pipeline.production.schema import FieldResult


class DomainClassifierExtractor(FieldExtractor):
    extractor_id = "ml.domain"
    version = "lr_tfidf_json_features"
    produces = ("domain",)
    depends_on = (
        "llm.wf8_dev20_v2_wash",
        "rules.conclusion_limitations",
        "rules.evidence",
    )

    def _extract(self, ctx: PaperContext) -> FieldResult:
        llm = ctx.get("llm.wf8_dev20_v2_wash")
        cl = ctx.get("rules.conclusion_limitations")
        ev = ctx.get("rules.evidence")

        if not llm or llm.status != "ok":
            return FieldResult(
                extractor_id=self.extractor_id,
                version=self.version,
                status="error",
                error="LLM partial missing — cannot build domain features",
                fields=list(self.produces),
                metadata={"domain_blocked_by": "llm"},
            )

        llm_val: dict[str, Any] = llm.value or {}
        cl_val: dict[str, Any] = (cl.value if cl and cl.status == "ok" else {}) or {}
        # evidence partial is list[dict] each carrying `evidence`; single exp -> [0].
        ev_list: list[dict[str, Any]] = (
            (ev.value if ev and ev.status == "ok" else []) or []
        )
        evidence_first: list[str] = (
            ev_list[0].get("evidence", []) if ev_list and isinstance(ev_list[0], dict) else []
        )

        item = {
            "research_problem": llm_val.get("research_problem", ""),
            "research_goal": llm_val.get("research_goal", ""),
            "experiment_subject": llm_val.get("experiment_subject", []),
            "method": llm_val.get("method", ""),
            "conclusion": cl_val.get("conclusion", ""),
            "evidence": evidence_first,
        }

        try:
            label, confidence = predict_field("domain", item, prepare="domain")
        except PackImportError as exc:
            return FieldResult(
                extractor_id=self.extractor_id,
                version=self.version,
                status="error",
                error=str(exc),
                fields=list(self.produces),
                metadata={"domain_blocked_by": "evidence"},
            )

        return FieldResult(
            extractor_id=self.extractor_id,
            version=self.version,
            status="ok",
            value=label,
            fields=list(self.produces),
            metadata={
                "confidence": confidence,
                "feature_path": "json",
                "domain_blocked_by": "evidence",
            },
        )
