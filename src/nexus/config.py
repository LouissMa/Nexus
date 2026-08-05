from __future__ import annotations

import json
import os
import threading
import uuid
from collections.abc import Callable, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, TypeVar

from .runtime_config import (
    ProfileSettings,
    RuntimeSettings,
    profile_settings_from_mapping,
    runtime_settings_from_mapping,
)


MutationResult = TypeVar("MutationResult")

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


_CONFIG_PATH_LOCKS: dict[str, threading.RLock] = {}
_CONFIG_PATH_LOCKS_GUARD = threading.Lock()


def _canonical_config_path(path: Path) -> Path:
    try:
        return path.expanduser().resolve(strict=False)
    except OSError:
        return path.expanduser().absolute()


def _shared_config_lock(path: Path) -> threading.RLock:
    key = os.path.normcase(str(_canonical_config_path(path)))
    with _CONFIG_PATH_LOCKS_GUARD:
        return _CONFIG_PATH_LOCKS.setdefault(key, threading.RLock())


def _acquire_os_lock(handle: Any) -> None:
    handle.seek(0)
    if os.name == "nt":
        import msvcrt

        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
            os.fsync(handle.fileno())
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        return

    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_EX)


def _release_os_lock(handle: Any) -> None:
    handle.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        return

    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def _local_config_transaction(path: Path):
    canonical = _canonical_config_path(path)
    canonical.parent.mkdir(parents=True, exist_ok=True)
    lock_path = canonical.with_name(f".{canonical.name}.lock")
    with _shared_config_lock(canonical):
        with lock_path.open("a+b") as handle:
            _acquire_os_lock(handle)
            try:
                yield canonical
            finally:
                _release_os_lock(handle)


def _read_local_config_unlocked(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            loaded = json.load(handle)
    except FileNotFoundError:
        return {}
    if not isinstance(loaded, dict):
        raise ValueError("Local configuration must be a JSON object.")
    return loaded


def _atomic_write_local_config_unlocked(path: Path, config: dict[str, Any]) -> None:
    payload = (json.dumps(config, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as handle:
            if os.name != "nt":
                os.chmod(temporary, 0o600)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        if os.name != "nt":
            directory_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    finally:
        temporary.unlink(missing_ok=True)


def mutate_local_config(
    mutation: Callable[[dict[str, Any]], MutationResult],
    path: Path | None = None,
) -> tuple[MutationResult, Path]:
    requested_path = Path(path or local_config_path())
    with _local_config_transaction(requested_path) as config_path:
        config = _read_local_config_unlocked(config_path)
        result = mutation(config)
        _atomic_write_local_config_unlocked(config_path, config)
    return result, requested_path


def load_local_config(path: Path | None = None) -> dict[str, Any]:
    config_path = _canonical_config_path(Path(path or local_config_path()))
    return _read_local_config_unlocked(config_path)


def save_local_config(config: dict[str, Any], path: Path | None = None) -> Path:
    requested_path = Path(path or local_config_path())
    with _local_config_transaction(requested_path) as config_path:
        _atomic_write_local_config_unlocked(config_path, config)
    return requested_path


def load_llm_settings(
    env: dict[str, str] | None = None, path: Path | None = None
) -> LLMSettings:
    values = os.environ if env is None else env
    config = load_local_config(path)
    llm = config.get("llm", {})
    provider = values.get("NEXUS_LLM_PROVIDER") or llm.get("provider") or "openai"
    preset = PROVIDER_PRESETS.get(provider, PROVIDER_PRESETS["custom"])
    timeout_value = (
        values.get("NEXUS_LLM_TIMEOUT_SECONDS") or llm.get("timeout_seconds") or 30
    )
    api_key = (
        values.get("NEXUS_LLM_API_KEY")
        or values.get("OPENAI_API_KEY")
        or llm.get("api_key")
    )

    return LLMSettings(
        provider=provider,
        api_key=api_key,
        base_url=(
            values.get("NEXUS_LLM_BASE_URL")
            or llm.get("base_url")
            or preset["base_url"]
        ).rstrip("/"),
        simple_model=values.get("NEXUS_LLM_SIMPLE_MODEL")
        or llm.get("simple_model")
        or preset["simple_model"],
        complex_model=values.get("NEXUS_LLM_COMPLEX_MODEL")
        or llm.get("complex_model")
        or preset["complex_model"],
        default_tier=values.get("NEXUS_LLM_DEFAULT_TIER")
        or llm.get("default_tier")
        or "simple",
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
    def mutation(config: dict[str, Any]) -> LLMSettings:
        selected_provider = provider if provider in PROVIDER_PRESETS else "custom"
        preset = PROVIDER_PRESETS[selected_provider]
        settings = LLMSettings(
            provider=selected_provider,
            api_key=api_key,
            base_url=(base_url or preset["base_url"]).rstrip("/"),
            simple_model=simple_model or preset["simple_model"],
            complex_model=complex_model or preset["complex_model"],
            default_tier=default_tier,
            timeout_seconds=timeout_seconds,
        )
        config["llm"] = asdict(settings)
        return settings

    return mutate_local_config(mutation, path)


def load_embedding_settings(
    env: dict[str, str] | None = None,
    path: Path | None = None,
) -> EmbeddingSettings:
    values = os.environ if env is None else env
    config = load_local_config(path)
    embedding = config.get("embedding", {})
    provider = (
        values.get("NEXUS_EMBEDDING_PROVIDER")
        or embedding.get("provider")
        or "local_sparse"
    )
    preset = EMBEDDING_PRESETS.get(provider, EMBEDDING_PRESETS["custom"])
    base_url = (
        values.get("NEXUS_EMBEDDING_BASE_URL")
        or embedding.get("base_url")
        or preset["base_url"]
    )
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
        model=values.get("NEXUS_EMBEDDING_MODEL")
        or embedding.get("model")
        or preset["model"],
        api_key=api_key,
        base_url=base_url.rstrip("/") if base_url else None,
        qdrant_url=values.get("NEXUS_QDRANT_URL") or embedding.get("qdrant_url"),
        qdrant_api_key=values.get("NEXUS_QDRANT_API_KEY")
        or embedding.get("qdrant_api_key"),
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
    def mutation(config: dict[str, Any]) -> EmbeddingSettings:
        selected_provider = provider if provider in EMBEDDING_PRESETS else "custom"
        preset = EMBEDDING_PRESETS[selected_provider]
        selected_base_url = base_url or preset["base_url"]
        settings = EmbeddingSettings(
            provider=selected_provider,
            model=model or preset["model"],
            api_key=api_key,
            base_url=selected_base_url.rstrip("/") if selected_base_url else None,
            qdrant_url=qdrant_url,
            qdrant_api_key=qdrant_api_key,
            collection_name=collection_name,
            timeout_seconds=timeout_seconds,
        )
        config["embedding"] = asdict(settings)
        return settings

    return mutate_local_config(mutation, path)


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
    def mutation(config: dict[str, Any]) -> None:
        if tool not in TOOL_NAMES:
            raise ValueError(f"Unknown tool '{tool}'.")
        tools = config.setdefault("tools", {})
        if not isinstance(tools, dict):
            raise ValueError("Tool configuration must be an object.")
        current = dict(tools.get(tool, {}))
        current.update(
            {key: value for key, value in (values or {}).items() if value is not None}
        )
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
            raise ValueError(
                f"Tool '{tool}' is missing required configuration: {', '.join(missing)}."
            )
        tools[tool] = current

    _result, saved_path = mutate_local_config(mutation, path)
    return load_tool_settings(env={}, path=saved_path), saved_path


def masked_tool_settings(
    settings: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    masked: dict[str, dict[str, Any]] = {}
    for name, config in settings.items():
        public = dict(config)
        for key in TOOL_SECRET_FIELDS:
            if public.get(key):
                public[key] = (
                    "***configured***"
                    if key == "calendar_url"
                    else mask_secret(str(public[key]))
                )
        masked[name] = public
    return masked


def load_runtime_settings(
    path: Path | None = None,
) -> tuple[ProfileSettings, RuntimeSettings]:
    config = load_local_config(path)
    profile = profile_settings_from_mapping(dict(config.get("profile", {})))
    runtime = runtime_settings_from_mapping(dict(config.get("runtime", {})))
    return profile, runtime


def update_profile_settings(
    display_name: str = "User",
    timezone: str | None = None,
    path: Path | None = None,
) -> tuple[ProfileSettings, Path]:
    def mutation(config: dict[str, Any]) -> ProfileSettings:
        values: dict[str, Any] = {"display_name": display_name}
        if timezone is not None:
            values["timezone"] = timezone
        settings = profile_settings_from_mapping(values)
        config["profile"] = asdict(settings)
        return settings

    return mutate_local_config(mutation, path)


def patch_profile_settings(
    changes: Mapping[str, Any],
    path: Path | None = None,
) -> tuple[ProfileSettings, Path]:
    allowed = {"display_name", "timezone"}
    supplied = dict(changes)
    unknown = set(supplied).difference(allowed)
    if unknown:
        raise ValueError(f"Unknown profile setting: {sorted(unknown)[0]}.")

    def mutation(config: dict[str, Any]) -> ProfileSettings:
        current = config.get("profile", {})
        if not isinstance(current, dict):
            raise ValueError("Profile configuration must be an object.")
        merged = dict(current)
        merged.update(supplied)
        settings = profile_settings_from_mapping(merged)
        config["profile"] = asdict(settings)
        return settings

    return mutate_local_config(mutation, path)


def update_runtime_settings(
    enabled_jobs: Sequence[str] = (),
    morning_time: str = "08:00",
    evening_time: str = "20:00",
    reminder_time: str = "12:00",
    grace_minutes: int = 30,
    poll_interval_seconds: int = 60,
    quiet_hours_start: str | None = None,
    quiet_hours_end: str | None = None,
    inbox_enabled: bool = True,
    console_enabled: bool = False,
    webhook_url: str | None = None,
    path: Path | None = None,
    *,
    use_llm: bool = False,
    live_tools: bool = False,
    agents: bool = False,
    coach_mode: str = "gentle",
) -> tuple[RuntimeSettings, Path]:
    def mutation(config: dict[str, Any]) -> RuntimeSettings:
        settings = RuntimeSettings(
            enabled_jobs=enabled_jobs,
            morning_time=morning_time,
            evening_time=evening_time,
            reminder_time=reminder_time,
            grace_minutes=grace_minutes,
            poll_interval_seconds=poll_interval_seconds,
            quiet_hours_start=quiet_hours_start,
            quiet_hours_end=quiet_hours_end,
            inbox_enabled=inbox_enabled,
            console_enabled=console_enabled,
            webhook_url=webhook_url,
            use_llm=use_llm,
            live_tools=live_tools,
            agents=agents,
            coach_mode=coach_mode,
        )
        config["runtime"] = asdict(settings)
        return settings

    return mutate_local_config(mutation, path)


def patch_runtime_settings(
    changes: Mapping[str, Any],
    path: Path | None = None,
) -> tuple[RuntimeSettings, Path]:
    allowed = set(RuntimeSettings.__dataclass_fields__)
    supplied = dict(changes)
    unknown = set(supplied).difference(allowed)
    if unknown:
        raise ValueError(f"Unknown runtime setting: {sorted(unknown)[0]}.")

    def mutation(config: dict[str, Any]) -> RuntimeSettings:
        current = config.get("runtime", {})
        if not isinstance(current, dict):
            raise ValueError("Runtime configuration must be an object.")
        merged = dict(current)
        merged.update(supplied)
        settings = runtime_settings_from_mapping(merged)
        config["runtime"] = asdict(settings)
        return settings

    return mutate_local_config(mutation, path)
