"""
v2_type_aware assignment strategy.

Improvements over v1_cooccurrence:
  - field_study: forced datasets=[] before any cooccurrence/inheritance
  - ablation: three-tier (blob cooccurrence -> inherit main.datasets -> single mainline -> empty)
  - Pass A: comparison/other only; section-scoped window hits (no cross-section bleed)
  - ablation excluded from primary fallback and broadcast
"""

from __future__ import annotations

from typing import Any

from .base import AssignStrategy
from .helpers import (
    classify_experiment,
    dataset_name_variants,
    experiment_name_tokens,
    experiment_text_blob,
    find_mentions,
    fuzzy_in_blob,
    is_pass_a_eligible,
    pick_fallback_target,
)
from .pairing import (
    build_section_spans,
    find_main_exp_for,
    section_window_hit,
)
from experiments.rule_extraction.datasets.shared.dataset_evaluator import _load_gazetteer_aliases


class AssignV2TypeAware(AssignStrategy):
    name = "v2_type_aware"

    def assign(
        self,
        paper_datasets: list[dict[str, Any]],
        experiments: list[dict[str, Any]],
        md_text: str,
        *,
        paper_id: str = "",
    ) -> list[dict[str, Any]]:
        alias_groups = _load_gazetteer_aliases()
        md_lower = (md_text or "").lower()
        sections = build_section_spans(md_text or "")

        exp_meta: list[dict[str, Any]] = []
        for idx, exp in enumerate(experiments):
            exp_meta.append({
                "idx": idx,
                "tokens": experiment_name_tokens(exp.get("experiment_name") or ""),
                "blob": experiment_text_blob(exp),
                "klass": classify_experiment(exp),
            })

        out: list[dict[str, Any]] = []
        for exp in experiments:
            out.append({**exp, "datasets": [], "assignment_trace": {
                "strategy": self.name,
                "rule_hits": [],
                "fallback_used": "none",
                "broadcast_triggered": False,
            }})

        # Step 1: field_study strong shield — forced empty, skip all further rules.
        field_study_indices: set[int] = set()
        for meta in exp_meta:
            if meta["klass"] == "field_study":
                field_study_indices.add(meta["idx"])
                out[meta["idx"]]["assignment_trace"]["rule"] = "field_study_forced_empty"
                out[meta["idx"]]["assignment_trace"]["experiment_class"] = "field_study"

        # Step 2: single-experiment short circuit (non-field_study only).
        if len(experiments) == 1:
            if field_study_indices:
                return out
            out[0]["datasets"] = [dict(d) for d in paper_datasets]
            out[0]["assignment_trace"]["fallback_used"] = "single_experiment"
            out[0]["assignment_trace"]["experiment_class"] = exp_meta[0]["klass"]
            return out

        # Step 3: Pass A — cooccurrence + fallback + broadcast for comparison/other only.
        pass_a_indices = {
            m["idx"] for m in exp_meta
            if is_pass_a_eligible(m["klass"])
        }
        unmatched: list[dict[str, Any]] = []

        for ds in paper_datasets:
            ds_copy = dict(ds)
            names = dataset_name_variants(ds)
            blob_hits: list[dict[str, Any]] = []
            window_hits: list[dict[str, Any]] = []

            for idx in pass_a_indices:
                meta = exp_meta[idx]
                md_hit = False
                section_title: str | None = None
                if meta["tokens"]:
                    mention_positions: list[int] = []
                    for nm in names:
                        mention_positions.extend(find_mentions(md_lower, nm))
                    if mention_positions:
                        md_hit, section_title = section_window_hit(
                            sections, md_lower, mention_positions, meta["tokens"]
                        )
                blob_hit = False
                if meta["blob"]:
                    for nm in names:
                        if fuzzy_in_blob(meta["blob"], nm, alias_groups):
                            blob_hit = True
                            break
                if blob_hit:
                    blob_hits.append({
                        "exp_index": idx, "rule": "blob_match",
                        "blob_hit": True, "md_hit": md_hit,
                        "section_title": section_title,
                    })
                elif md_hit:
                    window_hits.append({
                        "exp_index": idx, "rule": "md_section_window",
                        "blob_hit": False, "md_hit": True,
                        "section_title": section_title,
                    })

            hits = blob_hits if blob_hits else window_hits
            if hits:
                for h in hits:
                    out[h["exp_index"]]["datasets"].append(dict(ds_copy))
                    out[h["exp_index"]]["assignment_trace"]["rule_hits"].append({
                        "dataset": ds.get("name"),
                        **h,
                    })
            else:
                unmatched.append(ds_copy)

        # Primary fallback — comparison/other targets only (via pick_fallback_target).
        fallback_target = pick_fallback_target(exp_meta)
        if unmatched and fallback_target is not None:
            for ds in unmatched:
                out[fallback_target]["datasets"].append(dict(ds))
                out[fallback_target]["assignment_trace"]["rule_hits"].append({
                    "dataset": ds.get("name"),
                    "exp_index": fallback_target,
                    "rule": "primary_fallback",
                })
            out[fallback_target]["assignment_trace"]["fallback_used"] = "primary"
            unmatched = []

        # Broadcast — only to Pass A eligible experiments; never ablation/field_study.
        has_field_study = bool(field_study_indices)
        if unmatched and not has_field_study and pass_a_indices:
            for ds in unmatched:
                for idx in pass_a_indices:
                    out[idx]["datasets"].append(dict(ds))
                    out[idx]["assignment_trace"]["rule_hits"].append({
                        "dataset": ds.get("name"),
                        "rule": "broadcast",
                    })
                    out[idx]["assignment_trace"]["broadcast_triggered"] = True
                    out[idx]["assignment_trace"]["fallback_used"] = "broadcast"
            unmatched = []

        if unmatched:
            for idx in pass_a_indices:
                out[idx]["assignment_trace"]["dropped_unmatched"] = [
                    d.get("name") for d in unmatched
                ]

        # Step 4: Pass B — ablation three-tier assignment.
        for meta in exp_meta:
            if meta["klass"] != "ablation":
                continue
            idx = meta["idx"]
            cooccurring: list[dict[str, Any]] = []
            for ds in paper_datasets:
                names = dataset_name_variants(ds)
                if meta["blob"]:
                    for nm in names:
                        if fuzzy_in_blob(meta["blob"], nm, alias_groups):
                            cooccurring.append(dict(ds))
                            break

            if cooccurring:
                out[idx]["datasets"] = cooccurring
                out[idx]["assignment_trace"]["rule"] = "ablation_blob_cooccurrence"
                out[idx]["assignment_trace"]["rule_hits"].extend([
                    {"dataset": d.get("name"), "exp_index": idx, "rule": "ablation_blob_cooccurrence"}
                    for d in cooccurring
                ])
                continue

            main_idx = find_main_exp_for(idx, experiments, exp_meta, sections, out)
            if main_idx is not None and out[main_idx]["datasets"]:
                out[idx]["datasets"] = [dict(d) for d in out[main_idx]["datasets"]]
                out[idx]["assignment_trace"]["rule"] = "ablation_inherit_main"
                out[idx]["assignment_trace"]["inherited_from"] = main_idx
                out[idx]["assignment_trace"]["rule_hits"].append({
                    "rule": "ablation_inherit_main",
                    "inherited_from": main_idx,
                    "datasets": [d.get("name") for d in out[idx]["datasets"]],
                })
                continue

            comparison_indices = [m["idx"] for m in exp_meta if m["klass"] == "comparison"]
            if len(comparison_indices) == 1:
                main_idx = comparison_indices[0]
                if out[main_idx]["datasets"]:
                    out[idx]["datasets"] = [dict(d) for d in out[main_idx]["datasets"]]
                    out[idx]["assignment_trace"]["rule"] = "ablation_inherit_single_mainline"
                    out[idx]["assignment_trace"]["inherited_from"] = main_idx
                    continue

            out[idx]["datasets"] = []
            out[idx]["assignment_trace"]["rule"] = "ablation_no_main_fallback_empty"

        for meta, exp_out in zip(exp_meta, out):
            if "experiment_class" not in exp_out["assignment_trace"]:
                exp_out["assignment_trace"]["experiment_class"] = meta["klass"]

        return out
