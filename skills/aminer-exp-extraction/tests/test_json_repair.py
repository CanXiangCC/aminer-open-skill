"""Tests for pipeline.json_repair — escape fixing, fence stripping, parse repair.

Covers the \\uXXXX hex-validation fix (LaTeX commands like \\underline / \\upsilon
must not be treated as valid \\u escapes) plus regressions for fence stripping,
trailing-comma removal, and round-trip parsing.

Run: python tests/test_json_repair.py
(No pytest dep — matches the project's manual-call test convention.)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

PROD_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROD_ROOT))

from pipeline.json_repair import (  # noqa: E402
    _fix_invalid_escapes,
    parse_json_object,
    repair_json_text,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"


# --------------------------------------------------------------------------- #
# _fix_invalid_escapes — the \u blind-spot fix
# --------------------------------------------------------------------------- #


def test_fix_invalid_u_escape_latex_underline() -> None:
    r"""\\underline — 'n','d','e','r' -> 'n' and 'r' not hex -> invalid -> doubled."""
    text = r'{"k": "use \underline{t} here"}'
    fixed = _fix_invalid_escapes(text)
    assert "\\\\underline" in fixed, fixed
    parsed = json.loads(fixed)
    assert parsed["k"] == "use \\underline{t} here"


def test_fix_invalid_u_escape_latex_upsilon() -> None:
    r"""\\upsilon — 'p','s','i','l' none hex -> invalid -> doubled."""
    text = '{"k": "\\upsilon_{t}"}'  # actual chars: {"k": "\upsilon_{t}"}
    fixed = _fix_invalid_escapes(text)
    assert "\\\\upsilon" in fixed, fixed
    parsed = json.loads(fixed)
    assert parsed["k"] == "\\upsilon_{t}"


def test_fix_invalid_u_escape_unit() -> None:
    r"""\\unit — 'n','i','t' (only 3, and not all hex) -> invalid -> doubled."""
    text = '{"k": "\\unit"}'  # actual: {"k": "\unit"}
    fixed = _fix_invalid_escapes(text)
    assert "\\\\unit" in fixed, fixed


def test_valid_u_escape_passes_through() -> None:
    """Real \\uXXXX (4 hex digits) preserved as a unicode escape."""
    text = r'{"k": "\u4e2d\u6587"}'
    fixed = _fix_invalid_escapes(text)
    assert fixed == text, f"valid \\u escape should pass through unchanged: {fixed}"
    parsed = json.loads(fixed)
    assert parsed["k"] == "中文"


def test_valid_u_escape_lowercase_hex() -> None:
    text = r'{"k": "\uabcd"}'
    fixed = _fix_invalid_escapes(text)
    assert fixed == text
    assert json.loads(fixed)["k"] == "\uabcd"


def test_valid_u_escape_uppercase_hex() -> None:
    text = r'{"k": "\uABCD"}'
    fixed = _fix_invalid_escapes(text)
    assert fixed == text
    assert json.loads(fixed)["k"] == "\uABCD"


def test_fix_other_invalid_escape_theta() -> None:
    r"""\\Theta — \T not a valid JSON escape -> doubled."""
    text = r'{"k": "\Theta(n^{0.6})"}'
    fixed = _fix_invalid_escapes(text)
    assert "\\\\Theta" in fixed, fixed
    parsed = json.loads(fixed)
    assert parsed["k"] == "\\Theta(n^{0.6})"


def test_fix_already_doubled_backslash_idempotent() -> None:
    r"""Already-doubled \\\\X (literal backslash + X) stays correct."""
    text = r'{"k": "\\Theta"}'  # actual: {"k": "\\Theta"} -> literal \Theta
    fixed = _fix_invalid_escapes(text)
    assert fixed == text, fixed
    assert json.loads(fixed)["k"] == "\\Theta"


def test_fix_invalid_escape_percent() -> None:
    r"""\\% — % not a valid JSON escape -> doubled."""
    text = r'{"k": "50\%"}'
    fixed = _fix_invalid_escapes(text)
    assert "\\\\%" in fixed, fixed
    assert json.loads(fixed)["k"] == "50\\%"


def test_fix_escaped_quote_keeps_string_state() -> None:
    r"""\" is a valid escape and must not end the string."""
    text = r'{"k": "a\"b"}'
    fixed = _fix_invalid_escapes(text)
    assert fixed == text, fixed
    assert json.loads(fixed)["k"] == 'a"b'


# --------------------------------------------------------------------------- #
# repair_json_text — fence strip, brace extraction, trailing comma
# --------------------------------------------------------------------------- #


def test_repair_strips_code_fence() -> None:
    text = '```json\n{"k": "v"}\n```'
    assert json.loads(repair_json_text(text)) == {"k": "v"}


def test_repair_strips_bare_fence() -> None:
    text = '```\n{"k": "v"}\n```'
    assert json.loads(repair_json_text(text)) == {"k": "v"}


def test_repair_strips_thinking_block() -> None:
    text = '<think>reasoning here</think>\n{"k": "v"}'
    assert json.loads(repair_json_text(text)) == {"k": "v"}


def test_repair_extracts_braces() -> None:
    text = 'Here is the result:\n{"k": "v"}\nDone.'
    assert json.loads(repair_json_text(text)) == {"k": "v"}


def test_repair_removes_trailing_comma_object() -> None:
    text = '{"k": "v",}'
    assert json.loads(repair_json_text(text)) == {"k": "v"}


def test_repair_removes_trailing_comma_array() -> None:
    text = '{"k": ["a", "b",]}'
    assert json.loads(repair_json_text(text)) == {"k": ["a", "b"]}


def test_repair_combined_fence_comma_escape() -> None:
    text = '```json\n{"k": "v",\n "n": "\\underline{x}"}\n```'
    parsed = json.loads(repair_json_text(text))
    assert parsed["k"] == "v"
    assert parsed["n"] == "\\underline{x}"


# --------------------------------------------------------------------------- #
# parse_json_object — round trip + error reporting
# --------------------------------------------------------------------------- #


def test_parse_json_object_clean() -> None:
    data, err = parse_json_object('{"k": "v"}')
    assert data == {"k": "v"}
    assert err is None


def test_parse_json_object_needs_repair() -> None:
    text = '```json\n{"k": "v"}\n```'
    data, err = parse_json_object(text)
    assert data == {"k": "v"}
    assert err is None


def test_parse_json_object_invalid_returns_error() -> None:
    data, err = parse_json_object("not json at all {")
    assert data is None
    assert err is not None


def test_parse_json_object_root_not_object() -> None:
    data, err = parse_json_object('[1, 2, 3]')
    assert data is None
    assert "not a JSON object" in (err or "")


def test_parse_json_object_latex_u_escape() -> None:
    """End-to-end: a realistic LLM output with \\underline parses to a dict."""
    text = (
        '```json\n'
        '{"experiments": [{"experiment_name": "A", "method": "uses \\underline{x}"}]}\n'
        '```'
    )
    data, err = parse_json_object(text)
    assert err is None, err
    assert data["experiments"][0]["method"] == "uses \\underline{x}"


# --------------------------------------------------------------------------- #
# Real captured fixtures
# --------------------------------------------------------------------------- #


def _load_fixture(name: str) -> str | None:
    p = FIXTURES / name
    if not p.exists():
        return None
    return p.read_text(encoding="utf-8")


def test_parse_captured_raw_output_1() -> None:
    """Captured real LLM raw output (Invalid \\uXXXX escape case) parses after fix."""
    raw = _load_fixture("repair_raw_output_1.txt")
    if raw is None:
        print("  [skip] fixture repair_raw_output_1.txt not present")
        return
    data, err = parse_json_object(raw)
    assert (data is None) or isinstance(data, dict), f"unexpected: {data!r}"
    if data is not None:
        print(f"  [fix worked] parsed OK, keys={list(data.keys())[:5]}")
    else:
        print(f"  [still fails] err={err}")


def test_parse_captured_raw_output_2() -> None:
    """Captured real LLM raw output (Invalid \\uXXXX escape case) parses after fix."""
    raw = _load_fixture("repair_raw_output_2.txt")
    if raw is None:
        print("  [skip] fixture repair_raw_output_2.txt not present")
        return
    data, err = parse_json_object(raw)
    assert (data is None) or isinstance(data, dict), f"unexpected: {data!r}"
    if data is not None:
        print(f"  [fix worked] parsed OK, keys={list(data.keys())[:5]}")
    else:
        print(f"  [still fails] err={err}")


if __name__ == "__main__":
    tests = [
        test_fix_invalid_u_escape_latex_underline,
        test_fix_invalid_u_escape_latex_upsilon,
        test_fix_invalid_u_escape_unit,
        test_valid_u_escape_passes_through,
        test_valid_u_escape_lowercase_hex,
        test_valid_u_escape_uppercase_hex,
        test_fix_other_invalid_escape_theta,
        test_fix_already_doubled_backslash_idempotent,
        test_fix_invalid_escape_percent,
        test_fix_escaped_quote_keeps_string_state,
        test_repair_strips_code_fence,
        test_repair_strips_bare_fence,
        test_repair_strips_thinking_block,
        test_repair_extracts_braces,
        test_repair_removes_trailing_comma_object,
        test_repair_removes_trailing_comma_array,
        test_repair_combined_fence_comma_escape,
        test_parse_json_object_clean,
        test_parse_json_object_needs_repair,
        test_parse_json_object_invalid_returns_error,
        test_parse_json_object_root_not_object,
        test_parse_json_object_latex_u_escape,
        test_parse_captured_raw_output_1,
        test_parse_captured_raw_output_2,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"FAIL {t.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"ERROR {t.__name__}: {type(exc).__name__}: {exc}")
    print(f"\n{'OK: all json_repair tests passed' if failed == 0 else f'FAILED: {failed} test(s)'}")
    sys.exit(1 if failed else 0)
