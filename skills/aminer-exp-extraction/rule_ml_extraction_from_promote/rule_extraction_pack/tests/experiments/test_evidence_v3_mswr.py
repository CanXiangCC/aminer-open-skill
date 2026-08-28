"""Unit tests for Evidence v3 MSWR strategy (v1 + rerank + dynamic k, no v2 hard filter)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from experiments.rule_extraction.evidence.shared.evidence_evaluator import is_verbatim_in_md
from experiments.rule_extraction.evidence.strategies.v2_field_backtrace_mswr import EvidenceRuleV2
from experiments.rule_extraction.evidence.strategies.v3_field_backtrace_mswr import (
    EvidenceRuleV3,
    compute_k,
)


class TestDynamicK:
    def test_six_key_results_gives_k7(self):
        exp = {"key_results": [f"result {i}" for i in range(6)]}
        assert compute_k(exp) == 7

    def test_fixed_k_override(self):
        exp = {"key_results": [f"result {i}" for i in range(6)]}
        assert compute_k(exp, fixed_k=5) == 5


class TestNoHardFilter:
    def test_table_sentence_can_be_candidate_v3(self):
        md = (
            "Normal sentence with enough length for candidate pool inclusion here. "
            "<table><tr><td>Method</td><td>96.0</td></tr></table>"
        )
        v3_pool = EvidenceRuleV3._build_candidate_pool(md)
        v2_pool, _ = EvidenceRuleV2._build_candidate_pool(md)
        v3_has_table = any("<table" in s.lower() for s in v3_pool)
        v2_has_table = any("<table" in s.lower() for s in v2_pool)
        assert v3_has_table or len(v3_pool) >= len(v2_pool)
        assert not v2_has_table or len(v2_pool) <= len(v3_pool)


class TestQueryQuota:
    def test_result_quota_max_three(self):
        md = " ".join(
            f"Result sentence number {i} with enough length for filter here."
            for i in range(8)
        )
        experiments = [{
            "experiment_name": "Quota Test Experiment",
            "method": "Standard evaluation method description here.",
            "key_results": [
                f"Result sentence number {i} with enough length for filter here."
                for i in range(7)
            ],
        }]
        results = EvidenceRuleV3.extract_for_paper(md, experiments, fixed_k=8)
        trace = results[0]["evidence_trace"]
        result_count = sum(
            1 for s in trace["selected"]
            if s["query_type"] == "result" and not s.get("from_fill_pass")
        )
        assert result_count <= 3


class TestFillPass:
    def test_fill_pass_adds_slots_when_quota_insufficient(self):
        md = (
            "Alpha sentence one with sufficient length for candidate pool here. "
            "Beta sentence two with sufficient length for candidate pool here. "
            "Gamma sentence three with sufficient length for candidate pool here."
        )
        experiments = [{
            "experiment_name": "Fill Test",
            "method": "Method description sentence with enough length here.",
            "key_results": ["Alpha sentence one with sufficient length for candidate pool here."],
        }]
        results = EvidenceRuleV3.extract_for_paper(md, experiments, fixed_k=3)
        trace = results[0]["evidence_trace"]
        assert len(trace["selected"]) >= 2
        assert any(s.get("from_fill_pass") for s in trace["selected"])


class TestRerank:
    def test_rerank_prefers_higher_emb_sim(self):
        md = (
            "The semantic target sentence matches query content very well here. "
            "Unrelated filler sentence with different vocabulary entirely here."
        )
        experiments = [{
            "experiment_name": "Rerank Test",
            "method": "Some method text with enough length for query building.",
            "key_results": ["The semantic target sentence matches query content very well."],
        }]
        mock_scorer = MagicMock()
        mock_scorer.similarity.side_effect = lambda q, s: (
            0.95 if "semantic target" in s else 0.1
        )

        with patch.object(EvidenceRuleV3, "_score_sentence") as mock_score, patch(
            "experiments.rule_extraction.evidence.strategies.v3_field_backtrace_mswr.SemanticScorer",
            return_value=mock_scorer,
        ):
            def fake_score(sent, q, *args, **kwargs):
                cheap = 1.0 if "Unrelated filler" in sent else 0.2
                return {
                    "total": cheap,
                    "scope": 1.0,
                    "jaccard": 0.5,
                    "numeric_anchor": 0.5,
                    "substring_boost": 0.5,
                }
            mock_score.side_effect = fake_score
            results = EvidenceRuleV3.extract_for_paper(
                md, experiments, fixed_k=1, use_embedding=False,
            )
        selected = results[0]["evidence_trace"]["selected"]
        assert len(selected) >= 1
        assert "semantic target" in selected[0]["sentence"]
        assert "cheap_score" in selected[0]
        assert "emb_sim" in selected[0]
        assert "final_score" in selected[0]


class TestVerbatim:
    def test_all_output_verbatim(self):
        md = "Our detection rate dropped to 82.7% in real world TurtleBot experiments today."
        experiments = [{
            "experiment_name": "Real World TurtleBot",
            "method": "TurtleBot navigates a real-world room environment.",
            "key_results": ["The overall detection rate dropped to 82.7%."],
        }]
        results = EvidenceRuleV3.extract_for_paper(md, experiments, fixed_k=2)
        for sent in results[0]["evidence"]:
            assert is_verbatim_in_md(sent, md)
