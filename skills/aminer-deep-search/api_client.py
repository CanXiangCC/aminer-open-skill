from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Sequence

from openai import OpenAI


@dataclass
class Response:
    """API response wrapper."""

    content: str
    reasoning_content: str = ""


class APIClient:
    """OpenAI-compatible chat client with model fallback."""

    MODEL_NAME_LIST: list[str] = []

    def __init__(
        self,
        api_key: str | None,
        base_url: str | None = None,
        timeout: float = 20,
    ) -> None:
        if not api_key:
            raise ValueError(
                "LLM API key is required. Use OpenClaw llm.api_key or pass --api-key."
            )

        self.base_url = base_url
        self.api_key = api_key
        self.timeout = timeout
        client_kwargs: dict[str, Any] = {"api_key": self.api_key, "timeout": timeout}
        if self.base_url:
            client_kwargs["base_url"] = self.base_url
        self.client = OpenAI(**client_kwargs)

    def call(
        self,
        message: str,
        system_prompt: str | None = None,
        model_list: Sequence[str] | None = None,
        validator: Callable[[str], bool] | None = None,
    ) -> tuple[Response, bool]:
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": message})
        return self.call_messages(messages, model_list=model_list, validator=validator)

    def call_messages(
        self,
        messages: Sequence[dict[str, Any]],
        model_list: Sequence[str] | None = None,
        validator: Callable[[str], bool] | None = None,
    ) -> tuple[Response, bool]:
        models = list(model_list or self.MODEL_NAME_LIST)
        if not models:
            raise ValueError("LLM model is required. Set OpenClaw llm.model or pass --models.")
        for model in models:
            try:
                print(f"Trying model: {model}")
                response = self.client.chat.completions.create(
                    model=model,
                    messages=list(messages),
                    timeout=self.timeout,
                )
                message = response.choices[0].message
                content = message.content or ""
                reasoning = getattr(message, "reasoning_content", "") or ""
                if validator is not None and not validator(content):
                    print(f"Model {model} returned unparsable content; trying next model.")
                    continue
                return Response(content=content, reasoning_content=reasoning), True
            except Exception as exc:
                print(f"Model {model} failed: {exc}; trying next model.")
                continue
        print("All model calls failed.")
        return Response(content="", reasoning_content=""), False
