from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from typing import Any

from .audit import MCPAuditLogger
from .client import MCPGateway
from .models import (
    MCPCallResult,
    MCPConfigurationError,
    MCPError,
    MCPPermissionError,
    MCPToolSchema,
    MCPTransportError,
)


class MCPManager:
    def __init__(
        self,
        settings: dict[str, dict[str, Any]],
        gateway: MCPGateway,
        audit_logger: MCPAuditLogger,
    ):
        self.settings = settings
        self.gateway = gateway
        self.audit_logger = audit_logger

    def servers(self) -> list[dict[str, Any]]:
        return [
            {
                "name": name,
                "enabled": bool(server.get("enabled")),
                "transport": server.get("transport"),
                "tool_policy_count": len(server.get("tool_policies", {})),
                "planning_tool_count": len(server.get("planning_tools", [])),
            }
            for name, server in sorted(self.settings.items())
        ]

    def discover(self, server_name: str) -> list[MCPToolSchema]:
        server = self._enabled_server(server_name)
        started = monotonic()
        try:
            tools = self.gateway.list_tools(server)
            self._audit("discover", server_name, "success", duration=started)
            return tools
        except MCPError as exc:
            self._audit(
                "discover", server_name, "error", error=str(exc), duration=started
            )
            raise

    def call(
        self,
        server_name: str,
        tool: str,
        arguments: dict[str, Any],
        *,
        approved: bool = False,
    ) -> MCPCallResult:
        server = self._enabled_server(server_name)
        policy = server.get("tool_policies", {}).get(tool, "ask")
        if policy == "deny":
            message = f"MCP tool '{server_name}/{tool}' is denied by policy."
            self._audit("call", server_name, "denied", tool, arguments, message)
            raise MCPPermissionError(message)
        if policy == "ask" and not approved:
            message = f"MCP tool '{server_name}/{tool}' requires explicit approval. Use --approve."
            self._audit("call", server_name, "denied", tool, arguments, message)
            raise MCPPermissionError(message)

        started = monotonic()
        max_attempts = int(server.get("max_retries", 1)) + 1
        for attempt in range(1, max_attempts + 1):
            try:
                result = self.gateway.call_tool(server, tool, arguments)
                completed = replace(
                    result,
                    attempt_count=attempt,
                    executed_at=datetime.now(UTC).replace(microsecond=0).isoformat(),
                )
                self._audit(
                    "call",
                    server_name,
                    "success",
                    tool,
                    arguments,
                    duration=started,
                    attempt_count=attempt,
                )
                return completed
            except MCPTransportError as exc:
                if attempt < max_attempts:
                    continue
                self._audit(
                    "call",
                    server_name,
                    "error",
                    tool,
                    arguments,
                    str(exc),
                    started,
                    attempt,
                )
                raise
            except MCPError as exc:
                self._audit(
                    "call",
                    server_name,
                    "error",
                    tool,
                    arguments,
                    str(exc),
                    started,
                    attempt,
                )
                raise
        raise AssertionError("MCP retry loop ended unexpectedly.")

    def planning_context(self) -> dict[str, list[dict[str, Any]]]:
        context: dict[str, list[dict[str, Any]]] = {"results": [], "errors": []}
        for server_name, server in sorted(self.settings.items()):
            if not server.get("enabled", False):
                continue
            for binding in server.get("planning_tools", []):
                tool = binding["tool"]
                if server.get("tool_policies", {}).get(tool, "ask") != "allow":
                    context["errors"].append(
                        {
                            "server": server_name,
                            "tool": tool,
                            "error": "Planning tool policy must be 'allow'.",
                        }
                    )
                    continue
                try:
                    result = self.call(server_name, tool, binding.get("arguments", {}))
                    context["results"].append(
                        {
                            "server": server_name,
                            **result.to_dict(),
                        }
                    )
                except MCPError as exc:
                    context["errors"].append(
                        {
                            "server": server_name,
                            "tool": tool,
                            "error": str(exc),
                        }
                    )
        return context

    def audit_events(self, limit: int = 50) -> list[dict[str, Any]]:
        return self.audit_logger.recent(limit)

    def _enabled_server(self, name: str) -> dict[str, Any]:
        server = self.settings.get(name)
        if server is None:
            raise MCPConfigurationError(f"Unknown MCP server '{name}'.")
        if not server.get("enabled", False):
            raise MCPPermissionError(f"MCP server '{name}' is disabled.")
        return server

    def _audit(
        self,
        action: str,
        server: str,
        status: str,
        tool: str | None = None,
        arguments: dict[str, Any] | None = None,
        error: str | None = None,
        duration: float | None = None,
        attempt_count: int = 1,
    ) -> None:
        duration_ms = (
            int((monotonic() - duration) * 1000) if duration is not None else 0
        )
        self.audit_logger.record(
            action=action,
            server=server,
            tool=tool,
            status=status,
            arguments=arguments,
            error=error,
            duration_ms=duration_ms,
            attempt_count=attempt_count,
        )


def build_mcp_manager(
    settings: dict[str, dict[str, Any]],
    home: Path,
    *,
    gateway: MCPGateway | None = None,
) -> MCPManager:
    return MCPManager(
        settings,
        gateway or MCPGateway(),
        MCPAuditLogger(home / "mcp_audit.jsonl"),
    )
