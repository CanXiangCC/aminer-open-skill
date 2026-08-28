"""experiment_type ML classifier (per-experiment).

Uses JSON features (experiment_name / evidence / method / key_results) per
experiment — NOT the predict.py MD path. Runs in Wave-3 after evidence; the
orchestrator fans one prediction out per experiment (single-experiment in
v0.1.0). Returns a list[dict] mirroring the input experiments with an added
``experiment_type`` key.
"""

from __future__ import annotations

from typing import Any

from pipeline.production.adapters.rule_pack import PackImportError
from pipeline.production.context import PaperContext
from pipeline.production.extractors.base import FieldExtractor
from pipeline.production.extractors.ml._util import predict_field
from pipeline.production.schema import FieldResult


class ExperimentTypeClassifierExtractor(FieldExtractor):
    extractor_id = "ml.experiment_type"
    version = "lr_tfidf_json_features"
    produces = ("experiment_type",)
    depends_on = ("llm.wf8_dev20_v2_wash", "rules.evidence")

    def _extract(self, ctx: PaperContext) -> FieldResult:
        llm = ctx.get("llm.wf8_dev20_v2_wash")
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
                        "method": exp.get("method", ""),
                        "key_results": exp.get("key_results", []),
                        "evidence": ev_evidence,
                    }
                )
        else:
            experiments_in.append(
                {
                    "experiment_name": llm_val.get("experiment_name", ""),
                    "method": llm_val.get("method", ""),
                    "key_results": llm_val.get("key_results", []),
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
