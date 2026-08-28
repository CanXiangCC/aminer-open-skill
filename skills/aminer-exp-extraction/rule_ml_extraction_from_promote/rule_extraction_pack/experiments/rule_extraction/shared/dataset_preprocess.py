"""
共享数据预处理模块 - Shared Dataset Preprocessing

提供 strip_references + section 选段 + Layer A/B 分类 + trace 记录
"""

import re
import time
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from src.preprocess.strip_references import strip_references
from src.config.settings import SECTION_KEYWORD_BODY_TERMS

HEADER_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)

DATASET_SECTION_KEYWORDS = [
    "dataset", "datasets", "database", "databases", "data",
    "training data", "evaluation data", "benchmark", "benchmarks",
    "corpus", "corpora", "data set", "data sets",
    "dataset details", "data collection",
]

LAYER_B_TITLE_KEYWORDS = [
    "experiment", "experiments", "experimental", "results", "evaluation",
    "implementation details", "experimental setup", "evaluation protocol",
    "benchmarks", "materials and methods",
]

MIN_BODY_HITS = 3

# v4.1: table parsing only under sections whose root title contains these
TABLE_SECTION_TITLE_KEYWORDS = [
    "dataset", "datasets", "training dataset", "test dataset",
    "training data", "evaluation data", "dataset details",
]


def _title_matches_dataset_semantics(title: str) -> bool:
    t = title.lower()
    return any(kw in t for kw in DATASET_SECTION_KEYWORDS)


def _title_matches_layer_b(title: str) -> bool:
    t = title.lower()
    return any(kw in t for kw in LAYER_B_TITLE_KEYWORDS)


def _title_matches_dataset_table_scope(title: str) -> bool:
    """v4.1: stricter scope for table extraction (title must mention dataset)."""
    t = title.lower()
    return any(kw in t for kw in TABLE_SECTION_TITLE_KEYWORDS)


def _parse_sections(md_text: str) -> List[Dict[str, Any]]:
    matches = list(HEADER_RE.finditer(md_text))
    sections: List[Dict[str, Any]] = []
    for i, match in enumerate(matches):
        level = len(match.group(1))
        title = match.group(2).strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(md_text)
        content = md_text[start:end].strip()
        sections.append({
            "index": i,
            "level": level,
            "title": title,
            "content": content,
            "start": start,
            "end": end,
        })
    return sections


def _collect_subtree(sections: List[Dict[str, Any]], root_idx: int) -> List[Dict[str, Any]]:
    """Collect section at root_idx and all descendant sections (by header level)."""
    root = sections[root_idx]
    root_level = root["level"]
    collected = [root]
    for j in range(root_idx + 1, len(sections)):
        if sections[j]["level"] <= root_level:
            break
        collected.append(sections[j])
    return collected


def select_layers(
    md_text: str,
    *,
    strict_table_scope: bool = False,
    keyword_supplement_hits: int = MIN_BODY_HITS,
) -> Tuple[str, str, str, Dict[str, Any]]:
    """
    Select Layer A (dataset semantic sections + subtrees) and Layer B (experiment sections).

    Returns:
        (layer_a_text, layer_b_text, layer_a_table_text, trace)
    """
    trace: Dict[str, Any] = {
        "layer_a_sections": [],
        "layer_b_sections": [],
        "layer_a_table_sections": [],
        "section_tree": [],
        "selected_chars_by_layer": {"layer_a": 0, "layer_b": 0, "layer_a_table": 0},
        "title_match_count": 0,
        "keyword_supplement_count": 0,
        "strict_table_scope": strict_table_scope,
    }

    sections = _parse_sections(md_text)
    if not sections:
        return md_text, "", md_text, trace

    layer_a_parts: List[str] = []
    layer_a_table_parts: List[str] = []
    layer_b_parts: List[str] = []
    used_indices: set[int] = set()

    for i, sec in enumerate(sections):
        if _title_matches_dataset_semantics(sec["title"]):
            subtree = _collect_subtree(sections, i)
            table_scope = (not strict_table_scope) or _title_matches_dataset_table_scope(sec["title"])
            for node in subtree:
                idx = node["index"]
                if idx in used_indices:
                    continue
                used_indices.add(idx)
                if node["content"]:
                    layer_a_parts.append(node["content"])
                    if table_scope:
                        layer_a_table_parts.append(node["content"])
                trace["layer_a_sections"].append(node["title"])
                if table_scope:
                    trace["layer_a_table_sections"].append(node["title"])
            trace["title_match_count"] += 1
            trace["section_tree"].append({
                "title": sec["title"],
                "layer": "A",
                "subtree_size": len(subtree),
                "table_scope": table_scope,
            })

    for i, sec in enumerate(sections):
        if i in used_indices:
            continue
        title = sec["title"]
        if _title_matches_layer_b(title):
            if sec["content"]:
                layer_b_parts.append(sec["content"])
            trace["layer_b_sections"].append(title)
            used_indices.add(i)
            continue

        content_lower = sec["content"].lower()
        hits = sum(1 for term in SECTION_KEYWORD_BODY_TERMS if term.lower() in content_lower)
        if hits >= keyword_supplement_hits and sec["content"]:
            layer_b_parts.append(sec["content"])
            trace["layer_b_sections"].append(title)
            trace["keyword_supplement_count"] += 1
            used_indices.add(i)

    layer_a_text = "\n\n".join(layer_a_parts)
    layer_b_text = "\n\n".join(layer_b_parts)
    layer_a_table_text = "\n\n".join(layer_a_table_parts) if layer_a_table_parts else layer_a_text
    trace["selected_chars_by_layer"]["layer_a"] = len(layer_a_text)
    trace["selected_chars_by_layer"]["layer_b"] = len(layer_b_text)
    trace["selected_chars_by_layer"]["layer_a_table"] = len(layer_a_table_text)

    if not layer_a_text and not layer_b_text:
        layer_b_text = md_text
        trace["fallback_full_text"] = True

    return layer_a_text, layer_b_text, layer_a_table_text, trace


def select_experiment_sections(md_text: str) -> Tuple[str, Dict[str, Any]]:
    """
    Legacy: combined selected text (Layer A + Layer B) for v3 compatibility.
    """
    layer_a, layer_b, _, layer_trace = select_layers(md_text)
    combined = "\n\n".join(p for p in [layer_a, layer_b] if p)
    trace = {
        "section_titles": layer_trace["layer_a_sections"] + layer_trace["layer_b_sections"],
        "selected_chars": len(combined),
        "title_match_count": layer_trace["title_match_count"],
        "keyword_supplement_count": layer_trace["keyword_supplement_count"],
        **layer_trace,
    }
    return combined if combined else md_text, trace


def preprocess_paper(paper_md: str) -> Tuple[str, Dict[str, Any]]:
    """strip_references + section 选段 (combined, v3 compat)."""
    trace: Dict[str, Any] = {"preprocess": {}, "timing_ms": {}}
    start_time = time.perf_counter()

    ref_start = time.perf_counter()
    ref_result = strip_references(paper_md)
    stripped_md = ref_result.text
    trace["preprocess"]["strip_references"] = {
        "found": ref_result.references_found,
        "method": ref_result.detection_method,
        "confidence": ref_result.confidence,
        "removal_ratio": ref_result.removal_ratio,
        "anomaly_rejected": ref_result.anomaly_rejected,
        "chars_before": ref_result.original_char_count,
        "chars_after": ref_result.stripped_char_count,
    }
    trace["timing_ms"]["strip_references"] = round((time.perf_counter() - ref_start) * 1000, 2)

    section_start = time.perf_counter()
    selected_text, section_trace = select_experiment_sections(stripped_md)
    trace["preprocess"]["section_selection"] = section_trace
    trace["timing_ms"]["section_selection"] = round((time.perf_counter() - section_start) * 1000, 2)
    trace["timing_ms"]["preprocess_total"] = round((time.perf_counter() - start_time) * 1000, 2)

    return selected_text, trace


def preprocess_paper_layers(
    paper_md: str,
    *,
    strict_table_scope: bool = False,
    keyword_supplement_hits: int = MIN_BODY_HITS,
) -> Tuple[str, str, str, Dict[str, Any]]:
    """strip_references + Layer A/B split (+ optional table-only scope for v4.1)."""
    trace: Dict[str, Any] = {"preprocess": {}, "timing_ms": {}}
    start_time = time.perf_counter()

    ref_start = time.perf_counter()
    ref_result = strip_references(paper_md)
    stripped_md = ref_result.text
    trace["preprocess"]["strip_references"] = {
        "found": ref_result.references_found,
        "method": ref_result.detection_method,
        "confidence": ref_result.confidence,
        "removal_ratio": ref_result.removal_ratio,
        "anomaly_rejected": ref_result.anomaly_rejected,
        "chars_before": ref_result.original_char_count,
        "chars_after": ref_result.stripped_char_count,
    }
    trace["timing_ms"]["strip_references"] = round((time.perf_counter() - ref_start) * 1000, 2)

    section_start = time.perf_counter()
    layer_a, layer_b, layer_a_table, section_trace = select_layers(
        stripped_md,
        strict_table_scope=strict_table_scope,
        keyword_supplement_hits=keyword_supplement_hits,
    )
    trace["preprocess"]["section_selection"] = section_trace
    trace["timing_ms"]["section_selection"] = round((time.perf_counter() - section_start) * 1000, 2)
    trace["timing_ms"]["preprocess_total"] = round((time.perf_counter() - start_time) * 1000, 2)

    return layer_a, layer_b, layer_a_table, trace


def strip_references_only(paper_md: str) -> Tuple[str, Dict[str, Any]]:
    start_time = time.perf_counter()
    ref_result = strip_references(paper_md)
    ms = (time.perf_counter() - start_time) * 1000
    return ref_result.text, {
        "found": ref_result.references_found,
        "method": ref_result.detection_method or "none",
        "confidence": ref_result.confidence or 0,
        "removal_ratio": ref_result.removal_ratio,
        "anomaly_rejected": ref_result.anomaly_rejected,
        "chars_before": ref_result.original_char_count,
        "chars_after": ref_result.stripped_char_count,
        "ms": round(ms, 2),
    }


def get_timing_summary(trace: Dict[str, Any]) -> Dict[str, Any]:
    timing = trace.get("timing_ms", {})
    return {
        "preprocess_total": timing.get("preprocess_total", 0),
        "strip_references": timing.get("strip_references", 0),
        "section_select": timing.get("section_selection", 0),
    }
