"""Unit tests for wf4 normalize_description."""

from __future__ import annotations

import sys
from pathlib import Path

PROD_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROD_ROOT))

from pipeline.production.adapters.wf4_normalize import normalize_description  # noqa: E402


def test_none_returns_empty() -> None:
    assert normalize_description(None) == ""


def test_list_takes_first_non_empty_stripped() -> None:
    assert normalize_description(["", "  A full sentence.  ", "other"]) == "A full sentence."


def test_string_stripped() -> None:
    assert normalize_description("  Explains the method.  ") == "Explains the method."


def test_no_sentence_truncation() -> None:
    long_desc = "Sentence one. " * 10
    assert normalize_description(long_desc) == long_desc.strip()


if __name__ == "__main__":
    test_none_returns_empty()
    test_list_takes_first_non_empty_stripped()
    test_string_stripped()
    test_no_sentence_truncation()
    print("OK: all normalize_description tests passed")
