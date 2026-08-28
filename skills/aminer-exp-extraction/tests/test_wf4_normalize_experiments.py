"""Tests for wf4 multi-exp normalize + coerce (incl. flat compat, cap, empty)."""

from __future__ import annotations

import sys
from pathlib import Path

PROD_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROD_ROOT))

from pipeline.production.adapters.wf4_normalize import (  # noqa: E402
    coerce_wf4_llm_parsed,
    method_name_for_ml,
    normalize_domain,
    normalize_experiment_type,
    normalize_experiments,
    normalize_llm_datasets,
    normalize_methods,
)
from pipeline.production.config import WF4_MAX_EXPERIMENTS  # noqa: E402


def _m(name: str, description: str = "") -> dict:
    return {"name": name, "description": description, "aliases": []}


def _exp(name: str, method: str = "Some Method") -> dict:
    """Legacy-shaped experiment (method + method_description) for coerce tests."""
    return {
        "experiment_name": name,
        "key_results": ["r1"],
        "method": method,
        "method_description": "A method description.",
        "research_goal": "A goal.",
        "experiment_subject": ["task a"],
        "metrics": ["Accuracy"],
        "datasets": [{"name": "DS1", "aliases": []}],
    }


def _assert_no_legacy_method_keys(exp: dict) -> None:
    assert "method" not in exp
    assert "method_description" not in exp


def test_normalize_one_experiment() -> None:
    out = normalize_experiments([_exp("E1")])
    assert len(out) == 1
    assert out[0]["experiment_name"] == "E1"
    assert out[0]["methods"] == [_m("Some Method", "A method description.")]
    _assert_no_legacy_method_keys(out[0])
    assert out[0]["datasets"][0]["name"] == "DS1"
    assert "confidence_breakdown" not in out[0]["datasets"][0]


def test_normalize_two_three_experiments() -> None:
    out = normalize_experiments([_exp("E1"), _exp("E2", "Method B")])
    assert len(out) == 2
    out3 = normalize_experiments([_exp(f"E{i}") for i in range(3)])
    assert len(out3) == 3


def test_normalize_truncates_over_max() -> None:
    raw = [_exp(f"E{i}") for i in range(WF4_MAX_EXPERIMENTS + 2)]
    out = normalize_experiments(raw)
    assert len(out) == WF4_MAX_EXPERIMENTS
    assert out[0]["experiment_name"] == "E0"
    assert out[-1]["experiment_name"] == f"E{WF4_MAX_EXPERIMENTS - 1}"


def test_normalize_drops_malformed() -> None:
    out = normalize_experiments([_exp("ok"), "bad", None, 123, _exp("ok2")])
    assert len(out) == 2
    assert [e["experiment_name"] for e in out] == ["ok", "ok2"]


def test_coerce_new_multi_exp_schema() -> None:
    parsed = {
        "research_problem": "Machine Translation",
        "research_problem_description": "Translate text.",
        "experiments": [_exp("Main"), _exp("Ablation", "Ablation Method")],
    }
    value = coerce_wf4_llm_parsed(parsed)
    assert value["research_problem"] == "Machine Translation"
    assert len(value["experiments"]) == 2
    assert "research_problem" not in value["experiments"][0]
    assert value["experiments"][0]["methods"] == [
        _m("Some Method", "A method description.")
    ]
    _assert_no_legacy_method_keys(value["experiments"][0])


def test_coerce_old_flat_wrap_compat() -> None:
    parsed = {
        "research_problem": "Object Detection",
        "research_problem_description": "Detect objects.",
        "experiment_name": "Flat Exp",
        "method": "CNN",
        "method_description": "A CNN.",
        "research_goal": "Detect better.",
        "experiment_subject": ["detection"],
        "key_results": ["+2%"],
        "metrics": ["mAP"],
        "datasets": [{"name": "COCO"}],
    }
    value = coerce_wf4_llm_parsed(parsed)
    assert value["research_problem"] == "Object Detection"
    assert len(value["experiments"]) == 1
    assert value["experiments"][0]["experiment_name"] == "Flat Exp"
    assert value["experiments"][0]["methods"] == [_m("CNN", "A CNN.")]
    _assert_no_legacy_method_keys(value["experiments"][0])
    assert value["experiments"][0]["datasets"][0]["name"] == "COCO"


def test_coerce_empty_and_malformed_no_fabricate() -> None:
    assert coerce_wf4_llm_parsed(None)["experiments"] == []
    assert coerce_wf4_llm_parsed("not a dict")["experiments"] == []
    assert coerce_wf4_llm_parsed({})["experiments"] == []
    assert coerce_wf4_llm_parsed({"experiments": []})["experiments"] == []
    assert coerce_wf4_llm_parsed({"experiments": [None, "x"]})["experiments"] == []


def test_coerce_empty_experiments_with_rp_ok_shape() -> None:
    """EXT-02: RP + empty experiments is a valid coerce result (caller marks ok)."""
    value = coerce_wf4_llm_parsed(
        {
            "research_problem": "Survey of Graphs",
            "research_problem_description": "Review graph methods.",
            "experiments": [],
        }
    )
    assert value["research_problem"] == "Survey of Graphs"
    assert value["experiments"] == []
    assert value["methods_truncated_by_paper_budget"] is False


def test_paper_budget_e3_caps_one_method_each() -> None:
    """EXT-09: E=3 with 3 methods each → M_total≤3 and ≤1 per experiment."""
    exps = []
    for i in range(3):
        exps.append(
            {
                "experiment_name": f"E{i}",
                "key_results": [],
                "methods": [
                    _m(f"M{i}a", f"desc {i}a"),
                    _m(f"M{i}b", f"desc {i}b"),
                    _m(f"M{i}c", f"desc {i}c"),
                ],
                "research_goal": "",
                "experiment_subject": [],
                "metrics": [],
                "datasets": [],
            }
        )
    value = coerce_wf4_llm_parsed(
        {"research_problem": "X", "research_problem_description": "", "experiments": exps}
    )
    assert value["methods_truncated_by_paper_budget"] is True
    out = value["experiments"]
    assert len(out) == 3
    totals = [len(e["methods"]) for e in out]
    assert all(n <= 1 for n in totals)
    assert sum(totals) <= 3
    assert out[0]["methods"] == [_m("M0a", "desc 0a")]
    _assert_no_legacy_method_keys(out[0])


def test_paper_budget_e1_keeps_up_to_three() -> None:
    """EXT-09: E=1 may keep up to 3 methods."""
    value = coerce_wf4_llm_parsed(
        {
            "research_problem": "X",
            "research_problem_description": "",
            "experiments": [
                {
                    "experiment_name": "Main",
                    "methods": [
                        _m("A", "desc A"),
                        _m("B", "desc B"),
                        _m("C", "desc C"),
                        _m("D", "desc D"),
                    ],
                    "key_results": [],
                    "research_goal": "",
                    "experiment_subject": [],
                    "metrics": [],
                    "datasets": [],
                }
            ],
        }
    )
    exp = value["experiments"][0]
    assert exp["methods"] == [
        _m("A", "desc A"),
        _m("B", "desc B"),
        _m("C", "desc C"),
    ]
    _assert_no_legacy_method_keys(exp)
    assert value["methods_truncated_by_paper_budget"] is True


def test_legacy_method_promoted_to_methods() -> None:
    out = normalize_experiments([_exp("E1", "Legacy")])
    assert out[0]["methods"] == [_m("Legacy", "A method description.")]
    _assert_no_legacy_method_keys(out[0])


def test_legacy_string_methods_shared_description_on_first() -> None:
    """string[] + shared method_description → description only on first name."""
    out = normalize_methods(
        ["A", "B"],
        legacy_method_description="Shared desc.",
    )
    assert out == [_m("A", "Shared desc."), _m("B", "")]


def test_object_methods_passthrough() -> None:
    out = normalize_methods([_m("Foo", "Bar sentences."), _m("Baz", "")])
    assert out == [_m("Foo", "Bar sentences."), _m("Baz", "")]


def test_description_only_yields_empty() -> None:
    assert normalize_methods(None, legacy_method_description="Only desc.") == []


def test_method_name_for_ml() -> None:
    assert method_name_for_ml({"methods": [_m("X", "d")]}) == "X"
    assert method_name_for_ml({"methods": []}) == ""
    assert method_name_for_ml({"method": "ignored"}) == ""
    assert method_name_for_ml(None) == ""


def test_drop_paper_structure_dataset_names() -> None:
    kept = normalize_llm_datasets(
        [
            {"name": "ImageNet"},
            {"name": "Table 6"},
            {"name": "Table 2"},
            {"name": "Fig 1"},
            {"name": "Figure 3"},
            {"name": "Algorithm 1"},
            {"name": "Section 4.2"},
            {"name": "Appendix A"},  # no digits → keep (not matched)
            {"name": "Dyck"},
        ]
    )
    names = [d["name"] for d in kept]
    assert names == ["ImageNet", "Appendix A", "Dyck"]


def test_methods_object_carries_aliases_drops_justification() -> None:
    """methods objects keep aliases; justification is dropped from schema."""
    out = normalize_methods(
        [
            {
                "name": "DPO",
                "description": "Direct preference optimization.",
                "justification": "Core: \"DPO bypasses the reward model\".",
                "aliases": ["Direct Preference Optimization"],
            }
        ]
    )
    assert out == [
        {
            "name": "DPO",
            "description": "Direct preference optimization.",
            "aliases": ["Direct Preference Optimization"],
        }
    ]
    assert "justification" not in out[0]


def test_legacy_methods_object_coerced_up() -> None:
    """Legacy {name, description} coerced up with empty aliases."""
    out = normalize_methods([{"name": "Old", "description": "d"}])
    assert out == [{"name": "Old", "description": "d", "aliases": []}]


def test_datasets_drop_justification() -> None:
    """Incoming dataset justification is ignored (not in schema)."""
    out = normalize_llm_datasets(
        [
            {
                "name": "WMT",
                "description": "A translation benchmark.",
                "justification": "Used: \"we evaluate on WMT\".",
            },
            {"name": "Empty"},
        ]
    )
    assert "justification" not in out[0]
    assert out[0]["description"] == "A translation benchmark."
    assert "justification" not in out[1]


def test_coerce_carries_problem_aliases() -> None:
    """Paper-level aliases pass through coerce; justification is not kept."""
    value = coerce_wf4_llm_parsed(
        {
            "research_problem": "LLM Hallucination",
            "research_problem_description": "Hallucination is ...",
            "research_problem_justification": "Core: \"LLMs exhibit hallucinations\".",
            "research_problem_aliases": ["Hallucination"],
            "experiments": [],
        }
    )
    assert "research_problem_justification" not in value
    assert value["research_problem_aliases"] == ["Hallucination"]


def test_coerce_problem_aliases_default_empty() -> None:
    """Missing aliases default to empty (not None)."""
    value = coerce_wf4_llm_parsed(
        {"research_problem": "X", "research_problem_description": "", "experiments": []}
    )
    assert value["research_problem_aliases"] == []
    nd = coerce_wf4_llm_parsed(None)
    assert nd["research_problem_aliases"] == []
    assert "research_problem_justification" not in nd


def test_coerce_drops_method_and_dataset_justification() -> None:
    """Entity kept; justification keys stripped from methods/datasets."""
    value = coerce_wf4_llm_parsed(
        {
            "research_problem": "LLM Hallucination",
            "research_problem_justification": "Core: \"LLMs exhibit hallucinations\".",
            "experiments": [
                {
                    "experiment_name": "E0",
                    "methods": [
                        {
                            "name": "DPO",
                            "description": "d",
                            "justification": "m: \"DPO bypasses reward model\".",
                            "aliases": [],
                        }
                    ],
                    "datasets": [
                        {
                            "name": "WMT",
                            "description": "d",
                            "justification": "ds: \"we evaluate on WMT\".",
                        }
                    ],
                }
            ],
        },
        full_text="LLMs exhibit hallucinations in open-ended generation.",
    )
    assert "research_problem_justification" not in value
    exp = value["experiments"][0]
    assert exp["methods"][0]["name"] == "DPO"
    assert "justification" not in exp["methods"][0]
    assert exp["datasets"][0]["name"] == "WMT"
    assert "justification" not in exp["datasets"][0]


def test_normalize_domain_and_experiment_type_enums() -> None:
    assert normalize_domain("computer_science") == "computer_science"
    assert normalize_domain("Computer Science") == "computer_science"
    assert normalize_domain("computer-science") == "computer_science"
    assert normalize_domain("not_a_domain") == ""
    assert normalize_domain("") == ""
    assert normalize_domain(None) == ""
    assert normalize_experiment_type("benchmark") == "benchmark"
    assert normalize_experiment_type("Human Study") == "human_study"
    assert normalize_experiment_type("clinical-trial") == "clinical_trial"
    assert normalize_experiment_type("unknown_label") == ""
    assert normalize_experiment_type(None) == ""


def test_coerce_carries_domain_and_per_exp_type() -> None:
    value = coerce_wf4_llm_parsed(
        {
            "research_problem": "Machine Translation",
            "domain": "Computer Science",
            "experiments": [
                {**_exp("Main"), "experiment_type": "benchmark"},
                {**_exp("Ablation", "Ablation Method"), "experiment_type": "Ablation"},
            ],
        }
    )
    assert value["domain"] == "computer_science"
    assert value["experiments"][0]["experiment_type"] == "benchmark"
    assert value["experiments"][1]["experiment_type"] == "ablation"


def test_coerce_unknown_enums_become_empty() -> None:
    value = coerce_wf4_llm_parsed(
        {
            "research_problem": "X",
            "domain": "quantum_computing",
            "experiments": [{**_exp("E0"), "experiment_type": "pretraining"}],
        }
    )
    assert value["domain"] == ""
    assert value["experiments"][0]["experiment_type"] == ""


def test_coerce_old_flat_wrap_carries_experiment_type() -> None:
    parsed = {
        "research_problem": "Object Detection",
        "research_problem_description": "Detect objects.",
        "domain": "computer_science",
        "experiment_name": "Flat Exp",
        "experiment_type": "comparison",
        "method": "CNN",
        "method_description": "A CNN.",
        "research_goal": "Detect better.",
        "experiment_subject": ["detection"],
        "key_results": ["+2%"],
        "metrics": ["mAP"],
        "datasets": [{"name": "COCO"}],
    }
    value = coerce_wf4_llm_parsed(parsed)
    assert value["domain"] == "computer_science"
    assert value["experiments"][0]["experiment_type"] == "comparison"


def test_coerce_missing_enums_default_empty() -> None:
    value = coerce_wf4_llm_parsed(
        {"research_problem": "X", "research_problem_description": "", "experiments": []}
    )
    assert value["domain"] == ""
    nd = coerce_wf4_llm_parsed(None)
    assert nd["domain"] == ""


if __name__ == "__main__":
    test_normalize_one_experiment()
    test_normalize_two_three_experiments()
    test_normalize_truncates_over_max()
    test_normalize_drops_malformed()
    test_coerce_new_multi_exp_schema()
    test_coerce_old_flat_wrap_compat()
    test_coerce_empty_and_malformed_no_fabricate()
    test_coerce_empty_experiments_with_rp_ok_shape()
    test_paper_budget_e3_caps_one_method_each()
    test_paper_budget_e1_keeps_up_to_three()
    test_legacy_method_promoted_to_methods()
    test_legacy_string_methods_shared_description_on_first()
    test_object_methods_passthrough()
    test_description_only_yields_empty()
    test_method_name_for_ml()
    test_drop_paper_structure_dataset_names()
    test_methods_object_carries_aliases_drops_justification()
    test_legacy_methods_object_coerced_up()
    test_datasets_drop_justification()
    test_coerce_carries_problem_aliases()
    test_coerce_problem_aliases_default_empty()
    test_coerce_drops_method_and_dataset_justification()
    test_normalize_domain_and_experiment_type_enums()
    test_coerce_carries_domain_and_per_exp_type()
    test_coerce_unknown_enums_become_empty()
    test_coerce_old_flat_wrap_carries_experiment_type()
    test_coerce_missing_enums_default_empty()
    print("OK: all wf4 normalize experiment tests passed")