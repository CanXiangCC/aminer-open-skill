"""
datasets--策略v4.5--Union (Branch B tight + Hybrid gazetteer)

相对 v4.3:
- Branch A: unchanged (DatasetRuleV41 + default gazetteer.json soft match)
- Branch B: _match_gazetteer_tight (from v4.3.1) instead of bidirectional _match_gazetteer
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
from experiments.rule_extraction.datasets.strategies.v4_3_1_union import _match_gazetteer_tight

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
GAZETTEER_HYBRID_DEFAULT = DATA_DIR / "gazetteer_hybrid.json"


class DatasetRuleV45:
    """Dataset extraction v4.5: v4.3 + Branch B tight match + hybrid gazetteer."""

    @staticmethod
    def _load_gazetteer_for_v45() -> list[dict[str, Any]]:
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
            "version": "v4.5",
            "branch_a": {},
            "branch_b": {},
            "merge": {},
            "timing_ms": {},
            "tightening": {
                "channel_b_context_filter": True,
                "channel_b_table_method_filter": True,
                "branch_b_tight_match": True,
                "gazetteer_source": "hybrid",
                "gazetteer_hybrid_path": str(GAZETTEER_HYBRID_DEFAULT),
                "min_paper_count": 10,
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
        gazetteer = DatasetRuleV45._load_gazetteer_for_v45()
        after_gazetteer = _match_gazetteer_tight(loose_names, gazetteer)
        after_blacklist = DatasetRuleV3._filter_blacklist(after_gazetteer)
        trace["branch_b"] = {
            "loose_candidates": loose_names,
            "loose_count": len(loose_names),
            "after_gazetteer_tight": after_gazetteer,
            "after_blacklist": after_blacklist,
            "gazetteer_entry_count": len(gazetteer),
            "layer_a": loose_trace.get("layer_a"),
            "layer_b": loose_trace.get("layer_b"),
        }
        trace["timing_ms"]["branch_b"] = round((time.perf_counter() - t1) * 1000, 2)

        t2 = time.perf_counter()
        alias_groups = DatasetRuleV45._alias_groups_from_gazetteer(gazetteer)
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
    out = DatasetRuleV45.extract(sample, "test")
    print(json.dumps(out, indent=2, ensure_ascii=False))
