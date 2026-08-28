"""Sentence cleaning module for v4 evidence selection.

Implements R1-R5 filters from wf8洗句算法 without external dependencies.
v0.2.0 / v4.1 patch: R5 figure_caption + R4 OCR enhancements (spaced-digit, LaTeX, bib fragments).
"""

from __future__ import annotations

import re
from typing import Any


def split_sentences(text: str) -> list[str]:
    """Split text into sentences, normalize whitespace, filter short (<16 chars).

    Simple split on sentence boundaries without abbreviation protection.
    """
    # Normalize whitespace
    text = re.sub(r"\s+", " ", text)
    # Split on sentence boundaries
    parts = re.split(r"(?<=[.!?])\s+", text)
    # Filter short sentences
    return [p.strip() for p in parts if len(p.strip()) > 15]


def filter_english_only(sentences: list[str]) -> list[str]:
    """Keep only sentences where the first alphabetic character is ASCII."""
    result = []
    for s in sentences:
        first_alpha = next((ch for ch in s if ch.isalpha()), "")
        if first_alpha and first_alpha.isascii():
            result.append(s)
    return result


def _classify(s: str) -> str | None:
    """Classify why a sentence should be dropped.

    Returns:
        "html_table", "too_short", "title_layout", "ocr_fragment", "figure_caption", or None

    Order: R1 → R2 → R3 → R4 (enhanced) → R5, first match wins.
    """
    stripped = s.strip()

    # R1: HTML/table markers
    if re.search(r"(?i)<html|<table|</tr>|<td|<th", stripped):
        return "html_table"

    # R2: Too short (len >= 30 AND English words >= 6 required)
    # This applies BEFORE R3/R4, so short titles/fragments are "too_short"
    if len(stripped) < 30:
        return "too_short"
    english_words = re.findall(r"[a-zA-Z]+", stripped)
    if len(english_words) < 6:
        return "too_short"

    # R3: Title/layout markers (only for sentences that pass R2 length check)
    if re.match(r"^\s*#{1,3}\s", stripped):
        return "title_layout"
    if re.match(r"^[A-Z][A-Z\s\d\.\(\)\\%/]{15,}$", stripped):
        return "title_layout"
    if re.match(r"^(Human:|Assistant:)", stripped):
        return "title_layout"

    # R4: OCR fragment / noise
    if not re.search(r"[a-zA-Z]", stripped):
        return "ocr_fragment"
    letter_ratio = sum(1 for ch in stripped if ch.isalpha()) / max(len(stripped), 1)
    if letter_ratio < 0.40:
        return "ocr_fragment"
    if re.match(r"^\s*[\d\.\$\\\%\(\),\s]+\s*$", stripped):
        return "ocr_fragment"
    # R4d: Spaced-digit OCR (e.g., "$8 2 ." instead of "82")
    if re.search(r"(?:\d|\$|\.)\s+\d\s+\.", stripped):
        return "ocr_fragment"
    # R4e: LaTeX fragment markers
    if re.search(r"\\\\[a-z]+\{|\\\\mathrm\s*\{|\\[a-z]+\{", stripped, re.I):
        return "ocr_fragment"
    # R4f: Bibliographic fragments with multiple brackets
    if re.search(r"\[\d+\].*\[\d+\]", stripped) or re.search(r"\[\d+\s*,\s*\d+\]", stripped):
        return "ocr_fragment"

    # R5: Figure captions (after R4 so sentences with 6+ words are caught)
    # Substantive word exception for figure-related sentences
    weak_substantives = {"architecture", "pipeline", "method", "approach", "framework", "system", "model", "algorithm"}
    # R5a: Classic figure markers
    if re.search(r"^(Figure|Fig\.)\s+\d+", stripped, re.I):
        # Exception: Keep if contains substantive words
        if not any(word in stripped.lower() for word in weak_substantives):
            return "figure_caption"
    # R5b: Image/dataset caption patterns (include "sampling")
    if re.search(r"^A (?:sampling|sample|set|collection) of (?:images|figures|visuals|plots|graphs|charts)", stripped, re.I):
        return "figure_caption"
    # R5c: Image markup markers
    if re.search(r"!\[.*\]\(.*(?:images|img|figures?|figs?)/", stripped):
        return "figure_caption"
    # R5d: Captions showing/describing (with weak heuristics)
    if re.search(r"^(?:This|The|Our|A) (?:figure|image|plot|graph|chart|visualization).*?(?:shows|depicts|displays|illustrates|demonstrates|presents)", stripped, re.I):
        # Exception: Keep if contains substantive words
        if not any(word in stripped.lower() for word in weak_substantives):
            return "figure_caption"

    return None


def clean_sentences_for_llm(sentences: list[str]) -> tuple[list[str], dict[str, Any]]:
    """Apply R1-R5 filters to sentences.

    Returns:
        (kept_sentences, stats) where stats contains:
        - input_count: total input sentences
        - kept_count: sentences after all filters
        - dropped_count: sentences dropped
        - dropped_by_reason: counts per reason
        - dropped_samples: up to 5 dropped samples (truncated to 120 chars)
    """
    input_count = len(sentences)
    kept = []
    dropped_by_reason = {
        "html_table": 0,
        "too_short": 0,
        "title_layout": 0,
        "ocr_fragment": 0,
        "figure_caption": 0,
    }
    dropped_samples = []

    for sent in sentences:
        reason = _classify(sent)
        if reason is None:
            # Conservative: only normalize whitespace, don't change semantics
            kept.append(re.sub(r"\s+", " ", sent).strip())
        else:
            dropped_by_reason[reason] = dropped_by_reason.get(reason, 0) + 1
            if len(dropped_samples) < 5:
                dropped_samples.append(sent[:120])

    stats = {
        "input_count": input_count,
        "kept_count": len(kept),
        "dropped_count": input_count - len(kept),
        "dropped_by_reason": dropped_by_reason,
        "dropped_samples": dropped_samples,
    }
    return kept, stats