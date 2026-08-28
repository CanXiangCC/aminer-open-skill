"""
datasets--策略v4.6--Union (Branch B tiered match + Hybrid gazetteer)

相对 v4.5:
- Branch A: unchanged (DatasetRuleV41 + default gazetteer.json soft match)
- Branch B: _match_gazetteer_tiered (tight first, then controlled bidirectional fallback)
- Branch B gazetteer: gazetteer_hybrid.json (manual ∪ 20K paper_count>=10)
- Merge: same _merge_union, no confidence post-filter
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

project_root = Path(__file__).resolve().parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from experiments.rule_extraction.datasets.shared.dataset_evaluator import (
    normalize_dataset_name,
    normalize_fuzzy,
)
from experiments.rule_extraction.datasets.strategies.v3_gazetteer import DatasetRuleV3
from experiments.rule_extraction.datasets.strategies.v4_1_layered import DatasetRuleV41
from experiments.rule_extraction.datasets.strategies.v4_layered import DatasetRuleV4
from experiments.rule_extraction.datasets.strategies.v4_3_union import _merge_union
from experiments.rule_extraction.datasets.strategies.v4_3_1_union import (
    WEAK_SEMANTIC_BLACKLIST,
    _MIN_CANONICAL_LEN,
    _OVERLAP_RATIO,
)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
GAZETTEER_HYBRID_DEFAULT = DATA_DIR / "gazetteer_hybrid.json"

_FALLBACK_OVERLAP_RATIO = 0.6


def _match_tight_single(candidate: str, gazetteer: list[dict[str, Any]]) -> str | None:
    """Pass 1: single-candidate tight match (same rules as v4.3.1)."""
    candidate_norm = DatasetRuleV3._normalize_name(candidate)
    if not candidate_norm or len(candidate_norm) < 2:
        return None
    if candidate_norm in WEAK_SEMANTIC_BLACKLIST:
        return None

    best: tuple[int, str] | None = None

    for entry in gazetteer:
        canonical_name = entry["canonical_name"]
        canonical_norm = DatasetRuleV3._normalize_name(canonical_name)

        if canonical_norm and len(canonical_norm) >= _MIN_CANONICAL_LEN:
            if canonical_norm not in WEAK_SEMANTIC_BLACKLIST and candidate_norm in canonical_norm:
                overlap = len(candidate_norm)
                if overlap >= _MIN_CANONICAL_LEN and overlap / len(canonical_norm) >= _OVERLAP_RATIO:
                    if best is None or overlap > best[0]:
                        best = (overlap, canonical_name)

        for alias in entry.get("aliases", []):
            alias_norm = DatasetRuleV3._normalize_name(alias)
            if not alias_norm or len(alias_norm) < _MIN_CANONICAL_LEN:
                continue
            if alias_norm in WEAK_SEMANTIC_BLACKLIST:
                continue
            if candidate_norm in alias_norm:
                overlap = len(candidate_norm)
                if overlap >= _MIN_CANONICAL_LEN and overlap / len(alias_norm) >= _OVERLAP_RATIO:
                    if best is None or overlap > best[0]:
                        best = (overlap, canonical_name)

    return best[1] if best else None


def _match_bidirectional_fallback_single(
    candidate: str, gazetteer: list[dict[str, Any]]
) -> str | None:
    """Pass 2: controlled bidirectional substring match for unmatched candidates."""
    candidate_norm = DatasetRuleV3._normalize_name(candidate)
    if not candidate_norm or len(candidate_norm) < _MIN_CANONICAL_LEN:
        return None
    if candidate_norm in WEAK_SEMANTIC_BLACKLIST:
        return None

    matches: list[tuple[int, str]] = []

    for entry in gazetteer:
        canonical_name = entry["canonical_name"]
        canonical_norm = DatasetRuleV3._normalize_name(canonical_name)
        if not canonical_norm or len(canonical_norm) < _MIN_CANONICAL_LEN:
            continue
        if canonical_norm in WEAK_SEMANTIC_BLACKLIST:
            continue

        keys: list[tuple[str, str]] = [(canonical_norm, canonical_name)]
        for alias in entry.get("aliases", []):
            alias_norm = DatasetRuleV3._normalize_name(alias)
            if alias_norm and len(alias_norm) >= _MIN_CANONICAL_LEN:
                if alias_norm not in WEAK_SEMANTIC_BLACKLIST:
                    keys.append((alias_norm, canonical_name))

        for key_norm, canon in keys:
            if key_norm in candidate_norm:
                overlap_len = len(key_norm)
                if overlap_len / len(candidate_norm) >= _FALLBACK_OVERLAP_RATIO:
                    matches.append((overlap_len, canon))
            elif candidate_norm in key_norm:
                overlap_len = len(candidate_norm)
                if overlap_len / len(key_norm) >= _FALLBACK_OVERLAP_RATIO:
                    matches.append((overlap_len, canon))

    if not matches:
        return None
    matches.sort(key=lambda x: x[0], reverse=True)
    return matches[0][1]


def _match_gazetteer_tiered(
    candidates: list[str],
    gazetteer: list[dict[str, Any]],
) -> tuple[list[str], list[dict[str, str]], dict[str, int]]:
    """
    Tiered gazetteer match: tight (Pass 1) then bidirectional fallback (Pass 2).

    Returns:
        after_tiered canonical list,
        match_details [{candidate, canonical, pass}, ...],
        pass_counts {tight, bidirectional_fallback}
    """
    if not gazetteer:
        return [], [], {"tight": 0, "bidirectional_fallback": 0}

    matched_canons: set[str] = set()
    after_tiered: list[str] = []
    match_details: list[dict[str, str]] = []
    pass_counts = {"tight": 0, "bidirectional_fallback": 0}

    unmatched: list[str] = []

    for candidate in candidates:
        canon = _match_tight_single(candidate, gazetteer)
        if canon:
            match_details.append({
                "candidate": candidate,
                "canonical": canon,
                "pass": "tight",
            })
            pass_counts["tight"] += 1
            if canon not in matched_canons:
                matched_canons.add(canon)
                after_tiered.append(canon)
        else:
            unmatched.append(candidate)

    for candidate in unmatched:
        canon = _match_bidirectional_fallback_single(candidate, gazetteer)
        if canon:
            match_details.append({
                "candidate": candidate,
                "canonical": canon,
                "pass": "bidirectional_fallback",
            })
            pass_counts["bidirectional_fallback"] += 1
            if canon not in matched_canons:
                matched_canons.add(canon)
                after_tiered.append(canon)

    return after_tiered, match_details, pass_counts


def _canon_to_pass(match_details: list[dict[str, str]]) -> dict[str, str]:
    """Map canonical name -> first match pass (for gazetteer_only attribution)."""
    out: dict[str, str] = {}
    for detail in match_details:
        canon = detail["canonical"]
        if canon not in out:
            out[canon] = detail["pass"]
    return out


class DatasetRuleV46:
    """Dataset extraction v4.6: v4.5 + Branch B tiered gazetteer match."""

    @staticmethod
    def _load_gazetteer_for_v46() -> list[dict[str, Any]]:
        """Load gazetteer for Branch B: RULE_GAZETTEER_PATH env, else hybrid default."""
        env_path = os.environ.get("RULE_GAZETTEER_PATH")
        if env_path:
            p = Path(env_path)
            if p.exists():
                with open(p, encoding="utf-8") as f:
                    return json.load(f)
        if GAZETTEER_HYBRID_DEFAULT.exists():
            with open(GAZETTEER_HYBRID_DEFAULT, encoding="utf-8") as f:
                return json.load(f)
        return []

    @staticmethod
    def _alias_groups_from_gazetteer(entries: list[dict[str, Any]]) -> dict[str, set[str]]:
        """Build alias groups from the gazetteer used for Branch B merge dedupe."""
        groups: dict[str, set[str]] = {}
        for entry in entries:
            forms: set[str] = set()
            for raw in [entry.get("canonical_name", "")] + list(entry.get("aliases") or []):
                for variant in (normalize_fuzzy(raw), normalize_dataset_name(raw)):
                    if variant:
                        forms.add(variant)
            if not forms:
                continue
            group_key = min(forms)
            if group_key not in groups:
                groups[group_key] = set()
            groups[group_key].update(forms)
        return groups

    @staticmethod
    def extract(paper_md: str, paper_id: str = "") -> dict[str, Any]:
        start = time.perf_counter()
        trace: dict[str, Any] = {
            "version": "v4.6",
            "branch_a": {},
            "branch_b": {},
            "merge": {},
            "timing_ms": {},
            "tightening": {
                "channel_b_context_filter": True,
                "channel_b_table_method_filter": True,
                "branch_b_tiered_match": True,
                "gazetteer_source": "hybrid",
                "gazetteer_hybrid_path": str(GAZETTEER_HYBRID_DEFAULT),
                "min_paper_count": 10,
                "tight_overlap_ratio": _OVERLAP_RATIO,
                "fallback_overlap_ratio": _FALLBACK_OVERLAP_RATIO,
            },
        }

        # Branch A first — uses default gazetteer.json via v41 (must not set env before this).
        t0 = time.perf_counter()
        v41_out = DatasetRuleV41.extract(paper_md, paper_id)
        v41_datasets = v41_out["datasets"]
        v41_trace = v41_out.get("trace", {})
        trace["branch_a"] = {
            "count": len(v41_datasets),
            "names": [d["name"] for d in v41_datasets],
            "trace_ref": {
                "extraction": v41_trace.get("extraction"),
                "timing_ms": v41_trace.get("timing_ms"),
            },
        }
        trace["timing_ms"]["branch_a"] = round((time.perf_counter() - t0) * 1000, 2)

        t1 = time.perf_counter()
        loose_names, loose_trace = DatasetRuleV4.extract_loose_candidate_names(
            paper_md,
            require_context=True,
            filter_table_method_rows=True,
        )
        gazetteer = DatasetRuleV46._load_gazetteer_for_v46()
        after_tiered, match_details, pass_counts = _match_gazetteer_tiered(loose_names, gazetteer)
        after_tight = [d["canonical"] for d in match_details if d["pass"] == "tight"]
        # dedupe after_tight preserving order
        seen_tight: set[str] = set()
        after_tight_unique: list[str] = []
        for c in after_tight:
            if c not in seen_tight:
                seen_tight.add(c)
                after_tight_unique.append(c)
        after_blacklist = DatasetRuleV3._filter_blacklist(after_tiered)
        trace["branch_b"] = {
            "loose_candidates": loose_names,
            "loose_count": len(loose_names),
            "after_tight": after_tight_unique,
            "after_tiered": after_tiered,
            "after_blacklist": after_blacklist,
            "match_details": match_details,
            "pass_counts": pass_counts,
            "gazetteer_entry_count": len(gazetteer),
            "layer_a": loose_trace.get("layer_a"),
            "layer_b": loose_trace.get("layer_b"),
        }
        trace["timing_ms"]["branch_b"] = round((time.perf_counter() - t1) * 1000, 2)

        t2 = time.perf_counter()
        alias_groups = DatasetRuleV46._alias_groups_from_gazetteer(gazetteer)
        merged, merge_trace = _merge_union(v41_datasets, after_blacklist, alias_groups)
        trace["merge"] = merge_trace
        trace["timing_ms"]["merge"] = round((time.perf_counter() - t2) * 1000, 2)

        canon_pass = _canon_to_pass(match_details)
        gaz_only_tight = sum(
            1 for c in merge_trace["gazetteer_only"] if canon_pass.get(c) == "tight"
        )
        gaz_only_fallback = sum(
            1 for c in merge_trace["gazetteer_only"] if canon_pass.get(c) == "bidirectional_fallback"
        )

        trace["final"] = [d["name"] for d in merged]
        trace["timing_ms"]["strategy_total"] = round((time.perf_counter() - start) * 1000, 2)
        trace["extraction"] = {
            "branch_a_count": len(v41_datasets),
            "branch_b_gazetteer_count": len(after_blacklist),
            "merged_count": len(merged),
            "v4_1_only": len(merge_trace["v4_1_only"]),
            "gazetteer_only": len(merge_trace["gazetteer_only"]),
            "both": len(merge_trace["both"]),
            "branch_b_tight_count": pass_counts["tight"],
            "branch_b_fallback_count": pass_counts["bidirectional_fallback"],
            "gazetteer_only_tight": gaz_only_tight,
            "gazetteer_only_fallback": gaz_only_fallback,
        }

        return {"datasets": merged, "trace": trace}


if __name__ == "__main__":
    sample = """
# 4.1 Datasets
We use the benchmark dataset ShapeNet-ViPC [3]. We also evaluate on LFW [1] and VGGFace2 [2].
ImageNet [4] is a general benchmark. ResNet [5] is a model.
"""
    out = DatasetRuleV46.extract(sample, "test")
    print(json.dumps(out, indent=2, ensure_ascii=False))
