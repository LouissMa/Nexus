from __future__ import annotations

import json
import time
from copy import deepcopy
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from jsonschema import FormatChecker, ValidationError, validate

from .config import nexus_home
from .mcp.audit import MCPAuditLogger
from .mcp.models import MCPPermissionError, MCPToolError


MAX_ARGUMENT_BYTES = 8_192
MAX_RESULT_ITEMS = 50
MAX_RESULT_TEXT = 4_000
MAX_RESULT_BYTES = 65_536
POLICIES = {"deny", "ask", "allow"}


def _object_schema(
    properties: dict[str, Any], required: tuple[str, ...] = ()
) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(required),
        "additionalProperties": False,
    }


TOOL_CATALOG = (
    {
        "name": "nexus_today",
        "description": "Read today's Nexus tasks and life context.",
        "inputSchema": _object_schema(
            {"date": {"type": "string", "format": "date", "maxLength": 10}}
        ),
        "permission": "allow",
    },
    {
        "name": "nexus_search_memory",
        "description": "Search relevant private long-term memories with Nexus RAG.",
        "inputSchema": _object_schema(
            {
                "query": {"type": "string", "minLength": 1, "maxLength": 1_000},
                "limit": {"type": "integer", "minimum": 1, "maximum": 10, "default": 5},
                "task_context": {"type": "string", "maxLength": 1_000},
            },
            ("query",),
        ),
        "permission": "allow",
    },
    {
        "name": "nexus_list_goals",
        "description": "List the user's tracked goals.",
        "inputSchema": _object_schema({}),
        "permission": "allow",
    },
    {
        "name": "nexus_list_habits",
        "description": "List active habits and current streak summaries.",
        "inputSchema": _object_schema({}),
        "permission": "allow",
    },
    {
        "name": "nexus_list_projects",
        "description": "List active projects, milestones, and progress.",
        "inputSchema": _object_schema({}),
        "permission": "allow",
    },
    {
        "name": "nexus_get_suggestions",
        "description": "List active explainable Nexus suggestions.",
        "inputSchema": _object_schema({}),
        "permission": "allow",
    },
    {
        "name": "nexus_preview_replan",
        "description": "Preview a calendar-aware daily schedule without changing state.",
        "inputSchema": _object_schema(
            {
                "date": {"type": "string", "format": "date", "maxLength": 10},
                "events": {
                    "type": "array",
                    "maxItems": 100,
                    "items": {
                        "type": "object",
                        "properties": {
                            "summary": {"type": "string", "maxLength": 500},
                            "start": {"type": "string", "maxLength": 64},
                            "end": {"type": "string", "maxLength": 64},
                            "all_day": {"type": "boolean"},
                        },
                        "required": ["start", "end"],
                        "additionalProperties": False,
                    },
                },
                "working_start": {
                    "type": "string",
                    "pattern": "^[0-2][0-9]:[0-5][0-9]$",
                },
                "working_end": {"type": "string", "pattern": "^[0-2][0-9]:[0-5][0-9]$"},
            },
            ("date",),
        ),
        "permission": "allow",
    },
    {
        "name": "nexus_add_memory",
        "description": "Add a private long-term memory after explicit session approval.",
        "inputSchema": _object_schema(
            {
                "text": {"type": "string", "minLength": 1, "maxLength": 4_000},
                "tags": {
                    "type": "array",
                    "maxItems": 20,
                    "items": {"type": "string", "maxLength": 100},
                },
                "importance": {"type": "number", "minimum": 0, "maximum": 1},
                "privacy": {"type": "string", "enum": ["private", "shared"]},
                "expires_at": {"type": "string", "maxLength": 64},
                "pinned": {"type": "boolean"},
            },
            ("text",),
        ),
        "permission": "ask",
    },
    {
        "name": "nexus_add_goal",
        "description": "Add a tracked goal after explicit session approval.",
        "inputSchema": _object_schema(
            {
                "title": {"type": "string", "minLength": 1, "maxLength": 1_000},
                "description": {"type": "string", "maxLength": 1_000},
                "cadence_days": {"type": "integer", "minimum": 1, "maximum": 365},
            },
            ("title",),
        ),
        "permission": "ask",
    },
    {
        "name": "nexus_check_in_habit",
        "description": "Record a habit check-in after explicit session approval.",
        "inputSchema": _object_schema(
            {
                "habit_id": {"type": "string", "minLength": 1, "maxLength": 100},
                "date": {"type": "string", "format": "date", "maxLength": 10},
                "count": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 100,
                    "default": 1,
                },
                "note": {"type": "string", "maxLength": 1_000},
            },
            ("habit_id",),
        ),
        "permission": "ask",
    },
    {
        "name": "nexus_update_project_progress",
        "description": "Update project progress after explicit session approval.",
        "inputSchema": _object_schema(
            {
                "project_id": {"type": "string", "minLength": 1, "maxLength": 100},
                "percent": {"type": "integer", "minimum": 0, "maximum": 100},
                "note": {"type": "string", "maxLength": 1_000},
                "correction": {"type": "boolean", "default": False},
            },
            ("project_id", "percent"),
        ),
        "permission": "ask",
    },
    {
        "name": "nexus_apply_replan",
        "description": "Apply a verified replan preview after explicit session approval.",
        "inputSchema": _object_schema(
            {
                "preview": {"type": "object", "maxProperties": 20},
                "events": {"type": "array", "maxItems": 100},
            },
            ("preview",),
        ),
        "permission": "ask",
    },
)

NEXUS_MCP_TOOL_NAMES = tuple(item["name"] for item in TOOL_CATALOG)
_TOOL_BY_NAME = {item["name"]: item for item in TOOL_CATALOG}


def _bounded(value: Any, depth: int = 0) -> Any:
    if depth >= 8:
        return "[truncated]"
    if isinstance(value, Mapping):
        return {
            str(key)[:200]: _bounded(item, depth + 1)
            for key, item in list(value.items())[:MAX_RESULT_ITEMS]
        }
    if isinstance(value, (list, tuple)):
        return [_bounded(item, depth + 1) for item in value[:MAX_RESULT_ITEMS]]
    if isinstance(value, str):
        return value[:MAX_RESULT_TEXT]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)[:MAX_RESULT_TEXT]


class NexusMCPTools:
    """Static, bounded, permission-aware adapter over Nexus domain services."""

    def __init__(
        self,
        service: Any,
        *,
        policies: Mapping[str, str] | None = None,
        approvals: Sequence[str] = (),
        timezone: str = "UTC",
        audit_path: Path | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.service = service
        try:
            self.timezone = ZoneInfo(timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("timezone must be an IANA timezone name.") from exc
        self.clock = clock or (lambda: datetime.now(UTC))
        self.approvals = frozenset(approvals)
        self.policies = dict(policies or {})
        unknown = set(self.policies) - set(NEXUS_MCP_TOOL_NAMES)
        invalid = {value for value in self.policies.values() if value not in POLICIES}
        if unknown or invalid:
            raise ValueError("Invalid Nexus MCP tool policy configuration.")
        self.audit = MCPAuditLogger(
            audit_path or nexus_home() / "mcp_server_audit.jsonl"
        )

    def list_tools(self) -> list[dict[str, Any]]:
        result = deepcopy(list(TOOL_CATALOG))
        for item in result:
            item["permission"] = self.policies.get(item["name"], item["permission"])
        return result

    def call(
        self,
        name: str,
        arguments: dict[str, Any],
        session_approvals: Sequence[str] = (),
    ) -> dict[str, Any]:
        started = time.monotonic()
        try:
            spec = _TOOL_BY_NAME.get(name)
            if spec is None:
                raise MCPToolError(f"Unknown Nexus MCP tool '{name}'.")
            if not isinstance(arguments, dict):
                raise MCPToolError("Tool arguments must be a JSON object.")
            encoded = json.dumps(arguments, ensure_ascii=False).encode("utf-8")
            if len(encoded) > MAX_ARGUMENT_BYTES:
                raise MCPToolError("Tool arguments exceed the size limit.")
            try:
                validate(
                    instance=arguments,
                    schema=spec["inputSchema"],
                    format_checker=FormatChecker(),
                )
            except ValidationError as exc:
                field = ".".join(str(item) for item in exc.absolute_path)
                detail = field or "arguments"
                raise MCPToolError(
                    f"Invalid tool arguments: {detail} {exc.message}"
                ) from exc
            self._authorize(name, spec["permission"], session_approvals)
            result = _bounded(self._execute(name, arguments))
            if (
                len(json.dumps(result, ensure_ascii=False).encode("utf-8"))
                > MAX_RESULT_BYTES
            ):
                result = {
                    "truncated": True,
                    "reason": "Result exceeded the Nexus MCP response size limit.",
                }
        except Exception as exc:
            self._audit(name, arguments, "error", type(exc).__name__, started)
            raise
        self._audit(name, arguments, "success", None, started)
        return result

    def _authorize(
        self, name: str, default: str, session_approvals: Sequence[str]
    ) -> None:
        policy = self.policies.get(name, default)
        if policy == "deny":
            raise MCPPermissionError(f"Tool '{name}' is denied by policy.")
        approved = set(session_approvals).union(self.approvals)
        if policy == "ask" and name not in approved:
            raise MCPPermissionError(
                f"Tool '{name}' requires explicit session approval."
            )

    def _execute(self, name: str, arguments: dict[str, Any]) -> Any:
        if name == "nexus_today":
            plan_date = (
                arguments.get("date")
                or self.clock().astimezone(self.timezone).date().isoformat()
            )
            return {
                "date": plan_date,
                "tasks": self.service.list_daily_tasks(plan_date),
                "goals": self.service.list_goals(),
                "habits": self.service.list_habits(
                    timezone=str(self.timezone), now=self.clock()
                ),
                "suggestions": self.service.list_suggestions(
                    timezone=str(self.timezone), now=self.clock()
                ),
            }
        if name == "nexus_search_memory":
            return {
                "items": self.service.retrieve_memories(
                    arguments["query"],
                    arguments.get("limit", 5),
                    task_context=arguments.get("task_context"),
                    now=self.clock(),
                )
            }
        if name == "nexus_list_goals":
            return {"items": self.service.list_goals()}
        if name == "nexus_list_habits":
            return {
                "items": self.service.list_habits(
                    timezone=str(self.timezone), now=self.clock()
                )
            }
        if name == "nexus_list_projects":
            return {"items": self.service.list_projects()}
        if name == "nexus_get_suggestions":
            return {
                "items": self.service.list_suggestions(
                    timezone=str(self.timezone), now=self.clock()
                )
            }
        if name == "nexus_preview_replan":
            return self.service.preview_replan(
                arguments["date"],
                arguments.get("events", []),
                (
                    arguments.get("working_start", "09:00"),
                    arguments.get("working_end", "18:00"),
                ),
                timezone=str(self.timezone),
                now=self.clock(),
            )
        if name == "nexus_add_memory":
            return asdict(
                self.service.add_memory(
                    arguments["text"],
                    arguments.get("tags", []),
                    importance=arguments.get("importance"),
                    privacy=arguments.get("privacy", "private"),
                    expires_at=arguments.get("expires_at"),
                    pinned=arguments.get("pinned", False),
                    now=self.clock(),
                )
            )
        if name == "nexus_add_goal":
            return asdict(
                self.service.add_goal(
                    arguments["title"],
                    arguments.get("description", ""),
                    arguments.get("cadence_days", 3),
                )
            )
        if name == "nexus_check_in_habit":
            return self.service.check_in_habit(
                arguments["habit_id"],
                arguments.get(
                    "date", self.clock().astimezone(self.timezone).date().isoformat()
                ),
                arguments.get("count", 1),
                arguments.get("note", "MCP check-in"),
                timezone=str(self.timezone),
                now=self.clock(),
            )
        if name == "nexus_update_project_progress":
            return self.service.update_project_progress(
                arguments["project_id"],
                arguments["percent"],
                arguments.get("note", "MCP update"),
                arguments.get("correction", False),
                now=self.clock(),
            )
        return self.service.apply_replan(
            arguments["preview"],
            arguments.get("events", []),
            timezone=str(self.timezone),
            now=self.clock(),
        )

    def _audit(
        self,
        name: str,
        arguments: Any,
        status: str,
        error: str | None,
        started: float,
    ) -> None:
        if isinstance(arguments, dict):
            safe_arguments = {
                "count": len(arguments),
                "bytes": len(json.dumps(arguments, ensure_ascii=False).encode("utf-8")),
            }
        else:
            safe_arguments = {"type": type(arguments).__name__}
        self.audit.record(
            action="call",
            server="nexus",
            tool=name,
            status=status,
            arguments=safe_arguments,
            error=error,
            duration_ms=round((time.monotonic() - started) * 1_000),
        )


def run_stdio_server(tools: NexusMCPTools) -> None:
    """Run Nexus as a local stdio MCP server using the official SDK."""
    try:
        import anyio
        from mcp import types
        from mcp.server.lowlevel import Server
        from mcp.server.stdio import stdio_server
    except ImportError as exc:  # pragma: no cover - depends on optional install
        raise RuntimeError(
            "Install Nexus with the 'mcp' extra to run the MCP server."
        ) from exc

    server = Server("nexus-lifeagent", version="0.1.0")

    @server.list_tools()
    async def list_tools() -> list[Any]:
        return [
            types.Tool(
                name=item["name"],
                description=item["description"],
                inputSchema=item["inputSchema"],
            )
            for item in tools.list_tools()
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return tools.call(name, arguments)

    async def serve() -> None:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options(),
            )

    anyio.run(serve)
