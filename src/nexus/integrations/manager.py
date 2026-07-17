from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from .core import AuditLogger, JsonHttpClient, PermissionPolicy, ToolAdapter, ToolError, ToolResult
from .personal_tools import CalendarTool, EmailTool, FilesystemTool
from .web_tools import GitHubTool, NotionTool, TodoistTool, WeatherTool


class ToolManager:
    def __init__(
        self,
        settings: dict[str, dict[str, Any]],
        adapters: dict[str, ToolAdapter],
        audit_logger: AuditLogger,
    ):
        self.settings = settings
        self.adapters = adapters
        self.policy = PermissionPolicy(settings)
        self.audit_logger = audit_logger

    def execute(self, tool: str, operation: str = "read", **arguments: Any) -> ToolResult:
        try:
            self.policy.require(tool, operation)
            adapter = self.adapters.get(tool)
            if adapter is None:
                raise ToolError(f"Tool '{tool}' is not registered.")
            data = adapter.execute(operation, arguments)
            self.audit_logger.record(
                tool=tool,
                operation=operation,
                arguments=arguments,
                status="success",
            )
            return ToolResult(
                tool=tool,
                operation=operation,
                data=data,
                executed_at=datetime.now(UTC).replace(microsecond=0).isoformat(),
            )
        except ToolError as exc:
            self.audit_logger.record(
                tool=tool,
                operation=operation,
                arguments=arguments,
                status="error",
                error_message=str(exc),
            )
            raise
        except Exception as exc:
            message = f"Tool '{tool}' failed unexpectedly: {exc}"
            self.audit_logger.record(
                tool=tool,
                operation=operation,
                arguments=arguments,
                status="error",
                error_message=message,
            )
            raise ToolError(message) from exc

    def briefing_context(self, now: datetime | None = None) -> dict[str, Any]:
        now = now or datetime.now(UTC)
        context: dict[str, Any] = {"weather": None, "calendar": [], "todos": [], "errors": []}
        requests = [
            ("weather", "read", {}),
            ("calendar", "read", {"days": 2, "now": now.isoformat()}),
            ("todo", "read", {"limit": 20}),
        ]
        for tool, operation, arguments in requests:
            if not self.settings.get(tool, {}).get("enabled", False):
                continue
            try:
                result = self.execute(tool, operation, **arguments).data
                if tool == "weather":
                    context["weather"] = result
                elif tool == "calendar":
                    context["calendar"] = result.get("events", [])
                elif tool == "todo":
                    context["todos"] = result.get("tasks", [])
            except ToolError as exc:
                context["errors"].append({"tool": tool, "error": str(exc)})
        return context

    def audit_events(self, limit: int = 50) -> list[dict[str, Any]]:
        return self.audit_logger.recent(limit)


def build_tool_manager(
    settings: dict[str, dict[str, Any]],
    home: Path,
    *,
    http_client: JsonHttpClient | None = None,
    imap_factory: Callable[..., Any] | None = None,
) -> ToolManager:
    http = http_client or JsonHttpClient()
    adapters: dict[str, ToolAdapter] = {
        "weather": WeatherTool(settings.get("weather", {}), http),
        "calendar": CalendarTool(settings.get("calendar", {}), http),
        "todo": TodoistTool(settings.get("todo", {}), http),
        "github": GitHubTool(settings.get("github", {}), http),
        "notion": NotionTool(settings.get("notion", {}), http),
        "email": EmailTool(settings.get("email", {}), imap_factory=imap_factory),
        "filesystem": FilesystemTool(settings.get("filesystem", {})),
    }
    return ToolManager(settings, adapters, AuditLogger(home / "tool_audit.jsonl"))
