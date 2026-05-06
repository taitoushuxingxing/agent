"""OpenAI-compatible LLM client factory."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from app.core.llm_config import LLMModelConfig, LLMRuntimeConfig


@dataclass
class LLMResponse:
    content: str


class OpenAICompatibleLLM:
    def __init__(self, config: LLMModelConfig) -> None:
        self.config = config

    def invoke(self, prompt: str) -> LLMResponse:
        if not self.config.api_key:
            raise ValueError(f"missing API key environment variable: {self.config.api_key_env}")
        base_url = (self.config.base_url or "https://api.openai.com/v1").rstrip("/")
        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
        }
        with httpx.Client(timeout=self.config.timeout_seconds) as client:
            response = client.post(
                f"{base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.config.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
        data = response.json()
        return LLMResponse(content=data["choices"][0]["message"]["content"])


def create_llm_pair(config: LLMRuntimeConfig) -> tuple[Any | None, Any | None]:
    if not config.enabled:
        return None, None
    return OpenAICompatibleLLM(config.quick), OpenAICompatibleLLM(config.deep)
