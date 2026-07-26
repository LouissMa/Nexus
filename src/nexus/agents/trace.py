from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .models import AgentRunTrace

_SENSITIVE_KEYS = {
    "api_key",
    "authorization",
    "content",
    "env",
    "error",
    "headers",
    "memory",
    "memory_text",
    "password",
    "prompt",
    "query",
    "raw",
    "raw_content",
    "secret",
    "token",
}
_URL_PATTERN = re.compile(r"https?://[^\s\"']+", re.IGNORECASE)
_BEARER_PATTERN = re.compile(r"Bearer\s+\S+", re.IGNORECASE)
_KEY_PATTERN = re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b")


def sanitize_trace_data(value: Any, key: str | None = None) -> Any:
    normalized_key = (key or "").lower()
    if value is not None and (
        normalized_key in _SENSITIVE_KEYS
        or any(
            marker in normalized_key
            for marker in ("password", "secret", "token", "api_key", "prompt")
        )
    ):
        return "[redacted]"
    if normalized_key == "arguments" and isinstance(value, dict):
        if set(value) == {"argument_keys"} and isinstance(value["argument_keys"], list):
            return value
        return {"argument_keys": sorted(str(item) for item in value)}
    if isinstance(value, dict):
        return {
            str(item_key): sanitize_trace_data(item_value, str(item_key))
            for item_key, item_value in value.items()
        }
    if isinstance(value, list):
        return [sanitize_trace_data(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize_trace_data(item) for item in value]
    if isinstance(value, str):
        redacted = _URL_PATTERN.sub("[redacted-url]", value)
        redacted = _BEARER_PATTERN.sub("Bearer [redacted]", redacted)
        return _KEY_PATTERN.sub("[redacted-key]", redacted)
    return value


class AgentTraceStore:
    def __init__(self, path: Path):
        self.path = path

    def append(self, trace: AgentRunTrace) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            record = sanitize_trace_data(trace.to_dict())
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception:
            return

    def recent(self, limit: int = 50) -> list[dict[str, Any]]:
        if limit <= 0 or not self.path.exists():
            return []
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except Exception:
            return []
        records: list[dict[str, Any]] = []
        for line in lines:
            try:
                record = json.loads(line)
            except (json.JSONDecodeError, TypeError):
                continue
            if isinstance(record, dict):
                records.append(sanitize_trace_data(record))
        return records[-limit:]

    def find(self, run_id: str) -> dict[str, Any] | None:
        for record in reversed(self.recent(limit=10_000)):
            if record.get("run_id") == run_id:
                return record
        return None
