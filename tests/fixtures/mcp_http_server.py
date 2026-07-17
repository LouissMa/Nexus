from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP


server = FastMCP(
    "Nexus Phase 7 HTTP Test Server",
    host="127.0.0.1",
    port=int(os.environ["NEXUS_MCP_TEST_PORT"]),
    json_response=True,
)


@server.tool()
def add(left: int, right: int) -> dict[str, int]:
    """Add two integers for Nexus MCP integration tests."""
    return {"sum": left + right}


if __name__ == "__main__":
    server.run(transport="streamable-http")
