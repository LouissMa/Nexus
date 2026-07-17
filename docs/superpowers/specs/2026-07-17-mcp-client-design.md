# Phase 7 MCP Client Design

## Goal

Make Nexus a standards-based, permissioned MCP client that can configure external servers, discover their tools, call approved tools, normalize results, audit activity, and inject approved MCP context into daily planning.

Nexus does not expose its own capabilities as an MCP server in this phase. Autonomous LLM tool selection and the Tool Agent belong to Phase 8.

## Protocol And Dependency

- Use the official Python MCP SDK stable v1 line: `mcp>=1.27,<2`.
- Support the MCP `stdio` and Streamable HTTP transports.
- Complete the MCP initialize lifecycle before tool discovery or calls.
- Keep MCP optional through the `mcp` dependency extra so the existing offline CLI remains usable.

## Configuration

MCP server definitions live under `mcp.servers` in ignored `.nexus/config.local.json`.

Each server has:

- `enabled`: whether Nexus may connect.
- `transport`: `stdio` or `streamable_http`.
- `command` and `args`: executable configuration for stdio.
- `url` and `headers`: endpoint configuration for Streamable HTTP.
- `env`: explicit child-process environment additions for stdio.
- `timeout_seconds`: connection and call timeout.
- `max_retries`: retries for connection or transport failures.
- `tool_policies`: per-tool `deny`, `ask`, or `allow` decisions.
- `planning_tools`: approved tool names and static JSON arguments that may enrich daily planning.

Secrets in environment variables, headers, URLs, and token-like fields are masked in CLI output and omitted from audit records.

## Components

### MCP Models And Configuration

`src/nexus/mcp/config.py` validates server names, transports, required fields, timeouts, retry limits, policies, and planning bindings. It reads and updates the existing local configuration without disturbing LLM, embedding, or Phase 6 tool settings.

### MCP SDK Gateway

`src/nexus/mcp/client.py` owns official SDK imports and lifecycle handling. It opens stdio or Streamable HTTP sessions, initializes them, lists tools, and calls one tool. SDK absence produces a clear optional-dependency error.

An injected session factory makes protocol behavior testable without network access or child processes. The production gateway uses one session per operation so cleanup is deterministic.

### Registry And Permissions

`src/nexus/mcp/manager.py` coordinates configuration, discovery, calls, retries, permissions, normalization, and audit logging.

- Disabled or unknown servers are rejected.
- `deny` always rejects.
- `ask` requires a one-shot explicit approval from the caller.
- `allow` may run without an approval flag.
- Unconfigured tools default to `ask`.
- Planning only executes tools explicitly listed in `planning_tools` and whose policy is `allow`.

### Result Normalization

Tool discovery returns server name, tool name, title, description, and input JSON Schema.

Tool calls return a stable Nexus object containing server, tool, structured data, text blocks, non-text content metadata, error state, attempt count, and execution timestamp. MCP `isError` results are surfaced as tool errors and are not retried. Only connection, timeout, and transport failures are eligible for bounded retry.

### Audit

MCP events append to `.nexus/mcp_audit.jsonl`, ignored by Git. Events record discovery/call action, server, tool, status, duration, attempt count, and sanitized arguments or error. Raw content, credentials, headers, environment values, and URLs are not logged.

## CLI

Configuration commands:

- `nexus config mcp add <name> --transport stdio --command ... [--arg ...]`
- `nexus config mcp add <name> --transport streamable_http --url ... [--header KEY=VALUE]`
- `nexus config mcp disable <name>`
- `nexus config mcp remove <name>`
- `nexus config mcp policy <name> <tool> <deny|ask|allow>`
- `nexus config mcp planning-tool <name> <tool> --arguments JSON`
- `nexus config mcp show`

Runtime commands:

- `nexus mcp servers`
- `nexus mcp tools <server>`
- `nexus mcp call <server> <tool> --arguments JSON [--approve]`
- `nexus mcp audit [--limit N]`

Planning adds `nexus plan day --live-mcp`. It calls only configured `allow` planning bindings, preserves successful partial results, records failures, and injects the resulting context into local and optional LLM plan output. Planning still succeeds when MCP is absent or a server fails.

## Error Handling And Safety

- Reject malformed JSON arguments before connecting.
- Reject unsupported transports and invalid configuration before saving.
- Use timeouts around connection, discovery, and calls.
- Do not use shell execution for stdio commands; pass command and argument arrays directly to the SDK.
- Do not inherit configured secrets into audit output.
- Do not retry MCP-declared tool errors because a tool may have side effects.
- Keep all mutating capability behind explicit per-tool policy.

## Testing

- Configuration validation, masked output, policy persistence, and removal.
- Discovery and result normalization through fake sessions.
- `deny`, `ask`, `allow`, and planning-only permission behavior.
- Retry only for eligible transport failures.
- Audit redaction and success/failure records.
- CLI configuration, discovery, call approval, and invalid JSON behavior.
- Planning context injection and partial-failure fallback.
- Optional real stdio integration test using an in-repository minimal MCP server when the SDK is installed.
- Full existing regression suite.

## Documentation And Completion

Update English and Chinese README files, architecture, roadmap, AIOS checklist, file inventory, `.gitignore`, and optional dependencies. Phase 7 is complete when all checklist items are marked complete, tests pass, and no secret or local audit artifact is tracked.
