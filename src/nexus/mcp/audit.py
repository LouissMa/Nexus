from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class MCPAuditLogger:
    SECRET_KEYS = {
        "token",
        "password",
        "api_key",
        "authorization",
        "secret",
        "headers",
        "env",
        "url",
    }
    URL_PATTERN = re.compile(r"https?://[^\s'\"]+", re.IGNORECASE)
    BEARER_PATTERN = re.compile(r"(Bearer\s+)[^\s,;]+", re.IGNORECASE)
    ASSIGNMENT_PATTERN = re.compile(
        r"((?:token|password|api[_-]?key|secret)=)[^&\s]+", re.IGNORECASE
    )

    def __init__(self, path: Path):
        self.path = path

    def record(
        self,
        *,
        action: str,
        server: str,
        status: str,
        tool: str | None = None,
        arguments: dict[str, Any] | None = None,
        error: str | None = None,
        duration_ms: int = 0,
        attempt_count: int = 1,
    ) -> None:
        event = {
            "at": datetime.now(UTC).replace(microsecond=0).isoformat(),
            "action": action,
            "server": server,
            "tool": tool,
            "status": status,
            "arguments": self._sanitize(arguments or {}),
            "error": self._sanitize_error(error),
            "duration_ms": max(0, duration_ms),
            "attempt_count": max(0, attempt_count),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")

    def recent(self, limit: int = 50) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        events: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines()[
            -max(1, limit) :
        ]:
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return events

    def _sanitize(self, value: Any, key: str = "") -> Any:
        lowered = key.lower()
        if lowered in self.SECRET_KEYS or any(
            part in lowered for part in ("token", "password", "secret", "key")
        ):
            return "***"
        if isinstance(value, dict):
            return {
                item_key: self._sanitize(item, item_key)
                for item_key, item in value.items()
            }
        if isinstance(value, list):
            return [self._sanitize(item) for item in value]
        if isinstance(value, str):
            return self.URL_PATTERN.sub("***", value)
        return value

    def _sanitize_error(self, error: str | None) -> str | None:
        if error is None:
            return None
        sanitized = self.URL_PATTERN.sub("***", error)
        sanitized = self.BEARER_PATTERN.sub(r"\1***", sanitized)
        return self.ASSIGNMENT_PATTERN.sub(r"\1***", sanitized)
