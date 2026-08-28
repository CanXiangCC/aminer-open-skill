"""
Shared MSWR helpers for evidence v2 (copied from v1; v1 remains self-contained).
"""

from __future__ import annotations

import difflib
import re
from typing import Any

from experiments.rule_extraction.shared.dataset_preprocess import _parse_sections
from src.evaluation.semantic import jaccard_similarity, normalize_text

_STOPWORDS = frozenset({
    "the", "a", "an", "and", "or", "of", "in", "on", "for", "to", "with",
    "by", "from", "at", "is", "are", "was", "were", "be", "been", "being",
    "this", "that", "these", "those", "we", "our", "their", "its", "as",
    "using", "based", "via", "over", "under", "between", "among",
})

_NOISE_PATTERNS = [
    re.compile(r"^\s*future\s+work\b", re.I),
    re.compile(r"^\s*in\s+future\s+work\b", re.I),
    re.compile(r"^\[\d+\]\s*$"),
    re.compile(r"^[\[\(]?\d+[\]\)]?\s+et\s+al", re.I),
]

_NUMERIC_RE = re.compile(r"\d+\.?\d*")


def split_all_sentences(text: str) -> list[str]:
    abbreviations = [
        r"Dr\.", r"Mr\.", r"Mrs\.", r"Ms\.", r"Prof\.",
        r"Ph\.D\.", r"Ph\.D", r"M\.D\.", r"B\.S\.",
        r"U\.S\.", r"U\.K\.", r"e\.g\.", r"i\.e\.",
        r"Fig\.", r"Sec\.", r"Eq\.", r"vs\.",
        r"et al\.", r"etc\.",
    ]
    protected = text
    for i, abbr in enumerate(abbreviations):
        protected = re.sub(abbr, f"@@ABBR{i}@@@@", protected, flags=re.IGNORECASE)
    sentences = re.split(r"(?<=[.!?])\s+", protected)
    sentences = [re.sub(r"@@ABBR\d+@@@@", ".", s) for s in sentences]
    return [s.strip() for s in sentences if s.strip()]


def is_noise_sentence(sent: str) -> bool:
    if len(sent) < 20 or len(sent) > 500:
        return True
    if sent.lstrip().startswith("#"):
        return True
    stripped = sent.strip()
    if stripped.startswith("|") and stripped.count("|") >= 2:
        return True
    pipe_ratio = stripped.count("|") / max(len(stripped), 1)
    if pipe_ratio > 0.3:
        return True
    for pat in _NOISE_PATTERNS:
        if pat.search(stripped):
            return True
    return False


def significant_tokens(name: str) -> list[str]:
    tokens = re.findall(r"[a-zA-Z0-9]{4,}", name.lower())
    return [t for t in tokens if t not in _STOPWORDS]


def build_queries(experiment: dict) -> list[dict[str, Any]]:
    queries: list[dict[str, Any]] = []
    for kr in experiment.get("key_results") or []:
        if kr and str(kr).strip():
            queries.append({"text": str(kr).strip(), "weight": 1.0, "type": "result"})
    for sent in split_all_sentences(experiment.get("method") or "")[:2]:
        queries.append({"text": sent, "weight": 0.7, "type": "method"})
    name_tokens = significant_tokens(experiment.get("experiment_name") or "")
    if name_tokens:
        queries.append({"text": " ".join(name_tokens), "weight": 0.4, "type": "anchor"})
    return queries


def section_for_pos(sections: list[dict[str, Any]], pos: int) -> int | None:
    for i, sec in enumerate(sections):
        if sec["start"] <= pos < sec["end"]:
            return i
    return None


def scope(
    sentence: str,
    md_text: str,
    experiment: dict,
    sections: list[dict[str, Any]],
    single_exp: bool,
) -> float:
    if single_exp:
        return 1.0
    if not sections:
        return 0.3

    sent_pos = md_text.find(sentence)
    if sent_pos < 0:
        sent_pos = 0

    sent_section_idx = section_for_pos(sections, sent_pos)
    if sent_section_idx is None:
        return 0.3

    sec = sections[sent_section_idx]
    section_text = (sec.get("title") or "") + " " + (sec.get("content") or "")
    section_lower = section_text.lower()

    name_tokens = significant_tokens(experiment.get("experiment_name") or "")
    if name_tokens and any(t in section_lower for t in name_tokens):
        return 1.0

    method_sents = split_all_sentences(experiment.get("method") or "")
    if method_sents:
        method_pos = md_text.find(method_sents[0][:40])
        if method_pos >= 0:
            method_sec_idx = section_for_pos(sections, method_pos)
            if method_sec_idx == sent_section_idx:
                return 0.6

    return 0.3


def numeric_anchor(query: str, sentence: str) -> float:
    q_nums = _NUMERIC_RE.findall(query)
    if not q_nums:
        return 0.5
    matched = sum(1 for n in q_nums if n in sentence)
    if matched == len(q_nums):
        return 1.0
    if matched > 0:
        return 0.5
    return 0.0


def substring_boost(query: str, sentence: str) -> float:
    tokens = [t for t in re.findall(r"[a-zA-Z0-9]{4,}", query.lower()) if t not in _STOPWORDS]
    if tokens:
        return sum(1 for t in tokens if t in sentence.lower()) / len(tokens)
    return difflib.SequenceMatcher(None, query.lower(), sentence.lower()).ratio()


def cheap_score(
    sentence: str,
    query: dict[str, Any],
    md_text: str,
    experiment: dict,
    sections: list[dict[str, Any]],
    single_exp: bool,
    numeric_fn=numeric_anchor,
) -> dict[str, float]:
    q_text = query["text"]
    sc = scope(sentence, md_text, experiment, sections, single_exp)
    jac = jaccard_similarity(q_text, sentence)
    num = numeric_fn(q_text, sentence)
    sub = substring_boost(q_text, sentence)
    base = 0.55 * jac + 0.25 * num + 0.20 * sub
    total = sc * base * query["weight"]
    return {
        "total": total,
        "scope": sc,
        "jaccard": jac,
        "numeric_anchor": num,
        "substring_boost": sub,
    }


def is_verbatim(sentence: str, md_text: str) -> bool:
    if sentence.strip() in md_text:
        return True
    norm_s = normalize_text(sentence)
    norm_md = normalize_text(md_text)
    return bool(norm_s and norm_s in norm_md)


def parse_sections(md_text: str) -> list[dict[str, Any]]:
    return _parse_sections(md_text)
