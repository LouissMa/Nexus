from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

from nexus.mcp.client import MCPGateway


ROOT = Path(__file__).resolve().parents[1]


def available_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def wait_for_server(port: int, process: subprocess.Popen[bytes]) -> None:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise AssertionError(
                "MCP HTTP fixture exited before accepting connections."
            )
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.1)
    raise AssertionError("MCP HTTP fixture did not start within 10 seconds.")


def test_real_streamable_http_server_discovery_and_call() -> None:
    pytest.importorskip("mcp")
    port = available_port()
    env = os.environ.copy()
    env["NEXUS_MCP_TEST_PORT"] = str(port)
    process = subprocess.Popen(
        [sys.executable, str(ROOT / "tests" / "fixtures" / "mcp_http_server.py")],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        wait_for_server(port, process)
        server = {
            "enabled": True,
            "transport": "streamable_http",
            "url": f"http://127.0.0.1:{port}/mcp",
            "headers": {},
            "timeout_seconds": 15,
        }
        gateway = MCPGateway()
        tools = gateway.list_tools(server)
        result = gateway.call_tool(server, "add", {"left": 4, "right": 7})

        assert [tool.name for tool in tools] == ["add"]
        assert result.structured_data == {"sum": 11}
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
