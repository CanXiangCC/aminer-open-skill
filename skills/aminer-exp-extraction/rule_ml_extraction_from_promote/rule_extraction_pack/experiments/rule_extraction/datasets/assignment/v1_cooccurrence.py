"""
v1_cooccurrence assignment strategy.

Rule chain (see DESIGN.md):
  1. cooccurrence match
     a) md mention ±400 char window contains experiment_name significant tokens
     b) dataset name fuzzy-matches inside experiment method/key_results/evidence
  2. experiment_type constraints
     comparison/benchmark -> may receive fallbacks
     ablation/disentanglement -> only cooccurring datasets
     field_study/real-world -> default [] unless cooccurring explicitly
  3. primary-experiment fallback for unmatched datasets
  4. broadcast last-resort (only if no field_study experiment present)
"""

from __future__ import annotations

import re
from typing import Any

from .base import AssignStrategy

# Reuse the paper-level evaluator's normalization + gazetteer alias groups so
# assignment matching stays consistent with how extraction names are matched.
from experiments.rule_extraction.datasets.shared.dataset_evaluator import (
    _load_gazetteer_aliases,
    _fuzzy_match,
    normalize_dataset_name,
    normalize_fuzzy,
)


# Significant-token extraction for experiment_name matching.
_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9]+")

# Generic / non-discriminative words that should not count as experiment
# identifiers even if they appear in experiment_name.
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

# experiment_type / experiment_subject keywords for field_study / real-world
# detection (default datasets=[]).
_FIELD_STUDY_KEYWORDS = {
    "field", "field_study", "real_world", "real-world", "real world",
    "in the wild", "in-the-wild", "wild", "deployment", "deployed",
    "realworld", "realworlddeployment",
}

# experiment_type keywords for ablation/disentanglement (only cooccurring).
_ABLATION_KEYWORDS = {
    "ablation", "disentanglement", "disentangle", "component",
    "diagnostic", "probe",
}

# experiment_type keywords for comparison/benchmark (may receive fallbacks).
_COMPARISON_KEYWORDS = {
    "comparison", "benchmark", "evaluate", "evaluation", "main",
    "baseline", "state-of-the-art", "sota",
}

# experiment_name keywords for fallback target selection.
_FALLBACK_NAME_KEYWORDS = {
    "evaluation", "benchmark", "comparison", "main", "overall",
    "state", "sota",
}

WINDOW_CHARS = 400


def _experiment_name_tokens(experiment_name: str) -> list[str]:
    """Significant tokens from experiment_name (lowercased, len>=4, no stopwords)."""
    if not experiment_name:
        return []
    toks = _TOKEN_RE.findall(experiment_name.lower())
    return [t for t in toks if len(t) >= 4 and t not in _EXPERIMENT_NAME_STOPWORDS]


def _experiment_text_blob(exp: dict[str, Any]) -> str:
    """Concatenate the textual fields used for in-experiment dataset matching."""
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


def _classify_experiment(exp: dict[str, Any]) -> str:
    """Return one of: 'comparison', 'ablation', 'field_study', 'other'.

    classification precedence: field_study > ablation > comparison > other.
    field_study is checked from both experiment_type and experiment_subject
    so we catch real-world use cases even when experiment_type is generic.
    """
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


def _dataset_name_variants(ds: dict[str, Any]) -> list[str]:
    """All name strings (canonical + aliases) usable for matching."""
    names: list[str] = []
    name = (ds.get("name") or "").strip()
    if name:
        names.append(name)
    for alias in ds.get("aliases") or []:
        if isinstance(alias, str) and alias.strip():
            names.append(alias.strip())
    return names


def _find_mentions(md_text_lower: str, name: str) -> list[int]:
    """All start offsets where `name` appears in md_text (case-insensitive literal).

    For multi-word names we collapse internal whitespace in both name and md
    so spacing differences don't hide matches.
    """
    if not name:
        return []
    name_norm = re.sub(r"\s+", " ", name.strip()).lower()
    if not name_norm:
        return []
    if " " in name_norm:
        # collapse whitespace in md as well; we search the collapsed string and
        # map back by reconstructing via a parallel index. Simpler: just search
        # the literal with flexible whitespace via regex.
        pattern = re.escape(name_norm).replace(r"\ ", r"\s+")
        return [m.start() for m in re.finditer(pattern, md_text_lower)]
    return [m.start() for m in re.finditer(re.escape(name_norm), md_text_lower)]


def _window_hit_experiment(
    md_text_lower: str,
    mention_positions: list[int],
    exp_tokens: list[str],
    window: int = WINDOW_CHARS,
) -> bool:
    """True if any experiment_name significant token appears within ±window of any mention."""
    if not exp_tokens or not mention_positions:
        return False
    for pos in mention_positions:
        lo = max(0, pos - window)
        hi = pos + window
        window_text = md_text_lower[lo:hi]
        for tok in exp_tokens:
            if tok in window_text:
                return True
    return False


def _fuzzy_in_blob(blob: str, name: str, alias_groups: dict[str, set[str]]) -> bool:
    """True if `name` fuzzy-matches any token-ish substring inside blob.

    Uses the evaluator's _fuzzy_match against candidate substrings of blob.
    To keep cost reasonable we first try literal containment of the normalized
    name; only if that fails do we scan word windows.
    """
    if not name or not blob:
        return False
    nm = normalize_dataset_name(name)
    if nm and nm in blob.replace("-", "").replace("_", "").replace(" ", ""):
        return True
    # Fall back to checking whether the name fuzzy-matches the whole blob via
    # substring (treat blob as one big candidate). _fuzzy_match uses normalized
    # forms + substring with ratio threshold.
    return _fuzzy_match(name, blob, alias_groups)


class AssignV1Cooccurrence(AssignStrategy):
    name = "v1_cooccurrence"

    def assign(
        self,
        paper_datasets: list[dict[str, Any]],
        experiments: list[dict[str, Any]],
        md_text: str,
        *,
        paper_id: str = "",
    ) -> list[dict[str, Any]]:
        alias_groups = _load_gazetteer_aliases()
        md_lower = (md_text or "").lower()

        # Pre-compute per-experiment metadata once.
        exp_meta: list[dict[str, Any]] = []
        for idx, exp in enumerate(experiments):
            exp_meta.append({
                "idx": idx,
                "tokens": _experiment_name_tokens(exp.get("experiment_name") or ""),
                "blob": _experiment_text_blob(exp),
                "klass": _classify_experiment(exp),
            })

        # Bucket initialization: each experiment gets a copy + empty datasets.
        out: list[dict[str, Any]] = []
        for exp in experiments:
            out.append({**exp, "datasets": [], "assignment_trace": {
                "strategy": self.name,
                "rule_hits": [],
                "fallback_used": "none",
                "broadcast_triggered": False,
            }})

        # Short-circuit: single-experiment paper.
        if len(experiments) == 1:
            out[0]["datasets"] = [dict(d) for d in paper_datasets]
            out[0]["assignment_trace"]["fallback_used"] = "single_experiment"
            return out

        # Rule 1: cooccurrence match for each paper dataset.
        # Blob match (dataset name appears inside an experiment's
        # method/key_results/evidence text) is the stronger, more specific
        # signal; md ±400 char window match is weaker and can bleed across
        # nearby sections in short markdown. So if any blob hit exists we
        # assign ONLY to blob-hit experiments; otherwise we fall back to
        # window-hit experiments.
        unmatched: list[dict[str, Any]] = []
        for ds in paper_datasets:
            ds_copy = dict(ds)
            names = _dataset_name_variants(ds)
            blob_hits: list[dict[str, Any]] = []
            window_hits: list[dict[str, Any]] = []
            for idx, meta in enumerate(exp_meta):
                # 1a: md window around any mention contains experiment_name tokens
                md_hit = False
                if meta["tokens"]:
                    mention_positions: list[int] = []
                    for nm in names:
                        mention_positions.extend(_find_mentions(md_lower, nm))
                    if mention_positions and _window_hit_experiment(
                        md_lower, mention_positions, meta["tokens"]
                    ):
                        md_hit = True
                # 1b: dataset name fuzzy-matches inside experiment text blob
                blob_hit = False
                if meta["blob"]:
                    for nm in names:
                        if _fuzzy_in_blob(meta["blob"], nm, alias_groups):
                            blob_hit = True
                            break
                if blob_hit:
                    blob_hits.append({"exp_index": idx, "rule": "blob_match",
                                      "blob_hit": True, "md_hit": md_hit})
                elif md_hit:
                    window_hits.append({"exp_index": idx, "rule": "md_window",
                                        "blob_hit": False, "md_hit": True})

            hits = blob_hits if blob_hits else window_hits
            if hits:
                # Assign to every hit experiment (cooccurrence is non-exclusive).
                for h in hits:
                    out[h["exp_index"]]["datasets"].append(dict(ds_copy))
                    out[h["exp_index"]]["assignment_trace"]["rule_hits"].append({
                        "dataset": ds.get("name"),
                        **h,
                    })
            else:
                unmatched.append(ds_copy)

        # Rule 2: experiment_type constraints already enforced at assignment time
        # (ablation/field_study only get hits; comparison/other may receive fallbacks).
        # Rule 3: primary-experiment fallback for unmatched datasets.
        fallback_target = self._pick_fallback_target(exp_meta)
        if unmatched and fallback_target is not None:
            idx = fallback_target
            # Only comparison/other buckets accept fallbacks.
            for ds in unmatched:
                out[idx]["datasets"].append(dict(ds))
                out[idx]["assignment_trace"]["rule_hits"].append({
                    "dataset": ds.get("name"),
                    "exp_index": idx,
                    "rule": "primary_fallback",
                })
            out[idx]["assignment_trace"]["fallback_used"] = "primary"
            unmatched = []

        # Rule 4: broadcast last-resort.
        has_field_study = any(m["klass"] == "field_study" for m in exp_meta)
        if unmatched and not has_field_study:
            for ds in unmatched:
                for exp_out in out:
                    exp_out["datasets"].append(dict(ds))
                    exp_out["assignment_trace"]["rule_hits"].append({
                        "dataset": ds.get("name"),
                        "rule": "broadcast",
                    })
            for exp_out in out:
                exp_out["assignment_trace"]["fallback_used"] = "broadcast"
                exp_out["assignment_trace"]["broadcast_triggered"] = True
            unmatched = []

        # If still unmatched (e.g. field_study present), drop them and record.
        if unmatched:
            for exp_out in out:
                exp_out["assignment_trace"]["dropped_unmatched"] = [
                    d.get("name") for d in unmatched
                ]

        # Record classification on each trace for debugging.
        for meta, exp_out in zip(exp_meta, out):
            exp_out["assignment_trace"]["experiment_class"] = meta["klass"]

        return out

    @staticmethod
    def _pick_fallback_target(exp_meta: list[dict[str, Any]]) -> int | None:
        """Pick the experiment index that absorbs unmatched datasets.

        Preference order (per DESIGN.md fallback decision table):
          1. first experiment classified as 'comparison'
          2. first 'other' experiment whose experiment_name contains a
             fallback keyword (evaluation/benchmark/comparison/main/...)
        Ablation, field_study, and generic 'other' experiments are NEVER
        fallback targets -- if none of the above match, the caller falls
        through to broadcast (or drop if a field_study experiment exists).
        """
        comparison = [m["idx"] for m in exp_meta if m["klass"] == "comparison"]
        if comparison:
            return comparison[0]
        for m in exp_meta:
            if m["klass"] != "other":
                continue
            if any(tok in _FALLBACK_NAME_KEYWORDS for tok in m["tokens"]):
                return m["idx"]
        return None
