"""experiment_type ML classifier — wf4 variant (reads the wf4 LLM partial).

Identical to ``ml.experiment_type`` except it reads ``ctx.get(WF4_LLM_EXTRACTOR_ID)``
instead of the hardcoded wf8 eid. Feature shape is compatible (the 7 LLM fields
+ experiments_stripped built by ``_build_base_experiments_wf4``). The shared
``ml.experiment_type`` extractor is NOT modified.
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


class ExperimentTypeClassifierWf4Extractor(FieldExtractor):
    extractor_id = "ml.experiment_type_wf4"
    version = "lr_tfidf_json_features"
    produces = ("experiment_type",)
    depends_on = (WF4_LLM_EXTRACTOR_ID, "rules.evidence")

    def _extract(self, ctx: PaperContext) -> FieldResult:
        llm = ctx.get(WF4_LLM_EXTRACTOR_ID)
        ev = ctx.get("rules.evidence")
        if not llm or llm.status != "ok":
            return FieldResult(
                extractor_id=self.extractor_id,
                version=self.version,
                status="error",
                error="LLM partial missing — cannot build experiment_type features",
                fields=list(self.produces),
            )

        llm_val: dict[str, Any] = llm.value or {}
        ev_list: list[dict[str, Any]] = (
            (ev.value if ev and ev.status == "ok" else []) or []
        )
        # Build a per-experiment item list. v0.1.0 = single experiment.
        experiments_in: list[dict[str, Any]] = []
        if ctx.experiments_stripped:
            for idx, exp in enumerate(ctx.experiments_stripped):
                ev_evidence: list[str] = (
                    ev_list[idx].get("evidence", [])
                    if idx < len(ev_list) and isinstance(ev_list[idx], dict)
                    else []
                )
                experiments_in.append(
                    {
                        "experiment_name": exp.get("experiment_name", ""),
                        "method": method_name_for_ml(exp),
                        "key_results": exp.get("key_results", []),
                        "evidence": ev_evidence,
                    }
                )
        else:
            # Fallback: first LLM experiment (multi-exp) or old flat keys.
            exp0: dict[str, Any] = {}
            experiments = llm_val.get("experiments")
            if (
                isinstance(experiments, list)
                and experiments
                and isinstance(experiments[0], dict)
            ):
                exp0 = experiments[0]
            experiments_in.append(
                {
                    "experiment_name": exp0.get(
                        "experiment_name", llm_val.get("experiment_name", "")
                    ),
                    "method": method_name_for_ml(exp0),
                    "key_results": exp0.get(
                        "key_results", llm_val.get("key_results", [])
                    ),
                    "evidence": (
                        ev_list[0].get("evidence", [])
                        if ev_list and isinstance(ev_list[0], dict)
                        else []
                    ),
                }
            )

        out: list[dict[str, Any]] = []
        try:
            for item in experiments_in:
                label, confidence = predict_field(
                    "experiment_type", item, prepare="experiment_type"
                )
                out.append({**item, "experiment_type": label, "_confidence": confidence})
        except PackImportError as exc:
            return FieldResult(
                extractor_id=self.extractor_id,
                version=self.version,
                status="error",
                error=str(exc),
                fields=list(self.produces),
            )

        return FieldResult(
            extractor_id=self.extractor_id,
            version=self.version,
            status="ok",
            value=out,  # list[dict] each with experiment_type
            fields=list(self.produces),
            metadata={
                "experiment_count": len(out),
                "feature_path": "json",
            },
        )
