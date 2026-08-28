"""merge_run exports every experiment of every paper (not just experiments[0])."""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROD_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROD_ROOT))

import pipeline.production.runners.merge_run_predictions as mrp  # noqa: E402


def _build_run(tmp_path: Path) -> Path:
    pred_dir = tmp_path / "sess-a" / "job_batch_000" / "predictions"
    pred_dir.mkdir(parents=True)
    # p1: two experiments; p2: one experiment; p3: zero experiments (error paper).
    (pred_dir / "p1.json").write_text(
        json.dumps(
            {
                "paper_id": "p1",
                "paper_title": "Paper One",
                "workflow_id": "prod-wf4-llm-datasets-experiment",
                "run_id": "sess-a/job_batch_000",
                "experiments": [
                    {"paper_id": "p1", "experiment_name": "Main", "evidence": ["e-main"]},
                    {"paper_id": "p1", "experiment_name": "Ablation", "evidence": ["e-abl"]},
                ],
            }
        ),
        encoding="utf-8",
    )
    (pred_dir / "p2.json").write_text(
        json.dumps(
            {
                "paper_id": "p2",
                "paper_title": "Paper Two",
                "workflow_id": "prod-wf4-llm-datasets-experiment",
                "run_id": "sess-a/job_batch_000",
                "experiments": [{"experiment_name": "Only", "evidence": ["e-only"]}],
            }
        ),
        encoding="utf-8",
    )
    (pred_dir / "p3.json").write_text(
        json.dumps({"paper_id": "p3", "experiments": []}), encoding="utf-8"
    )
    return pred_dir


def test_merge_run_exports_all_experiments(tmp_path: Path, monkeypatch) -> None:
    _build_run(tmp_path)
    monkeypatch.setattr(mrp, "RUNS_DIR", tmp_path)

    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps({"papers": [{"paper_id": "p1"}, {"paper_id": "p2"}, {"paper_id": "p3"}]}),
        encoding="utf-8",
    )
    out_flat = tmp_path / "out" / "extractions.json"
    out_pure = tmp_path / "out" / "experiments.json"
    report = tmp_path / "out" / "report.md"

    stats = mrp.merge_run(
        run_id="sess-a/job_batch_000",
        manifest_path=manifest,
        out_flat=out_flat,
        out_papers=None,
        report_path=report,
        out_experiments=out_pure,
    )

    flat = json.loads(out_flat.read_text(encoding="utf-8"))
    pure = json.loads(out_pure.read_text(encoding="utf-8"))

    # 2 (p1) + 1 (p2) flat entries; p3 has no experiments.
    assert stats["flat_entries"] == 3
    assert stats["multi_exp_papers"] == 1
    assert len(flat) == 3
    assert len(pure) == 3

    p1_rows = [r for r in flat if r["paper_id"] == "p1"]
    assert [r["experiment_name"] for r in p1_rows] == ["Main", "Ablation"]
    # Each experiment keeps its OWN evidence (per-experiment mapping upstream).
    assert p1_rows[0]["evidence"] == ["e-main"]
    assert p1_rows[1]["evidence"] == ["e-abl"]
    # Run provenance is merged onto every entry.
    for row in p1_rows:
        assert row["paper_title"] == "Paper One"
        assert row["workflow_id"] == "prod-wf4-llm-datasets-experiment"
        assert row["run_id"] == "sess-a/job_batch_000"

    # Single-experiment paper unchanged: exactly one row.
    p2_rows = [r for r in flat if r["paper_id"] == "p2"]
    assert len(p2_rows) == 1
    assert p2_rows[0]["experiment_name"] == "Only"

    # Pure output carries all experiments as-is, without run provenance keys.
    assert all("run_id" not in r and "llm_model_tag" not in r for r in pure)

    # Zero-experiment paper is reported as a prediction error (report only).
    assert stats["missing"] == []
    report_text = report.read_text(encoding="utf-8")
    assert "p3" in report_text and "no experiments in prediction" in report_text


def test_merge_run_single_experiment_unchanged(tmp_path: Path, monkeypatch) -> None:
    """Pre-multi-exp runs (1 experiment/paper) keep the exact old output shape."""
    pred_dir = tmp_path / "sess-b" / "job_batch_000" / "predictions"
    pred_dir.mkdir(parents=True)
    (pred_dir / "q1.json").write_text(
        json.dumps(
            {
                "paper_id": "q1",
                "paper_title": "Solo",
                "workflow_id": "wf",
                "run_id": "sess-b/job_batch_000",
                "experiments": [{"experiment_name": "E", "evidence": []}],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(mrp, "RUNS_DIR", tmp_path)
    manifest = tmp_path / "m.json"
    manifest.write_text(json.dumps({"papers": ["q1"]}), encoding="utf-8")

    stats = mrp.merge_run(
        run_id="sess-b/job_batch_000",
        manifest_path=manifest,
        out_flat=tmp_path / "f.json",
        out_papers=None,
        report_path=tmp_path / "r.md",
    )
    flat = json.loads((tmp_path / "f.json").read_text(encoding="utf-8"))
    assert stats["flat_entries"] == 1
    assert stats["multi_exp_papers"] == 0
    assert len(flat) == 1
    assert flat[0]["experiment_name"] == "E"
    assert flat[0]["paper_title"] == "Solo"


if __name__ == "__main__":
    raise SystemExit("run via pytest")
