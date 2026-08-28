"""BERT client for benchmark workflows."""

from __future__ import annotations

import re
import time
from typing import Any

import requests

from pipeline.benchmark.config import BERT_SERVER_URL, BERT_TIMEOUT


def split_sentences(text: str) -> list[str]:
    """Split text into sentences (simple implementation for benchmark)."""
    text = re.sub(r"\s+", " ", text)
    parts = re.split(r"(?<=[.!?])\s+", text)
    result: list[str] = []
    for part in parts:
        sentence = part.strip()
        if len(sentence) > 15:
            result.append(sentence)
    return result


def filter_english_only(sentences: list[str]) -> list[str]:
    """Filter to keep only English sentences."""
    english: list[str] = []
    for sentence in sentences:
        first_alpha = next((ch for ch in sentence if ch.isalpha()), "")
        if first_alpha and first_alpha.isascii():
            english.append(sentence)
    return english


class SerialBertClient:
    """Serial BERT client for filtering sentences (POST /filter/batch, single-paper).

    The per-paper ``/filter`` endpoint is no longer registered on the API
    gateway; single-paper filtering is routed through ``/filter/batch`` with a
    one-element ``papers`` list (same SciBERT model and threshold server-side).
    """

    def __init__(self, url: str = BERT_SERVER_URL, timeout: int = BERT_TIMEOUT) -> None:
        self.url = url
        self.timeout = timeout

    def check_health(self) -> dict[str, Any]:
        """Check BERT service health."""
        response = requests.get(f"{self.url}/health", timeout=5)
        response.raise_for_status()
        return response.json()

    def filter_sentences_serial(
        self,
        sentences: list[str],
        threshold: float = 0.6,
    ) -> dict[str, Any]:
        """Filter sentences via /filter/batch with a single paper.

        Args:
            sentences: List of sentences to filter
            threshold: Confidence threshold (default: 0.6)

        Returns:
            Dict with 'kept_sentences', 'confidences', 'indices', 'total', 'kept_count',
                 'inference_time_ms', 'elapsed_sec'
        """
        import json as _json

        start = time.perf_counter()

        from pipeline.production.adapters.gateway_auth import gateway_headers

        response = requests.post(
            f"{self.url}/filter/batch",
            json={
                # Proxy contract (EXTRACTION_GPU_API.md §1.1): papers is
                # []string — each paper object serialized to a JSON string.
                "papers": [
                    _json.dumps({"paper_id": "serial", "sentences": sentences})
                ],
                "threshold": threshold,
            },
            timeout=self.timeout,
            headers=gateway_headers(),
        )
        elapsed = time.perf_counter() - start

        if response.status_code != 200:
            raise RuntimeError(f"BERT service error: {response.status_code} - {response.text[:200]}")

        data = response.json()
        entries = data.get("papers", [])
        if not entries:
            raise RuntimeError("BERT /filter/batch returned no paper entries")
        entry = entries[0]
        return {
            "kept_sentences": entry["kept"],
            "confidences": entry.get("confidences"),
            "indices": entry.get("indices", []),
            "total": entry.get("total", len(sentences)),
            "kept_count": entry.get("kept_count", len(entry["kept"])),
            "inference_time_ms": data.get("inference_time_ms"),
            "elapsed_sec": elapsed,
        }


class BatchBertClient:
    """Future: POST /filter/batch. Not implemented in v0.1.0."""

    def filter_papers(self, papers: list[dict]) -> dict:
        """Phase 2: bert batch mode."""
        raise NotImplementedError("Phase 2: bert batch mode not implemented in v0.1.0")