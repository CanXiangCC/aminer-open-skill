"""OpenAI Chat-compatible LLM client for remote API.

Maintains the same return contract as SingleLLMClient.generate()
for compatibility with run_llm_stage_wf4.
"""

from __future__ import annotations

import json
import time
from typing import Any

import requests

from pipeline.benchmark.config import LLM_MODEL
from pipeline.production.adapters.gateway_auth import gateway_headers


class OpenAIChatLLMClient:
    """OpenAI Chat Completions API client for LLM.

    Works with any OpenAI-compatible /v1/chat/completions endpoint
    (configure via configs/default.yaml or the LLM_CHAT_URL env var).

    Return format matches SingleLLMClient.generate() for drop-in replacement.
    """

    def __init__(
        self,
        api_url: str,
        timeout: int = 180,
        default_model: str | None = None,
    ) -> None:
        self.api_url = api_url
        self.timeout = timeout
        # Effective model sent as payload["model"] on every generate() call.
        # The API also accepts requests without model (server-side default), but
        # we always send it explicitly so all 4 cluster backends resolve the
        # same model (ref-program/test_services.sh contract).
        self.default_model = default_model or LLM_MODEL
        self._model = self.default_model
        self._session = requests.Session()

    def generate(
        self,
        prompt: str,
        model: str | None = None,
        temperature: float = 0.05,
        num_predict: int = 2048,
        format: str | None = None,  # Ignored for OpenAI chat (ponytail: not needed)
        stop: list[str] | None = None,  # Mapped if supported
        num_ctx: int | None = None,  # Mapped if supported (ponytail: may be ignored)
    ) -> dict[str, Any]:
        """Generate via OpenAI chat completions API.

        Returns same dict shape as SingleLLMClient.generate():
        {raw_output, elapsed_sec, eval_count?, prompt_eval_count?, total_duration_ns?}
        """
        start = time.perf_counter()

        # Proxy contract (EXTRACTION_GPU_API.md §2.1): composite fields are
        # JSON strings — messages is []string of serialized message objects,
        # chat_template_kwargs is a serialized kwargs object. The proxy layer
        # json.loads-escapes them back for the vLLM upstream. Scalar fields
        # (model/temperature/max_tokens) stay native.
        payload: dict[str, Any] = {
            "model": model or self._model,
            "messages": [
                json.dumps({"role": "user", "content": prompt}, ensure_ascii=False)
            ],
            "chat_template_kwargs": json.dumps({"enable_thinking": False}),
        }

        # Always send sampling params explicitly: omitting them at the
        # production defaults (temperature=0.05, num_predict=2048) would make
        # behavior depend on the server-side defaults, which differ across the
        # 4 cluster backends (ollama path already sends both unconditionally).
        payload["temperature"] = temperature
        payload["max_tokens"] = num_predict
        if stop is not None:
            payload["stop"] = stop
        # num_ctx is server-side option; not standard OpenAI - may be ignored
        if num_ctx is not None:
            payload["num_ctx"] = num_ctx  # ponytail: passed but not standard

        response = self._session.post(
            self.api_url, json=payload, timeout=self.timeout,
            headers=gateway_headers({"Content-Type": "application/json"}),
        )
        elapsed = time.perf_counter() - start
        response.raise_for_status()

        result_data = response.json()
        raw_output = result_data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()

        # Extract token counts if available in usage field
        usage = result_data.get("usage", {})
        eval_count = usage.get("completion_tokens")
        prompt_eval_count = usage.get("prompt_tokens")

        return {
            "raw_output": raw_output,
            "elapsed_sec": elapsed,
            "eval_count": eval_count,
            "prompt_eval_count": prompt_eval_count,
            "total_duration_ns": None,  # Not provided by OpenAI format (ponytail: unused)
        }

    def resolve_model(self, preferred: list[str] | None = None) -> str:
        """Return the model this client sends as payload["model"].

        Signature kept for API compatibility with SingleLLMClient.
        """
        return self._model