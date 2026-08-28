"""Adapter for the remote rule/ML pack.

Isolates ``sys.path`` manipulation so the rest of production never touches the
pack's import mechanics. All pack strategy classes are imported lazily through
getters here; an import failure raises :class:`PackImportError` which the
caller (an Extractor) catches and records as ``status="error"`` — no silent
fallback.

PACK_ROOT = rule_ml_extraction_from_promote/rule_extraction_pack (frozen).
"""

from __future__ import annotations

import importlib
import sys
from types import ModuleType
from typing import Any

from pipeline.production.config import PACK_ML_SRC, PACK_ROOT

_PACK_ON_PATH = False


class PackImportError(RuntimeError):
    """Raised when a pack strategy module cannot be imported."""


def ensure_pack_on_path() -> None:
    """Insert PACK_ROOT and ml_classification/src on sys.path (idempotent).

    PACK_ROOT MUST precede PACK_ML_SRC: the pack's rule modules do
    ``from src.evaluation.semantic import ...`` and ``src`` must resolve to
    ``PACK_ROOT/src``. ``ml_classification/src`` is also a package named
    ``src`` (it has __init__.py) and would shadow it if it came first. ML
    modules are imported top-level (``tfidf_feature`` etc.), so they remain
    reachable as long as PACK_ML_SRC is on path at all. Insert in reverse so
    PACK_ROOT lands at index 0.
    """
    global _PACK_ON_PATH
    if _PACK_ON_PATH:
        return
    for p in (str(PACK_ML_SRC), str(PACK_ROOT)):
        if p not in sys.path:
            sys.path.insert(0, p)
    _shim_src_structure()
    _PACK_ON_PATH = True


def _shim_src_structure() -> None:
    """Production-side import shim — NOT a pack modification.

    The pack's ``src/preprocess/strip_references.py`` imports
    ``from src.structure.reference_detector import (...)``, but the
    ``src/structure/`` package is not shipped in the pack (nor in the zip).
    The main project root has a working ``reference_detector`` that exports
    the exact same names (MIN_DOC_CHARS, detect_references, line_at_offset —
    confirmed). We alias ``src.structure.reference_detector`` to it via
    ``sys.modules`` so the pack's import resolves. This is allowed: only the
    production adapter touches import mechanics; no pack strategy code changes.
    """
    if "src.structure.reference_detector" in sys.modules:
        return
    try:
        import types

        import reference_detector as rd  # main-project top-level module
    except Exception:  # noqa: BLE001 — if unavailable, let the pack import fail loudly
        return
    structure_pkg = types.ModuleType("src.structure")
    structure_pkg.__path__ = []  # mark as package
    structure_pkg.reference_detector = rd
    sys.modules["src.structure"] = structure_pkg
    sys.modules["src.structure.reference_detector"] = rd


def _import(dotted: str) -> ModuleType:
    ensure_pack_on_path()
    try:
        return importlib.import_module(dotted)
    except Exception as exc:  # noqa: BLE001
        raise PackImportError(f"cannot import pack module {dotted!r}: {exc}") from exc


# --- rule strategies ---------------------------------------------------------

def get_dataset_v43() -> Any:
    """experiments.rule_extraction.datasets.strategies.v4_3_union.DatasetRuleV43"""
    mod = _import("experiments.rule_extraction.datasets.strategies.v4_3_union")
    return mod.DatasetRuleV43


def get_assign_v2_type_aware() -> Any:
    """experiments.rule_extraction.datasets.assignment.v2_type_aware.AssignV2TypeAware"""
    mod = _import("experiments.rule_extraction.datasets.assignment.v2_type_aware")
    return mod.AssignV2TypeAware


def get_evidence_v4() -> Any:
    """experiments.rule_extraction.evidence.strategies.v4_clean_mswr.EvidenceRuleV4"""
    mod = _import("experiments.rule_extraction.evidence.strategies.v4_clean_mswr")
    return mod.EvidenceRuleV4


def get_conclusion_v5() -> Any:
    """experiments.rule_extraction.conclusion.strategies.v5_layered.ConclusionRuleV5"""
    mod = _import("experiments.rule_extraction.conclusion.strategies.v5_layered")
    return mod.ConclusionRuleV5


def get_limitations_vk() -> Any:
    """experiments.rule_extraction.limitations.strategies.vK_enhanced_filter.LimitationsRuleK"""
    mod = _import("experiments.rule_extraction.limitations.strategies.vK_enhanced_filter")
    return mod.LimitationsRuleK


def get_sample_size_rule() -> Any:
    """src.rule_extraction.rules.sample_size.SampleSizeRule"""
    mod = _import("src.rule_extraction.rules.sample_size")
    return mod.SampleSizeRule


# --- ML strategies -----------------------------------------------------------

def get_data_preparator() -> Any:
    """ml_classification.scripts.data_preparation_dataset2.DataPreparatorDataset2"""
    mod = _import("ml_classification.scripts.data_preparation_dataset2")
    return mod.DataPreparatorDataset2


def get_lr_classifier() -> Any:
    """ml_classification.src.logistic_regression.LogisticRegressionClassifier"""
    mod = _import("logistic_regression")
    return mod.LogisticRegressionClassifier
