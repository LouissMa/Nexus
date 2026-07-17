from __future__ import annotations

import json
from pathlib import Path

import pytest

from nexus.mcp.audit import MCPAuditLogger
from nexus.mcp.config import (
    disable_mcp_server,
    load_mcp_settings,
    masked_mcp_settings,
    remove_mcp_server,
    set_mcp_planning_tool,
    set_mcp_tool_policy,
    upsert_mcp_server,
)
from nexus.mcp.manager import MCPManager
from nexus.mcp.models import (
    MCPCallResult,
    MCPPermissionError,
    MCPToolError,
    MCPToolSchema,
    MCPTransportError,
)


def stdio_server(**overrides: object) -> dict[str, object]:
    server: dict[str, object] = {
        "enabled": True,
        "transport": "stdio",
        "command": "python",
        "args": ["server.py"],
        "env": {"PRIVATE_TOKEN": "stdio-secret"},
        "timeout_seconds": 10,
        "max_retries": 1,
        "tool_policies": {},
        "planning_tools": [],
    }
    server.update(overrides)
    return server


def test_mcp_configuration_lifecycle_and_masking(tmp_path: Path) -> None:
    path = tmp_path / "config.local.json"
    settings, saved_path = upsert_mcp_server(
        "research",
        stdio_server(),
        path=path,
    )

    assert saved_path == path
    assert settings["research"]["command"] == "python"
    assert load_mcp_settings(path=path) == settings

    settings, _ = set_mcp_tool_policy("research", "search", "allow", path=path)
    settings, _ = set_mcp_planning_tool(
        "research", "search", {"query": "today's papers"}, path=path
    )
    assert settings["research"]["tool_policies"]["search"] == "allow"
    assert settings["research"]["planning_tools"] == [
        {"tool": "search", "arguments": {"query": "today's papers"}}
    ]

    masked = masked_mcp_settings(settings)
    assert masked["research"]["env"] == {"PRIVATE_TOKEN": "***"}
    assert "stdio-secret" not in json.dumps(masked)

    disabled, _ = disable_mcp_server("research", path=path)
    assert disabled["research"]["enabled"] is False
    removed, _ = remove_mcp_server("research", path=path)
    assert removed == {}


@pytest.mark.parametrize(
    ("server", "message"),
    [
        ({"transport": "stdio", "args": []}, "command"),
        ({"transport": "streamable_http"}, "url"),
        ({"transport": "sse", "url": "https://example.test"}, "transport"),
        (stdio_server(timeout_seconds=0), "timeout_seconds"),
        (stdio_server(max_retries=5), "max_retries"),
    ],
)
def test_invalid_mcp_configuration_is_rejected(
    tmp_path: Path, server: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        upsert_mcp_server("broken", server, path=tmp_path / "config.json")


def test_streamable_http_configuration_masks_url_and_headers(tmp_path: Path) -> None:
    settings, _ = upsert_mcp_server(
        "remote",
        {
            "enabled": True,
            "transport": "streamable_http",
            "url": "https://secret.example/mcp?token=secret",
            "headers": {"Authorization": "Bearer hidden"},
        },
        path=tmp_path / "config.json",
    )
    masked = masked_mcp_settings(settings)
    assert masked["remote"]["url"] == "***configured***"
    assert masked["remote"]["headers"] == {"Authorization": "***"}
    assert "hidden" not in json.dumps(masked)


class FakeGateway:
    def __init__(self, failures: list[Exception] | None = None):
        self.failures = list(failures or [])
        self.calls = 0

    def list_tools(self, server: dict[str, object]) -> list[MCPToolSchema]:
        return [
            MCPToolSchema(
                name="search",
                title="Research Search",
                description="Search papers",
                input_schema={"type": "object", "properties": {"query": {"type": "string"}}},
            )
        ]

    def call_tool(
        self, server: dict[str, object], tool: str, arguments: dict[str, object]
    ) -> MCPCallResult:
        self.calls += 1
        if self.failures:
            raise self.failures.pop(0)
        return MCPCallResult(
            tool=tool,
            text=[f"result for {arguments.get('query', '')}"],
            structured_data={"count": 2},
            content_metadata=[],
            is_error=False,
        )


def build_manager(
    tmp_path: Path,
    server: dict[str, object],
    gateway: FakeGateway | None = None,
) -> MCPManager:
    return MCPManager(
        {"research": server},
        gateway or FakeGateway(),
        MCPAuditLogger(tmp_path / "mcp_audit.jsonl"),
    )


def test_mcp_permissions_discovery_and_audit(tmp_path: Path) -> None:
    manager = build_manager(tmp_path, stdio_server())
    tools = manager.discover("research")
    assert tools[0].name == "search"

    with pytest.raises(MCPPermissionError, match="approval"):
        manager.call("research", "search", {"query": "Nexus"})
    result = manager.call("research", "search", {"query": "Nexus"}, approved=True)
    assert result.structured_data == {"count": 2}
    assert result.attempt_count == 1

    events = manager.audit_events()
    assert [event["status"] for event in events] == ["success", "denied", "success"]
    assert events[-1]["arguments"] == {"query": "Nexus"}


def test_deny_allow_retry_and_non_retryable_tool_errors(tmp_path: Path) -> None:
    denied = build_manager(
        tmp_path / "denied", stdio_server(tool_policies={"search": "deny"})
    )
    with pytest.raises(MCPPermissionError, match="denied"):
        denied.call("research", "search", {})

    gateway = FakeGateway([MCPTransportError("temporary connection failure")])
    allowed = build_manager(
        tmp_path / "allowed",
        stdio_server(tool_policies={"search": "allow"}, max_retries=1),
        gateway,
    )
    result = allowed.call("research", "search", {"query": "AI"})
    assert gateway.calls == 2
    assert result.attempt_count == 2

    tool_gateway = FakeGateway([MCPToolError("server tool failed")])
    tool_error = build_manager(
        tmp_path / "tool-error",
        stdio_server(tool_policies={"search": "allow"}, max_retries=2),
        tool_gateway,
    )
    with pytest.raises(MCPToolError):
        tool_error.call("research", "search", {})
    assert tool_gateway.calls == 1


def test_planning_context_uses_only_explicit_allow_bindings(tmp_path: Path) -> None:
    server = stdio_server(
        tool_policies={"search": "allow", "draft": "ask"},
        planning_tools=[
            {"tool": "search", "arguments": {"query": "Nexus"}},
            {"tool": "draft", "arguments": {}},
        ],
    )
    manager = build_manager(tmp_path, server)
    context = manager.planning_context()

    assert context["results"][0]["tool"] == "search"
    assert context["results"][0]["structured_data"] == {"count": 2}
    assert context["errors"] == [
        {"server": "research", "tool": "draft", "error": "Planning tool policy must be 'allow'."}
    ]


def test_mcp_audit_redacts_sensitive_arguments_and_errors(tmp_path: Path) -> None:
    logger = MCPAuditLogger(tmp_path / "audit.jsonl")
    logger.record(
        action="call",
        server="remote",
        tool="search",
        status="error",
        arguments={"token": "secret-token", "nested": {"password": "hidden"}},
        error="request failed for https://secret.example/mcp?token=secret-token",
        duration_ms=12,
        attempt_count=1,
    )
    encoded = json.dumps(logger.recent())
    assert "secret-token" not in encoded
    assert "hidden" not in encoded
    assert "secret.example" not in encoded

