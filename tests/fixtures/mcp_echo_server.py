from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP


server = FastMCP("Nexus Phase 7 Test Server")


@server.tool()
def echo(message: str) -> dict[str, object]:
    """Return one message for Nexus MCP integration tests."""
    return {
        "message": message,
        "configured_env": os.environ.get("NEXUS_MCP_TEST_VALUE"),
        "safe_path_present": bool(os.environ.get("PATH")),
    }


if __name__ == "__main__":
    server.run(transport="stdio")
