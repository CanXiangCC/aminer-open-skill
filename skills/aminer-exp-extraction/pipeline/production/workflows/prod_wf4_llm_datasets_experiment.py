"""prod-wf4-llm-datasets-experiment: wf3 + LLM multi-exp datasets extraction.

Experimental, non-canonical. Inherits wf3's /filter/batch + LLM scheduling but:

  - LLM outputs paper-level research_problem* + experiments[1..3] (each with
    method/datasets/metrics/etc.) via ``llm.wf4_dev20_v2_wash_datasets``.
  - ``rules.datasets.extract`` and ``rules.datasets.assign`` are REMOVED from the
    wave DAG — datasets come from the LLM only.
  - Input axis is dataset-aware: wf4 union (adds "data" keyword) + wf4 wash
    (keeps dataset/data heading lines) + 40-sentence LLM cap.
  - ``merger="wf4"`` selects ``MergerWf4`` in ``finalize_paper``.

Driven by ``runners/batch_run_wf4.py``. The scheduler is
``BatchBertPipelineSchedulerWf4`` (PREP -> BERT-BATCH -> LLM), which uses
``prepare_llm_inputs_wf4`` / ``run_bert_batch_for_papers_wf4`` /
``process_llm_and_post_wf4``.
"""

from __future__ import annotations

from typing import Any

from pipeline.production.config import (
    WF4_LLM_EXTRACTOR_ID,
    WF4_MAX_QWEN_SENTENCES,
    WF4_WORKFLOW_ID,
    WF4_WORKFLOW_VERSION,
)
from pipeline.production.context import PaperContext
from pipeline.production.schema import LLM_FIELDS
from pipeline.production.workflows.spec import WorkflowSpec, register_workflow


def _build_base_experiments_wf4(ctx: PaperContext) -> None:
    """W1->W2 glue: derive base experiments from the wf4 multi-exp LLM partial.

    - ``base_experiments`` carries per-exp LLM fields incl. datasets — MergerWf4.
    - ``experiments_stripped`` carries LLM_FIELDS (no datasets) for evidence;
      paper-level ``research_problem`` is injected into each stripped item.
    """
    llm = ctx.get(WF4_LLM_EXTRACTOR_ID)
    if not llm or llm.status != "ok" or not isinstance(llm.value, dict):
        ctx.base_experiments = []
        ctx.experiments_stripped = []
        return

    llm_val = llm.value
    experiments = llm_val.get("experiments") or []
    if not isinstance(experiments, list) or not experiments:
        ctx.base_experiments = []
        ctx.experiments_stripped = []
        return

    paper_rp = llm_val.get("research_problem", "") or ""
    base: list[dict[str, Any]] = []
    stripped: list[dict[str, Any]] = []
    for exp in experiments:
        if not isinstance(exp, dict):
            continue
        item = {
            "experiment_name": exp.get("experiment_name", ""),
            "research_goal": exp.get("research_goal", ""),
            "experiment_subject": exp.get("experiment_subject", []),
            "methods": exp.get("methods") or [],
            "key_results": exp.get("key_results", []),
            "metrics": exp.get("metrics", []),
            "datasets": exp.get("datasets", []),
        }
        base.append(item)
        s: dict[str, Any] = {f: exp.get(f) for f in LLM_FIELDS}
        s["research_problem"] = paper_rp  # paper-level for evidence features
        stripped.append(s)

    ctx.base_experiments = base
    ctx.experiments_stripped = stripped


SPEC = WorkflowSpec(
    workflow_id=WF4_WORKFLOW_ID,
    workflow_version=WF4_WORKFLOW_VERSION,
    description=(
        "实验性 wf4：LLM multi-exp (1..3) + datasets；移除 rules.datasets.extract/assign；"
        "union 扩展 data 关键词；sentence_clean 保留 dataset/data 标题行；LLM 40 句；merger=wf4。"
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
    },
)

register_workflow(SPEC)
