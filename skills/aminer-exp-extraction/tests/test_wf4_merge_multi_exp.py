"""MergerWf4 multi-exp + no-fabricate on empty/error LLM partial."""

from __future__ import annotations

import sys
from pathlib import Path

PROD_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROD_ROOT))

from pipeline.production.config import WF4_LLM_EXTRACTOR_ID  # noqa: E402
from pipeline.production.context import PaperContext  # noqa: E402
from pipeline.production.merge_wf4 import MergerWf4  # noqa: E402
from pipeline.production.schema import FieldResult  # noqa: E402


def _ctx_with_partials(
    *,
    llm_status: str = "ok",
    llm_value: dict | None = None,
    llm_error: str | None = None,
    evidence_value: list | None = None,
) -> PaperContext:
    ctx = PaperContext(
        paper_id="paper123",
        md_path=Path("dummy.md"),
        run_id="test-run",
        workflow_id="prod-wf4-llm-datasets-experiment",
        dry_run=False,
    )
    ctx.set(
        FieldResult(
            extractor_id=WF4_LLM_EXTRACTOR_ID,
            version="0.4.0-wf4-multi-exp",
            status=llm_status,
            value=llm_value or {},
            error=llm_error,
            fields=[
                "research_problem",
                "research_problem_description",
                "research_problem_aliases",
                "experiments",
            ],
        )
    )
    ctx.set(
        FieldResult(
            extractor_id="meta.paper_id",
            version="0.1.0",
            status="ok",
            value="paper123",
            fields=["paper_id"],
        )
    )
    ctx.set(
        FieldResult(
            extractor_id="meta.placeholder",
            version="0.1.0",
            status="ok",
            value={"_id": "", "experiment_history": [], "score": None},
            fields=["_id", "experiment_history", "score"],
        )
    )
    ctx.set(
        FieldResult(
            extractor_id="rules.conclusion_limitations",
            version="v5",
            status="ok",
            value={"conclusion": "Shared conclusion.", "limitations": "Shared lim."},
            fields=["conclusion", "limitations"],
        )
    )
    ctx.set(
        FieldResult(
            extractor_id="rules.sample_size_policy_wf4",
            version="0.1.0-wf4",
            status="ok",
            value=None,
            fields=["sample_size"],
        )
    )
    ctx.set(
        FieldResult(
            extractor_id="rules.evidence",
            version="v4",
            status="ok",
            # One result per experiment, in experiment order (extractor contract).
            value=evidence_value
            if evidence_value is not None
            else [
                {"evidence": ["ev1", "ev2"]},
                {"evidence": ["ev3"]},
            ],
            fields=["evidence"],
        )
    )
    return ctx


def test_merger_two_experiments_share_non_llm() -> None:
    llm_value = {
        "research_problem": "Visual Detection",
        "research_problem_description": "Detect visual relations.",
        "domain": "computer_science",
        "experiments": [
            {
                "experiment_name": "Main",
                "experiment_type": "benchmark",
                "research_goal": "g1",
                "experiment_subject": ["det"],
                "methods": [
                    {
                        "name": "MethodA",
                        "description": "desc A",
                        "aliases": [],
                    }
                ],
                "key_results": ["r1"],
                "metrics": ["mAP"],
                "datasets": [{"name": "DS1"}],
            },
            {
                "experiment_name": "Ablation",
                "experiment_type": "ablation",
                "research_goal": "g2",
                "experiment_subject": ["ablation"],
                "methods": [
                    {
                        "name": "MethodB",
                        "description": "desc B",
                        "aliases": [],
                    }
                ],
                "key_results": ["r2"],
                "metrics": ["Recall"],
                "datasets": [{"name": "DS2"}],
            },
        ],
    }
    ctx = _ctx_with_partials(llm_value=llm_value)
    experiments, provenance, conflicts = MergerWf4().merge(ctx)
    assert len(experiments) == 2
    assert len(provenance) == 2
    assert experiments[0]["experiment_name"] == "Main"
    assert experiments[1]["experiment_name"] == "Ablation"
    assert experiments[0]["methods"] == [
        {
            "name": "MethodA",
            "description": "desc A",
            "aliases": [],
        }
    ]
    assert experiments[1]["methods"] == [
        {
            "name": "MethodB",
            "description": "desc B",
            "aliases": [],
        }
    ]
    for exp in experiments:
        assert "method" not in exp
        assert "method_description" not in exp
    # Shared paper-level fields (domain from LLM; conclusion from rules)
    for exp in experiments:
        assert exp["domain"] == "computer_science"
        assert exp["conclusion"] == "Shared conclusion."
        assert exp["limitations"] == "Shared lim."
        assert exp.get("research_problem") in (None, "")  # paper-level only
    # Per-experiment evidence: results[i] maps to experiments[i] by index.
    assert experiments[0]["evidence"] == ["ev1", "ev2"]
    assert experiments[1]["evidence"] == ["ev3"]
    assert experiments[0]["experiment_type"] == "benchmark"
    assert experiments[1]["experiment_type"] == "ablation"
    assert provenance[0]["extraction_sources"]["domain"]["extractor_id"].startswith("llm.")
    assert provenance[0]["extraction_sources"]["experiment_type"]["extractor_id"].startswith(
        "llm."
    )
    assert "research_problem" not in experiments[0] or not experiments[0].get(
        "research_problem"
    )


def test_merger_empty_llm_does_not_fabricate() -> None:
    ctx = _ctx_with_partials(
        llm_status="error",
        llm_value={"research_problem": "", "experiments": []},
        llm_error="parse_error: bad json",
    )
    experiments, provenance, conflicts = MergerWf4().merge(ctx)
    assert experiments == []
    assert provenance == []
    assert any(c.get("field_group") == "llm" for c in conflicts)


def test_merger_ok_but_empty_experiments_no_fabricate() -> None:
    """EXT-02: ok + empty experiments → [] and no llm conflict."""
    ctx = _ctx_with_partials(
        llm_status="ok",
        llm_value={"research_problem": "X", "experiments": []},
    )
    experiments, _prov, conflicts = MergerWf4().merge(ctx)
    assert experiments == []
    assert not any(c.get("field_group") == "llm" for c in conflicts)


def test_merger_evidence_length_mismatch_fills_empty() -> None:
    """Fewer evidence results than experiments -> missing ones get [] + conflict."""
    llm_value = {
        "domain": "computer_science",
        "experiments": [
            {"experiment_name": "Main", "methods": [{"name": "MethodA"}]},
            {"experiment_name": "Ablation", "methods": [{"name": "MethodB"}]},
        ],
    }
    ctx = _ctx_with_partials(
        llm_value=llm_value,
        evidence_value=[{"evidence": ["ev1"]}],
    )
    experiments, _prov, conflicts = MergerWf4().merge(ctx)
    assert len(experiments) == 2
    assert experiments[0]["evidence"] == ["ev1"]
    assert experiments[1]["evidence"] == []
    assert any(c.get("field_group") == "rules.evidence" for c in conflicts)


if __name__ == "__main__":
    test_merger_two_experiments_share_non_llm()
    test_merger_empty_llm_does_not_fabricate()
    test_merger_ok_but_empty_experiments_no_fabricate()
    test_merger_evidence_length_mismatch_fills_empty()
    print("OK: all wf4 merge multi-exp tests passed")
