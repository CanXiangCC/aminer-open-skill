"""Smoke tests for metrics rule extraction experiment."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
METRICS_ROOT = PROJECT_ROOT / "experiments" / "rule_extraction" / "metrics"


@pytest.fixture
def project_root() -> Path:
    return PROJECT_ROOT


def test_build_gold_dev10(project_root: Path) -> None:
    from experiments.rule_extraction.metrics.scripts.build_gold_sets import build_gold_sets

    batch = "dev_10"
    src_dir = project_root / "data" / "gold" / batch / "full_text_glm5_2"
    if not src_dir.exists():
        pytest.skip("dev_10 gold source missing")

    stats = build_gold_sets(batch, project_root)
    assert stats["total_papers"] == 10
    union_dir = METRICS_ROOT / "data" / "gold" / batch / "paper_union"
    files = list(union_dir.glob("*.json"))
    assert len(files) == 10
    for f in files:
        doc = json.loads(f.read_text(encoding="utf-8"))
        assert "metrics" in doc
        assert isinstance(doc["metrics"], list)


def test_build_gazetteer_20k_fixture(tmp_path: Path) -> None:
    from experiments.rule_extraction.metrics.scripts.build_gazetteer_20k import build_gazetteer_20k

    per_paper = tmp_path / "per_paper"
    per_paper.mkdir()
    p1 = [
        {"paper_id": "paper_a", "metrics": ["BLEU", "ROUGE", "accuracy"]},
        {"paper_id": "paper_a", "metrics": ["BLEU", "METEOR"]},
    ]
    p2 = [{"paper_id": "paper_b", "metrics": ["BLEU", "accuracy"]}]
    (per_paper / "paper_a.json").write_text(json.dumps(p1), encoding="utf-8")
    (per_paper / "paper_b.json").write_text(json.dumps(p2), encoding="utf-8")

    out = tmp_path / "gazetteer_20k.json"
    gazetteer, stats = build_gazetteer_20k(per_paper, out, min_paper_count=2)
    assert stats["files_valid"] == 2
    assert stats["entries_after_min_paper_count"] >= 2
    assert out.exists()
    names = {e["canonical_name"] for e in gazetteer}
    assert "BLEU" in names
    assert "accuracy" in names


def test_build_gazetteer_hybrid(tmp_path: Path) -> None:
    from experiments.rule_extraction.metrics.scripts.build_gazetteer_hybrid import build_hybrid

    manual = [
        {"canonical_name": "F1-score", "aliases": ["F1"], "normalized_keys": ["f1score"], "paper_count": 0},
    ]
    auto = [
        {"canonical_name": "BLEU", "aliases": [], "normalized_keys": ["bleu"], "paper_count": 15},
        {"canonical_name": "noise_metric", "aliases": [], "normalized_keys": ["noise"], "paper_count": 3},
    ]
    manual_path = tmp_path / "manual.json"
    auto_path = tmp_path / "auto.json"
    manual_path.write_text(json.dumps(manual), encoding="utf-8")
    auto_path.write_text(json.dumps(auto), encoding="utf-8")

    merged, stats = build_hybrid(manual_path, auto_path, min_paper_count=10)
    assert stats["merged_total"] == 2
    assert stats["only_manual"] == 1
    assert stats["only_20k"] == 1
    canon = {e["canonical_name"] for e in merged}
    assert "F1-score" in canon and "BLEU" in canon
    assert "noise_metric" not in canon


def test_v1_extract_fixture_md() -> None:
    from experiments.rule_extraction.metrics.strategies.v1_gazetteer_scan import MetricRuleV1

    MetricRuleV1._gazetteer = None
    MetricRuleV1._patterns = None

    md = """# Introduction
Some intro text.

## Evaluation Metrics
We report BLEU and ROUGE on the test set.
Accuracy is also measured.

## Results
Our model achieved 95.2% accuracy on the benchmark.
"""
    out = MetricRuleV1.extract(md, paper_id="fixture")
    assert "metrics" in out
    assert "trace" in out
    assert isinstance(out["metrics"], list)
    assert out["trace"]["hits_count"] >= 1
    assert "extract_ms" in out["trace"]


def test_metric_evaluator_modes() -> None:
    from experiments.rule_extraction.metrics.shared.metric_evaluator import evaluate_paper_metrics

    empty = evaluate_paper_metrics([], [])
    assert empty["gold_count"] == 0
    assert empty["rule_count"] == 0

    exact = evaluate_paper_metrics(["accuracy", "BLEU"], ["accuracy", "BLEU"])
    assert exact["strict"]["f1"] == 1.0
    assert exact["fuzzy"]["f1"] == 1.0

    alias = evaluate_paper_metrics(["acc"], ["accuracy"])
    assert alias["strict"]["matched_count"] == 1
    assert alias["fuzzy"]["matched_count"] >= 1

    semantic = evaluate_paper_metrics(["BLEU score"], ["BLEU"], semantic_scorer=None)
    assert "semantic" in semantic


def test_test_runner_smoke(project_root: Path) -> None:
    gold_union = METRICS_ROOT / "data" / "gold" / "dev_10" / "paper_union"
    if not gold_union.exists() or not list(gold_union.glob("*.json")):
        pytest.skip("Gold2 not built yet")

    hybrid = METRICS_ROOT / "data" / "gazetteer_hybrid.json"
    g20k = METRICS_ROOT / "data" / "gazetteer_20k.json"
    if not hybrid.exists() and not g20k.exists():
        pytest.skip("Gazetteer not built yet")

    run_id = "pytest_metrics_smoke"
    cmd = [
        sys.executable,
        "-m",
        "experiments.rule_extraction.metrics.test_runner",
        "--strategy",
        "v1",
        "--batch",
        "dev_10",
        "--gold-set",
        "paper_union",
        "--run-id",
        run_id,
        "--eval-modes",
        "strict,fuzzy",
    ]
    result = subprocess.run(cmd, cwd=project_root, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr or result.stdout

    manifest_path = METRICS_ROOT / "runs" / run_id / "run_manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    timing = manifest.get("timing", {})
    for key in (
        "total_wall_ms",
        "gazetteer_load_ms",
        "extract_total_ms",
        "extract_mean_ms",
        "extract_p50_ms",
        "extract_p95_ms",
        "eval_ms",
        "papers",
    ):
        assert key in timing, f"missing timing.{key}"
