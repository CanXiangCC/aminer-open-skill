"""LLM client for benchmark workflows."""

from __future__ import annotations

import time
from typing import Any

import requests

from pipeline.benchmark.config import OLLAMA_API_URL, OLLAMA_TAGS_URL, OLLAMA_TIMEOUT


class SingleLLMClient:
    """Single LLM client for JSON extraction.

    Uses a persistent ``requests.Session`` (HTTP keep-alive) so repeated
    ``generate`` calls reuse one TCP connection instead of paying per-request
    connection setup. The resolved model name is cached after the first
    ``generate``/``resolve_model`` call — Ollama's model set does not change
    mid-run, so re-querying ``/api/tags`` per paper is pure waste.
    """

    def __init__(
        self,
        api_url: str = OLLAMA_API_URL,
        tags_url: str = OLLAMA_TAGS_URL,
        timeout: int = OLLAMA_TIMEOUT,
        default_model: str | None = None,
    ) -> None:
        self.api_url = api_url
        self.tags_url = tags_url
        self.timeout = timeout
        self.default_model = default_model
        self._session = requests.Session()
        self._model: str | None = None  # cached resolved model name

    def resolve_model(self, preferred: list[str] | None = None) -> str:
        """Resolve the actual model name from Ollama (cached on first call)."""
        if self._model is not None and preferred is None:
            return self._model

        response = self._session.get(self.tags_url, timeout=5)
        response.raise_for_status()
        models = [item["name"] for item in response.json().get("models", [])]

        if preferred is None and self.default_model is not None:
            preferred_list = [self.default_model]
        else:
            preferred_list = preferred or [
                "sam860/qwen3:1.7b-Q4_K_XL",
                "qwen3:1.7b",
                "qwen3-1.7b",
                "qwen3:1.7b-q4_K_M",
                "qwen2.5:1.5b",
            ]

        for name in preferred_list:
            if name in models:
                if preferred is None:
                    self._model = name
                return name
        if self.default_model is not None and preferred is None:
            raise RuntimeError(
                f"Ollama model not found: {self.default_model!r}. "
                f"Installed: {models}. Run `ollama list` and fix wf4_models.json."
            )
        if preferred is not None:
            raise RuntimeError(
                f"Ollama model not found in preferred {preferred!r}. Installed: {models}"
            )
        for name in models:
            if "qwen" in name.lower() and ("1.7" in name or "1.5" in name):
                if preferred is None:
                    self._model = name
                return name
        if models:
            if preferred is None:
                self._model = models[0]
            return models[0]
        raise RuntimeError("No Ollama models available")

    def generate(
        self,
        prompt: str,
        model: str | None = None,
        temperature: float = 0.05,
        num_predict: int = 2048,
        format: str | None = None,
        stop: list[str] | None = None,
        num_ctx: int | None = None,
    ) -> dict[str, Any]:
        """Generate text using LLM model.

        Args:
            prompt: The prompt to send
            model: Model name (auto-resolved+cached if None)
            temperature: Sampling temperature
            num_predict: Maximum tokens to generate
            format: Optional Ollama ``format`` (e.g. ``"json"``) to force
                structured output. Only added to the payload when not None.
            stop: Optional Ollama ``stop`` sequences (added to ``options``).
            num_ctx: Optional Ollama ``num_ctx`` context window (added to
                ``options``).

        Returns:
            Dict with 'raw_output', 'elapsed_sec', 'eval_count', 'prompt_eval_count', 'total_duration_ns'
        """
        start = time.perf_counter()

        if model is None:
            model = self._model if self._model is not None else self.resolve_model()

        options: dict[str, Any] = {
            "temperature": temperature,
            "num_predict": num_predict,
        }
        if stop is not None:
            options["stop"] = stop
        if num_ctx is not None:
            options["num_ctx"] = num_ctx
        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": options,
            "think": False,
        }
        if format is not None:
            payload["format"] = format

        response = self._session.post(self.api_url, json=payload, timeout=self.timeout)
        elapsed = time.perf_counter() - start

        if response.status_code != 200:
            raise RuntimeError(f"Ollama error: {response.status_code} - {response.text[:200]}")

        result_data = response.json()
        raw_output = result_data.get("response", "").strip()

        return {
            "raw_output": raw_output,
            "elapsed_sec": elapsed,
            "eval_count": result_data.get("eval_count"),
            "prompt_eval_count": result_data.get("prompt_eval_count"),
            "total_duration_ns": result_data.get("total_duration"),
        }


class ParallelLLMClient:
    """Future: Parallel LLM client for batch processing. Not implemented in v0.1.0."""

    def generate_batch(self, prompts: list[str]) -> list[dict]:
        """Phase 2: LLM parallel mode."""
        raise NotImplementedError("Phase 2: LLM parallel mode not implemented in v0.1.0")