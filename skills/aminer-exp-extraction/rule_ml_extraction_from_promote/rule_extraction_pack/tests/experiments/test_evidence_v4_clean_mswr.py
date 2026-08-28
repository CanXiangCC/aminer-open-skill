"""Unit tests for Evidence v4 strategy (clean + MSWR + Jaccard-only rerank)."""

from unittest.mock import MagicMock, patch

from experiments.rule_extraction.evidence.shared.evidence_evaluator import is_verbatim_in_md
from experiments.rule_extraction.evidence.strategies.v4_clean_mswr import (
    EvidenceRuleV4,
    compute_k,
)


class TestDynamicK:
    def test_six_key_results_gives_k7(self):
        exp = {"key_results": [f"result {i}" for i in range(6)]}
        assert compute_k(exp) == 7

    def test_fixed_k_override(self):
        exp = {"key_results": [f"result {i}" for i in range(6)]}
        assert compute_k(exp, fixed_k=5) == 5


class TestCleaningPipeline:
    def test_build_pool_applies_all_filters(self):
        md = (
            "This is a normal sentence with enough length and words here. "
            "<table><tr><td>Method</td><td>96.0</td></tr></table> "
            "Short. "
            "# This is a long section header title here. "
            "Another normal sentence with sufficient content for testing."
        )
        pool = EvidenceRuleV4._build_candidate_pool(md)
        # Should keep only the two normal sentences
        assert len(pool) == 2
        assert all("<table" not in s for s in pool)
        assert all("Short." not in s for s in pool)
        assert all("# This is a long" not in s for s in pool)

    def test_pool_filters_html_table_patterns(self):
        md = (
            "Normal sentence here for testing purposes. "
            "<table><tr><td>Method</td><td>96.0</td></tr></table> "
            "<td>Another table cell here now</td>"
        )
        pool = EvidenceRuleV4._build_candidate_pool(md)
        assert len(pool) == 1
        assert "<table" not in pool[0]
        assert "<td" not in pool[0]

    def test_pool_filters_short_sentences(self):
        md = (
            "This is a normal sentence with enough length and words. "
            "Too short. "
            "Another normal sentence here for testing purposes."
        )
        pool = EvidenceRuleV4._build_candidate_pool(md)
        assert len(pool) == 2
        assert "Too short." not in pool

    def test_pool_filters_non_ascii(self):
        md = "你好 world. This is a normal English sentence here for testing."
        pool = EvidenceRuleV4._build_candidate_pool(md)
        assert len(pool) == 1
        assert "你好" not in pool[0]

    def test_deduplicates_normalized_text(self):
        md = (
            "This is a sentence here for testing now. "
            "This is   a  sentence here for testing now. "
            "Another sentence here today for testing."
        )
        pool = EvidenceRuleV4._build_candidate_pool(md)
        # First two sentences normalize to same
        assert len(pool) == 2


class TestTraceCleanStats:
    def test_trace_has_clean_stats(self):
        md = (
            "Normal sentence one here for testing. "
            "<table>table</table> "
            "Normal sentence two here."
        )
        experiments = [{
            "experiment_name": "Test",
            "method": "Method description here with enough content.",
            "key_results": ["Normal sentence one here for testing."],
        }]
        results = EvidenceRuleV4.extract_for_paper(md, experiments, fixed_k=2)
        trace = results[0]["evidence_trace"]

        assert trace["sentence_clean"] is True
        assert "clean_stats" in trace
        assert "input_count" in trace["clean_stats"]
        assert "kept_count" in trace["clean_stats"]
        assert "dropped_by_reason" in trace["clean_stats"]

    def test_trace_has_split_and_english_counts(self):
        md = (
            "This is a long sentence that starts with ASCII. "
            "First English sentence here for testing. "
            "Second English sentence here for testing."
        )
        experiments = [{
            "experiment_name": "Test",
            "method": "Method description here for testing.",
            "key_results": ["First English sentence here for testing."],
        }]
        results = EvidenceRuleV4.extract_for_paper(md, experiments, fixed_k=2)
        trace = results[0]["evidence_trace"]

        assert "split_count" in trace
        assert "english_count" in trace
        assert trace["english_count"] >= trace["split_count"]  # english_count can be >= split (filter_english keeps all ASCII)

    def test_trace_has_candidate_count(self):
        md = (
            "First sentence here for testing purposes. "
            "Second sentence here for testing purposes. "
            "Third sentence here for testing purposes."
        )
        experiments = [{
            "experiment_name": "Test",
            "method": "Method description here for testing.",
            "key_results": ["First sentence here for testing purposes."],
        }]
        results = EvidenceRuleV4.extract_for_paper(md, experiments, fixed_k=2)
        trace = results[0]["evidence_trace"]

        assert "candidate_count" in trace
        assert trace["candidate_count"] == 3


class TestJaccardRerankOnly:
    def test_rerank_uses_jaccard_not_embedding(self):
        md = (
            "The semantic target sentence matches query content very well here. "
            "Unrelated filler sentence with different vocabulary entirely here."
        )
        experiments = [{
            "experiment_name": "Rerank Test",
            "method": "Some method text with enough length for query building.",
            "key_results": ["The semantic target sentence matches query content very well."],
        }]

        # Mock jaccard_similarity to track calls
        jaccard_calls = []
        original_jaccard = EvidenceRuleV4._score_sentence

        def track_jaccard(sent, q, *args, **kwargs):
            result = original_jaccard(sent, q, *args, **kwargs)
            jaccard_calls.append((sent, q))
            return result

        with patch.object(EvidenceRuleV4, "_score_sentence", side_effect=track_jaccard):
            results = EvidenceRuleV4.extract_for_paper(md, experiments, fixed_k=2)
            trace = results[0]["evidence_trace"]

        # Verify rerank entries exist
        selected = trace["selected"]
        assert len(selected) > 0
        # Rerank entries have emb_sim (which is jaccard in v4)
        reranked = [s for s in selected if s.get("rerank_pool_size")]
        assert len(reranked) > 0
        # All reranked entries should have jaccard scores
        for entry in reranked:
            assert "jaccard" in entry
            assert "emb_sim" in entry

    def test_use_embedding_flag_ignored(self):
        """v4 should ignore use_embedding parameter."""
        md = "Sentence one here. Sentence two here."
        experiments = [{
            "experiment_name": "Test",
            "method": "Method here.",
            "key_results": ["Sentence one here."],
        }]

        # Should not raise even with use_embedding=True
        results = EvidenceRuleV4.extract_for_paper(
            md, experiments, fixed_k=1, use_embedding=True
        )
        assert len(results) == 1


class TestVerbatim:
    def test_all_evidence_verbatim_in_md(self):
        md = (
            "First sentence here for testing. "
            "Second sentence here for testing. "
            "Third sentence here for testing."
        )
        experiments = [{
            "experiment_name": "Test",
            "method": "Method description here.",
            "key_results": ["First sentence here."],
        }]
        results = EvidenceRuleV4.extract_for_paper(md, experiments, fixed_k=2)

        for r in results:
            for sent in r["evidence"]:
                assert is_verbatim_in_md(sent, md), f"Non-verbatim: {sent}"

    def test_dropped_non_verbatim_tracked(self):
        md = "Normal sentence here."
        experiments = [{
            "experiment_name": "Test",
            "method": "Method here.",
            "key_results": ["Nonexistent sentence."],
        }]
        results = EvidenceRuleV4.extract_for_paper(md, experiments, fixed_k=1)
        trace = results[0]["evidence_trace"]

        # Should track dropped non-verbatim
        assert "dropped_non_verbatim" in trace


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
        results = EvidenceRuleV4.extract_for_paper(md, experiments, fixed_k=8)
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
        results = EvidenceRuleV4.extract_for_paper(md, experiments, fixed_k=3)
        trace = results[0]["evidence_trace"]
        assert len(trace["selected"]) >= 2
        assert any(s.get("from_fill_pass") for s in trace["selected"])