"""Lightweight tests for v4.6 tiered gazetteer match."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

project_root = Path(__file__).resolve().parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from experiments.rule_extraction.datasets.strategies.v4_3_union import DatasetRuleV43
from experiments.rule_extraction.datasets.strategies.v4_5_union import DatasetRuleV45
from experiments.rule_extraction.datasets.strategies.v4_6_union import (
    DatasetRuleV46,
    _match_gazetteer_tiered,
)


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


@pytest.fixture
def replay_gazetteer() -> list[dict]:
    return [
        {
            "canonical_name": "Replay-Attack",
            "aliases": ["ReplayAttack"],
            "normalized_keys": ["replayattack"],
            "paper_count": 20,
        },
        {
            "canonical_name": "RFW",
            "aliases": ["Racial Faces in the Wild"],
            "normalized_keys": ["rfw"],
            "paper_count": 15,
        },
    ]


def test_tiered_rejects_blacklist_and_short(mini_gazetteer):
    after, details, counts = _match_gazetteer_tiered(["sun", "ab"], mini_gazetteer)
    assert after == []
    assert details == []
    assert counts == {"tight": 0, "bidirectional_fallback": 0}


def test_tiered_tight_hits_imagenet(mini_gazetteer):
    after, details, counts = _match_gazetteer_tiered(["imagenet"], mini_gazetteer)
    assert after == ["ImageNet benchmark"]
    assert len(details) == 1
    assert details[0]["pass"] == "tight"
    assert counts["tight"] == 1
    assert counts["bidirectional_fallback"] == 0


def test_tiered_fallback_rescues_replay_attack(replay_gazetteer):
    # "Replay" is too short for tight (overlap ratio fails) but fallback can match
    after, details, counts = _match_gazetteer_tiered(["Replay-Attack"], replay_gazetteer)
    assert "Replay-Attack" in after
    assert len(details) == 1
    assert details[0]["pass"] in ("tight", "bidirectional_fallback")


def test_tiered_fallback_path_used():
    gazetteer = [{
        "canonical_name": "VGGFace2",
        "aliases": [],
        "normalized_keys": ["vggface2"],
        "paper_count": 10,
    }]
    # tight is candidate ⊂ canonical only; "on VGGFace2" → canonical ⊂ candidate → fallback
    after, details, counts = _match_gazetteer_tiered(["on VGGFace2"], gazetteer)
    assert after == ["VGGFace2"]
    assert details[0]["pass"] == "bidirectional_fallback"
    assert counts["bidirectional_fallback"] == 1
    assert counts["tight"] == 0


def test_pass2_does_not_repeat_pass1(replay_gazetteer):
    after, details, counts = _match_gazetteer_tiered(
        ["Replay-Attack", "RFW"],
        replay_gazetteer,
    )
    candidates_seen = [d["candidate"] for d in details]
    assert len(candidates_seen) == len(set(candidates_seen))
    assert counts["tight"] + counts["bidirectional_fallback"] == len(details)


def test_v46_extract_trace_version():
    md = """
# Datasets
We evaluate on ImageNet and CIFAR-10 datasets for classification.
"""
    out = DatasetRuleV46.extract(md, "test_paper")
    assert out["trace"]["version"] == "v4.6"
    tightening = out["trace"]["tightening"]
    assert tightening["branch_b_tiered_match"] is True
    assert tightening["gazetteer_source"] == "hybrid"
    assert "match_details" in out["trace"]["branch_b"]
    assert "datasets" in out


def test_v43_v45_unaffected():
    md = "# Datasets\nWe use ImageNet.\n"
    assert DatasetRuleV43.extract(md, "test")["trace"]["version"] == "v4.3"
    assert DatasetRuleV45.extract(md, "test")["trace"]["version"] == "v4.5"
