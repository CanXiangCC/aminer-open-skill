"""Experiment alignment helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from src.evaluation.schemas import ExperimentDict
from src.evaluation.semantic import SemanticScorer, jaccard_similarity

SIMILARITY_FIELDS = (
    "experiment_name",
    "research_goal",
    "method",
    "conclusion",
)

SEMANTIC_FIELDS = (
    "experiment_name",
    "research_problem",
    "research_goal",
    "method",
    "conclusion",
)


@dataclass(frozen=True)
class ExperimentMatch:
    """Matched experiment pair with its similarity score."""

    gold_index: int
    pred_index: int
    similarity: float


@dataclass
class AlignmentResult:
    """Result of aligning Gold and Prediction experiment arrays."""

    matches: list[ExperimentMatch]
    unmatched_gold: list[int]
    unmatched_prediction: list[int]
    count_alignment_factor: float


def simple_text_similarity(left: object, right: object) -> float:
    """Backward-compatible token Jaccard similarity."""
    return jaccard_similarity(left, right)


def join_values(values: Iterable[object]) -> str:
    """Join scalar/list values into one comparison string."""
    parts: list[str] = []
    for value in values:
        if isinstance(value, list):
            parts.extend(str(item) for item in value if item is not None)
        elif value is not None:
            parts.append(str(value))
    return " ".join(parts)


def experiment_text(
    experiment: ExperimentDict,
    fields: Iterable[str] = SIMILARITY_FIELDS,
) -> str:
    """Build comparison text for an experiment object."""
    return join_values(experiment.get(field, "") for field in fields)


def experiment_similarity(
    gold_exp: ExperimentDict,
    pred_exp: ExperimentDict,
    *,
    semantic_scorer: SemanticScorer | None = None,
) -> float:
    """Compute semantic similarity between two experiments for alignment."""
    scorer = semantic_scorer or SemanticScorer(type="jaccard")
    return scorer.similarity(
        experiment_text(gold_exp, SIMILARITY_FIELDS),
        experiment_text(pred_exp, SIMILARITY_FIELDS),
    )


def align_experiments(
    gold_experiments: list[ExperimentDict],
    pred_experiments: list[ExperimentDict],
    *,
    semantic_scorer: SemanticScorer | None = None,
    min_similarity: float = 0.0,
) -> AlignmentResult:
    """Greedily align Gold and Prediction experiments by semantic similarity."""
    candidate_pairs: list[ExperimentMatch] = []
    for gold_index, gold_exp in enumerate(gold_experiments):
        for pred_index, pred_exp in enumerate(pred_experiments):
            similarity = experiment_similarity(
                gold_exp,
                pred_exp,
                semantic_scorer=semantic_scorer,
            )
            if similarity >= min_similarity:
                candidate_pairs.append(
                    ExperimentMatch(
                        gold_index=gold_index,
                        pred_index=pred_index,
                        similarity=similarity,
                    )
                )

    candidate_pairs.sort(key=lambda item: item.similarity, reverse=True)
    used_gold: set[int] = set()
    used_pred: set[int] = set()
    matches: list[ExperimentMatch] = []

    for candidate in candidate_pairs:
        if candidate.gold_index in used_gold or candidate.pred_index in used_pred:
            continue
        used_gold.add(candidate.gold_index)
        used_pred.add(candidate.pred_index)
        matches.append(candidate)

    unmatched_gold = [
        index for index in range(len(gold_experiments)) if index not in used_gold
    ]
    unmatched_prediction = [
        index for index in range(len(pred_experiments)) if index not in used_pred
    ]
    denominator = max(len(gold_experiments), len(pred_experiments), 1)
    return AlignmentResult(
        matches=matches,
        unmatched_gold=unmatched_gold,
        unmatched_prediction=unmatched_prediction,
        count_alignment_factor=len(matches) / denominator,
    )
