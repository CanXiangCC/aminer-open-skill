"""prod-wf1-async-v1: first full-field production line.

LLM (frozen wf8 dev20-v2-wash, 7 fields) + pack rules (datasets/evidence/
conclusion/limitations/sample_size) + pack ML (domain/experiment_type),
arranged as an async Wave DAG so rule/ML work overlaps the LLM wait window.

Wave layout (see ARCHITECTURE.md for the mermaid diagram):
  Wave-1 (parallel): llm.wf8  |  rules.conclusion_limitations  |  rules.datasets.extract
  Wave-2 (parallel, after LLM): rules.datasets.assign  |  rules.evidence
  Wave-3 (parallel, after CL+evidence+LLM): ml.domain  |  ml.experiment_type
  tail (serial): rules.sample_size_policy
  meta (serial, T0/T5): meta.paper_id, meta.placeholder
"""

from __future__ import annotations

from typing import Any

from pipeline.production.context import PaperContext
from pipeline.production.schema import LLM_FIELDS
from pipeline.production.workflows.spec import WorkflowSpec, register_workflow

# Wave-1 -> Wave-2 glue: derive the single base experiment from the LLM 7-field
# partial. ``base_experiments`` carries the LLM experiment; ``experiments_stripped``
# is the same dict without a `datasets` key (datasets.assign sets it; evidence
# reads experiment_name/key_results/method). v0.1.0 = 1 experiment.
def _build_base_experiments(ctx: PaperContext) -> None:
    llm = ctx.get("llm.wf8_dev20_v2_wash")
    if not llm or llm.status != "ok" or not isinstance(llm.value, dict):
        ctx.base_experiments = []
        ctx.experiments_stripped = []
        return
    exp: dict[str, Any] = {f: llm.value.get(f) for f in LLM_FIELDS}
    ctx.base_experiments = [exp]
    ctx.experiments_stripped = [dict(exp)]


SPEC = WorkflowSpec(
    workflow_id="prod-wf1-async-v1",
    workflow_version="0.1.0",
    description=(
        "首条全字段生产线：wf8 LLM (7 字段) + pack 规则/ML + 异步 Wave 编排。"
        " 1 paper -> 1 experiment (v0.1.0)。"
    ),
    waves=[
        # Wave-1: 3 parallel tasks (LLM is the long pole ~4s; rules overlap).
        [
            "llm.wf8_dev20_v2_wash",
            "rules.conclusion_limitations",
            "rules.datasets.extract",
        ],
        # Wave-2: 2 parallel tasks (need LLM partial -> experiments_stripped).
        [
            "rules.datasets.assign",
            "rules.evidence",
        ],
        # Wave-3: 2 parallel ML tasks (need conclusion + evidence + LLM).
        [
            "ml.domain",
            "ml.experiment_type",
        ],
    ],
    tail=[
        # Serial: needs datasets extract + assign.
        "rules.sample_size_policy",
    ],
    between_waves={
        1: _build_base_experiments,  # after Wave-1 (LLM ready), before Wave-2
    },
    metadata={
        "llm_workflow": "wf8-merged-seven-fields-dev20-v2-wash",
        "llm_extractor_id": "llm.wf8_dev20_v2_wash",
        "llm_fields": [
            "experiment_name",
            "research_problem",
            "research_goal",
            "experiment_subject",
            "method",
            "key_results",
            "metrics",
        ],
        "rule_fields": [
            "datasets",
            "evidence",
            "conclusion",
            "limitations",
            "sample_size",
        ],
        "ml_fields": ["domain", "experiment_type"],
        "multi_experiment": False,
    },
)

register_workflow(SPEC)
