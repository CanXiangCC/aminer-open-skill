"""
datasets--策略v4--分层混合提取

Layer A: dataset 语义 section 宽松匹配 + scoped 表格
Layer B: 强语境正则
Gazetteer: 软标注 confidence，不过滤
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Optional

project_root = Path(__file__).resolve().parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from experiments.rule_extraction.shared.dataset_preprocess import preprocess_paper_layers
from experiments.rule_extraction.datasets.shared.extraction_patterns import (
    LAYER_A_PATTERNS,
    LAYER_B_PATTERNS,
    extract_abbrev_citations,
    extract_camel_case,
    extract_with_patterns,
    is_valid_candidate,
)
from experiments.rule_extraction.datasets.strategies.v1_section_table import DatasetRuleV1
from experiments.rule_extraction.datasets.strategies.v3_gazetteer import DatasetRuleV3


class DatasetRuleV4:
    """Dataset extraction v4: layered recall + gazetteer soft confidence."""

    BLACKLIST = DatasetRuleV3.BLACKLIST

    @staticmethod
    def extract_loose_candidate_names(
        paper_md: str,
        *,
        require_context: bool = False,
        filter_table_method_rows: bool = False,
    ) -> tuple[list[str], dict[str, Any]]:
        """
        v4 Layer A/B loose candidates only (for v4.2/v4.3 gazetteer hard-filter branch).
        No gazetteer soft match, confidence, or final blacklist pass on output names.

        require_context: abbrev_ref/camel_case require nearby dataset/benchmark context.
        filter_table_method_rows: drop table rows that look like method/metric headers.
        """
        import re as _re

        trace: dict[str, Any] = {
            "layer_a": {"from_text": [], "from_table": []},
            "layer_b": {"from_text": []},
            "require_context": require_context,
            "filter_table_method_rows": filter_table_method_rows,
        }
        layer_a_text, layer_b_text, layer_a_table_text, preprocess_trace = preprocess_paper_layers(
            paper_md
        )
        trace["preprocess"] = preprocess_trace.get("preprocess", {})

        method_markers = _re.compile(
            r"\b(?:method|network|algorithm|accuracy|precision|recall|miou|map|ap|f1|acc)\b",
            _re.IGNORECASE,
        )

        seen: set[str] = set()
        names: list[str] = []

        def add_name(name: str, layer: str, source: str) -> None:
            if not is_valid_candidate(name):
                return
            key = name.lower()
            if key in DatasetRuleV4.BLACKLIST:
                return
            norm = DatasetRuleV3._normalize_name(name)
            if any(b in norm for b in DatasetRuleV4.BLACKLIST):
                return
            if key in seen:
                return
            seen.add(key)
            names.append(name)
            bucket = trace["layer_a"] if layer == "A" else trace["layer_b"]
            bucket["from_text"].append({"name": name, "source": source})

        for name, source in extract_with_patterns(layer_a_text, LAYER_A_PATTERNS):
            add_name(name, "A", source)

        for name, source in extract_abbrev_citations(
            layer_a_text, require_context=require_context, context_window=45
        ):
            add_name(name, "A", source)

        for name, source in extract_camel_case(
            layer_a_text, require_context=require_context, context_window=45
        ):
            add_name(name, "A", source)

        for raw in DatasetRuleV1._extract_from_tables(layer_a_table_text):
            cleaned = DatasetRuleV1._clean_dataset_name(raw)
            if not cleaned or not DatasetRuleV1._is_valid_dataset_name(cleaned):
                continue
            if filter_table_method_rows and method_markers.search(cleaned) and not _re.search(
                r"dataset|corpus|benchmark", cleaned, _re.IGNORECASE
            ):
                continue
            if DatasetRuleV1._is_table_header(cleaned):
                continue
            key = cleaned.lower()
            if key not in seen and key not in DatasetRuleV4.BLACKLIST:
                norm = DatasetRuleV3._normalize_name(cleaned)
                if not any(b in norm for b in DatasetRuleV4.BLACKLIST):
                    seen.add(key)
                    names.append(cleaned)
                    trace["layer_a"]["from_table"].append(cleaned)

        for name, source in extract_with_patterns(layer_b_text, LAYER_B_PATTERNS):
            add_name(name, "B", source)

        for name, source in extract_abbrev_citations(
            layer_b_text, require_context=require_context, context_window=35
        ):
            add_name(name, "B", source)

        return sorted(names, key=str.lower), trace

    @staticmethod
    def extract(paper_md: str, paper_id: str = "") -> dict[str, Any]:
        start = time.perf_counter()
        trace: dict[str, Any] = {
            "preprocess": {},
            "layer_a": {"from_text": [], "from_table": [], "candidates": []},
            "layer_b": {"candidates": []},
            "gazetteer": {"matches": []},
            "blacklist_removed": [],
            "final": [],
            "timing_ms": {},
        }

        layer_a_text, layer_b_text, layer_a_table_text, preprocess_trace = preprocess_paper_layers(paper_md)
        trace["preprocess"] = preprocess_trace.get("preprocess", {})
        trace["timing_ms"]["preprocess_total"] = preprocess_trace.get("timing_ms", {}).get("preprocess_total", 0)

        # Layer A extraction
        t0 = time.perf_counter()
        candidates: dict[str, dict[str, Any]] = {}

        def add_candidate(name: str, layer: str, source: str) -> None:
            if not is_valid_candidate(name):
                return
            key = name.lower()
            if key in DatasetRuleV4.BLACKLIST:
                return
            norm = DatasetRuleV3._normalize_name(name)
            if any(b in norm for b in DatasetRuleV4.BLACKLIST):
                return
            if key not in candidates:
                candidates[key] = {
                    "name": name,
                    "extraction_layer": layer,
                    "extraction_source": source,
                    "confidence_signals": [],
                }
            else:
                existing = candidates[key]
                if layer == "A" and existing["extraction_layer"] != "A":
                    existing["extraction_layer"] = "A"
                if source not in existing["confidence_signals"]:
                    existing["confidence_signals"].append(source)

        for name, source in extract_with_patterns(layer_a_text, LAYER_A_PATTERNS):
            add_candidate(name, "A", source)
            trace["layer_a"]["from_text"].append({"name": name, "source": source})

        for name, source in extract_abbrev_citations(layer_a_text):
            add_candidate(name, "A", source)
            trace["layer_a"]["from_text"].append({"name": name, "source": source})

        for name, source in extract_camel_case(layer_a_text):
            add_candidate(name, "A", source)
            trace["layer_a"]["from_text"].append({"name": name, "source": source})

        table_names = DatasetRuleV1._extract_from_tables(layer_a_table_text)
        for raw in table_names:
            cleaned = DatasetRuleV1._clean_dataset_name(raw)
            if cleaned and DatasetRuleV1._is_valid_dataset_name(cleaned):
                add_candidate(cleaned, "A", "table_first_col")
                trace["layer_a"]["from_table"].append(cleaned)

        trace["layer_a"]["candidates"] = list(candidates.keys())
        trace["timing_ms"]["layer_a_extract"] = round((time.perf_counter() - t0) * 1000, 2)

        # Layer B extraction
        t1 = time.perf_counter()
        for name, source in extract_with_patterns(layer_b_text, LAYER_B_PATTERNS):
            add_candidate(name, "B", source)
            trace["layer_b"]["candidates"].append({"name": name, "source": source})

        for name, source in extract_abbrev_citations(layer_b_text):
            add_candidate(name, "B", source)
            trace["layer_b"]["candidates"].append({"name": name, "source": source})

        trace["timing_ms"]["layer_b_extract"] = round((time.perf_counter() - t1) * 1000, 2)

        # Gazetteer soft match
        t2 = time.perf_counter()
        gazetteer = DatasetRuleV3._load_gazetteer()
        name_list = [c["name"] for c in candidates.values()]
        for cand in candidates.values():
            name = cand["name"]
            cand_norm = DatasetRuleV3._normalize_name(name)
            best_match: Optional[tuple[str, str, int]] = None  # canonical, match_type, overlap_len

            for entry in gazetteer:
                canonical = entry["canonical_name"]
                canonical_norm = DatasetRuleV3._normalize_name(canonical)
                forms = [(canonical_norm, canonical, "canonical")]
                for alias in entry.get("aliases", []):
                    forms.append((DatasetRuleV3._normalize_name(alias), canonical, "alias"))

                for form_norm, canon, match_type in forms:
                    if not form_norm or len(form_norm) < 2:
                        continue
                    matched = False
                    overlap = 0
                    if form_norm == cand_norm:
                        matched, overlap = True, len(form_norm)
                    elif form_norm in cand_norm and len(form_norm) >= 3:
                        if len(form_norm) / len(cand_norm) >= 0.5:
                            matched, overlap = True, len(form_norm)
                    elif cand_norm in form_norm and len(cand_norm) >= 3:
                        if len(cand_norm) / len(form_norm) >= 0.5:
                            matched, overlap = True, len(cand_norm)

                    if matched and (best_match is None or overlap > best_match[2]):
                        best_match = (canon, match_type, overlap)

            if best_match:
                canon, match_type, _ = best_match
                cand["gazetteer_canonical"] = canon
                cand["confidence_signals"].append(f"gazetteer_{match_type}")
                trace["gazetteer"]["matches"].append({
                    "candidate": name,
                    "canonical": canon,
                    "match_type": match_type,
                })

        trace["timing_ms"]["gazetteer_soft"] = round((time.perf_counter() - t2) * 1000, 2)

        # Confidence assignment
        datasets: list[dict[str, Any]] = []
        for cand in sorted(candidates.values(), key=lambda c: c["name"].lower()):
            signals = cand["confidence_signals"]
            layer = cand["extraction_layer"]
            has_gaz_exact = any(s in ("gazetteer_canonical", "gazetteer_alias") for s in signals)
            has_gaz = any(s.startswith("gazetteer_") for s in signals)
            layer_a_strong = any(
                s in ("benchmark_dataset", "the_x_dataset", "table_first_col", "author_year_benchmark")
                for s in signals
            )

            if has_gaz_exact:
                confidence = "high"
            elif layer == "A" and layer_a_strong:
                confidence = "medium"
            elif layer == "B" or "abbrev_ref" in signals:
                confidence = "medium"
            elif has_gaz:
                confidence = "low"
            else:
                confidence = "low"

            entry: dict[str, Any] = {
                "name": cand["name"],
                "aliases": [],
                "dataset_type": "other",
                "description": "",
                "sample_size": None,
                "is_public": None,
                "is_self_collected": None,
                "urls": [],
                "github_urls": [],
                "doi_list": [],
                "cstr_list": [],
                "confidence": confidence,
                "confidence_signals": signals,
                "extraction_layer": layer,
                "extraction_source": cand["extraction_source"],
            }
            if cand.get("gazetteer_canonical"):
                entry["gazetteer_canonical"] = cand["gazetteer_canonical"]
            datasets.append(entry)

        # Blacklist filter on final names
        filtered: list[dict[str, Any]] = []
        for ds in datasets:
            norm = DatasetRuleV3._normalize_name(ds["name"])
            if any(b in norm for b in DatasetRuleV4.BLACKLIST):
                trace["blacklist_removed"].append(ds["name"])
                continue
            filtered.append(ds)

        trace["final"] = [d["name"] for d in filtered]
        trace["timing_ms"]["strategy_total"] = round((time.perf_counter() - start) * 1000, 2)
        trace["extraction"] = {
            "candidates_raw_count": len(candidates),
            "after_blacklist_count": len(filtered),
            "layer_a_count": len(trace["layer_a"]["candidates"]),
            "layer_b_count": len(trace["layer_b"]["candidates"]),
            "gazetteer_matched_count": len(trace["gazetteer"]["matches"]),
        }

        return {"datasets": filtered, "trace": trace}


if __name__ == "__main__":
    sample = """
# 4.1 Datasets
# 4.1.1 Training Dataset
We use the benchmark dataset ShapeNet-ViPC [3], which is derived from ShapeNet.
"""
    out = DatasetRuleV4.extract(sample, "test")
    print(json.dumps(out, indent=2, ensure_ascii=False))
