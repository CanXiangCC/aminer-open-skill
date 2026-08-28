"""Prompt rule assertions for wf4 multi-exp + problem/method phrase constraints."""

from __future__ import annotations

import sys
from pathlib import Path

PROD_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROD_ROOT))

from pipeline.production.adapters.wf4_prompt import build_wf4_prompt  # noqa: E402
from pipeline.production.adapters.wf4_prompt_adapter import (  # noqa: E402
    _RULES,
    _SCHEMA,
    build_wf4_prompt_for_adapter,
)

OLD_COMBINED_RULE = "research_problem, research_goal: 1-2 sentences each"
REMOVED_MARKERS = (
    "Prefer exactly 1",
    "If unsure, return exactly 1",
    "method_description:",  # legacy experiment-level field
    "NOT equal to any methods[] item",
    "the total number of method phrases across ALL experiments",
    "research_problem_justification",
    "justification:",
    '"justification": "",',
    "PREFER Chinese explanatory text",
    'Prefer filling this (it is CORE to the paper) over leaving ""',
    "SEPARATE from evidence",
)
NEW_MARKERS = (
    "≤5 words",
    "≤40 characters",
    "paper-level",
    "CORE technical contribution",
    "Autoregressive Blank Infilling",  # anti-example only
    "contrastive learning",  # anti-example only
    "appear verbatim in the sentences",
    "General paradigms ONLY if the exact phrase appears",
    "Machine Translation",
    "research_problem_description",
    "2-4 English sentences defining the research problem AS AN ENTITY",
    "research_problem_aliases",
    "2-4 English sentences defining the method AS AN ENTITY",
    "2-4 English sentences defining the dataset AS AN ENTITY",
    "only widely-recognized academic abbreviations",
    "methods[].name",
    "the total number of method names across ALL experiments",
    '{"name": "", "description": "", "aliases": []}',
    "experiments:",
    "0 to 3 items",
    "Paper-level methods budget",
    "main experiment vs ablation",
    "Do NOT put research_problem inside each experiment object",
    "prefer the task domain",
    "proper dataset/benchmark name only",
    'NOT "Table 2"',
    'anti-example: "ChatGPT"',
    "DeePSiM",
    "ToolMaker",
    # --- PR4 quality reinforcement ---
    "FORBIDDEN openers",  # anti paper-use leakage list
    "SELF-CHECK before emitting",  # self-check rule
    # --- PR5: description English-only ---
    "MUST be in English; FORBIDDEN Chinese characters",
    # --- 0.6.3: LLM closed-set domain / experiment_type ---
    "Do NOT put domain inside each experiment object",
    "computer_science, medicine, biology",
    "named ablation/component-removal",
    "public datasets/leaderboards",
)
REMOVED_LEAKY_POSITIVE_EXAMPLES = (
    # Old positive-example framing that encouraged template hallucination
    'Author-coined names and general paradigms are BOTH OK (e.g. "DeePSiM", "Bilinear Pooling", "contrastive learning", "Autoregressive Blank Infilling")',
)
REMOVED_PREFER_GENERAL = (
    "prefer general paradigms over proprietary names",
    "Put the most general paradigm first",
)
SCHEMA_MARKERS = (
    '"methods": [',
    '"name": "",',
    '"description": "",',
    '"aliases": []',
    '"research_problem_aliases": [],',
    '"domain": "",',
    '"experiment_type": "",',
)


def _assert_new_rules(text: str) -> None:
    assert OLD_COMBINED_RULE not in text
    for marker in REMOVED_MARKERS:
        assert marker not in text, f"stale marker still present: {marker!r}"
    for marker in REMOVED_PREFER_GENERAL:
        assert marker not in text, f"stale prefer-general marker still present: {marker!r}"
    for marker in REMOVED_LEAKY_POSITIVE_EXAMPLES:
        assert marker not in text, f"leaky positive example still present: {marker!r}"
    for marker in NEW_MARKERS:
        assert marker in text, f"missing marker: {marker!r}"


def _assert_schema_markers(text: str) -> None:
    for marker in SCHEMA_MARKERS:
        assert marker in text, f"missing schema marker: {marker!r}"
    assert "justification" not in text, "justification must be removed from schema/rules"


def test_build_wf4_prompt_has_multi_exp_schema() -> None:
    prompt = build_wf4_prompt(["Sample sentence."], "Test Paper")
    _assert_new_rules(prompt)
    _assert_schema_markers(prompt)
    # methods lives inside experiments[] object in the schema example
    exp_idx = prompt.index('"experiments"')
    methods_idx = prompt.index('"methods": [', exp_idx)
    assert methods_idx > exp_idx


def test_adapter_v0_matches_build_wf4_prompt() -> None:
    sentences = ["S1.", "S2."]
    title = "Title"
    assert build_wf4_prompt_for_adapter(sentences, title, None) == build_wf4_prompt(
        sentences, title
    )
    assert build_wf4_prompt_for_adapter(sentences, title, "v0") == build_wf4_prompt(
        sentences, title
    )


def test_adapter_schema_and_rules_markers() -> None:
    _assert_schema_markers(_SCHEMA)
    _assert_new_rules(_RULES)
    prompt_v3 = build_wf4_prompt_for_adapter(["Hello."], "T", "v3")
    _assert_new_rules(prompt_v3)
    _assert_schema_markers(prompt_v3)


if __name__ == "__main__":
    test_build_wf4_prompt_has_multi_exp_schema()
    test_adapter_v0_matches_build_wf4_prompt()
    test_adapter_schema_and_rules_markers()
    print("OK: all wf4 prompt rule tests passed")
