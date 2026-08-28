"""Unit tests for Evidence v2 MSWR strategy and enhanced evaluator."""

from __future__ import annotations

from experiments.rule_extraction.evidence.shared.evidence_evaluator import (
    evaluate_experiment_evidence,
    paper_is_cross_lingual,
)
from experiments.rule_extraction.evidence.strategies.v2_field_backtrace_mswr import (
    EvidenceRuleV2,
    compute_k,
)


class TestHardFilter:
    def test_table_sentence_not_in_candidates(self):
        md = (
            "Normal sentence with enough length for candidate pool inclusion here. "
            "<table><tr><td>Method</td><td>96.0</td></tr></table> "
            "Another valid sentence with sufficient length for testing purposes."
        )
        candidates, trace = EvidenceRuleV2._build_candidate_pool(md)
        for sent in candidates:
            assert "<table" not in sent.lower()
        assert trace["hard_noise_dropped"]

    def test_numeric_anchor_zero_for_table(self):
        table_sent = "<table><tr><td>AS</td><td>96.0</td></tr></table>"
        assert EvidenceRuleV2._numeric_anchor("96.0% AS rate", table_sent) == 0.0


class TestDynamicK:
    def test_six_key_results_gives_k7(self):
        exp = {"key_results": [f"result {i}" for i in range(6)]}
        assert compute_k(exp) == 7

    def test_fixed_k_override(self):
        exp = {"key_results": [f"result {i}" for i in range(6)]}
        assert compute_k(exp, fixed_k=5) == 5


class TestQueryQuota:
    def test_result_quota_max_three(self):
        md = (
            "First result sentence with enough length to pass noise filter easily here. "
            "Second result sentence with enough length to pass noise filter easily here. "
            "Third result sentence with enough length to pass noise filter easily here. "
            "Fourth result sentence with enough length to pass noise filter easily here. "
            "Fifth result sentence with enough length to pass noise filter easily here. "
            "Sixth result sentence with enough length to pass noise filter easily here."
        )
        experiments = [{
            "experiment_name": "Quota Test Experiment",
            "method": "Standard evaluation method description here.",
            "key_results": [
                "First result sentence with enough length to pass noise filter easily here.",
                "Second result sentence with enough length to pass noise filter easily here.",
                "Third result sentence with enough length to pass noise filter easily here.",
                "Fourth result sentence with enough length to pass noise filter easily here.",
                "Fifth result sentence with enough length to pass noise filter easily here.",
                "Sixth result sentence with enough length to pass noise filter easily here.",
            ],
        }]
        results = EvidenceRuleV2.extract_for_paper(md, experiments, fixed_k=8)
        trace = results[0]["evidence_trace"]
        result_count = sum(1 for s in trace["selected"] if s["query_type"] == "result")
        assert result_count <= 3


class TestRerankTrace:
    def test_selected_has_rerank_fields(self):
        md = "Our detection rate dropped to 82.7% in real world TurtleBot experiments today."
        experiments = [{
            "experiment_name": "Real World TurtleBot",
            "method": "TurtleBot navigates a real-world room environment.",
            "key_results": ["The overall detection rate dropped to 82.7%."],
        }]
        results = EvidenceRuleV2.extract_for_paper(md, experiments, fixed_k=2)
        selected = results[0]["evidence_trace"]["selected"]
        assert len(selected) >= 1
        for s in selected:
            assert "cheap_score" in s
            assert "emb_sim" in s
            assert "final_score" in s
            assert "rerank_pool_size" in s


class TestEvaluatorVerbatimGold:
    def test_non_verbatim_gold_excluded_from_verbatim_recall(self):
        md = "GPT-4 achieved AS of 96.0 and CAS of 90.5 on the benchmark dataset."
        gold = [
            "GPT-4 achieved AS of 96.0 and CAS of 90.5 on the benchmark dataset.",
            "This gold sentence is a paraphrase not found in markdown at all.",
        ]
        pred = ["GPT-4 achieved AS of 96.0 and CAS of 90.5 on the benchmark dataset."]
        ev = evaluate_experiment_evidence(gold, pred, md, k=5)
        assert ev["gold_verbatim_count"] == 1
        assert ev["gold_non_verbatim_count"] == 1
        assert ev["semantic_recall_at_k_verbatim_gold"] >= 1.0
        assert ev["semantic_recall_at_k_all_gold"] < 1.0


class TestCrossLingual:
    def test_cjk_key_result_detected(self):
        experiments = [{
            "experiment_name": "Test",
            "key_results": ["在多个数据集上取得了最优结果"],
        }]
        assert paper_is_cross_lingual(experiments) is True

    def test_english_only_not_cross_lingual(self):
        experiments = [{
            "experiment_name": "Test",
            "key_results": ["Achieved state of the art on benchmark"],
        }]
        assert paper_is_cross_lingual(experiments) is False
