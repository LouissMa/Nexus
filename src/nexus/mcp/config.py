from __future__ import annotations

import re
from copy import deepcopy
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from ..config import load_local_config, save_local_config


MCP_TRANSPORTS = {"stdio", "streamable_http"}
MCP_POLICIES = {"deny", "ask", "allow"}
SERVER_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


def load_mcp_settings(path: Path | None = None) -> dict[str, dict[str, Any]]:
    stored = load_local_config(path).get("mcp", {}).get("servers", {})
    if not isinstance(stored, dict):
        raise ValueError("MCP server configuration must be an object.")
    return {name: _validate_server(name, server) for name, server in stored.items()}


def upsert_mcp_server(
    name: str,
    server: dict[str, Any],
    *,
    path: Path | None = None,
) -> tuple[dict[str, dict[str, Any]], Path]:
    validated = _validate_server(name, server)
    config = load_local_config(path)
    servers = config.setdefault("mcp", {}).setdefault("servers", {})
    servers[name] = validated
    saved_path = save_local_config(config, path)
    return load_mcp_settings(path=saved_path), saved_path


def disable_mcp_server(
    name: str, *, path: Path | None = None
) -> tuple[dict[str, dict[str, Any]], Path]:
    config = load_local_config(path)
    servers = config.setdefault("mcp", {}).setdefault("servers", {})
    if name not in servers:
        raise ValueError(f"Unknown MCP server '{name}'.")
    servers[name]["enabled"] = False
    saved_path = save_local_config(config, path)
    return load_mcp_settings(path=saved_path), saved_path


def remove_mcp_server(
    name: str, *, path: Path | None = None
) -> tuple[dict[str, dict[str, Any]], Path]:
    config = load_local_config(path)
    servers = config.setdefault("mcp", {}).setdefault("servers", {})
    if name not in servers:
        raise ValueError(f"Unknown MCP server '{name}'.")
    del servers[name]
    saved_path = save_local_config(config, path)
    return load_mcp_settings(path=saved_path), saved_path


def set_mcp_tool_policy(
    server_name: str,
    tool: str,
    policy: str,
    *,
    path: Path | None = None,
) -> tuple[dict[str, dict[str, Any]], Path]:
    if policy not in MCP_POLICIES:
        raise ValueError(f"Unknown MCP policy '{policy}'.")
    config, server = _editable_server(server_name, path)
    server.setdefault("tool_policies", {})[tool] = policy
    saved_path = save_local_config(config, path)
    return load_mcp_settings(path=saved_path), saved_path


def set_mcp_planning_tool(
    server_name: str,
    tool: str,
    arguments: dict[str, Any],
    *,
    path: Path | None = None,
) -> tuple[dict[str, dict[str, Any]], Path]:
    config, server = _editable_server(server_name, path)
    bindings = server.setdefault("planning_tools", [])
    binding = {"tool": tool, "arguments": deepcopy(arguments)}
    for index, current in enumerate(bindings):
        if current.get("tool") == tool:
            bindings[index] = binding
            break
    else:
        bindings.append(binding)
    saved_path = save_local_config(config, path)
    return load_mcp_settings(path=saved_path), saved_path


def masked_mcp_settings(
    settings: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    masked = deepcopy(settings)
    for server in masked.values():
        if server.get("url"):
            server["url"] = "***configured***"
        if server.get("headers"):
            server["headers"] = {key: "***" for key in server["headers"]}
        if server.get("env"):
            server["env"] = {key: "***" for key in server["env"]}
    return masked


def _editable_server(
    name: str, path: Path | None
) -> tuple[dict[str, Any], dict[str, Any]]:
    config = load_local_config(path)
    servers = config.setdefault("mcp", {}).setdefault("servers", {})
    if name not in servers:
        raise ValueError(f"Unknown MCP server '{name}'.")
    return config, servers[name]


def _validate_server(name: str, value: Any) -> dict[str, Any]:
    if not SERVER_NAME_PATTERN.fullmatch(name):
        raise ValueError("MCP server name must use letters, numbers, '.', '_', or '-'.")
    if not isinstance(value, dict):
        raise ValueError(f"MCP server '{name}' must be an object.")
    server = deepcopy(value)
    transport = server.get("transport")
    if transport not in MCP_TRANSPORTS:
        raise ValueError(f"MCP server '{name}' has unsupported transport '{transport}'.")
    if transport == "stdio" and not server.get("command"):
        raise ValueError(f"MCP stdio server '{name}' requires command.")
    if transport == "streamable_http":
        url = server.get("url")
        parsed = urlparse(str(url or ""))
        if not url or parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError(f"MCP Streamable HTTP server '{name}' requires a valid url.")

    timeout = server.get("timeout_seconds", 30)
    retries = server.get("max_retries", 1)
    if not isinstance(timeout, int) or timeout < 1 or timeout > 300:
        raise ValueError("timeout_seconds must be between 1 and 300.")
    if not isinstance(retries, int) or retries < 0 or retries > 3:
        raise ValueError("max_retries must be between 0 and 3.")

    args = server.get("args", [])
    env = server.get("env", {})
    headers = server.get("headers", {})
    policies = server.get("tool_policies", {})
    planning_tools = server.get("planning_tools", [])
    if not isinstance(args, list) or not all(isinstance(item, str) for item in args):
        raise ValueError("MCP stdio args must be a list of strings.")
    if not _string_mapping(env) or not _string_mapping(headers):
        raise ValueError("MCP env and headers must contain string keys and values.")
    if not isinstance(policies, dict) or any(
        not isinstance(tool, str) or policy not in MCP_POLICIES
        for tool, policy in policies.items()
    ):
        raise ValueError("MCP tool policies must map tool names to deny, ask, or allow.")
    if not isinstance(planning_tools, list):
        raise ValueError("MCP planning_tools must be a list.")
    for binding in planning_tools:
        if (
            not isinstance(binding, dict)
            or not isinstance(binding.get("tool"), str)
            or not isinstance(binding.get("arguments", {}), dict)
        ):
            raise ValueError("Each MCP planning tool requires a tool name and object arguments.")

    server.setdefault("enabled", True)
    server["args"] = args
    server["env"] = env
    server["headers"] = headers
    server["timeout_seconds"] = timeout
    server["max_retries"] = retries
    server["tool_policies"] = policies
    server["planning_tools"] = planning_tools
    return server


def _string_mapping(value: Any) -> bool:
    return isinstance(value, dict) and all(
        isinstance(key, str) and isinstance(item, str) for key, item in value.items()
    )
