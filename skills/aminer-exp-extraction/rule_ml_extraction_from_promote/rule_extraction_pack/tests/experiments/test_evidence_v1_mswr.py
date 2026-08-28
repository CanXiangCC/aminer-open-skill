"""Unit tests for Evidence v1 MSWR strategy and evaluator."""

from __future__ import annotations

from experiments.rule_extraction.evidence.shared.evidence_evaluator import (
    _greedy_match,
    _match_fn,
    evaluate_experiment_evidence,
    is_verbatim_in_md,
)
from experiments.rule_extraction.evidence.strategies.v1_field_backtrace_mswr import EvidenceRuleV1


class TestNumericAnchor:
    def test_all_numbers_match(self):
        assert EvidenceRuleV1._numeric_anchor("achieved 96.0% AS", "CoT+SG&C achieved AS of 96.0") == 1.0

    def test_partial_match(self):
        assert EvidenceRuleV1._numeric_anchor("96.0% and 90.5%", "AS of 96.0 was best") == 0.5

    def test_no_numbers_in_query(self):
        assert EvidenceRuleV1._numeric_anchor("no numbers here", "some sentence 42") == 0.5

    def test_no_match(self):
        assert EvidenceRuleV1._numeric_anchor("99.9%", "completely different text") == 0.0


class TestGreedyDedup:
    def test_jaccard_dedup_skips_near_duplicate(self):
        md = (
            "We present an LLM-based method that leverages a scene graph for anomaly detection. "
            "We present an LLM-based method leveraging a scene graph for detection tasks. "
            "GPT-4 outperformed GPT-3.5-Turbo with AS 94.0%. "
            "The scene graph is essential for spatial reasoning in home environments."
        )
        experiments = [{
            "experiment_name": "SafetyDetect Evaluation",
            "method": "GPT-4 with scene graph and chain of thought prompting.",
            "key_results": [
                "GPT-4 achieved AS of 96.0% and CAS of 90.5%.",
                "Scene graph methods are significantly more competitive.",
            ],
        }]
        results = EvidenceRuleV1.extract_for_paper(md, experiments, k=3)
        evidence = results[0]["evidence"]
        assert len(evidence) <= 3
        # Near-duplicates should not both appear
        for i, a in enumerate(evidence):
            for b in evidence[i + 1:]:
                from src.evaluation.semantic import jaccard_similarity
                assert jaccard_similarity(a, b) <= 0.85


class TestVerbatimValidation:
    def test_non_substring_discarded(self):
        md = "The model achieved strong results on the benchmark dataset."
        experiments = [{
            "experiment_name": "Benchmark Test",
            "method": "Standard training procedure.",
            "key_results": ["This sentence does not exist anywhere in the markdown file at all."],
        }]
        results = EvidenceRuleV1.extract_for_paper(md, experiments, k=2)
        for sent in results[0]["evidence"]:
            assert is_verbatim_in_md(sent, md)

    def test_verbatim_ok_in_trace(self):
        md = "Our detection rate dropped to 82.7% in real world experiments on TurtleBot."
        experiments = [{
            "experiment_name": "Real World TurtleBot",
            "method": "TurtleBot navigates real-world room.",
            "key_results": ["The overall detection rate dropped to 82.7%."],
        }]
        results = EvidenceRuleV1.extract_for_paper(md, experiments, k=1)
        assert len(results[0]["evidence"]) >= 1
        selected = results[0]["evidence_trace"]["selected"]
        assert all(s["verbatim_ok"] for s in selected)


class TestSingleExperimentScope:
    def test_single_exp_scope_is_one(self):
        md = "## Results\n\nFirst experiment sentence here with enough length.\n\nSecond sentence also long enough."
        experiments = [{
            "experiment_name": "Only Experiment",
            "method": "Some method description here.",
            "key_results": ["First experiment sentence here with enough length."],
        }]
        results = EvidenceRuleV1.extract_for_paper(md, experiments, k=1)
        selected = results[0]["evidence_trace"]["selected"]
        if selected:
            assert selected[0]["scope"] == 1.0


class TestEvaluatorGreedyMatch:
    def test_exact_match(self):
        gold = ["Sentence A here.", "Sentence B here."]
        pred = ["Sentence A here.", "Unrelated extra."]
        pairs, matched_gold, _ = _greedy_match(gold, pred, _match_fn)
        assert len(pairs) == 1
        assert 0 in matched_gold

    def test_fuzzy_substring_match(self):
        gold = ["Our method achieved ninety six percent anomaly success rate."]
        pred = ["achieved ninety six percent anomaly success rate on benchmark"]
        pairs, _, _ = _greedy_match(gold, pred, _match_fn)
        assert len(pairs) == 1

    def test_jaccard_match(self):
        md = "GPT-4 achieved AS of 96.0 and CAS of 90.5 on SafetyDetect dataset."
        gold = ["GPT-4 achieved AS of 96.0 and CAS of 90.5."]
        pred = ["GPT-4 achieved AS of 96.0 and CAS of 90.5 on SafetyDetect dataset."]
        ev = evaluate_experiment_evidence(gold, pred, md, k=5)
        assert ev["semantic_recall_at_k"] >= 1.0 or ev["recall_at_k"] >= 1.0

    def test_verbatim_gold_fields(self):
        md = "Exact match sentence appears in the markdown document here."
        gold = ["Exact match sentence appears in the markdown document here.", "Not in md paraphrase."]
        pred = ["Exact match sentence appears in the markdown document here."]
        ev = evaluate_experiment_evidence(gold, pred, md, k=5)
        assert ev["gold_verbatim_count"] == 1
        assert ev["semantic_recall_at_k_verbatim_gold"] == 1.0
        assert ev["recall_ceiling_at_k"] == 0.5  # k_used=1 pred, gold_count=2
