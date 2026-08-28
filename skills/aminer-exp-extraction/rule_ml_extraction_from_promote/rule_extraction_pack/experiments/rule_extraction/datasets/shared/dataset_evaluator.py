"""
Dataset extraction evaluation: strict, fuzzy, and semantic matching.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from src.evaluation.semantic import SemanticScorer

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
GAZETTEER_PATH = (
    PROJECT_ROOT / "experiments" / "rule_extraction" / "datasets" / "data" / "gazetteer.json"
)

_SUFFIX_RE = re.compile(r"(dataset|corpus|benchmark|set|collection)$")
SEMANTIC_THRESHOLD = 0.85


def normalize_dataset_name(name: str) -> str:
    if not name:
        return ""
    return name.lower().strip().replace(" ", "").replace("-", "").replace("_", "")


def normalize_fuzzy(name: str) -> str:
    n = normalize_dataset_name(name)
    return _SUFFIX_RE.sub("", n)


def _load_gazetteer_aliases() -> dict[str, set[str]]:
    """Map normalized alias -> set of equivalent normalized forms.

    Honors the RULE_GAZETTEER_PATH env var so evaluation alias groups stay
    in sync with the gazetteer used by the strategy under test.
    """
    import os

    gazetteer_path = GAZETTEER_PATH
    env_path = os.environ.get("RULE_GAZETTEER_PATH")
    if env_path:
        candidate = Path(env_path)
        if candidate.exists():
            gazetteer_path = candidate
    if not gazetteer_path.exists():
        return {}
    with open(gazetteer_path, encoding="utf-8") as f:
        entries = json.load(f)
    groups: dict[str, set[str]] = {}
    for entry in entries:
        forms: set[str] = set()
        for raw in [entry.get("canonical_name", "")] + list(entry.get("aliases") or []):
            for variant in (normalize_fuzzy(raw), normalize_dataset_name(raw)):
                if variant:
                    forms.add(variant)
        if not forms:
            continue
        group_key = min(forms)
        if group_key not in groups:
            groups[group_key] = set()
        groups[group_key].update(forms)
    return groups


def _gazetteer_equivalent(a: str, b: str, alias_groups: dict[str, set[str]]) -> bool:
    fa, fb = normalize_fuzzy(a), normalize_fuzzy(b)
    if fa == fb:
        return True
    for forms in alias_groups.values():
        if fa in forms and fb in forms:
            return True
    return False


def _fuzzy_match(a: str, b: str, alias_groups: dict[str, set[str]]) -> bool:
    fa, fb = normalize_fuzzy(a), normalize_fuzzy(b)
    if not fa or not fb:
        return False
    if fa == fb:
        return True
    if _gazetteer_equivalent(a, b, alias_groups):
        return True
    shorter, longer = (fa, fb) if len(fa) <= len(fb) else (fb, fa)
    if len(shorter) < 3:
        return False
    if shorter in longer and len(shorter) / len(longer) >= 0.5:
        return True
    return False


def _greedy_match(
    gold_names: list[str],
    pred_names: list[str],
    match_fn,
    score_fn=None,
    threshold: float = 0.0,
) -> tuple[list[dict[str, Any]], set[int], set[int]]:
    """Greedy 1:1 matching; returns pairs and unmatched indices."""
    pairs: list[dict[str, Any]] = []
    used_pred: set[int] = set()
    matched_gold: set[int] = set()

    for gi, g in enumerate(gold_names):
        best_pi = -1
        best_score = threshold
        for pi, p in enumerate(pred_names):
            if pi in used_pred:
                continue
            if match_fn(g, p):
                score = score_fn(g, p) if score_fn else 1.0
                if score > best_score:
                    best_score = score
                    best_pi = pi
        if best_pi >= 0:
            pairs.append({
                "gold": gold_names[gi],
                "pred": pred_names[best_pi],
                "score": round(best_score, 4),
            })
            used_pred.add(best_pi)
            matched_gold.add(gi)

    return pairs, matched_gold, used_pred


def _metrics_from_pairs(
    pairs: list[dict[str, Any]],
    gold_count: int,
    pred_count: int,
    use_soft_tp: bool = False,
) -> dict[str, Any]:
    if use_soft_tp:
        tp = sum(p["score"] for p in pairs)
    else:
        tp = float(len(pairs))
    precision = tp / pred_count if pred_count else 0.0
    recall = tp / gold_count if gold_count else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    matched_gold = [p["gold"] for p in pairs]
    matched_pred = [p["pred"] for p in pairs]
    return {
        "matched_count": len(pairs),
        "recall": recall,
        "precision": precision,
        "f1": f1,
        "matched_gold_names": matched_gold,
        "matched_pred_names": matched_pred,
    }


def evaluate_paper_datasets(
    gold_datasets: list[dict[str, Any]],
    rule_datasets: list[dict[str, Any]],
    *,
    semantic_scorer: SemanticScorer | None = None,
    alias_groups: dict[str, set[str]] | None = None,
) -> dict[str, Any]:
    """Evaluate one paper with strict, fuzzy, and semantic modes."""
    gold_names = [ds["name"] for ds in gold_datasets if ds.get("name")]
    pred_names = [ds["name"] for ds in rule_datasets if ds.get("name")]
    alias_groups = alias_groups if alias_groups is not None else _load_gazetteer_aliases()

    # Strict
    gold_strict = {normalize_dataset_name(n) for n in gold_names}
    pred_strict = {normalize_dataset_name(n) for n in pred_names}
    strict_matched = gold_strict & pred_strict
    strict = {
        "matched_count": len(strict_matched),
        "missed_count": len(gold_strict - pred_strict),
        "extra_count": len(pred_strict - gold_strict),
        "recall": len(strict_matched) / len(gold_strict) if gold_strict else 0.0,
        "precision": len(strict_matched) / len(pred_strict) if pred_strict else 0.0,
        "matched_names": sorted(strict_matched),
        "missed_names": sorted(gold_strict - pred_strict),
        "extra_names": sorted(pred_strict - gold_strict),
    }
    strict["f1"] = (
        2 * strict["recall"] * strict["precision"] / (strict["recall"] + strict["precision"])
        if (strict["recall"] + strict["precision"]) > 0
        else 0.0
    )

    # Fuzzy
    fuzzy_pairs, _, _ = _greedy_match(
        gold_names,
        pred_names,
        lambda g, p: _fuzzy_match(g, p, alias_groups),
    )
    fuzzy_m = _metrics_from_pairs(fuzzy_pairs, len(gold_names), len(pred_names))
    fuzzy_missed = [g for g in gold_names if g not in fuzzy_m["matched_gold_names"]]
    fuzzy_extra = [p for p in pred_names if p not in fuzzy_m["matched_pred_names"]]
    fuzzy = {
        **fuzzy_m,
        "missed_count": len(fuzzy_missed),
        "extra_count": len(fuzzy_extra),
        "missed_names": [normalize_dataset_name(n) for n in fuzzy_missed],
        "extra_names": [normalize_dataset_name(n) for n in fuzzy_extra],
    }

    # Semantic
    semantic_pairs: list[dict[str, Any]] = []
    if semantic_scorer and gold_names and pred_names:
        used_pred: set[int] = set()
        for g in gold_names:
            best_pi = -1
            best_sim = SEMANTIC_THRESHOLD
            for pi, p in enumerate(pred_names):
                if pi in used_pred:
                    continue
                sim = semantic_scorer.similarity(g, p)
                if sim > best_sim:
                    best_sim = sim
                    best_pi = pi
            if best_pi >= 0:
                semantic_pairs.append({"gold": g, "pred": pred_names[best_pi], "score": round(best_sim, 4)})
                used_pred.add(best_pi)
    elif not gold_names and not pred_names:
        semantic_m = {"matched_count": 0, "recall": 1.0, "precision": 1.0, "f1": 1.0,
                      "matched_gold_names": [], "matched_pred_names": []}
    else:
        semantic_m = {"matched_count": 0, "recall": 0.0, "precision": 0.0, "f1": 0.0,
                      "matched_gold_names": [], "matched_pred_names": []}

    if semantic_scorer or (not gold_names and not pred_names):
        if gold_names or pred_names:
            semantic_m = _metrics_from_pairs(
                semantic_pairs, len(gold_names), len(pred_names), use_soft_tp=True
            )
        semantic_missed = [g for g in gold_names if g not in semantic_m.get("matched_gold_names", [])]
        semantic_extra = [p for p in pred_names if p not in semantic_m.get("matched_pred_names", [])]
        semantic = {
            **semantic_m,
            "missed_count": len(semantic_missed),
            "extra_count": len(semantic_extra),
            "missed_names": [normalize_dataset_name(n) for n in semantic_missed],
            "extra_names": [normalize_dataset_name(n) for n in semantic_extra],
        }
    else:
        semantic = dict(strict)

    match_pairs = []
    for p in strict_matched:
        match_pairs.append({"gold": p, "pred": p, "mode": "strict", "score": 1.0})
    for p in fuzzy_pairs:
        if normalize_dataset_name(p["gold"]) not in strict_matched:
            match_pairs.append({**p, "mode": "fuzzy"})
    for p in semantic_pairs:
        gs = normalize_dataset_name(p["gold"])
        if gs not in strict_matched and not any(
            fp["gold"] == p["gold"] for fp in fuzzy_pairs
        ):
            match_pairs.append({**p, "mode": "semantic"})

    return {
        "gold_count": len(gold_datasets),
        "rule_count": len(rule_datasets),
        "strict": strict,
        "fuzzy": fuzzy,
        "semantic": semantic,
        "match_pairs": match_pairs,
    }


def aggregate_evaluations(paper_evals: list[dict[str, Any]], mode: str = "strict") -> dict[str, Any]:
    """Aggregate per-paper evaluations for one mode."""
    total_gold = sum(e["gold_count"] for e in paper_evals)
    total_rule = sum(e["rule_count"] for e in paper_evals)
    total_matched = sum(e[mode]["matched_count"] for e in paper_evals)
    total_missed = sum(e[mode]["missed_count"] for e in paper_evals)
    total_extra = sum(e[mode]["extra_count"] for e in paper_evals)

    if mode == "semantic":
        tp = sum(
            sum(p["score"] for p in e.get("match_pairs", []) if p.get("mode") == "semantic")
            for e in paper_evals
        )
        recall = tp / total_gold if total_gold else 0.0
        precision = tp / total_rule if total_rule else 0.0
    else:
        recall = total_matched / total_gold if total_gold else 0.0
        precision = total_matched / total_rule if total_rule else 0.0

    f1 = 2 * recall * precision / (recall + precision) if (recall + precision) > 0 else 0.0
    return {
        "total_papers": len(paper_evals),
        "total_gold_datasets": total_gold,
        "total_rule_datasets": total_rule,
        "total_matched": total_matched,
        "total_missed": total_missed,
        "total_extra": total_extra,
        "recall": recall,
        "precision": precision,
        "f1": f1,
    }
