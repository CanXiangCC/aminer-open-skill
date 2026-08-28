"""Production Merger for wf4 (LLM multi-exp + datasets).

``MergerWf4`` subclasses ``ProductionMerger`` and overrides ``_build_experiments``
+ ``_build_provenance``. Semantic differences from wf3:

  - ``datasets`` is owned by the LLM partial (``llm.wf4_dev20_v2_wash_datasets``),
    read per experiment from ``llm.value["experiments"][i]["datasets"]``.
  - ``sample_size`` is owned by ``rules.sample_size_policy_wf4``.
  - 1 paper -> 1..3 experiments (hard-capped upstream). Non-LLM paper-level
    fields are copied onto every experiment. Empty LLM / parse-error -> [].

The meta / conclusion-limitations / evidence branches
mirror ``ProductionMerger._build_experiments`` but fan out across N experiments.
``domain`` (paper-level) and ``experiment_type`` (per experiment) are owned by
the wf4 LLM partial.
"""

from __future__ import annotations

from typing import Any

from pipeline.production.config import WF4_LLM_EXTRACTOR_ID
from pipeline.production.context import PaperContext
from pipeline.production.merge import ProductionMerger
from pipeline.production.schema import empty_experiment

# Per-experiment LLM fields (research_problem* and domain stay paper-level).
_LLM_EXP_FIELDS = (
    "experiment_name",
    "experiment_type",
    "research_goal",
    "experiment_subject",
    "methods",
    "key_results",
    "metrics",
)

# wf4 field ownership: datasets -> LLM, sample_size -> rules.sample_size_policy_wf4.
_FIELD_OWNER_WF4 = {
    "experiment_name": WF4_LLM_EXTRACTOR_ID,
    "research_problem": WF4_LLM_EXTRACTOR_ID,
    "research_goal": WF4_LLM_EXTRACTOR_ID,
    "experiment_subject": WF4_LLM_EXTRACTOR_ID,
    "methods": WF4_LLM_EXTRACTOR_ID,
    "key_results": WF4_LLM_EXTRACTOR_ID,
    "metrics": WF4_LLM_EXTRACTOR_ID,
    "datasets": WF4_LLM_EXTRACTOR_ID,
    "paper_id": "meta.paper_id",
    "_id": "meta.placeholder",
    "experiment_history": "meta.placeholder",
    "score": "meta.placeholder",
    "conclusion": "rules.conclusion_limitations",
    "limitations": "rules.conclusion_limitations",
    "sample_size": "rules.sample_size_policy_wf4",
    "evidence": "rules.evidence",
    "domain": WF4_LLM_EXTRACTOR_ID,
    "experiment_type": WF4_LLM_EXTRACTOR_ID,
}


def _resolve_llm_experiments(llm_val: dict[str, Any]) -> list[dict[str, Any]]:
    """Return experiment dicts from new multi-exp shape or old flat compat."""
    experiments = llm_val.get("experiments")
    if isinstance(experiments, list) and experiments:
        return [e for e in experiments if isinstance(e, dict)]
    # Flat-compat fallback (should already be wrapped in Stage-B).
    if any(
        llm_val.get(k) not in (None, "", [], {})
        for k in ("experiment_name", "methods", "datasets", "key_results")
    ):
        return [
            {
                "experiment_name": llm_val.get("experiment_name", ""),
                "key_results": llm_val.get("key_results", []),
                "methods": llm_val.get("methods", []),
                "research_goal": llm_val.get("research_goal", ""),
                "experiment_subject": llm_val.get("experiment_subject", []),
                "metrics": llm_val.get("metrics", []),
                "datasets": llm_val.get("datasets", []),
                "experiment_type": llm_val.get("experiment_type", ""),
            }
        ]
    return []


class MergerWf4(ProductionMerger):
    """wf4 merger: 1 paper -> 1..3 experiments; datasets from LLM partial."""

    def _build_experiments(
        self, ctx: PaperContext, conflicts: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """1 paper -> 1..3 experiments with shared non-LLM paper-level fields.

        Empty LLM / error / no usable experiments -> [] (do not fabricate).
        """
        self._dry_run = ctx.dry_run
        llm = ctx.get(WF4_LLM_EXTRACTOR_ID)
        llm_val: dict[str, Any] = (llm.value if llm and llm.status == "ok" else {}) or {}
        llm_experiments = _resolve_llm_experiments(llm_val) if isinstance(llm_val, dict) else []

        if not llm or llm.status != "ok":
            if not getattr(self, "_dry_run", False):
                conflicts.append(
                    {
                        "field_group": "llm",
                        "issue": "llm partial missing or error",
                        "extractor": WF4_LLM_EXTRACTOR_ID,
                    }
                )
            return []
        # EXT-02: ok + empty experiments is valid (no fabricate, no conflict).
        if not llm_experiments:
            return []

        # --- shared paper-level non-LLM fields (copied onto every experiment) ---
        paper_id = ctx.paper_id
        pid = ctx.get("meta.paper_id")
        if pid and pid.status == "ok":
            paper_id = pid.value or ctx.paper_id

        meta_id = ""
        meta_history: list[Any] = []
        meta_score = None
        ph = ctx.get("meta.placeholder")
        if ph and ph.status == "ok" and isinstance(ph.value, dict):
            meta_id = ph.value.get("_id", "")
            meta_history = ph.value.get("experiment_history", [])
            meta_score = ph.value.get("score")

        conclusion = ""
        limitations = ""
        cl = ctx.get("rules.conclusion_limitations")
        if cl and cl.status == "ok" and isinstance(cl.value, dict):
            conclusion = cl.value.get("conclusion", "")
            limitations = cl.value.get("limitations", "")
        else:
            self._record_error(conflicts, "rules.conclusion_limitations", ["conclusion", "limitations"])

        sample_size = None
        ss = ctx.get("rules.sample_size_policy_wf4")
        if ss and ss.status == "ok":
            sample_size = ss.value
        else:
            self._record_error(conflicts, "rules.sample_size_policy_wf4", ["sample_size"])

        # rules.evidence returns one result per input experiment, in the same
        # order (extractor iterates experiments_stripped and appends 1:1).
        evidence_per_exp: list[list[Any]] = []
        ev = ctx.get("rules.evidence")
        if ev and ev.status == "ok" and isinstance(ev.value, list) and ev.value:
            for item in ev.value:
                evidence_per_exp.append(
                    list(item.get("evidence", [])) if isinstance(item, dict) else []
                )
            if len(evidence_per_exp) != len(llm_experiments):
                conflicts.append(
                    {
                        "field_group": "rules.evidence",
                        "issue": (
                            f"evidence results ({len(evidence_per_exp)}) != "
                            f"experiments ({len(llm_experiments)})"
                        ),
                        "extractor": "rules.evidence",
                    }
                )
        else:
            self._record_error(conflicts, "rules.evidence", ["evidence"])

        domain = ""
        if isinstance(llm_val, dict):
            domain = llm_val.get("domain") or ""

        out: list[dict[str, Any]] = []
        for i, llm_exp in enumerate(llm_experiments):
            exp = empty_experiment(paper_id)
            for f in _LLM_EXP_FIELDS:
                exp[f] = llm_exp.get(f, exp[f])
            exp.pop("research_problem", None)
            exp["datasets"] = llm_exp.get("datasets", []) if isinstance(llm_exp, dict) else []

            exp["paper_id"] = paper_id
            exp["_id"] = meta_id
            exp["experiment_history"] = meta_history
            exp["score"] = meta_score
            exp["conclusion"] = conclusion
            exp["limitations"] = limitations
            exp["sample_size"] = sample_size
            exp["evidence"] = evidence_per_exp[i] if i < len(evidence_per_exp) else []
            exp["domain"] = domain
            out.append(exp)

        return out

    def _build_provenance(
        self, ctx: PaperContext, experiments: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for _exp in experiments:
            sources: dict[str, Any] = {}
            for field, owner_id in _FIELD_OWNER_WF4.items():
                partial = ctx.get(owner_id)
                sources[field] = {
                    "extractor_id": owner_id,
                    "version": partial.version if partial else None,
                    "status": partial.status if partial else "missing",
                }
            out.append({"extraction_sources": sources, "experimental": True})
        return out
