"""prod-wf3-batch-bert-pipeline: cross-paper /filter/batch + LLM pipeline.

Single variable vs prod-wf2: 10x per-paper ``POST /filter`` -> 1x (or few
chunked) ``POST /filter/batch`` — one server-side GPU mini-batch across papers.
W1-rules, Stage-P, LLM pipeline, POST_LLM, field/merge semantics identical to
wf2. waves/tail/between_waves are the SAME as wf2 — only the batch BERT entry
differs (BatchBertPipelineScheduler: PREP -> BERT-BATCH -> LLM).

Driven by ``runners/batch_run_bert_pipeline.py``.
"""

from __future__ import annotations

from pipeline.production.workflows.prod_wf1_async_v1 import _build_base_experiments
from pipeline.production.workflows.spec import WorkflowSpec, register_workflow

SPEC = WorkflowSpec(
    workflow_id="prod-wf3-batch-bert-pipeline",
    workflow_version="0.1.0",
    description=(
        "跨篇 /filter/batch + LLM 流水线：10× 单篇 BERT → 1× 跨篇 GPU mini-batch；"
        "字段/merge/规则/ML 与 wf2 相同，仅 BERT 阶段不同。"
    ),
    waves=[
        [
            "llm.wf8_dev20_v2_wash",
            "rules.conclusion_limitations",
            "rules.datasets.extract",
        ],
        [
            "rules.datasets.assign",
            "rules.evidence",
        ],
        [
            "ml.domain",
            "ml.experiment_type",
        ],
    ],
    tail=[
        "rules.sample_size_policy",
    ],
    between_waves={
        1: _build_base_experiments,
    },
    metadata={
        "llm_workflow": "wf8-merged-seven-fields-dev20-v2-wash",
        "llm_extractor_id": "llm.wf8_dev20_v2_wash",
        "batch_mode": "filter_batch",
        "bert_batch_size": 32,
        "llm_fields": [
            "experiment_name",
            "research_problem",
            "research_goal",
            "experiment_subject",
            "method",
            "key_results",
            "metrics",
        ],
        "rule_fields": ["datasets", "evidence", "conclusion", "limitations", "sample_size"],
        "ml_fields": ["domain", "experiment_type"],
        "multi_experiment": False,
    },
)

register_workflow(SPEC)
