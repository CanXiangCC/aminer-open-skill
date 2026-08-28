"""Run-level manifest: workflow spec snapshot + extractor versions + pack note.

One ``manifest.json`` per run under ``runs/{run_id}/``. Records component
replacements from the registry so A/B swaps are auditable.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pipeline.production.config import PACK_ROOT, RUNS_DIR
from pipeline.production import registry
from pipeline.production.workflows.spec import WorkflowSpec


def write_run_manifest(
    spec: WorkflowSpec,
    run_id: str,
    *,
    paper_ids: list[str],
    extra: dict[str, Any] | None = None,
) -> Path:
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = run_dir / "manifest.json"

    extractor_info = {
        eid: registry.get_spec_info(eid) for eid in spec.all_extractor_ids()
    }
    payload: dict[str, Any] = {
        "run_id": run_id,
        "workflow_id": spec.workflow_id,
        "workflow_version": spec.workflow_version,
        "description": spec.description,
        "waves": spec.waves,
        "tail": spec.tail,
        "metadata": spec.metadata,
        "extractors": extractor_info,
        "component_replacements": registry.replacements(),
        "pack_root": str(PACK_ROOT),
        "pack_note": "rule_ml_extraction_from_promote/rule_extraction_pack (frozen; import-only)",
        "paper_ids": paper_ids,
    }
    if extra:
        payload.update(extra)
    manifest_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest_path
