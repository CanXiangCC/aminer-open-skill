"""wf4 LLM extractor: registry/stub for multi-exp datasets-LLM path.

In the real (non-dry) batch path, ``process_llm_and_post_wf4`` calls
``run_llm_stage_wf4`` directly (NOT this extractor's ``_extract``) — the
``FieldResult`` is built inside the stage with ``extractor_id=WF4_LLM_EXTRACTOR_ID``.

Value shape (Stage-B):
  {
    "research_problem": str,              # paper-level
    "research_problem_description": str,   # paper-level
    "experiments": [                      # 1..3 after normalize
      {
        "experiment_name", "key_results", "methods",  # methods: [{name, description}, ...]
        "research_goal", "experiment_subject", "metrics", "datasets"
      },
      ...
    ]
  }

In the dry-run path, ``FieldExtractor.extract`` returns ``self._stub`` before
reaching ``_extract``. ``_extract`` raises ``NotImplementedError`` as a guardrail.
"""

from __future__ import annotations

from pipeline.production.config import WF4_LLM_EXTRACTOR_ID, WF4_WORKFLOW_VERSION
from pipeline.production.context import PaperContext
from pipeline.production.extractors.base import FieldExtractor
from pipeline.production.schema import FieldResult


class Wf4DatasetsLlmExtractor(FieldExtractor):
    extractor_id = WF4_LLM_EXTRACTOR_ID  # "llm.wf4_dev20_v2_wash_datasets"
    version = WF4_WORKFLOW_VERSION  # "0.6.0-wf4-lilaoshi-wiki-schema"
    produces = (
        "research_problem",
        "research_problem_description",
        "research_problem_aliases",
        "experiments",
    )
    depends_on: tuple[str, ...] = ()

    def _extract(self, ctx: PaperContext) -> FieldResult:
        raise NotImplementedError(
            "wf4 LLM runs via run_llm_stage_wf4 in BatchBertPipelineSchedulerWf4; "
            "not invokable standalone (the real batch path calls run_llm_stage_wf4 "
            "directly; the dry-run path returns a stub before reaching _extract)."
        )
