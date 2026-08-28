"""Unit tests for v2_type_aware assignment strategy."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

project_root = Path(__file__).resolve().parent.parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from experiments.rule_extraction.datasets.assignment import ASSIGN_STRATEGIES
from experiments.rule_extraction.datasets.assignment.v2_type_aware import AssignV2TypeAware


def _ds(name: str, aliases: list[str] | None = None) -> dict:
    return {"name": name, "aliases": aliases or []}


def _exp(
    name: str,
    *,
    method: str = "",
    key_results: list[str] | None = None,
    evidence: list[str] | None = None,
    experiment_type: str = "comparison",
    experiment_subject: list[str] | None = None,
) -> dict:
    return {
        "experiment_name": name,
        "method": method,
        "key_results": key_results or [],
        "evidence": evidence or [],
        "experiment_type": experiment_type,
        "experiment_subject": experiment_subject or [],
        "datasets": [],
    }


def test_field_study_forced_empty_despite_blob():
    """field_study must stay [] even when blob mentions benchmark datasets."""
    strategy = AssignV2TypeAware()
    paper_datasets = [_ds("NOCS-REAL275"), _ds("SafetyDetect")]
    experiments = [
        _exp("Lab Benchmark", experiment_type="comparison"),
        _exp(
            "Real-World Deployment",
            experiment_type="field_study",
            method="deployed on NOCS-REAL275 and SafetyDetect in the wild",
            experiment_subject=["real-world driving"],
        ),
    ]
    md = "NOCS and SafetyDetect benchmarks.\n" * 3
    out = strategy.assign(paper_datasets, experiments, md, paper_id="p1")
    assert out[1]["datasets"] == []
    assert out[1]["assignment_trace"]["rule"] == "field_study_forced_empty"


def test_ablation_blob_cooccurrence_subset_only():
    """Ablation with blob mentioning only Wild6D gets that subset, not all paper datasets."""
    strategy = AssignV2TypeAware()
    paper_datasets = [_ds("NOCS-REAL275"), _ds("Wild6D")]
    experiments = [
        _exp("Main Comparison", experiment_type="comparison", method="trained on both"),
        _exp(
            "Ablation on Wild6D",
            experiment_type="ablation",
            method="we ablate components on Wild6D only",
        ),
    ]
    md = "## Main\nNOCS and Wild6D.\n## Ablation\nWild6D ablation.\n"
    out = strategy.assign(paper_datasets, experiments, md, paper_id="p2")
    ablation_names = {d["name"] for d in out[1]["datasets"]}
    assert ablation_names == {"Wild6D"}
    assert out[1]["assignment_trace"]["rule"] == "ablation_blob_cooccurrence"


def test_ablation_inherits_main_datasets_not_paper_union():
    """Ablation with no blob hit inherits main.datasets; does not read paper_datasets directly."""
    strategy = AssignV2TypeAware()
    paper_datasets = [_ds("DatasetAlpha"), _ds("DatasetBeta")]
    experiments = [
        _exp(
            "Main Dataset Evaluation",
            experiment_type="comparison",
            method="evaluated on DatasetAlpha and DatasetBeta",
            evidence=["results on DatasetAlpha and DatasetBeta"],
        ),
        _exp("Component Ablation", experiment_type="ablation", method="we remove modules"),
    ]
    md = (
        "## Main Dataset Evaluation\n"
        "We use DatasetAlpha and DatasetBeta for training.\n"
        "## Component Ablation\n"
        "We remove one module at a time.\n"
    )
    out = strategy.assign(paper_datasets, experiments, md, paper_id="p3")
    main_names = {d["name"] for d in out[0]["datasets"]}
    ablation_names = {d["name"] for d in out[1]["datasets"]}
    assert main_names == {"DatasetAlpha", "DatasetBeta"}
    assert ablation_names == main_names
    assert out[1]["assignment_trace"]["rule"] in (
        "ablation_inherit_main", "ablation_inherit_single_mainline"
    )
    assert out[1]["assignment_trace"].get("inherited_from") == 0


def test_ablation_pairs_nearest_main_with_multiple_comparisons():
    """With two comparison experiments, ablation inherits from section-matched main."""
    strategy = AssignV2TypeAware()
    paper_datasets = [_ds("JAAD"), _ds("HighD")]
    experiments = [
        _exp(
            "Pedestrian Crossing Behavior Prediction",
            experiment_type="comparison",
            method="trained on JAAD",
            evidence=["JAAD results"],
        ),
        _exp(
            "Vehicle Lane Change Maneuver Prediction",
            experiment_type="comparison",
            method="trained on HighD",
            evidence=["HighD results"],
        ),
        _exp(
            "Pedestrian Ablation Study",
            experiment_type="ablation",
            method="ablate pedestrian model components",
        ),
    ]
    md = (
        "## Pedestrian Crossing Behavior Prediction\n"
        "JAAD dataset for pedestrian intent.\n\n"
        "## Vehicle Lane Change Maneuver Prediction\n"
        "HighD dataset on highways.\n\n"
        "## Pedestrian Ablation Study\n"
        "We ablate pedestrian modules.\n"
    )
    out = strategy.assign(paper_datasets, experiments, md, paper_id="p4")
    ped_main = {d["name"] for d in out[0]["datasets"]}
    ablation_names = {d["name"] for d in out[2]["datasets"]}
    assert "JAAD" in ped_main
    assert ablation_names == ped_main
    assert "HighD" not in ablation_names


def test_6632f3d_style_no_cross_contamination():
    """Pedestrian and Lane Change mains should not cross-assign via section routing."""
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
        _exp(
            "Pedestrian Crossing Behavior Prediction",
            method="KG embedding trained on JAAD and PSI",
            evidence=["trained and tested using JAAD and PSI"],
        ),
        _exp(
            "Vehicle Lane Change Maneuver Prediction",
            method="TransE on HighD",
            evidence=["HighD dataset is used"],
        ),
    ]
    out = AssignV2TypeAware().assign(paper_datasets, experiments, md, paper_id="6632f3d20")
    ped_names = {d["name"] for d in out[0]["datasets"]}
    lane_names = {d["name"] for d in out[1]["datasets"]}
    assert "JAAD" in ped_names or "PSI" in ped_names
    assert "HighD" in lane_names
    assert "HighD" not in ped_names


def test_ablation_not_in_broadcast():
    """Unmatched datasets broadcast only to comparison/other, not ablation."""
    strategy = AssignV2TypeAware()
    paper_datasets = [_ds("ObscureDataset123")]
    experiments = [
        _exp("Method A Description", experiment_type="other"),
        _exp("Ablation Components", experiment_type="ablation"),
    ]
    md = "Generic intro with no dataset mentions.\n" * 3
    out = strategy.assign(paper_datasets, experiments, md, paper_id="p5")
    assert any(d["name"] == "ObscureDataset123" for d in out[0]["datasets"])
    assert out[1]["datasets"] == []


def test_v2_registered():
    assert "v2_type_aware" in ASSIGN_STRATEGIES
    assert ASSIGN_STRATEGIES["v2_type_aware"] is AssignV2TypeAware
