"""
Shared extraction patterns for dataset rule extraction (v4 and fixes).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Iterator


@dataclass(frozen=True)
class PatternSpec:
    name: str
    regex: re.Pattern[str]
    group: int = 1


def _compile(pattern: str, flags: int = re.IGNORECASE) -> re.Pattern[str]:
    return re.compile(pattern, flags)


# Layer A: explicit dataset phrasing
LAYER_A_PATTERNS: list[PatternSpec] = [
    PatternSpec(
        "benchmark_dataset",
        _compile(
            r"(?:we|our)\s+(?:use|evaluate|train|test|validate)\s+(?:on\s+)?"
            r"(?:the\s+)?(?:benchmark\s+)?dataset\s+([A-Z][A-Za-z0-9\-\.]+)"
        ),
    ),
    PatternSpec(
        "the_x_dataset",
        _compile(r"(?:the|a|an)\s+([A-Z][A-Za-z0-9\-\.]+(?:\s+[A-Z][A-Za-z0-9\-\.]+)?)\s+dataset\b"),
    ),
    PatternSpec(
        "x_is_dataset",
        _compile(
            r"([A-Z][A-Za-z0-9\-\.]+(?:\s+[A-Z][A-Za-z0-9\-\.]+)?)\s+is\s+(?:a|an|the)?\s*"
            r"[A-Za-z\- ]*\s*(?:dataset|corpus|benchmark)\b"
        ),
    ),
    PatternSpec(
        "author_year_benchmark",
        _compile(
            r"([A-Z][A-Za-z0-9\-\.]+)\s+\([A-Za-z][^)]{0,80}\d{4}\)\s+is\s+(?:one\s+of\s+)?"
            r"(?:the\s+)?(?:widely[\-\s]?known\s+)?[A-Za-z\- ]*\s*benchmarks?"
        ),
    ),
    PatternSpec(
        "evaluate_on_x",
        _compile(
            r"(?:evaluate|train|test|validate|benchmark)\s+(?:on|using|with)\s+"
            r"(?:the\s+)?([A-Z][A-Za-z0-9\-\.]+(?:\s+[A-Z][A-Za-z0-9\-\.]+)?)"
            r"(?:\s+dataset|\s+corpus|\s+benchmark|[,\.\[]|$)"
        ),
    ),
    PatternSpec(
        "on_x_we_achieve",
        _compile(
            r"(?:on|with)\s+(?:the\s+)?([A-Z][A-Za-z0-9\-\.]+(?:\s+[A-Z][A-Za-z0-9\-\.]+)?)"
            r",\s+we\s+(?:achieve|obtain|report|show|demonstrate)"
        ),
    ),
]

ABBREV_REF_PATTERN = _compile(r"\b([A-Z]{2,}(?:-\d+[A-Z]?)?)\s*(?:,\s*)?\[\d+(?:,\s*\d+)*\]")
CAMEL_CASE_PATTERN = _compile(r"\b([A-Z][A-Za-z0-9]+(?:[A-Z][a-z0-9]+)+)\b")

LAYER_B_PATTERNS: list[PatternSpec] = [
    PatternSpec(
        "we_evaluate_on",
        _compile(
            r"(?:we|our)\s+(?:evaluate|train|test|validate|use|experiment|benchmark)"
            r"(?:\s+(?:on|with|using)?\s+(?:the\s+)?)?"
            r"([A-Z][A-Za-z0-9\-\s]+?)(?=\s+(?:dataset|corpus|benchmark)|,|\sand\s|\.|\n|$)"
        ),
    ),
    PatternSpec(
        "the_x_dataset_b",
        _compile(r"(?:the|a|an)\s+([A-Z][A-Za-z0-9\-\s]+?)(?:\s+(?:dataset|corpus|benchmark))"),
    ),
    PatternSpec(
        "such_as_list",
        _compile(
            r"(?:such as|including|like|e\.g\.|for example)\s+"
            r"([A-Z][A-Z0-9\-]+?)(?=,|\s+and\s+|\.)"
        ),
    ),
    PatternSpec(
        "abbrev_ref",
        ABBREV_REF_PATTERN,
    ),
]

STOP_WORDS = {
    "the", "a", "an", "our", "we", "this", "that", "benchmark", "dataset",
    "corpus", "experiments", "experiment", "results", "method", "methods",
}

# v4.1: obvious non-dataset abbrev / tokens from papers
ABBREV_BLOCKLIST = {
    "although", "bleu", "ter", "nmt", "mmt", "tool", "resnet", "transformer",
    "api", "apis", "acc", "as", "fr", "ids", "in", "given", "commonly",
    "existing", "commercial", "algorithms", "networks", "loss", "bias",
}

CONTEXT_TERMS_RE = _compile(
    r"dataset|datasets|corpus|benchmark|benchmarks|"
    r"evaluate|evaluated|train|training|test|testing|validate|validation",
    re.IGNORECASE,
)


def is_valid_candidate(name: str, *, min_letters: int = 2) -> bool:
    if not name or len(name.strip()) < 2:
        return False
    name = name.strip()
    if name.lower() in STOP_WORDS:
        return False
    if name.isdigit():
        return False
    if not name[0].isupper():
        return False
    letter_count = sum(1 for c in name if c.isalpha())
    if letter_count < min_letters:
        return False
    return True


def split_and_list(text: str) -> list[str]:
    if " and " in text.lower():
        return [p.strip() for p in re.split(r"\s+and\s+", text, flags=re.IGNORECASE) if p.strip()]
    return [text.strip()]


def extract_with_patterns(
    text: str,
    patterns: list[PatternSpec],
) -> list[tuple[str, str]]:
    """Return list of (candidate_name, source_tag)."""
    found: list[tuple[str, str]] = []
    seen: set[str] = set()
    for spec in patterns:
        for match in spec.regex.finditer(text):
            raw = match.group(spec.group).strip()
            for part in split_and_list(raw):
                if is_valid_candidate(part):
                    key = part.lower()
                    if key not in seen:
                        seen.add(key)
                        found.append((part, spec.name))
    return found


def _has_dataset_context(text: str, start: int, end: int, window: int) -> bool:
    lo = max(0, start - window)
    hi = min(len(text), end + window)
    return bool(CONTEXT_TERMS_RE.search(text[lo:hi]))


def extract_abbrev_citations(
    text: str,
    *,
    require_context: bool = False,
    context_window: int = 40,
) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    seen: set[str] = set()
    for match in ABBREV_REF_PATTERN.finditer(text):
        name = match.group(1)
        key = name.lower()
        if key in ABBREV_BLOCKLIST:
            continue
        if require_context and not _has_dataset_context(
            text, match.start(), match.end(), context_window
        ):
            continue
        if is_valid_candidate(name) and key not in seen:
            seen.add(key)
            found.append((name, "abbrev_ref"))
    return found


def extract_camel_case(
    text: str,
    min_len: int = 4,
    *,
    require_context: bool = False,
    context_window: int = 45,
) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    seen: set[str] = set()
    for match in CAMEL_CASE_PATTERN.finditer(text):
        name = match.group(1)
        if len(name) < min_len or sum(1 for c in name if c.isupper()) < 2:
            continue
        if require_context and not _has_dataset_context(
            text, match.start(), match.end(), context_window
        ):
            continue
        if is_valid_candidate(name) and name.lower() not in seen:
            seen.add(name.lower())
            found.append((name, "camel_case"))
    return found
