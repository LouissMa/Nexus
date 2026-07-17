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

EMBEDDING_PRESETS = {
    "local_sparse": {
        "base_url": None,
        "model": "local-sparse-v1",
    },
    "fastembed": {
        "base_url": None,
        "model": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "model": "text-embedding-3-small",
    },
    "custom": {
        "base_url": "https://api.openai.com/v1",
        "model": "text-embedding-3-small",
    },
}

TOOL_NAMES = ("weather", "calendar", "todo", "github", "notion", "email", "filesystem")
TOOL_ALLOWED_OPERATIONS = {
    "weather": ["read"],
    "calendar": ["read"],
    "todo": ["read"],
    "github": ["read"],
    "notion": ["read"],
    "email": ["read"],
    "filesystem": ["list", "read", "search"],
}
TOOL_SECRET_FIELDS = {"token", "password", "calendar_url"}

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


@dataclass(frozen=True)
class EmbeddingSettings:
    provider: str = "local_sparse"
    model: str = "local-sparse-v1"
    api_key: str | None = None
    base_url: str | None = None
    qdrant_url: str | None = None
    qdrant_api_key: str | None = None
    collection_name: str = "nexus_memories"
    timeout_seconds: int = 30

    @property
    def semantic_enabled(self) -> bool:
        return self.provider != "local_sparse"

    @property
    def is_configured(self) -> bool:
        if self.provider == "fastembed":
            return True
        if self.provider in {"openai", "custom"}:
            return bool(self.api_key and self.base_url)
        return self.provider == "local_sparse"

    def masked(self) -> dict[str, Any]:
        data = asdict(self)
        data["api_key"] = mask_secret(self.api_key)
        data["qdrant_api_key"] = mask_secret(self.qdrant_api_key)
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
    values = os.environ if env is None else env
    config = load_local_config(path)
    llm = config.get("llm", {})
    provider = values.get("NEXUS_LLM_PROVIDER") or llm.get("provider") or "openai"
    preset = PROVIDER_PRESETS.get(provider, PROVIDER_PRESETS["custom"])
    timeout_value = values.get("NEXUS_LLM_TIMEOUT_SECONDS") or llm.get("timeout_seconds") or 30
    api_key = values.get("NEXUS_LLM_API_KEY") or values.get("OPENAI_API_KEY") or llm.get("api_key")

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


def load_embedding_settings(
    env: dict[str, str] | None = None,
    path: Path | None = None,
) -> EmbeddingSettings:
    values = os.environ if env is None else env
    config = load_local_config(path)
    embedding = config.get("embedding", {})
    provider = values.get("NEXUS_EMBEDDING_PROVIDER") or embedding.get("provider") or "local_sparse"
    preset = EMBEDDING_PRESETS.get(provider, EMBEDDING_PRESETS["custom"])
    base_url = values.get("NEXUS_EMBEDDING_BASE_URL") or embedding.get("base_url") or preset["base_url"]
    api_key = (
        values.get("NEXUS_EMBEDDING_API_KEY")
        or (values.get("OPENAI_API_KEY") if provider == "openai" else None)
        or embedding.get("api_key")
    )
    timeout_value = (
        values.get("NEXUS_EMBEDDING_TIMEOUT_SECONDS")
        or embedding.get("timeout_seconds")
        or 30
    )
    return EmbeddingSettings(
        provider=provider,
        model=values.get("NEXUS_EMBEDDING_MODEL") or embedding.get("model") or preset["model"],
        api_key=api_key,
        base_url=base_url.rstrip("/") if base_url else None,
        qdrant_url=values.get("NEXUS_QDRANT_URL") or embedding.get("qdrant_url"),
        qdrant_api_key=values.get("NEXUS_QDRANT_API_KEY") or embedding.get("qdrant_api_key"),
        collection_name=(
            values.get("NEXUS_QDRANT_COLLECTION")
            or embedding.get("collection_name")
            or "nexus_memories"
        ),
        timeout_seconds=int(timeout_value),
    )


def update_embedding_settings(
    provider: str,
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    qdrant_url: str | None = None,
    qdrant_api_key: str | None = None,
    collection_name: str = "nexus_memories",
    timeout_seconds: int = 30,
    path: Path | None = None,
) -> tuple[EmbeddingSettings, Path]:
    if provider not in EMBEDDING_PRESETS:
        provider = "custom"
    preset = EMBEDDING_PRESETS[provider]
    selected_base_url = base_url or preset["base_url"]
    settings = EmbeddingSettings(
        provider=provider,
        model=model or preset["model"],
        api_key=api_key,
        base_url=selected_base_url.rstrip("/") if selected_base_url else None,
        qdrant_url=qdrant_url,
        qdrant_api_key=qdrant_api_key,
        collection_name=collection_name,
        timeout_seconds=timeout_seconds,
    )
    config = load_local_config(path)
    config["embedding"] = asdict(settings)
    saved_path = save_local_config(config, path)
    return settings, saved_path

def load_tool_settings(
    env: dict[str, str] | None = None,
    path: Path | None = None,
) -> dict[str, dict[str, Any]]:
    values = os.environ if env is None else env
    stored = load_local_config(path).get("tools", {})
    settings = {name: dict(stored.get(name, {})) for name in TOOL_NAMES}
    overlays: dict[str, dict[str, Any]] = {
        "weather": {"location": values.get("NEXUS_WEATHER_LOCATION")},
        "calendar": {"calendar_url": values.get("NEXUS_CALENDAR_URL")},
        "todo": {"token": values.get("NEXUS_TODOIST_TOKEN")},
        "github": {
            "token": values.get("NEXUS_GITHUB_TOKEN"),
            "repo": values.get("NEXUS_GITHUB_REPO"),
        },
        "notion": {"token": values.get("NEXUS_NOTION_TOKEN")},
        "email": {
            "host": values.get("NEXUS_IMAP_HOST"),
            "port": values.get("NEXUS_IMAP_PORT"),
            "username": values.get("NEXUS_IMAP_USERNAME"),
            "password": values.get("NEXUS_IMAP_PASSWORD"),
            "mailbox": values.get("NEXUS_IMAP_MAILBOX"),
        },
        "filesystem": {
            "roots": (
                values["NEXUS_FILESYSTEM_ROOTS"].split(os.pathsep)
                if values.get("NEXUS_FILESYSTEM_ROOTS")
                else None
            ),
        },
    }
    for name, tool_values in overlays.items():
        configured_by_env = False
        for key, value in tool_values.items():
            if value is not None:
                settings[name][key] = int(value) if key == "port" else value
                configured_by_env = True
        if configured_by_env:
            settings[name]["enabled"] = True
        settings[name].setdefault("enabled", False)
        settings[name].setdefault("allowed_operations", TOOL_ALLOWED_OPERATIONS[name])
    return settings


def update_tool_settings(
    tool: str,
    values: dict[str, Any] | None = None,
    *,
    enabled: bool = True,
    path: Path | None = None,
) -> tuple[dict[str, dict[str, Any]], Path]:
    if tool not in TOOL_NAMES:
        raise ValueError(f"Unknown tool '{tool}'.")
    config = load_local_config(path)
    tools = config.setdefault("tools", {})
    current = dict(tools.get(tool, {}))
    current.update({key: value for key, value in (values or {}).items() if value is not None})
    current["enabled"] = enabled
    current["allowed_operations"] = TOOL_ALLOWED_OPERATIONS[tool]
    required_fields = {
        "weather": ["location"],
        "calendar": ["calendar_url"],
        "todo": ["token"],
        "github": ["repo"],
        "notion": ["token"],
        "email": ["host", "username", "password"],
        "filesystem": ["roots"],
    }[tool]
    missing = [field for field in required_fields if not current.get(field)]
    if enabled and missing:
        raise ValueError(f"Tool '{tool}' is missing required configuration: {', '.join(missing)}.")
    tools[tool] = current
    saved_path = save_local_config(config, path)
    return load_tool_settings(env={}, path=saved_path), saved_path


def masked_tool_settings(settings: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    masked: dict[str, dict[str, Any]] = {}
    for name, config in settings.items():
        public = dict(config)
        for key in TOOL_SECRET_FIELDS:
            if public.get(key):
                public[key] = "***configured***" if key == "calendar_url" else mask_secret(str(public[key]))
        masked[name] = public
    return masked
