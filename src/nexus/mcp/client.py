from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack
from typing import Any, AsyncIterator, Callable

from .models import MCPCallResult, MCPToolError, MCPToolSchema, MCPTransportError


class MCPGateway:
    def __init__(self, session_factory: Callable[[dict[str, Any]], Any] | None = None):
        self.session_factory = session_factory

    def list_tools(self, server: dict[str, Any]) -> list[MCPToolSchema]:
        return asyncio.run(self._with_timeout(self._list_tools(server), server))

    def call_tool(
        self, server: dict[str, Any], tool: str, arguments: dict[str, Any]
    ) -> MCPCallResult:
        return asyncio.run(self._with_timeout(self._call_tool(server, tool, arguments), server))

    async def _with_timeout(self, operation: Any, server: dict[str, Any]) -> Any:
        try:
            return await asyncio.wait_for(operation, timeout=server.get("timeout_seconds", 30))
        except MCPToolError:
            raise
        except TimeoutError as exc:
            raise MCPTransportError("MCP operation timed out.") from exc
        except MCPTransportError:
            raise
        except Exception as exc:
            raise MCPTransportError(f"MCP transport failed: {exc}") from exc

    async def _list_tools(self, server: dict[str, Any]) -> list[MCPToolSchema]:
        async with self._session(server) as session:
            response = await session.list_tools()
            return [
                MCPToolSchema(
                    name=tool.name,
                    title=getattr(tool, "title", None),
                    description=getattr(tool, "description", None),
                    input_schema=dict(getattr(tool, "inputSchema", {}) or {}),
                )
                for tool in response.tools
            ]

    async def _call_tool(
        self, server: dict[str, Any], tool: str, arguments: dict[str, Any]
    ) -> MCPCallResult:
        async with self._session(server) as session:
            response = await session.call_tool(tool, arguments)
            text: list[str] = []
            content_metadata: list[dict[str, Any]] = []
            for content in response.content:
                if getattr(content, "type", None) == "text":
                    text.append(content.text)
                else:
                    dump = getattr(content, "model_dump", None)
                    item = dump(mode="json") if dump else {"type": getattr(content, "type", "unknown")}
                    content_metadata.append(item)
            result = MCPCallResult(
                tool=tool,
                text=text,
                structured_data=getattr(response, "structuredContent", None),
                content_metadata=content_metadata,
                is_error=bool(getattr(response, "isError", False)),
            )
            if result.is_error:
                detail = "\n".join(result.text) or "MCP server reported a tool error."
                raise MCPToolError(detail)
            return result

    def _session(self, server: dict[str, Any]) -> Any:
        if self.session_factory is not None:
            return self.session_factory(server)
        return self._sdk_session(server)

    async def _sdk_session(self, server: dict[str, Any]) -> AsyncIterator[Any]:
        try:
            import httpx
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
            from mcp.client.streamable_http import streamable_http_client
        except ImportError as exc:
            raise MCPTransportError(
                "MCP support is not installed. Install the project with `pip install -e .[mcp]`."
            ) from exc

        async with AsyncExitStack() as stack:
            if server["transport"] == "stdio":
                params = StdioServerParameters(
                    command=server["command"],
                    args=server.get("args", []),
                    env=server.get("env") or None,
                )
                read, write = await stack.enter_async_context(stdio_client(params))
            else:
                http_client = await stack.enter_async_context(
                    httpx.AsyncClient(
                        headers=server.get("headers", {}),
                        timeout=server.get("timeout_seconds", 30),
                        follow_redirects=True,
                    )
                )
                read, write, _ = await stack.enter_async_context(
                    streamable_http_client(server["url"], http_client=http_client)
                )
            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            yield session
