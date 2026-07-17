from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Protocol
from urllib import error, parse, request


class ToolError(RuntimeError):
    pass


class ToolPermissionError(ToolError):
    pass


@dataclass(frozen=True)
class ToolResult:
    tool: str
    operation: str
    data: dict[str, Any]
    executed_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ToolAdapter(Protocol):
    name: str

    def execute(self, operation: str, arguments: dict[str, Any]) -> dict[str, Any]: ...


class JsonHttpClient:
    def __init__(
        self,
        timeout_seconds: int = 20,
        opener: Callable[..., Any] | None = None,
        max_response_bytes: int = 5_000_000,
    ):
        self.timeout_seconds = timeout_seconds
        self.opener = opener or request.urlopen
        self.max_response_bytes = max_response_bytes

    def request_json(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> Any:
        body = self.request_bytes(
            method,
            url,
            params=params,
            headers=headers,
            payload=payload,
        )
        try:
            return json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ToolError(f"Tool endpoint returned invalid JSON: {exc}") from exc

    def request_bytes(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> bytes:
        if params:
            query = parse.urlencode(
                {key: value for key, value in params.items() if value is not None}
            )
            separator = "&" if "?" in url else "?"
            url = f"{url}{separator}{query}"
        encoded = json.dumps(payload).encode("utf-8") if payload is not None else None
        request_headers = {"User-Agent": "Nexus-LifeAgent/0.1", **(headers or {})}
        if payload is not None:
            request_headers.setdefault("Content-Type", "application/json")
        http_request = request.Request(
            url, data=encoded, method=method, headers=request_headers
        )
        try:
            with self.opener(http_request, timeout=self.timeout_seconds) as response:
                body = response.read(self.max_response_bytes + 1)
                if len(body) > self.max_response_bytes:
                    raise ToolError(
                        f"Tool response exceeds {self.max_response_bytes} bytes."
                    )
                return body
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise ToolError(
                f"Tool endpoint returned HTTP {exc.code}: {detail}"
            ) from exc
        except (error.URLError, TimeoutError, OSError) as exc:
            raise ToolError(f"Tool request failed: {exc}") from exc


class PermissionPolicy:
    def __init__(self, settings: dict[str, dict[str, Any]]):
        self.settings = settings

    def require(self, tool: str, operation: str) -> None:
        config = self.settings.get(tool, {})
        if not config.get("enabled", False):
            raise ToolPermissionError(
                f"Tool '{tool}' is disabled. Configure it with `nexus config tool set {tool}`."
            )
        allowed = config.get("allowed_operations", ["read"])
        if operation not in allowed:
            raise ToolPermissionError(
                f"Operation '{operation}' is not permitted for tool '{tool}'."
            )


class AuditLogger:
    SECRET_KEYS = {"token", "password", "api_key", "calendar_url", "url"}

    def __init__(self, path: Path):
        self.path = path

    def record(
        self,
        *,
        tool: str,
        operation: str,
        arguments: dict[str, Any],
        status: str,
        error_message: str | None = None,
    ) -> None:
        event = {
            "at": datetime.now(UTC).replace(microsecond=0).isoformat(),
            "tool": tool,
            "operation": operation,
            "arguments": self._sanitize(arguments),
            "status": status,
            "error": error_message,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")

    def recent(self, limit: int = 50) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()
        events: list[dict[str, Any]] = []
        for line in lines[-max(1, limit) :]:
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return events

    def _sanitize(self, value: Any, key: str = "") -> Any:
        if key.lower() in self.SECRET_KEYS:
            return "***"
        if isinstance(value, dict):
            return {
                item_key: self._sanitize(item, item_key)
                for item_key, item in value.items()
            }
        if isinstance(value, list):
            return [self._sanitize(item) for item in value]
        return value
