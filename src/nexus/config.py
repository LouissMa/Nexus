from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


PROVIDER_PRESETS = {
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "simple_model": "gpt-4o-mini",
        "complex_model": "gpt-4o",
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "simple_model": "v4flash",
        "complex_model": "v4pro",
    },
    "custom": {
        "base_url": "https://api.openai.com/v1",
        "simple_model": "gpt-4o-mini",
        "complex_model": "gpt-4o",
    },
}


@dataclass(frozen=True)
class LLMSettings:
    provider: str = "openai"
    api_key: str | None = None
    base_url: str = "https://api.openai.com/v1"
    simple_model: str = "gpt-4o-mini"
    complex_model: str = "gpt-4o"
    default_tier: str = "simple"
    timeout_seconds: int = 30

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    def model_for_tier(self, tier: str | None = None) -> str:
        selected = tier or self.default_tier
        if selected == "complex":
            return self.complex_model
        return self.simple_model

    def masked(self) -> dict[str, Any]:
        data = asdict(self)
        data["api_key"] = mask_secret(self.api_key)
        return data


def nexus_home() -> Path:
    return Path(os.environ.get("NEXUS_HOME", ".nexus"))


def local_config_path() -> Path:
    return nexus_home() / "config.local.json"


def mask_secret(value: str | None) -> str | None:
    if not value:
        return None
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}...{value[-4:]}"


def load_local_config(path: Path | None = None) -> dict[str, Any]:
    config_path = path or local_config_path()
    if not config_path.exists():
        return {}
    with config_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_local_config(config: dict[str, Any], path: Path | None = None) -> Path:
    config_path = path or local_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with config_path.open("w", encoding="utf-8") as handle:
        json.dump(config, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return config_path


def load_llm_settings(env: dict[str, str] | None = None, path: Path | None = None) -> LLMSettings:
    values = env or os.environ
    config = load_local_config(path)
    llm = config.get("llm", {})
    provider = values.get("NEXUS_LLM_PROVIDER") or llm.get("provider") or "openai"
    preset = PROVIDER_PRESETS.get(provider, PROVIDER_PRESETS["custom"])

    timeout_value = values.get("NEXUS_LLM_TIMEOUT_SECONDS") or llm.get("timeout_seconds") or 30
    api_key = (
        values.get("NEXUS_LLM_API_KEY")
        or values.get("OPENAI_API_KEY")
        or llm.get("api_key")
    )

    return LLMSettings(
        provider=provider,
        api_key=api_key,
        base_url=(values.get("NEXUS_LLM_BASE_URL") or llm.get("base_url") or preset["base_url"]).rstrip("/"),
        simple_model=values.get("NEXUS_LLM_SIMPLE_MODEL") or llm.get("simple_model") or preset["simple_model"],
        complex_model=values.get("NEXUS_LLM_COMPLEX_MODEL") or llm.get("complex_model") or preset["complex_model"],
        default_tier=values.get("NEXUS_LLM_DEFAULT_TIER") or llm.get("default_tier") or "simple",
        timeout_seconds=int(timeout_value),
    )


def update_llm_settings(
    provider: str,
    api_key: str | None = None,
    base_url: str | None = None,
    simple_model: str | None = None,
    complex_model: str | None = None,
    default_tier: str = "simple",
    timeout_seconds: int = 30,
    path: Path | None = None,
) -> tuple[LLMSettings, Path]:
    if provider not in PROVIDER_PRESETS:
        provider = "custom"
    preset = PROVIDER_PRESETS[provider]
    settings = LLMSettings(
        provider=provider,
        api_key=api_key,
        base_url=(base_url or preset["base_url"]).rstrip("/"),
        simple_model=simple_model or preset["simple_model"],
        complex_model=complex_model or preset["complex_model"],
        default_tier=default_tier,
        timeout_seconds=timeout_seconds,
    )
    config = load_local_config(path)
    config["llm"] = asdict(settings)
    saved_path = save_local_config(config, path)
    return settings, saved_path
