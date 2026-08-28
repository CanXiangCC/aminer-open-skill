"""Register prod-wf4 LLM model sweep variants from config/wf4_models.json.

Each candidate shallow-clones the parent WorkflowSpec (same waves/tail/between_waves)
and only extends metadata with llm_model_tag, model_sweep, model_slug, parent_workflow.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from pipeline.production.workflows.spec import WorkflowSpec, get_workflow, register_workflow

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "wf4_models.json"


def _load_config() -> dict:
    return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))


def _clone_variant(parent: WorkflowSpec, candidate: dict) -> WorkflowSpec:
    slug = candidate["slug"]
    workflow_id = candidate["workflow_id"]
    llm_model_tag = candidate["llm_model_tag"]
    metadata = dict(parent.metadata)
    metadata.update(
        {
            "llm_model_tag": llm_model,
            "parent_workflow": parent.workflow_id,
            "model_sweep": True,
            "model_slug": slug,
        }
    )
    # Optional per-model calling-convention overrides (wf4 model-sweep fix):
    # ollama_format (e.g. "json"), num_predict (int), prompt_adapter ("v3").
    # Absent => None => downstream uses production defaults (V0 prompt, no format).
    for opt_key in ("ollama_format", "num_predict", "prompt_adapter"):
        if candidate.get(opt_key) is not None:
            metadata[opt_key] = candidate[opt_key]
    return replace(
        parent,
        workflow_id=workflow_id,
        workflow_version=f"{parent.workflow_version}-model-{slug}",
        description=(
            f"wf4 model sweep ({slug}): {parent.description} "
            f"[llm_model_tag={llm_model_tag}]"
        ),
        metadata=metadata,
    )


def register_wf4_model_variants() -> list[WorkflowSpec]:
    """Register all candidates from wf4_models.json. Parent must already be registered."""
    cfg = _load_config()
    parent_id = cfg["parent_workflow_id"]
    parent = get_workflow(parent_id)
    specs: list[WorkflowSpec] = []
    for candidate in cfg.get("candidates") or []:
        spec = _clone_variant(parent, candidate)
        register_workflow(spec)
        specs.append(spec)
    return specs


# Import side-effect: register variants when this module loads (after parent import).
register_wf4_model_variants()
