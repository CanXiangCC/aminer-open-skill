"""Shared ML inference helper for domain / experiment_type classifiers.

Uses the pack's ``DataPreparatorDataset2`` JSON-feature preparation (the
``prepare_*_text`` recipe) and loads the pack's pkl models DIRECTLY via joblib.

It does NOT use the pack's ``LogisticRegressionClassifier`` wrapper: that
class passes ``multi_class='multinomial'`` to sklearn's ``LogisticRegression``,
which is rejected by sklearn >= 1.5 (the installed env is 1.9). Loading the
serialized sklearn objects directly avoids the broken ``__init__`` entirely.
This is a production-side adapter choice; no pack strategy code is modified
(see ARCHITECTURE.md / plan risk note).

It also does NOT use ``predict.py`` (pseudocode).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import joblib

from pipeline.production.adapters.rule_pack import (
    PackImportError,
    get_data_preparator,
)
from pipeline.production.config import ML_SCRATCH_DIR, PACK_ML_MODELS

_clf_cache: dict[str, dict[str, Any]] = {}
_preparator: Any = None


def _get_preparator() -> Any:
    global _preparator
    if _preparator is None:
        ML_SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
        Cls = get_data_preparator()
        # DataPreparatorDataset2 only needs dirs for training-time methods;
        # inference uses prepare_*_text which ignore them.
        _preparator = Cls(outputs_dir=ML_SCRATCH_DIR, processed_dir=ML_SCRATCH_DIR)
    return _preparator


def _load_field(field: str) -> dict[str, Any]:
    """Load (and cache) model.pkl + vectorizer.pkl + label_encoder.pkl for field."""
    if field in _clf_cache:
        return _clf_cache[field]
    model_dir = Path(PACK_ML_MODELS) / field
    model = joblib.load(model_dir / "model.pkl")  # fitted sklearn LogisticRegression
    vec_data = joblib.load(model_dir / "vectorizer.pkl")
    if isinstance(vec_data, dict):
        vectorizer = vec_data["vectorizer"]
        selector = vec_data.get("selector")
    else:
        vectorizer = vec_data
        selector = None
    label_encoder = joblib.load(model_dir / "label_encoder.pkl")
    bundle = {
        "model": model,
        "vectorizer": vectorizer,
        "selector": selector,
        "label_encoder": label_encoder,
    }
    _clf_cache[field] = bundle
    return bundle


def predict_field(field: str, item: dict[str, Any], *, prepare: str) -> tuple[str, Any]:
    """Predict one label for ``field`` from a JSON-feature ``item`` dict.

    Args:
        field: "domain" or "experiment_type".
        item: dict of merged fields the preparator reads from.
        prepare: "domain" or "experiment_type" — selects prepare_*_text.

    Returns:
        (label, confidence) — confidence is max probability or None.
    """
    dp = _get_preparator()
    if prepare == "domain":
        text = dp.prepare_domain_text(item)
    else:
        text = dp.prepare_experiment_text(item)

    bundle = _load_field(field)
    X = bundle["vectorizer"].transform([text])
    if bundle["selector"] is not None:
        X = bundle["selector"].transform(X)
    model = bundle["model"]
    pred_idx = model.predict(X)
    label = str(bundle["label_encoder"].inverse_transform(pred_idx)[0])

    confidence: float | None = None
    try:
        proba = model.predict_proba(X)
        confidence = float(proba.max(axis=1)[0])
    except Exception:  # noqa: BLE001 — confidence is best-effort
        confidence = None
    return label, confidence


def reset_cache() -> None:
    """Clear cached classifiers (used between independent runs if needed)."""
    _clf_cache.clear()
    global _preparator
    _preparator = None


__all__ = ["PackImportError", "predict_field", "reset_cache"]
