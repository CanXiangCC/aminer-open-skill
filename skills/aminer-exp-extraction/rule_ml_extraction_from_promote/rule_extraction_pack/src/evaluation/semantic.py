"""Semantic similarity helpers for evaluation scoring."""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from typing import Any

DEFAULT_SEMANTIC_MODEL = "all-MiniLM-L6-v2"
MISSING_SENTENCE_TRANSFORMERS_MESSAGE = (
    "sentence-transformers is required for embedding semantic scoring. "
    "Install with: pip install sentence-transformers"
)


def normalize_text(value: object) -> str:
    """Lowercase text and collapse non-word separators for jaccard fallback."""
    text = "" if value is None else str(value)
    text = text.lower()
    text = re.sub(r"[_\-]+", " ", text)
    text = re.sub(r"[^\w\s.]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def tokenize(value: object) -> set[str]:
    """Tokenize normalized text into a set of lexical tokens."""
    normalized = normalize_text(value)
    return {token for token in normalized.split(" ") if token}


def jaccard_similarity(left: object, right: object) -> float:
    """Token Jaccard fallback used for debug and dependency-light tests."""
    left_tokens = tokenize(left)
    right_tokens = tokenize(right)
    if not left_tokens and not right_tokens:
        return 1.0
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def clamp_score(value: float) -> float:
    """Clamp a similarity score to the benchmark range."""
    if math.isnan(value):
        return 0.0
    return max(0.0, min(1.0, value))


class SemanticScorer:
    """Unified semantic similarity scorer for evaluation."""

    def __init__(
        self,
        type: str = "embedding",
        model: str = DEFAULT_SEMANTIC_MODEL,
        device: str | None = "cpu",
        similarity: str = "cosine",
        local_files_only: bool = False,
    ) -> None:
        self.type = (type or "embedding").lower()
        self.model = model or DEFAULT_SEMANTIC_MODEL
        self.device = device
        self.similarity_name = (similarity or "cosine").lower()
        self.local_files_only = bool(local_files_only)
        self._model: Any | None = None
        if self.type not in {"embedding", "jaccard"}:
            raise ValueError("semantic scorer type must be 'embedding' or 'jaccard'.")
        if self.similarity_name != "cosine":
            raise ValueError("Only cosine semantic similarity is supported.")
        if self.type == "embedding":
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise RuntimeError(MISSING_SENTENCE_TRANSFORMERS_MESSAGE) from exc
            kwargs: dict[str, Any] = {"local_files_only": self.local_files_only}
            if self.device:
                kwargs["device"] = self.device
            self._model = SentenceTransformer(self.model, **kwargs)

    def similarity(self, left: str, right: str) -> float:
        """Return 0-1 similarity for two text strings."""
        if self.type == "jaccard":
            return jaccard_similarity(left, right)
        left_text = "" if left is None else str(left)
        right_text = "" if right is None else str(right)
        if not left_text.strip() and not right_text.strip():
            return 1.0
        if not left_text.strip() or not right_text.strip():
            return 0.0
        embeddings = self._model.encode(  # type: ignore[union-attr]
            [left_text, right_text],
            normalize_embeddings=True,
        )
        return clamp_score(_dot(embeddings[0], embeddings[1]))

    def to_config(self) -> dict[str, str | bool | None]:
        """Return JSON-serializable scorer configuration."""
        return {
            "type": self.type,
            "model": self.model,
            "device": self.device,
            "similarity": self.similarity_name,
            "local_files_only": self.local_files_only,
        }


def _dot(left: Sequence[float], right: Sequence[float]) -> float:
    return float(sum(float(a) * float(b) for a, b in zip(left, right, strict=False)))
