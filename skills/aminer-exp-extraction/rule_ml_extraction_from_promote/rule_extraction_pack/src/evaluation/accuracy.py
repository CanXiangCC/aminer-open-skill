"""Accuracy metrics for comparing Prediction experiments against Gold."""

from __future__ import annotations

from statistics import mean
from typing import Iterable

from src.evaluation.alignment import (
    SEMANTIC_FIELDS,
    AlignmentResult,
    align_experiments,
    experiment_text,
)
from src.evaluation.schemas import ExperimentDict
from src.evaluation.semantic import SemanticScorer

METRIC_SYNONYMS = {
    "acc": "accuracy",
    "accuracy": "accuracy",
}


def semantic_f1_score(
    gold_items: Iterable[str],
    pred_items: Iterable[str],
    *,
    semantic_scorer: SemanticScorer | None = None,
    threshold: float = 0.80,
) -> float:
    """Use semantic similarity to compute F1 score (fuzzy matching).

    Args:
        gold_items: Gold label collection
        pred_items: Prediction label collection
        semantic_scorer: Semantic scorer, fallback to exact match if None
        threshold: Similarity threshold, pairs below this won't match

    Returns:
        F1 score (0-1)
    """
    gold_list = list(gold_items)
    pred_list = list(pred_items)

    # Empty set handling
    if not gold_list and not pred_list:
        return 1.0
    if not gold_list or not pred_list:
        return 0.0

    # Fallback to exact matching
    if semantic_scorer is None:
        return f1_score(gold_list, pred_list)

    # Compute similarity matrix
    true_positives = 0.0
    used_pred: set[int] = set()

    # Greedy matching: for each gold, find the most similar pred
    for gold_item in gold_list:
        best_idx = -1
        best_sim = threshold

        for pred_idx, pred_item in enumerate(pred_list):
            if pred_idx in used_pred:
                continue
            sim = semantic_scorer.similarity(gold_item, pred_item)
            if sim > best_sim:
                best_sim = sim
                best_idx = pred_idx

        if best_idx >= 0:
            true_positives += best_sim  # Use similarity as contribution
            used_pred.add(best_idx)

    # Compute F1
    precision = true_positives / len(pred_list) if pred_list else 0.0
    recall = true_positives / len(gold_list) if gold_list else 0.0

    if precision + recall == 0:
        return 0.0

    f1 = 2 * precision * recall / (precision + recall)
    return float(f1)


def normalize_label(value: object) -> str:
    """Normalize a set-comparison label."""
    text = "" if value is None else str(value)
    text = text.lower().strip()
    return " ".join(text.split())


def normalize_metric(value: object) -> str:
    """Normalize metric names with a small synonym map."""
    label = normalize_label(value)
    return METRIC_SYNONYMS.get(label, label)


def f1_score(gold_items: Iterable[str], pred_items: Iterable[str]) -> float:
    """Compute set F1. Empty vs empty is treated as fully matched."""
    gold_set = {item for item in gold_items if item}
    pred_set = {item for item in pred_items if item}
    if not gold_set and not pred_set:
        return 1.0
    if not gold_set or not pred_set:
        return 0.0
    true_positive = len(gold_set & pred_set)
    if true_positive == 0:
        return 0.0
    precision = true_positive / len(pred_set)
    recall = true_positive / len(gold_set)
    return 2 * precision * recall / (precision + recall)


def dataset_names(experiment: ExperimentDict) -> list[str]:
    """Extract normalized dataset names from the authoritative datasets field."""
    datasets = experiment.get("datasets") or []
    names: list[str] = []
    for dataset in datasets:
        if isinstance(dataset, dict):
            name = normalize_label(dataset.get("name"))
            if name:
                names.append(name)
    return names


def normalized_metrics(experiment: ExperimentDict) -> list[str]:
    """Extract normalized metric labels."""
    return [normalize_metric(metric) for metric in experiment.get("metrics") or []]


def key_results_text(experiment: ExperimentDict) -> str:
    """Join key result strings for semantic comparison."""
    return " ".join(str(item) for item in experiment.get("key_results") or [])


def domain_score(gold_exp: ExperimentDict, pred_exp: ExperimentDict) -> float:
    """Domain exact-match score."""
    return 1.0 if gold_exp.get("domain") == pred_exp.get("domain") else 0.0


def experiment_accuracy(
    gold_exp: ExperimentDict,
    pred_exp: ExperimentDict,
    *,
    semantic_scorer: SemanticScorer,
    datasets_threshold: float = 0.75,
    metrics_threshold: float = 0.80,
) -> dict:
    """Compute weighted accuracy details for a matched experiment pair."""
    domain = domain_score(gold_exp, pred_exp)

    # Use semantic F1 for datasets
    datasets = semantic_f1_score(
        dataset_names(gold_exp),
        dataset_names(pred_exp),
        semantic_scorer=semantic_scorer,
        threshold=datasets_threshold,
    )

    # Use semantic F1 for metrics
    metrics = semantic_f1_score(
        normalized_metrics(gold_exp),
        normalized_metrics(pred_exp),
        semantic_scorer=semantic_scorer,
        threshold=metrics_threshold,
    )

    key_results = semantic_scorer.similarity(
        key_results_text(gold_exp),
        key_results_text(pred_exp),
    )
    exp_semantic = semantic_scorer.similarity(
        experiment_text(gold_exp, SEMANTIC_FIELDS),
        experiment_text(pred_exp, SEMANTIC_FIELDS),
    )
    score = (
        0.15 * domain
        + 0.20 * datasets
        + 0.15 * metrics
        + 0.25 * key_results
        + 0.25 * exp_semantic
    )
    return {
        "domain_score": domain,
        "datasets_score": datasets,
        "metrics_score": metrics,
        "key_results_score": key_results,
        "exp_semantic_score": exp_semantic,
        "exp_accuracy": score,
    }


def paper_accuracy(
    gold_experiments: list[ExperimentDict],
    pred_experiments: list[ExperimentDict],
    *,
    semantic_scorer: SemanticScorer | None = None,
    alignment: AlignmentResult | None = None,
    datasets_threshold: float = 0.75,
    metrics_threshold: float = 0.80,
) -> dict:
    """Compute paper-level accuracy with experiment alignment penalty."""
    scorer = semantic_scorer or SemanticScorer(type="jaccard")
    alignment_result = alignment or align_experiments(
        gold_experiments,
        pred_experiments,
        semantic_scorer=scorer,
    )
    matched_details: list[dict] = []
    for match in alignment_result.matches:
        details = experiment_accuracy(
            gold_experiments[match.gold_index],
            pred_experiments[match.pred_index],
            semantic_scorer=scorer,
            datasets_threshold=datasets_threshold,
            metrics_threshold=metrics_threshold,
        )
        details.update(
            {
                "gold_index": match.gold_index,
                "pred_index": match.pred_index,
                "alignment_similarity": match.similarity,
            }
        )
        matched_details.append(details)

    if not matched_details:
        accuracy = 0.0
    else:
        accuracy = mean(item["exp_accuracy"] for item in matched_details)
        accuracy *= alignment_result.count_alignment_factor

    return {
        "paper_accuracy": accuracy,
        "count_alignment_factor": alignment_result.count_alignment_factor,
        "matched_count": len(alignment_result.matches),
        "gold_count": len(gold_experiments),
        "pred_count": len(pred_experiments),
        "unmatched_gold": alignment_result.unmatched_gold,
        "unmatched_prediction": alignment_result.unmatched_prediction,
        "matched_experiments": matched_details,
    }
