"""prod-wf4-llm-datasets-experiment-concurrent10: wf4 multi-exp with 10 LLM workers.

Experimental, non-canonical. Same multi-exp schema as the main wf4 workflow,
tuned for ``--llm-concurrency 10``.
"""

from __future__ import annotations

from pipeline.production.config import (
    WF4_LLM_EXTRACTOR_ID,
    WF4_MAX_QWEN_SENTENCES,
    WF4_WORKFLOW_VERSION,
)
from pipeline.production.workflows.prod_wf4_llm_datasets_experiment import (
    _build_base_experiments_wf4,
)
from pipeline.production.workflows.spec import WorkflowSpec, register_workflow

SPEC = WorkflowSpec(
    workflow_id="prod-wf4-llm-datasets-experiment-concurrent10",
    workflow_version=f"{WF4_WORKFLOW_VERSION}-concurrent10",
    description=(
        "实验性 wf4 (10并发): LLM multi-exp (1..3) + datasets；移除 rules.datasets；"
        "union/wash/LLM 与主 wf4 一致；merger=wf4。"
        "设计用于 10 个并发 LLM worker (--llm-concurrency 10)。"
    ),
    waves=[
        [WF4_LLM_EXTRACTOR_ID, "rules.conclusion_limitations"],
        ["rules.evidence"],
    ],
    tail=[
        "rules.sample_size_policy_wf4",
    ],
    between_waves={
        1: _build_base_experiments_wf4,
    },
    metadata={
        "experimental": True,
        "canonical": False,
        "llm_workflow": "wf4-llm-multi-exp-datasets",
        "llm_extractor_id": WF4_LLM_EXTRACTOR_ID,
        "llm_mode": "wf4_multi_exp_datasets",
        "llm_fields": [
            "research_problem",
            "research_problem_description",
            "research_problem_aliases",
            "domain",
            "experiments",
        ],
        "datasets_source": "llm",
        "rule_fields": ["evidence", "conclusion", "limitations", "sample_size"],
        "ml_fields": [],
        "batch_mode": "filter_batch",
        "bert_batch_size": 32,
        "max_llm_sentences": WF4_MAX_QWEN_SENTENCES,
        "input_axis": "wf4_dataset_aware_union+wash",
        "output_schema": "v8+multi_exp_datasets",
        "merger": "wf4",
        "multi_experiment": True,
        "concurrency_notes": "Designed for 10 concurrent LLM workers (--llm-concurrency 10)",
    },
)

register_workflow(SPEC)
