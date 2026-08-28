"""
datasets--策略v4.3--Union Ensemble (语境收紧 + gazetteer扩充)

相对 v4.2:
- Channel B: abbrev_ref/camel_case 要求 dataset/benchmark 语境
- Channel B: 表格行过滤 method/metric 表头
- Gazetteer: 扩充 face recognition 子领域 ~25 条
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
        entry["confidence_signals"] = ["gazetteer_hard_filter"]
        entry["extraction_layer"] = "B"
        entry["extraction_source"] = "v4_loose_gazetteer"
        entry["gazetteer_canonical"] = canon
        entry["merge_source"] = "v4_loose_gazetteer"
        by_key[key] = entry
        merge_trace["gazetteer_only"].append(canon)

    merged = sorted(by_key.values(), key=lambda d: d["name"].lower())
    return merged, merge_trace


class DatasetRuleV43:
    """Dataset extraction v4.3: v4.2 + context-filtered channel B + expanded gazetteer."""

    @staticmethod
    def extract(paper_md: str, paper_id: str = "") -> dict[str, Any]:
        start = time.perf_counter()
        trace: dict[str, Any] = {
            "version": "v4.3",
            "branch_a": {},
            "branch_b": {},
            "merge": {},
            "timing_ms": {},
            "tightening": {
                "channel_b_context_filter": True,
                "channel_b_table_method_filter": True,
                "gazetteer_face_expansion": True,
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
        after_gazetteer = DatasetRuleV3._match_gazetteer(loose_names, gazetteer)
        after_blacklist = DatasetRuleV3._filter_blacklist(after_gazetteer)
        trace["branch_b"] = {
            "loose_candidates": loose_names,
            "loose_count": len(loose_names),
            "after_gazetteer": after_gazetteer,
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
ImageNet [4] is a general benchmark. ResNet [5] is a model.
"""
    out = DatasetRuleV43.extract(sample, "test")
    print(json.dumps(out, indent=2, ensure_ascii=False))
