"""Shared helpers for assignment strategies (v2 imports; v1 keeps its own copy)."""

from __future__ import annotations

import re
from typing import Any

from experiments.rule_extraction.datasets.shared.dataset_evaluator import (
    _fuzzy_match,
    normalize_dataset_name,
)

_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9]+")

_EXPERIMENT_NAME_STOPWORDS = {
    "experiment", "experiments", "results", "result", "evaluation",
    "evaluating", "study", "analysis", "performance", "main", "novel",
    "proposed", "approach", "method", "model", "models", "system",
    "systems", "task", "tasks", "table", "section", "overview",
    "comparison", "benchmark", "ablation", "disentanglement",
    "prediction", "training", "testing", "test", "tests", "experiment1",
    "experiment2", "exp1", "exp2", "setup", "settings", "setting",
    "dataset", "datasets", "evaluation", "the", "this", "our",
    "using", "via", "with", "for", "and", "based",
}

_FIELD_STUDY_KEYWORDS = {
    "field", "field_study", "real_world", "real-world", "real world",
    "in the wild", "in-the-wild", "wild", "deployment", "deployed",
    "realworld", "realworlddeployment",
}

_ABLATION_KEYWORDS = {
    "ablation", "disentanglement", "disentangle", "component",
    "diagnostic", "probe",
}

_COMPARISON_KEYWORDS = {
    "comparison", "benchmark", "evaluate", "evaluation", "main",
    "baseline", "state-of-the-art", "sota",
}

FALLBACK_NAME_KEYWORDS = {
    "evaluation", "benchmark", "comparison", "main", "overall",
    "state", "sota",
}

WINDOW_CHARS = 400


def experiment_name_tokens(experiment_name: str) -> list[str]:
    if not experiment_name:
        return []
    toks = _TOKEN_RE.findall(experiment_name.lower())
    return [t for t in toks if len(t) >= 4 and t not in _EXPERIMENT_NAME_STOPWORDS]


def experiment_text_blob(exp: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("method", "research_problem", "research_goal"):
        v = exp.get(key)
        if isinstance(v, str) and v:
            parts.append(v)
    for key in ("key_results", "evidence", "experiment_history"):
        v = exp.get(key)
        if isinstance(v, list):
            parts.extend(str(x) for x in v if x)
        elif isinstance(v, str) and v:
            parts.append(v)
    return " ".join(parts).lower()


def classify_experiment(exp: dict[str, Any]) -> str:
    etype = str(exp.get("experiment_type") or "").lower().strip()
    subject = exp.get("experiment_subject")
    if isinstance(subject, list):
        subject_blob = " ".join(str(s).lower() for s in subject)
    else:
        subject_blob = str(subject or "").lower()

    blob = f"{etype} {subject_blob}"
    norm_blob = blob.replace("-", "").replace("_", "").replace(" ", "")

    for kw in _FIELD_STUDY_KEYWORDS:
        nk = kw.replace("-", "").replace("_", "").replace(" ", "")
        if nk in norm_blob:
            return "field_study"

    for kw in _ABLATION_KEYWORDS:
        nk = kw.replace("-", "").replace("_", "").replace(" ", "")
        if nk in norm_blob:
            return "ablation"

    for kw in _COMPARISON_KEYWORDS:
        nk = kw.replace("-", "").replace("_", "").replace(" ", "")
        if nk in norm_blob:
            return "comparison"

    return "other"


def dataset_name_variants(ds: dict[str, Any]) -> list[str]:
    names: list[str] = []
    name = (ds.get("name") or "").strip()
    if name:
        names.append(name)
    for alias in ds.get("aliases") or []:
        if isinstance(alias, str) and alias.strip():
            names.append(alias.strip())
    return names


def find_mentions(md_text_lower: str, name: str) -> list[int]:
    if not name:
        return []
    name_norm = re.sub(r"\s+", " ", name.strip()).lower()
    if not name_norm:
        return []
    if " " in name_norm:
        pattern = re.escape(name_norm).replace(r"\ ", r"\s+")
        return [m.start() for m in re.finditer(pattern, md_text_lower)]
    return [m.start() for m in re.finditer(re.escape(name_norm), md_text_lower)]


def fuzzy_in_blob(blob: str, name: str, alias_groups: dict[str, set[str]]) -> bool:
    if not name or not blob:
        return False
    nm = normalize_dataset_name(name)
    if nm and nm in blob.replace("-", "").replace("_", "").replace(" ", ""):
        return True
    return _fuzzy_match(name, blob, alias_groups)


def pick_fallback_target(exp_meta: list[dict[str, Any]]) -> int | None:
    comparison = [m["idx"] for m in exp_meta if m["klass"] == "comparison"]
    if comparison:
        return comparison[0]
    for m in exp_meta:
        if m["klass"] != "other":
            continue
        if any(tok in FALLBACK_NAME_KEYWORDS for tok in m["tokens"]):
            return m["idx"]
    return None


def is_pass_a_eligible(klass: str) -> bool:
    """comparison and other participate in Pass A; ablation/field_study do not."""
    return klass in ("comparison", "other")
