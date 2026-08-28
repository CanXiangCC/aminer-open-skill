"""P5 characterization tests: OpenAI chat client always sends sampling params.

The client used to omit ``temperature``/``max_tokens`` when they equaled the
production defaults (0.05 / 2048), silently deferring to server-side defaults
that differ across the 4 cluster backends. These tests pin the fixed contract:
both keys are present in every payload, plus the pre-existing invariants
(explicit model, enable_thinking=False) that must not regress.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

PROD_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROD_ROOT))

from pipeline.benchmark.stages.openai_chat_llm_client import (  # noqa: E402
    OpenAIChatLLMClient,
)


class _FakeResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return {
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"completion_tokens": 1, "prompt_tokens": 2},
        }


def _capture_post(monkeypatch) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []

    def fake_post(self, url, json=None, timeout=None, headers=None):
        payloads.append(json)
        return _FakeResponse()

    monkeypatch.setattr("requests.Session.post", fake_post)
    return payloads


def test_payload_always_sends_max_tokens_and_temperature(monkeypatch) -> None:
    payloads = _capture_post(monkeypatch)
    client = OpenAIChatLLMClient("http://fake:8000/v1/chat/completions")

    # Production defaults: the exact values the old code used to omit.
    client.generate("prompt")
    assert payloads[-1]["max_tokens"] == 2048
    assert payloads[-1]["temperature"] == 0.05

    # Explicit overrides are reflected.
    client.generate("prompt", temperature=0.3, num_predict=512)
    assert payloads[-1]["max_tokens"] == 512
    assert payloads[-1]["temperature"] == 0.3


def test_payload_model_and_thinking(monkeypatch) -> None:
    payloads = _capture_post(monkeypatch)
    client = OpenAIChatLLMClient("http://fake:8000/v1/chat/completions")

    out = client.generate("prompt")
    assert out["raw_output"] == "ok"
    # Proxy contract (EXTRACTION_GPU_API.md §2.1): composite fields travel as
    # JSON strings — chat_template_kwargs serialized, messages []string.
    assert payloads[-1]["chat_template_kwargs"] == '{"enable_thinking": false}'
    assert payloads[-1]["messages"] == [
        json.dumps({"role": "user", "content": "prompt"})
    ]
    # model is always explicit (never omitted for the server to default)
    assert payloads[-1]["model"] == client._model

    client.generate("prompt", model="llm-override")
    assert payloads[-1]["model"] == "llm-override"
