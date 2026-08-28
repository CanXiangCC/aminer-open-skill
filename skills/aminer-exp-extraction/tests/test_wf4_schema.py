"""wf4_experiment_v1.schema.json + stdlib validator against real outputs."""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROD_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROD_ROOT))

from pipeline.production.schema import (  # noqa: E402
    empty_experiment,
    validate_wf4_experiment,
)

# Newest tracked run (0.6.3 LLM-enums) — real production output shapes.
_REAL_RUN = (
    PROD_ROOT
    / "pipeline_output"
    / "production"
    / "runs"
    / "prod-lilaoshi-smoke10-llm-enums-20260814"
)


def _wf4_exp(**overrides) -> dict:
    exp = empty_experiment("paper1")
    exp.pop("research_problem", None)  # paper-level; MergerWf4 pops it
    exp.update(overrides)
    return exp


def test_empty_experiment_shape_is_valid() -> None:
    assert validate_wf4_experiment(_wf4_exp()) == []


def test_research_problem_on_experiment_is_rejected() -> None:
    exp = _wf4_exp()
    exp["research_problem"] = "Task"  # paper-level field must NOT ride experiments
    errs = validate_wf4_experiment(exp)
    assert any("unexpected key" in e and "research_problem" in e for e in errs)


def test_invalid_samples_produce_errors() -> None:
    # legacy string method / string methods list
    errs = validate_wf4_experiment(_wf4_exp(methods="ResNet"))
    assert errs
    errs = validate_wf4_experiment(_wf4_exp(methods=[{"name": "M", "justification": "x"}]))
    assert any("unexpected key" in e and "justification" in e for e in errs)
    # score must be number|null, not string
    errs = validate_wf4_experiment(_wf4_exp(score="0.9"))
    assert any("score" in e and "expected type" in e for e in errs)
    # domain outside closed set
    errs = validate_wf4_experiment(_wf4_exp(domain="cs"))
    assert any("domain" in e and "not in enum" in e for e in errs)
    # dataset_type outside closed set
    errs = validate_wf4_experiment(
        _wf4_exp(datasets=[{"name": "D", "dataset_type": "timeseries"}])
    )
    assert any("dataset_type" in e and "not in enum" in e for e in errs)
    # missing required key
    bad = _wf4_exp()
    bad.pop("evidence")
    errs = validate_wf4_experiment(bad)
    assert any("missing required key" in e and "evidence" in e for e in errs)


def test_real_predictions_validate(tmp_path: Path) -> None:
    """Every experiment of the tracked 0.6.3 smoke run passes the schema."""
    pred_dir = _REAL_RUN / "job_batch_000" / "predictions"
    if not pred_dir.is_dir():
        import pytest

        pytest.skip(f"tracked run not present: {pred_dir}")
    files = sorted(pred_dir.glob("*.json"))
    assert files, "expected tracked predictions"
    n_exp = 0
    for pf in files:
        pred = json.loads(pf.read_text(encoding="utf-8"))
        for exp in pred.get("experiments") or []:
            errs = validate_wf4_experiment(exp)
            assert errs == [], f"{pf.name}: {errs[:3]}"
            n_exp += 1
    assert n_exp >= 10  # 10-paper smoke, >=1 experiment each


if __name__ == "__main__":
    raise SystemExit("run via pytest")
