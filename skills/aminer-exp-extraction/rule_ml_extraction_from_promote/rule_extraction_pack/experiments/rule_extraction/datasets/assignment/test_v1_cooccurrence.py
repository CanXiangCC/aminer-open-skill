"""Lightweight unit tests for v1_cooccurrence assignment strategy.

Covers the rule chain documented in DESIGN.md:
  - single-experiment short-circuit
  - cooccurrence match (md window + experiment blob)
  - experiment_type constraints (field_study default [])
  - primary fallback + broadcast last-resort
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

project_root = Path(__file__).resolve().parent.parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from experiments.rule_extraction.datasets.assignment import (
    ASSIGN_STRATEGIES,
    run_assignment,
)
from experiments.rule_extraction.datasets.assignment.v1_cooccurrence import (
    AssignV1Cooccurrence,
    _classify_experiment,
    _experiment_name_tokens,
)


def _ds(name: str, aliases: list[str] | None = None) -> dict:
    return {"name": name, "aliases": aliases or []}


def _exp(name: str, *, method: str = "", key_results: list[str] | None = None,
         evidence: list[str] | None = None, experiment_type: str = "comparison",
         experiment_subject: list[str] | None = None) -> dict:
    return {
        "experiment_name": name,
        "method": method,
        "key_results": key_results or [],
        "evidence": evidence or [],
        "experiment_type": experiment_type,
        "experiment_subject": experiment_subject or [],
        "datasets": [],  # stripped in real use; tests mirror that
    }


# ---------- helpers ----------

def test_experiment_name_tokens_filters_stopwords():
    toks = _experiment_name_tokens("Main Experiment Results for Evaluation")
    assert "main" not in toks
    assert "experiment" not in toks
    assert "results" not in toks
    assert "evaluation" not in toks
    # Only "evaluation" was len>=4 and stopword; everything else stopworded -> empty
    assert toks == []


def test_experiment_name_tokens_keeps_significant():
    toks = _experiment_name_tokens("Pedestrian Crossing Behavior Prediction")
    assert "pedestrian" in toks
    assert "crossing" in toks
    assert "behavior" in toks
    assert "prediction" not in toks  # stopword


def test_classify_experiment_field_study():
    exp = _exp("Real-World Deployment", experiment_type="field_study")
    assert _classify_experiment(exp) == "field_study"
    exp2 = _exp("In-the-Wild Study", experiment_subject=["real-world video"])
    assert _classify_experiment(exp2) == "field_study"


def test_classify_experiment_ablation():
    exp = _exp("Component Ablation", experiment_type="ablation")
    assert _classify_experiment(exp) == "ablation"


def test_classify_experiment_comparison():
    exp = _exp("Comparison with SOTA", experiment_type="comparison")
    assert _classify_experiment(exp) == "comparison"


# ---------- strategy ----------

def test_single_experiment_short_circuits():
    strategy = AssignV1Cooccurrence()
    paper_datasets = [_ds("JAAD"), _ds("PSI"), _ds("HighD")]
    experiments = [_exp("Only Experiment")]
    out = strategy.assign(paper_datasets, experiments, "whatever md", paper_id="p1")
    assert len(out) == 1
    assert [d["name"] for d in out[0]["datasets"]] == ["JAAD", "PSI", "HighD"]
    assert out[0]["assignment_trace"]["fallback_used"] == "single_experiment"


def test_cooccurrence_mutually_exclusive_like_6632f3d20():
    """Mirror dev_20 paper 6632f3d20: Pedestrian uses JAAD/PSI, Lane Change uses HighD."""
    md = (
        "## Pedestrian Crossing Behavior Prediction\n"
        "We train on JAAD and PSI datasets for pedestrian intent.\n"
        "JAAD contains 348 clips. PSI has 196 scenes.\n\n"
        "## Vehicle Lane Change Maneuver Prediction\n"
        "We use the HighD dataset recorded on German highways.\n"
        "HighD provides 60 recordings.\n"
    )
    paper_datasets = [_ds("JAAD"), _ds("PSI"), _ds("HighD")]
    experiments = [
        _exp("Pedestrian Crossing Behavior Prediction",
             method="KG embedding trained on JAAD and PSI",
             evidence=["trained and tested using JAAD and PSI"]),
        _exp("Vehicle Lane Change Maneuver Prediction",
             method="TransE on HighD",
             evidence=["HighD dataset is used"]),
    ]
    out = AssignV1Cooccurrence().assign(paper_datasets, experiments, md, paper_id="6632f3d20")
    ped_names = {d["name"] for d in out[0]["datasets"]}
    lane_names = {d["name"] for d in out[1]["datasets"]}
    assert "JAAD" in ped_names
    assert "PSI" in ped_names
    assert "HighD" in lane_names
    # HighD must not leak into pedestrian
    assert "HighD" not in ped_names
    assert "JAAD" not in lane_names


def test_field_study_defaults_empty():
    """Real-world experiment gets datasets=[] unless cooccurrence explicitly hits."""
    md = "We benchmark on ImageNet and COCO in lab conditions.\n" * 5
    paper_datasets = [_ds("ImageNet"), _ds("COCO")]
    experiments = [
        _exp("Lab Benchmark", experiment_type="comparison"),
        _exp("Real-World Deployment", experiment_type="field_study",
             experiment_subject=["real-world driving video"]),
    ]
    out = AssignV1Cooccurrence().assign(paper_datasets, experiments, md, paper_id="p2")
    # ImageNet/COCO cooccur with "Lab Benchmark" (the md mentions them) but
    # NOT with the real-world experiment, so field_study should stay empty.
    field_study_ds = out[1]["datasets"]
    assert field_study_ds == []
    assert out[1]["assignment_trace"]["experiment_class"] == "field_study"


def test_broadcast_fallback_when_no_comparison():
    """All datasets unmatched + no field_study + no comparison -> broadcast."""
    md = "Generic intro with no dataset mentions at all.\n" * 3
    paper_datasets = [_ds("ObscureDataset123")]
    experiments = [
        _exp("Method A Description", experiment_type="other"),
        _exp("Method B Description", experiment_type="other"),
    ]
    out = AssignV1Cooccurrence().assign(paper_datasets, experiments, md, paper_id="p3")
    # Each experiment should have received the dataset via broadcast.
    for exp in out:
        assert exp["assignment_trace"]["broadcast_triggered"] is True
        assert any(d["name"] == "ObscureDataset123" for d in exp["datasets"])


def test_no_broadcast_when_field_study_present():
    """Unmatched datasets should be dropped (not broadcast) when a field_study
    experiment is present, per DESIGN.md rule 4."""
    md = "No dataset mentioned anywhere here.\n" * 3
    paper_datasets = [_ds("ObscureDatasetXYZ")]
    experiments = [
        _exp("Lab Test", experiment_type="other"),
        _exp("Field Trial", experiment_type="field_study"),
    ]
    out = AssignV1Cooccurrence().assign(paper_datasets, experiments, md, paper_id="p4")
    assert all(not exp["assignment_trace"]["broadcast_triggered"] for exp in out)
    # The unmatched dataset should be recorded as dropped on at least one trace.
    all_traces = [exp["assignment_trace"] for exp in out]
    assert any("dropped_unmatched" in t for t in all_traces)


def test_broadcast_strategy_copies_to_all():
    from experiments.rule_extraction.datasets.assignment.v1_broadcast import AssignV1Broadcast
    paper_datasets = [_ds("A"), _ds("B")]
    experiments = [_exp("E1"), _exp("E2"), _exp("E3")]
    out = AssignV1Broadcast().assign(paper_datasets, experiments, "md", paper_id="p5")
    assert len(out) == 3
    for exp in out:
        assert [d["name"] for d in exp["datasets"]] == ["A", "B"]
        assert exp["assignment_trace"]["broadcast_triggered"] is True


def test_run_assignment_orchestrator_annotates_timing():
    strategy = AssignV1Cooccurrence()
    paper_datasets = [_ds("OnlyDS")]
    experiments = [_exp("Only Exp")]
    out = run_assignment(strategy, paper_datasets, experiments, "md", paper_id="p6")
    assert out[0]["assignment_trace"]["assign_ms"] >= 0
    assert out[0]["assignment_trace"]["strategy"] == "v1_cooccurrence"


def test_assign_strategies_registry():
    assert "v1_cooccurrence" in ASSIGN_STRATEGIES
    assert "v1_broadcast" in ASSIGN_STRATEGIES
    assert ASSIGN_STRATEGIES["v1_cooccurrence"] is AssignV1Cooccurrence
