"""
datasets--策略v4.3.1--Union (语境过滤 + 表格行过滤 + Gazetteer硬过滤收紧)

相对 v4.2（原始 gazetteer，不扩充）：
- Channel B: abbrev_ref/camel_case 要求 dataset/benchmark 语境
- Channel B: 表格行过滤 method/metric 表头
- Gazetteer 硬过滤收紧：
  - canonical normalized 长度 >= 4
  - 弱语义黑名单 (other/lbp/fasd/npu/gabor/deepface/aid/sun/ar)
  - overlap 比例 0.5 -> 0.7
  - 只允许 candidate ⊂ canonical 单向子串
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

project_root = Path(__file__).resolve().parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from experiments.rule_extraction.datasets.shared.dataset_evaluator import (
    _load_gazetteer_aliases,
    normalize_fuzzy,
)
from experiments.rule_extraction.datasets.strategies.v3_gazetteer import DatasetRuleV3
from experiments.rule_extraction.datasets.strategies.v4_1_layered import DatasetRuleV41
from experiments.rule_extraction.datasets.strategies.v4_layered import DatasetRuleV4

WEAK_SEMANTIC_BLACKLIST = {
    "other", "lbp", "fasd", "npu", "gabor", "deepface", "aid", "sun", "ar",
    "lbp", "fasd", "npu", "gabor", "deepface", "aid", "sun", "ar",
}

_MIN_CANONICAL_LEN = 4
_OVERLAP_RATIO = 0.7


def _match_gazetteer_tight(
    candidates: list[str], gazetteer: list[dict[str, Any]]
) -> list[str]:
    """
    v4.3.1 tightened gazetteer hard filter:
    - canonical/alias normalized length >= 4
    - weak semantic blacklist
    - overlap ratio >= 0.7
    - only candidate_norm ⊂ canonical_norm (single direction)
    """
    if not gazetteer:
        return []

    matched: list[str] = []
    matched_canons: set[str] = set()

    for candidate in candidates:
        candidate_norm = DatasetRuleV3._normalize_name(candidate)
        if not candidate_norm or len(candidate_norm) < 2:
            continue
        if candidate_norm in WEAK_SEMANTIC_BLACKLIST:
            continue

        best: tuple[int, str] | None = None

        for entry in gazetteer:
            canonical_name = entry["canonical_name"]
            canonical_norm = DatasetRuleV3._normalize_name(canonical_name)

            if not canonical_norm or len(canonical_norm) < _MIN_CANONICAL_LEN:
                pass
            elif canonical_norm in WEAK_SEMANTIC_BLACKLIST:
                pass
            elif candidate_norm in canonical_norm:
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

        if best and best[1] not in matched_canons:
            matched.append(best[1])
            matched_canons.add(best[1])

    return matched


def _dedupe_key(name: str, alias_groups: dict[str, set[str]]) -> str:
    for label in (name,):
        nf = normalize_fuzzy(label)
        if not nf:
            continue
        for group_key, forms in alias_groups.items():
            if nf in forms:
                return group_key
        return nf
    return ""


def _merge_union(
    v41_datasets: list[dict[str, Any]],
    gazetteer_canonicals: list[str],
    alias_groups: dict[str, set[str]],
) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    by_key: dict[str, dict[str, Any]] = {}
    merge_trace: dict[str, list[str]] = {
        "v4_1_only": [],
        "gazetteer_only": [],
        "both": [],
    }

    for ds in v41_datasets:
        name = ds["name"]
        canon = ds.get("gazetteer_canonical") or name
        key = _dedupe_key(canon, alias_groups) or _dedupe_key(name, alias_groups)
        if not key:
            key = normalize_fuzzy(name) or name.lower()
        entry = dict(ds)
        entry["merge_source"] = "v4_1"
        by_key[key] = entry
        merge_trace["v4_1_only"].append(name)

    for canon in gazetteer_canonicals:
        key = _dedupe_key(canon, alias_groups) or normalize_fuzzy(canon) or canon.lower()
        if key in by_key:
            existing = by_key[key]
            existing["merge_source"] = "both"
            if "gazetteer_canonical" not in existing:
                existing["gazetteer_canonical"] = canon
            if existing["name"] in merge_trace["v4_1_only"]:
                merge_trace["v4_1_only"].remove(existing["name"])
            merge_trace["both"].append(existing["name"])
            continue
        entry = DatasetRuleV3._build_dataset_entry(canon)
        entry["confidence"] = "high"
        entry["confidence_signals"] = ["gazetteer_hard_filter_tight"]
        entry["extraction_layer"] = "B"
        entry["extraction_source"] = "v4_loose_gazetteer_tight"
        entry["gazetteer_canonical"] = canon
        entry["merge_source"] = "v4_loose_gazetteer"
        by_key[key] = entry
        merge_trace["gazetteer_only"].append(canon)

    merged = sorted(by_key.values(), key=lambda d: d["name"].lower())
    return merged, merge_trace


class DatasetRuleV431:
    """Dataset extraction v4.3.1: v4.2 + context filter + tight gazetteer (no expansion)."""

    @staticmethod
    def extract(paper_md: str, paper_id: str = "") -> dict[str, Any]:
        start = time.perf_counter()
        trace: dict[str, Any] = {
            "version": "v4.3.1",
            "branch_a": {},
            "branch_b": {},
            "merge": {},
            "timing_ms": {},
            "tightening": {
                "channel_b_context_filter": True,
                "channel_b_table_method_filter": True,
                "gazetteer_hard_filter_tight": True,
                "gazetteer_expansion": False,
                "min_canonical_len": _MIN_CANONICAL_LEN,
                "overlap_ratio": _OVERLAP_RATIO,
                "weak_semantic_blacklist": sorted(WEAK_SEMANTIC_BLACKLIST),
            },
        }

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
        gazetteer = DatasetRuleV3._load_gazetteer()
        after_gazetteer = _match_gazetteer_tight(loose_names, gazetteer)
        after_blacklist = DatasetRuleV3._filter_blacklist(after_gazetteer)
        trace["branch_b"] = {
            "loose_candidates": loose_names,
            "loose_count": len(loose_names),
            "after_gazetteer_tight": after_gazetteer,
            "after_blacklist": after_blacklist,
            "layer_a": loose_trace.get("layer_a"),
            "layer_b": loose_trace.get("layer_b"),
        }
        trace["timing_ms"]["branch_b"] = round((time.perf_counter() - t1) * 1000, 2)

        t2 = time.perf_counter()
        alias_groups = _load_gazetteer_aliases()
        merged, merge_trace = _merge_union(v41_datasets, after_blacklist, alias_groups)
        trace["merge"] = merge_trace
        trace["timing_ms"]["merge"] = round((time.perf_counter() - t2) * 1000, 2)

        trace["final"] = [d["name"] for d in merged]
        trace["timing_ms"]["strategy_total"] = round((time.perf_counter() - start) * 1000, 2)
        trace["extraction"] = {
            "branch_a_count": len(v41_datasets),
            "branch_b_gazetteer_count": len(after_blacklist),
            "merged_count": len(merged),
            "v4_1_only": len(merge_trace["v4_1_only"]),
            "gazetteer_only": len(merge_trace["gazetteer_only"]),
            "both": len(merge_trace["both"]),
        }

        return {"datasets": merged, "trace": trace}


if __name__ == "__main__":
    sample = """
# 4.1 Datasets
We use the benchmark dataset ShapeNet-ViPC [3]. We also evaluate on LFW [1] and VGGFace2 [2].
ImageNet [4] is a general benchmark. ResNet [5] is a model. SUN [6] is a scene dataset.
"""
    out = DatasetRuleV431.extract(sample, "test")
    print(json.dumps(out, indent=2, ensure_ascii=False))
