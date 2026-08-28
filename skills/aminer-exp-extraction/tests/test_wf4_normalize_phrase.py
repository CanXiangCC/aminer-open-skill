"""Unit tests for wf4 normalize_single_phrase."""

from __future__ import annotations

import sys
from pathlib import Path

PROD_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROD_ROOT))

from pipeline.production.adapters.wf4_normalize import normalize_single_phrase  # noqa: E402


def test_none_returns_empty() -> None:
    assert normalize_single_phrase(None) == ""


def test_list_takes_first_non_empty_stripped() -> None:
    assert normalize_single_phrase(["", "  Foo Bar  ", "baz"]) == "Foo Bar"


def test_list_all_empty_returns_empty() -> None:
    assert normalize_single_phrase(["", "   "]) == ""


def test_string_stripped() -> None:
    assert normalize_single_phrase("  hello  ") == "hello"


def test_non_string_coerced() -> None:
    assert normalize_single_phrase(123) == "123"


def test_no_word_count_truncation() -> None:
    long_phrase = "word " * 20
    assert normalize_single_phrase(long_phrase) == long_phrase.strip()


if __name__ == "__main__":
    test_none_returns_empty()
    test_list_takes_first_non_empty_stripped()
    test_list_all_empty_returns_empty()
    test_string_stripped()
    test_non_string_coerced()
    test_no_word_count_truncation()
    print("OK: all normalize_single_phrase tests passed")
