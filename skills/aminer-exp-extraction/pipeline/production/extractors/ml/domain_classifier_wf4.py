"""domain ML classifier — wf4 variant (reads the wf4 LLM partial).

Identical to ``ml.domain`` except it reads ``ctx.get(WF4_LLM_EXTRACTOR_ID)``
instead of the hardcoded wf8 eid (wf4 stores its LLM 8-field partial under
``llm.wf4_dev20_v2_wash_datasets``). The 7 feature fields are shape-compatible
with the wf8 partial, so ``predict_field`` behavior is unchanged.

The shared ``ml.domain`` extractor is NOT modified (wf1/wf2/wf3 keep reading
``llm.wf8_dev20_v2_wash``).
"""

from __future__ import annotations

from typing import Any

from pipeline.production.adapters.rule_pack import PackImportError
from pipeline.production.adapters.wf4_normalize import method_name_for_ml
from pipeline.production.config import WF4_LLM_EXTRACTOR_ID
from pipeline.production.context import PaperContext
from pipeline.production.extractors.base import FieldExtractor
from pipeline.production.extractors.ml._util import predict_field
from pipeline.production.schema import FieldResult


class DomainClassifierWf4Extractor(FieldExtractor):
    extractor_id = "ml.domain_wf4"
    version = "lr_tfidf_json_features"
    produces = ("domain",)
    depends_on = (
        WF4_LLM_EXTRACTOR_ID,
        "rules.conclusion_limitations",
        "rules.evidence",
    )

    def _extract(self, ctx: PaperContext) -> FieldResult:
        llm = ctx.get(WF4_LLM_EXTRACTOR_ID)
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
        ev_list: list[dict[str, Any]] = (
            (ev.value if ev and ev.status == "ok" else []) or []
        )
        evidence_first: list[str] = (
            ev_list[0].get("evidence", []) if ev_list and isinstance(ev_list[0], dict) else []
        )

        # Prefer first experiment for per-exp fields; paper-level RP stays top-level.
        exp0: dict[str, Any] = {}
        experiments = llm_val.get("experiments")
        if isinstance(experiments, list) and experiments and isinstance(experiments[0], dict):
            exp0 = experiments[0]

        item = {
            "research_problem": llm_val.get("research_problem", ""),
            "research_goal": exp0.get("research_goal", llm_val.get("research_goal", "")),
            "experiment_subject": exp0.get(
                "experiment_subject", llm_val.get("experiment_subject", [])
            ),
            "method": method_name_for_ml(exp0),
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
