"""WorkflowSpec: declarative DAG = ordered waves of extractor_ids.

The orchestrator runs waves sequentially; within a wave, extractors run
concurrently via ``asyncio.gather(asyncio.to_thread(...))``. Inter-wave glue
(building base experiments from the LLM partial, etc.) is provided by the
workflow itself via ``between_waves`` hooks — the orchestrator is fully
generic and never references a specific workflow_id. Swapping an extractor
version (registry) or adding a new workflow (new WorkflowSpec) touches no
orchestrator code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from pipeline.production.context import PaperContext

# A hook run after wave `n` completes, before wave `n+1`. It mutates ctx
# (e.g. derive experiments_stripped from the LLM partial). Keyed by the
# 1-based wave number just finished.
BetweenWaveHook = Callable[[PaperContext], None]


@dataclass
class WorkflowSpec:
    workflow_id: str
    workflow_version: str
    description: str
    # waves[i] = list of extractor_ids that run concurrently in wave i.
    waves: list[list[str]]
    # Extractor_ids that run after all waves (serial tail).
    tail: list[str] = field(default_factory=list)
    # Inter-wave glue: {wave_number_just_finished: hook}. Optional.
    between_waves: dict[int, BetweenWaveHook] = field(default_factory=dict)
    # Free-form metadata for the manifest.
    metadata: dict[str, Any] = field(default_factory=dict)

    def all_extractor_ids(self) -> list[str]:
        ids: list[str] = []
        for w in self.waves:
            ids.extend(w)
        ids.extend(self.tail)
        return ids

    def run_between_wave(self, ctx: PaperContext, finished_wave: int) -> None:
        """Run the inter-wave glue hook after `finished_wave` (no-op if none)."""
        hook = self.between_waves.get(finished_wave)
        if hook is not None:
            hook(ctx)


_REGISTRY: dict[str, WorkflowSpec] = {}


def register_workflow(spec: WorkflowSpec) -> WorkflowSpec:
    _REGISTRY[spec.workflow_id] = spec
    return spec


def get_workflow(workflow_id: str) -> WorkflowSpec:
    if not _REGISTRY:
        _ensure_defaults()
    if workflow_id not in _REGISTRY:
        raise KeyError(f"unknown workflow: {workflow_id}")
    return _REGISTRY[workflow_id]


def list_workflows() -> list[str]:
    if not _REGISTRY:
        _ensure_defaults()
    return list(_REGISTRY.keys())


def _ensure_defaults() -> None:
    # Bulk production: wf4 only (vendored minimal set).
    from pipeline.production.workflows import prod_wf4_llm_datasets_experiment  # noqa: F401
    from pipeline.production.workflows import prod_wf4_llm_datasets_experiment_concurrent10  # noqa: F401
