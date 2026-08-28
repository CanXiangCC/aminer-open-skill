"""Lightweight tests for v4.5 extract strategy and hybrid gazetteer."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

project_root = Path(__file__).resolve().parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from experiments.rule_extraction.datasets.strategies.v4_3_1_union import _match_gazetteer_tight
from experiments.rule_extraction.datasets.strategies.v4_3_union import DatasetRuleV43
from experiments.rule_extraction.datasets.strategies.v4_5_union import (
    DATA_DIR,
    DatasetRuleV45,
    GAZETTEER_HYBRID_DEFAULT,
)
from experiments.rule_extraction.datasets.scripts.build_gazetteer_hybrid import build_hybrid


@pytest.fixture
def mini_gazetteer() -> list[dict]:
    return [
        {
            "canonical_name": "ImageNet benchmark",
            "aliases": ["ImageNet"],
            "normalized_keys": ["imagenet"],
            "paper_count": 100,
        },
        {
            "canonical_name": "SUN scene dataset",
            "aliases": ["SUN"],
            "normalized_keys": ["sun"],
            "paper_count": 50,
        },
    ]


def test_tight_match_rejects_blacklist_and_short(mini_gazetteer):
    assert _match_gazetteer_tight(["sun"], mini_gazetteer) == []
    assert _match_gazetteer_tight(["imagenet"], mini_gazetteer) == ["ImageNet benchmark"]


def test_hybrid_gazetteer_file_exists():
    assert GAZETTEER_HYBRID_DEFAULT.exists()
    with open(GAZETTEER_HYBRID_DEFAULT, encoding="utf-8") as f:
        entries = json.load(f)
    assert len(entries) > 1277
    stats_path = DATA_DIR / "gazetteer_hybrid_stats.json"
    assert stats_path.exists()
    with open(stats_path, encoding="utf-8") as f:
        stats = json.load(f)
    for key in ("manual_count", "merged_total", "only_manual", "only_20k", "overlap"):
        assert key in stats


def test_hybrid_manual_priority(tmp_path):
    manual = tmp_path / "manual.json"
    auto = tmp_path / "auto.json"
    manual.write_text(
        json.dumps([{
            "canonical_name": "ManualName",
            "aliases": ["MN"],
            "normalized_keys": ["manualname"],
            "paper_count": 5,
        }]),
        encoding="utf-8",
    )
    auto.write_text(
        json.dumps([
            {
                "canonical_name": "ManualName",
                "aliases": [],
                "normalized_keys": ["manualname"],
                "paper_count": 99,
            },
            {
                "canonical_name": "AutoOnly",
                "aliases": [],
                "normalized_keys": ["autoonly"],
                "paper_count": 15,
            },
        ]),
        encoding="utf-8",
    )
    merged, stats = build_hybrid(manual, auto, min_paper_count=10)
    by_name = {e["canonical_name"]: e for e in merged}
    assert by_name["ManualName"]["paper_count"] == 5
    assert "AutoOnly" in by_name
    assert stats["overlap"] == 1
    assert stats["only_20k"] == 1


def test_v45_extract_trace_version():
    md = """
# Datasets
We evaluate on ImageNet and CIFAR-10 datasets for classification.
"""
    out = DatasetRuleV45.extract(md, "test_paper")
    assert out["trace"]["version"] == "v4.5"
    tightening = out["trace"]["tightening"]
    assert tightening["branch_b_tight_match"] is True
    assert tightening["gazetteer_source"] == "hybrid"
    assert "datasets" in out


def test_v43_unaffected():
    md = "# Datasets\nWe use ImageNet.\n"
    out = DatasetRuleV43.extract(md, "test")
    assert out["trace"]["version"] == "v4.3"
