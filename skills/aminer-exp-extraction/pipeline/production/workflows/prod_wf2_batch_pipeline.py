"""prod-wf2-batch-pipeline: cross-paper BERT ∥ LLM two-stage pipeline.

Single variable vs prod-wf1: at batch time, wf8's LLM is split into Stage-A
(BERT) + Stage-B (LLM) and pipelined across papers (paper n LLM overlaps
paper n+1 BERT). Field/merge/rule/ML and per-paper POST_LLM order are identical
to prod-wf1. waves/tail/between_waves are the SAME as prod-wf1 — only the batch
entry point (BatchPipelineScheduler) differs.

Driven by ``runners/batch_run_pipeline.py``; not meant for run_single (single
paper has no cross-paper overlap benefit — use prod-wf1 there).
"""

from __future__ import annotations

from pipeline.production.workflows.prod_wf1_async_v1 import _build_base_experiments
from pipeline.production.workflows.spec import WorkflowSpec, register_workflow

SPEC = WorkflowSpec(
    workflow_id="prod-wf2-batch-pipeline",
    workflow_version="0.1.0",
    description=(
        "跨篇 BERT ∥ LLM 流水线：wf8 LLM 拆 BERT+LLM 两槽跨篇交错；"
        "字段/merge/规则/ML 与 prod-wf1 相同，仅 batch 入口不同。"
    ),
    waves=[
        # Wave-1: LLM (run as BERT→LLM stages by the scheduler) + W1-rules
        # (conclusion_limitations + datasets.extract) overlap BERT/LLM.
        [
            "llm.wf8_dev20_v2_wash",
            "rules.conclusion_limitations",
            "rules.datasets.extract",
        ],
        # Wave-2 / Wave-3 / tail: identical to prod-wf1 (POST_LLM per paper).
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
        1: _build_base_experiments,  # same glue as prod-wf1
    },
    metadata={
        "llm_workflow": "wf8-merged-seven-fields-dev20-v2-wash",
        "llm_extractor_id": "llm.wf8_dev20_v2_wash",
        "batch_mode": "bert_qwen_pipeline",
        "bert_concurrency": 1,
        "llm_concurrency": 1,
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
