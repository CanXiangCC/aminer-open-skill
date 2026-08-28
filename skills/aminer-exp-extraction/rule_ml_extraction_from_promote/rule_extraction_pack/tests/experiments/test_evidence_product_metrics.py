"""Tests for evidence product-track metrics."""

from experiments.rule_extraction.evidence.shared.evidence_evaluator import (
    PRODUCT_THRESHOLDS,
    check_product_gates,
    evaluate_experiment_product,
    is_noise_pred_sentence,
    relevance_score_for_sentence,
)


class TestNoiseDetection:
    def test_bib_line_is_noise(self):
        assert is_noise_pred_sentence("In WACV , pages 586–595.")

    def test_url_is_noise(self):
        assert is_noise_pred_sentence("http://www.fgnet.rsunit.com.")

    def test_table_html_is_noise(self):
        assert is_noise_pred_sentence("<table><tr><td>96.0</td></tr></table>")

    def test_result_sentence_not_noise(self):
        sent = (
            "CQIL ranks first on Protocol 1 with APCER 11.09%, "
            "BPCER 10.29%, and ACER 10.69%."
        )
        assert not is_noise_pred_sentence(sent)


class TestRelevance:
    def test_high_overlap_with_key_results(self):
        kr = "CQIL ranks first on Protocol 1 with APCER 11.09%, BPCER 10.29%, and ACER 10.69%."
        pred = "As shown in Tab. IV, CQIL ranks first with APCER 11.09% and BPCER 10.29%."
        score = relevance_score_for_sentence(pred, [kr])
        assert score >= PRODUCT_THRESHOLDS["relevance_mean_min"]

    def test_unrelated_sentence_low_relevance(self):
        kr = "CQIL ranks first on Protocol 1 with APCER 11.09%."
        pred = "Index Terms—Face anti-spoofing, Dataset, Surveillance scenes."
        score = relevance_score_for_sentence(pred, [kr])
        assert score < PRODUCT_THRESHOLDS["relevance_mean_min"]


class TestProductGates:
    def test_all_gates_pass(self):
        gates = check_product_gates({
            "noise_rate": 0.05,
            "relevance_mean": 0.35,
            "traceable_rate": 1.0,
        })
        assert gates["pass"] is True
        assert all(gates["checks"].values())

    def test_fails_on_high_noise(self):
        gates = check_product_gates({
            "noise_rate": 0.30,
            "relevance_mean": 0.35,
            "traceable_rate": 1.0,
        })
        assert gates["pass"] is False
        assert gates["checks"]["low_noise"] is False

    def test_evaluate_experiment_product_fields(self):
        md = "Our method achieves 95% accuracy on the benchmark dataset."
        exp = {
            "key_results": ["Our method achieves 95% accuracy on the benchmark."],
            "method": "We train a transformer model.",
        }
        product = evaluate_experiment_product(
            exp,
            ["Our method achieves 95% accuracy on the benchmark dataset."],
            md,
        )
        assert product["traceable_rate"] == 1.0
        assert product["noise_rate"] == 0.0
        assert product["relevance_mean"] > 0.0
        assert product["product_pass"] is True
