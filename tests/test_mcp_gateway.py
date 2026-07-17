from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from nexus.mcp.client import MCPGateway
from nexus.mcp.models import MCPToolError, MCPTransportError


class FakeSession:
    def __init__(self, is_error: bool = False):
        self.is_error = is_error

    async def list_tools(self) -> SimpleNamespace:
        return SimpleNamespace(
            tools=[
                SimpleNamespace(
                    name="search",
                    title="Search",
                    description="Search research",
                    inputSchema={"type": "object"},
                )
            ]
        )

    async def call_tool(
        self, tool: str, arguments: dict[str, object]
    ) -> SimpleNamespace:
        return SimpleNamespace(
            content=[
                SimpleNamespace(type="text", text=f"found {arguments['query']}"),
                SimpleNamespace(
                    type="image", model_dump=lambda **kwargs: {"type": "image"}
                ),
            ],
            structuredContent={"items": 1},
            isError=self.is_error,
        )


def session_factory(session: FakeSession):
    @asynccontextmanager
    async def factory(server: dict[str, object]):
        yield session

    return factory


def server() -> dict[str, object]:
    return {
        "enabled": True,
        "transport": "stdio",
        "command": "python",
        "args": ["server.py"],
        "timeout_seconds": 10,
    }


def test_gateway_normalizes_tool_schemas_and_results() -> None:
    gateway = MCPGateway(session_factory(FakeSession()))
    tools = gateway.list_tools(server())
    result = gateway.call_tool(server(), "search", {"query": "Nexus"})

    assert tools[0].to_dict() == {
        "name": "search",
        "title": "Search",
        "description": "Search research",
        "input_schema": {"type": "object"},
    }
    assert result.text == ["found Nexus"]
    assert result.structured_data == {"items": 1}
    assert result.content_metadata == [{"type": "image"}]


def test_gateway_surfaces_mcp_declared_tool_error() -> None:
    gateway = MCPGateway(session_factory(FakeSession(is_error=True)))
    with pytest.raises(MCPToolError, match="found Nexus"):
        gateway.call_tool(server(), "search", {"query": "Nexus"})


def failing_session_factory():
    @asynccontextmanager
    async def factory(server: dict[str, object]):
        raise RuntimeError(
            f"request failed for {server['url']} with {server['headers']['Authorization']}"
        )
        yield

    return factory


def test_gateway_redacts_transport_configuration_from_errors() -> None:
    gateway = MCPGateway(failing_session_factory())
    remote = {
        "enabled": True,
        "transport": "streamable_http",
        "url": "https://private.example/mcp?token=url-secret",
        "headers": {"Authorization": "Bearer header-secret"},
        "timeout_seconds": 10,
    }
    with pytest.raises(MCPTransportError) as raised:
        gateway.list_tools(remote)

    message = str(raised.value)
    assert "private.example" not in message
    assert "url-secret" not in message
    assert "header-secret" not in message
