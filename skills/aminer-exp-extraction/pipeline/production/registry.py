"""Extractor registry.

Extractors register by ``extractor_id``. Swapping a strategy version (e.g.
``rules.datasets.extract`` v4_3 -> v4_5) means replacing one entry here — the
orchestrator and WorkflowSpec never change (acceptance criterion 6).

Component replacements are recorded via :func:`record_replacement` so the run
manifest can carry ``{extractor_id, old_version, new_version, reason}``.
"""

from __future__ import annotations

from typing import Any

from pipeline.production.extractors.base import FieldExtractor

_REGISTRY: dict[str, FieldExtractor] = {}
_REPLACEMENTS: list[dict[str, str]] = []


def register(extractor: FieldExtractor) -> FieldExtractor:
    eid = extractor.extractor_id
    if eid in _REGISTRY:
        old = _REGISTRY[eid]
        if old.version != extractor.version:
            _REPLACEMENTS.append(
                {
                    "extractor_id": eid,
                    "old_version": old.version,
                    "new_version": extractor.version,
                    "reason": "register_overwrite",
                }
            )
    _REGISTRY[eid] = extractor
    return extractor


def get(extractor_id: str) -> FieldExtractor:
    if extractor_id not in _REGISTRY:
        raise KeyError(f"extractor not registered: {extractor_id}")
    return _REGISTRY[extractor_id]


def all_extractors() -> dict[str, FieldExtractor]:
    return dict(_REGISTRY)


def replacements() -> list[dict[str, str]]:
    return list(_REPLACEMENTS)


def record_replacement(extractor_id: str, old_version: str, new_version: str, reason: str) -> None:
    _REPLACEMENTS.append(
        {
            "extractor_id": extractor_id,
            "old_version": old_version,
            "new_version": new_version,
            "reason": reason,
        }
    )


def _register_defaults() -> None:
    """Register the default extractor set (imported once)."""
    from pipeline.production.extractors.llm.wf8_dev20_v2_wash import (
        Wf8Dev20V2WashExtractor,
    )
    from pipeline.production.extractors.llm.wf4_datasets_llm import (
        Wf4DatasetsLlmExtractor,
    )
    from pipeline.production.extractors.meta.paper_id import PaperIdExtractor
    from pipeline.production.extractors.meta.placeholder import PlaceholderExtractor
    from pipeline.production.extractors.ml.domain_classifier import (
        DomainClassifierExtractor,
    )
    from pipeline.production.extractors.ml.domain_classifier_wf4 import (
        DomainClassifierWf4Extractor,
    )
    from pipeline.production.extractors.ml.experiment_type_classifier import (
        ExperimentTypeClassifierExtractor,
    )
    from pipeline.production.extractors.ml.experiment_type_classifier_wf4 import (
        ExperimentTypeClassifierWf4Extractor,
    )
    from pipeline.production.extractors.rules.conclusion_limitations import (
        ConclusionLimitationsExtractor,
    )
    from pipeline.production.extractors.rules.datasets_assign import (
        DatasetsAssignExtractor,
    )
    from pipeline.production.extractors.rules.datasets_extract import (
        DatasetsExtractExtractor,
    )
    from pipeline.production.extractors.rules.evidence import EvidenceExtractor
    from pipeline.production.extractors.rules.sample_size_policy import (
        SampleSizePolicyExtractor,
    )
    from pipeline.production.extractors.rules.sample_size_policy_wf4 import (
        SampleSizePolicyWf4Extractor,
    )

    for cls in (
        PaperIdExtractor(),
        PlaceholderExtractor(),
        Wf8Dev20V2WashExtractor(),
        DatasetsExtractExtractor(),
        DatasetsAssignExtractor(),
        EvidenceExtractor(),
        ConclusionLimitationsExtractor(),
        SampleSizePolicyExtractor(),
        DomainClassifierExtractor(),
        ExperimentTypeClassifierExtractor(),
        # --- wf4 experimental extractors (additive, new extractor_ids) ---
        Wf4DatasetsLlmExtractor(),
        SampleSizePolicyWf4Extractor(),
        DomainClassifierWf4Extractor(),
        ExperimentTypeClassifierWf4Extractor(),
    ):
        register(cls)


def ensure_registered() -> None:
    if not _REGISTRY:
        _register_defaults()


# Eager self-registration on import of the package.
ensure_registered()


def get_spec_info(extractor_id: str) -> dict[str, Any]:
    ext = get(extractor_id)
    return {
        "extractor_id": ext.extractor_id,
        "version": ext.version,
        "produces": list(ext.produces),
        "depends_on": list(ext.depends_on),
    }
