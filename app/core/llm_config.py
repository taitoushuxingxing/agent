"""LLM configuration loader."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.config import load_environment


@dataclass(frozen=True)
class LLMModelConfig:
    provider: str
    model: str
    base_url: str | None
    api_key_env: str | None
    temperature: float
    max_tokens: int
    timeout_seconds: int

    @property
    def api_key(self) -> str | None:
        return os.getenv(self.api_key_env) if self.api_key_env else None


@dataclass(frozen=True)
class LLMRuntimeConfig:
    enabled: bool
    quick: LLMModelConfig
    deep: LLMModelConfig


def load_llm_config(path: str | Path) -> LLMRuntimeConfig:
    load_environment()
    config_path = Path(path)
    data = json.loads(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}
    return _apply_env_overrides(
        LLMRuntimeConfig(
            enabled=bool(data.get("enabled", False)),
            quick=_model_config(data.get("quick", {}), "QUICK"),
            deep=_model_config(data.get("deep", {}), "DEEP"),
        )
    )


def _model_config(data: dict[str, Any], prefix: str) -> LLMModelConfig:
    default_model = "gpt-4o-mini" if prefix == "QUICK" else "gpt-4o"
    return LLMModelConfig(
        provider=data.get("provider", "openai"),
        model=data.get("model", default_model),
        base_url=data.get("base_url"),
        api_key_env=data.get("api_key_env", "OPENAI_API_KEY"),
        temperature=float(data.get("temperature", 0.2)),
        max_tokens=int(data.get("max_tokens", 4000)),
        timeout_seconds=int(data.get("timeout_seconds", 60)),
    )


def _default_config() -> LLMRuntimeConfig:
    return LLMRuntimeConfig(
        enabled=False,
        quick=_model_config({}, "QUICK"),
        deep=_model_config({}, "DEEP"),
    )


def _apply_env_overrides(config: LLMRuntimeConfig) -> LLMRuntimeConfig:
    enabled = _env_bool("VEHICLE_DIAGNOSIS_LLM_ENABLED", config.enabled)
    return LLMRuntimeConfig(
        enabled=enabled,
        quick=_override_model(config.quick, "QUICK"),
        deep=_override_model(config.deep, "DEEP"),
    )


def _override_model(config: LLMModelConfig, prefix: str) -> LLMModelConfig:
    base = f"VEHICLE_DIAGNOSIS_LLM_{prefix}_"
    return LLMModelConfig(
        provider=os.getenv(base + "PROVIDER", config.provider),
        model=os.getenv(base + "MODEL", config.model),
        base_url=os.getenv(base + "BASE_URL", config.base_url or "") or None,
        api_key_env=os.getenv(base + "API_KEY_ENV", config.api_key_env or "") or None,
        temperature=float(os.getenv(base + "TEMPERATURE", str(config.temperature))),
        max_tokens=int(os.getenv(base + "MAX_TOKENS", str(config.max_tokens))),
        timeout_seconds=int(os.getenv(base + "TIMEOUT_SECONDS", str(config.timeout_seconds))),
    )


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}
