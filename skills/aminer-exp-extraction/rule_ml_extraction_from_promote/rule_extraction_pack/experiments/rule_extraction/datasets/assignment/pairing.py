"""Main-experiment pairing and section utilities for assignment v2."""

from __future__ import annotations

import re
from typing import Any

from experiments.rule_extraction.shared.dataset_preprocess import _parse_sections

from .helpers import experiment_name_tokens

_HEADER_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


def build_section_spans(md_text: str) -> list[dict[str, Any]]:
    """Parse md into sections with full span offsets (header through next header)."""
    matches = list(_HEADER_RE.finditer(md_text))
    sections = _parse_sections(md_text)
    for i, sec in enumerate(sections):
        sec = dict(sec)
        sec["header_start"] = matches[i].start()
        sec["span_end"] = matches[i + 1].start() if i + 1 < len(matches) else len(md_text)
        sections[i] = sec
    return sections


def offset_to_section(sections: list[dict[str, Any]], pos: int) -> dict[str, Any] | None:
    for sec in sections:
        if sec["header_start"] <= pos < sec["span_end"]:
            return sec
    return None


def section_title_tokens(title: str) -> set[str]:
    return set(experiment_name_tokens(title))


def token_jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def section_window_hit(
    sections: list[dict[str, Any]],
    md_text_lower: str,
    mention_positions: list[int],
    exp_tokens: list[str],
) -> tuple[bool, str | None]:
    """True if exp_tokens appear in the same section as any dataset mention."""
    if not exp_tokens or not mention_positions:
        return False, None
    tok_set = set(exp_tokens)
    for pos in mention_positions:
        sec = offset_to_section(sections, pos)
        if not sec:
            continue
        section_text = md_text_lower[sec["header_start"]:sec["span_end"]]
        if any(tok in section_text for tok in tok_set):
            return True, sec.get("title")
    return False, None


def _pair_score(
    ablation_meta: dict[str, Any],
    candidate_meta: dict[str, Any],
    experiments: list[dict[str, Any]],
    sections: list[dict[str, Any]],
) -> float:
    ablation_tokens = set(ablation_meta["tokens"])
    candidate_tokens = set(candidate_meta["tokens"])
    name_score = token_jaccard(ablation_tokens, candidate_tokens)

    ablation_name = experiments[ablation_meta["idx"]].get("experiment_name") or ""
    candidate_name = experiments[candidate_meta["idx"]].get("experiment_name") or ""
    ablation_toks = set(experiment_name_tokens(ablation_name))
    candidate_toks = set(experiment_name_tokens(candidate_name))

    section_score = 0.0
    for sec in sections:
        stoks = section_title_tokens(sec.get("title") or "")
        ab_sec = token_jaccard(ablation_toks, stoks)
        cand_sec = token_jaccard(candidate_toks, stoks)
        if ab_sec > 0:
            section_score = max(section_score, cand_sec)

    return name_score * 0.6 + section_score * 0.4


def find_main_exp_for(
    ablation_idx: int,
    experiments: list[dict[str, Any]],
    exp_meta: list[dict[str, Any]],
    sections: list[dict[str, Any]],
    assigned_out: list[dict[str, Any]],
) -> int | None:
    """Pick the comparison/benchmark main experiment for an ablation to inherit from."""
    del assigned_out  # reserved for future scoring using assigned datasets
    ablation_meta = exp_meta[ablation_idx]
    candidates = [m for m in exp_meta if m["klass"] == "comparison" and m["idx"] != ablation_idx]
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]["idx"]

    best_idx: int | None = None
    best_score = -1.0
    for cand in candidates:
        score = _pair_score(ablation_meta, cand, experiments, sections)
        if score > best_score:
            best_score = score
            best_idx = cand["idx"]
    return best_idx if best_score > 0 else None
