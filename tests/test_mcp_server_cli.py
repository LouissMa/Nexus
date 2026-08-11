from __future__ import annotations

import os
import json
import subprocess
import sys
from pathlib import Path

import pytest

from nexus.mcp.client import MCPGateway
from nexus.service import NexusService
from nexus.store import JsonStore


def run_cli(*args: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "nexus.cli", *args],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_mcp_server_stdio_cli_is_registered_and_rejects_unknown_approval(
    tmp_path: Path,
) -> None:
    env = os.environ.copy()
    env["NEXUS_HOME"] = str(tmp_path / "nexus-home")
    help_result = run_cli("mcp-server", "stdio", "--help", env=env)
    assert help_result.returncode == 0
    assert "--approve-tool" in help_result.stdout

    invalid = run_cli(
        "mcp-server", "stdio", "--approve-tool", "not-a-nexus-tool", env=env
    )
    assert invalid.returncode == 2
    assert "Unknown Nexus MCP tool" in invalid.stderr


def test_real_nexus_stdio_server_lifecycle(tmp_path: Path) -> None:
    pytest.importorskip("mcp")
    home = tmp_path / "nexus-home"
    service = NexusService(JsonStore(home / "state.json"))
    service.add_goal("Expose Nexus", "MCP server lifecycle", 3)
    server = {
        "enabled": True,
        "transport": "stdio",
        "command": sys.executable,
        "args": ["-m", "nexus.cli", "mcp-server", "stdio"],
        "env": {"NEXUS_HOME": str(home)},
        "timeout_seconds": 15,
    }

    gateway = MCPGateway()
    tools = gateway.list_tools(server)
    result = gateway.call_tool(server, "nexus_list_goals", {})

    assert len(tools) == 12
    assert result.is_error is False
    assert result.structured_data["items"][0]["title"] == "Expose Nexus"


def test_mcp_server_cli_reports_invalid_persisted_policy_without_traceback(
    tmp_path: Path,
) -> None:
    home = tmp_path / "nexus-home"
    home.mkdir()
    (home / "config.local.json").write_text(
        json.dumps(
            {"nexus_mcp_server": {"tool_policies": {"not-a-nexus-tool": "allow"}}}
        ),
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["NEXUS_HOME"] = str(home)

    result = run_cli("mcp-server", "stdio", env=env)

    assert result.returncode == 2
    assert "Invalid Nexus MCP tool policy" in result.stderr
    assert "Traceback" not in result.stderr
