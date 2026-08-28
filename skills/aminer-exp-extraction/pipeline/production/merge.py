"""Production Merger.

Field ownership is disjoint (LLM_FIELDS vs RULE_FIELDS vs META_FIELDS — see
schema.py), so there are no real conflicts; the conflict log records any
anomaly (e.g. an extractor in error state whose field falls back to default).

This is the source of truth — the pack ``merger.py`` is NOT called (its
LLM_FIELDS list is stale: it still lists datasets/conclusion/limitations/
evidence as LLM-owned).
"""

from __future__ import annotations

from typing import Any

from pipeline.production.context import PaperContext
from pipeline.production.schema import (
    LLM_FIELDS,
    META_FIELDS,
    RULE_FIELDS,
    empty_experiment,
)

# Map each field -> the extractor_id that owns it (for provenance).
_FIELD_OWNER = {
    "experiment_name": "llm.wf8_dev20_v2_wash",
    "research_problem": "llm.wf8_dev20_v2_wash",
    "research_goal": "llm.wf8_dev20_v2_wash",
    "experiment_subject": "llm.wf8_dev20_v2_wash",
    "method": "llm.wf8_dev20_v2_wash",
    "key_results": "llm.wf8_dev20_v2_wash",
    "metrics": "llm.wf8_dev20_v2_wash",
    "paper_id": "meta.paper_id",
    "_id": "meta.placeholder",
    "experiment_history": "meta.placeholder",
    "score": "meta.placeholder",
    "conclusion": "rules.conclusion_limitations",
    "limitations": "rules.conclusion_limitations",
    "sample_size": "rules.sample_size_policy",
    "datasets": "rules.datasets.assign",
    "evidence": "rules.evidence",
    "domain": "ml.domain",
    "experiment_type": "ml.experiment_type",
}


class ProductionMerger:
    """Merges extractor partials into the final experiment[] array."""

    def merge(self, ctx: PaperContext) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        """Return (experiments, provenance_per_exp, merge_conflicts)."""
        self._dry_run = ctx.dry_run
        conflicts: list[dict[str, Any]] = []
        experiments = self._build_experiments(ctx, conflicts)
        provenance = self._build_provenance(ctx, experiments)
        return experiments, provenance, conflicts

    # ------------------------------------------------------------------ build

    def _build_experiments(
        self, ctx: PaperContext, conflicts: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """v0.1.0: 1 paper -> 1 experiment. Multi-exp reserved."""
        exp = empty_experiment(ctx.paper_id)

        # --- LLM group ---
        llm = ctx.get("llm.wf8_dev20_v2_wash")
        llm_val: dict[str, Any] = (llm.value if llm and llm.status == "ok" else {}) or {}
        for f in LLM_FIELDS:
            exp[f] = llm_val.get(f, exp[f])
        if not llm or llm.status != "ok":
            if not getattr(self, "_dry_run", False):
                conflicts.append(
                    {"field_group": "llm", "issue": "llm partial missing or error", "extractor": "llm.wf8_dev20_v2_wash"}
                )

        # --- meta ---
        pid = ctx.get("meta.paper_id")
        if pid and pid.status == "ok":
            exp["paper_id"] = pid.value or ctx.paper_id
        ph = ctx.get("meta.placeholder")
        if ph and ph.status == "ok" and isinstance(ph.value, dict):
            exp["_id"] = ph.value.get("_id", "")
            exp["experiment_history"] = ph.value.get("experiment_history", [])
            exp["score"] = ph.value.get("score")

        # --- conclusion / limitations ---
        cl = ctx.get("rules.conclusion_limitations")
        if cl and cl.status == "ok" and isinstance(cl.value, dict):
            exp["conclusion"] = cl.value.get("conclusion", "")
            exp["limitations"] = cl.value.get("limitations", "")
        else:
            self._record_error(conflicts, "rules.conclusion_limitations", ["conclusion", "limitations"])

        # --- sample_size ---
        ss = ctx.get("rules.sample_size_policy")
        if ss and ss.status == "ok":
            exp["sample_size"] = ss.value
        else:
            self._record_error(conflicts, "rules.sample_size_policy", ["sample_size"])

        # --- datasets (from assign; per-experiment) ---
        assign = ctx.get("rules.datasets.assign")
        if assign and assign.status == "ok" and isinstance(assign.value, list) and assign.value:
            first = assign.value[0]
            exp["datasets"] = first.get("datasets", []) if isinstance(first, dict) else []
        else:
            self._record_error(conflicts, "rules.datasets.assign", ["datasets"])
            # extract-only fallback: paper_datasets unassigned (still populated).
            ex = ctx.get("rules.datasets.extract")
            if ex and ex.status == "ok" and isinstance(ex.value, list):
                exp["datasets"] = list(ex.value)

        # --- evidence (per-experiment) ---
        ev = ctx.get("rules.evidence")
        if ev and ev.status == "ok" and isinstance(ev.value, list) and ev.value:
            first = ev.value[0]
            exp["evidence"] = first.get("evidence", []) if isinstance(first, dict) else []
        else:
            self._record_error(conflicts, "rules.evidence", ["evidence"])

        # --- domain (paper-level) ---
        dom = ctx.get("ml.domain")
        if dom and dom.status == "ok":
            exp["domain"] = dom.value or ""
        else:
            self._record_error(conflicts, "ml.domain", ["domain"])

        # --- experiment_type (per-experiment) ---
        et = ctx.get("ml.experiment_type")
        if et and et.status == "ok" and isinstance(et.value, list) and et.value:
            first = et.value[0]
            exp["experiment_type"] = first.get("experiment_type", "") if isinstance(first, dict) else ""
        else:
            self._record_error(conflicts, "ml.experiment_type", ["experiment_type"])

        return [exp]

    def _build_provenance(
        self, ctx: PaperContext, experiments: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for _exp in experiments:
            sources: dict[str, Any] = {}
            for field, owner_id in _FIELD_OWNER.items():
                partial = ctx.get(owner_id)
                sources[field] = {
                    "extractor_id": owner_id,
                    "version": partial.version if partial else None,
                    "status": partial.status if partial else "missing",
                }
            out.append({"extraction_sources": sources})
        return out

    # ------------------------------------------------------------------ utils

    def _record_error(
        self, conflicts: list[dict[str, Any]], extractor_id: str, fields: list[str]
    ) -> None:
        # In dry-run every extractor is a stub by design — not a real conflict.
        if getattr(self, "_dry_run", False):
            return
        conflicts.append(
            {
                "extractor": extractor_id,
                "fields": fields,
                "issue": "extractor missing or error; field falls back to default",
            }
        )

    def expand_multi_experiment(self, ctx: PaperContext) -> list[dict[str, Any]]:
        """Reserved for multi-experiment expansion (future wf). v0.1.0 unused."""
        raise NotImplementedError("multi-experiment expansion reserved for post-v0.1.0")


def merge_fields_summary() -> dict[str, list[str]]:
    """Return the field-ownership summary (for docs / manifest)."""
    return {
        "llm": list(LLM_FIELDS),
        "rules": list(RULE_FIELDS),
        "meta": list(META_FIELDS),
    }
