"""EXT-01: select_llm_sentences selects by score, returns document order."""

from __future__ import annotations

import sys
from pathlib import Path

PROD_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROD_ROOT))

from pipeline.benchmark.workflows.wf1_merged import (  # noqa: E402
    metric_richness_score,
    select_llm_sentences,
)


def test_under_cap_preserves_input_order() -> None:
    sents = ["first", "second", "third"]
    out, stats = select_llm_sentences(sents, confidences=[0.9, 0.1, 0.5], max_sentences=10)
    assert out == sents
    assert stats["truncated"] is False
    assert stats["selected"] == 3


def test_over_cap_set_is_top_n_order_is_document() -> None:
    # Metric-rich sentences beat plain ones; among equals, higher conf wins.
    sents = [
        "plain A",  # 0
        "Accuracy is 95.2% on the test set.",  # 1 metric-rich
        "plain B",  # 2
        "F1 score reached 0.88 overall.",  # 3 metric-rich
        "plain C",  # 4
        "plain D high conf",  # 5 — fill by conf
        "plain E",  # 6
    ]
    confs = [0.1, 0.5, 0.2, 0.4, 0.3, 0.99, 0.05]
    max_n = 3
    out, stats = select_llm_sentences(sents, confidences=confs, max_sentences=max_n)
    assert stats["truncated"] is True
    assert stats["selected"] == max_n

    ranked = sorted(
        range(len(sents)),
        key=lambda i: (-metric_richness_score(sents[i]), -confs[i], i),
    )
    expected_idxs = sorted(ranked[:max_n])
    assert out == [sents[i] for i in expected_idxs]
    # Relative document order among selected
    assert out == sorted(out, key=lambda s: sents.index(s))


if __name__ == "__main__":
    test_under_cap_preserves_input_order()
    test_over_cap_set_is_top_n_order_is_document()
    print("OK: select_llm_sentences tests passed")
