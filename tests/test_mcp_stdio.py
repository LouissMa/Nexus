from __future__ import annotations

import sys
from pathlib import Path

import pytest

from nexus.mcp.client import MCPGateway


ROOT = Path(__file__).resolve().parents[1]


def test_real_stdio_server_discovery_and_call() -> None:
    pytest.importorskip("mcp")
    server = {
        "enabled": True,
        "transport": "stdio",
        "command": sys.executable,
        "args": [str(ROOT / "tests" / "fixtures" / "mcp_echo_server.py")],
        "env": {"NEXUS_MCP_TEST_VALUE": "configured"},
        "timeout_seconds": 15,
    }
    gateway = MCPGateway()

    tools = gateway.list_tools(server)
    result = gateway.call_tool(server, "echo", {"message": "hello Nexus"})

    assert [tool.name for tool in tools] == ["echo"]
    assert result.is_error is False
    assert result.structured_data == {
        "message": "hello Nexus",
        "configured_env": "configured",
        "safe_path_present": True,
    }
