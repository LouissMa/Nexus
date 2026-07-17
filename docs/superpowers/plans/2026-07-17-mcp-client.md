# Phase 7 MCP Client Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a complete permissioned MCP client phase for Nexus, including configuration, discovery, calls, audit, CLI, and planning integration.

**Architecture:** A focused `nexus.mcp` package wraps the official MCP SDK behind an injectable gateway. An MCP manager applies configuration, policy, retries, normalization, and audit before exposing stable results to CLI and planning.

**Tech Stack:** Python 3.11+, official `mcp>=1.27,<2`, argparse, asyncio, JSONL audit, pytest.

## Global Constraints

- Nexus is an MCP client only in Phase 7.
- Support `stdio` and Streamable HTTP.
- Keep MCP optional and preserve all offline behavior.
- Policies are `deny`, `ask`, and `allow`; unknown tools default to `ask`.
- Planning may execute only explicitly configured `allow` bindings.
- Never log or display raw credentials, headers, environment secrets, or URLs.
- Never retry an MCP-declared tool error.

---

### Task 1: MCP Configuration Model

**Files:**
- Create: `src/nexus/mcp/__init__.py`
- Create: `src/nexus/mcp/config.py`
- Modify: `src/nexus/config.py`
- Test: `tests/test_mcp.py`

**Interfaces:**
- Produces: `load_mcp_settings()`, `upsert_mcp_server()`, `disable_mcp_server()`, `remove_mcp_server()`, `set_mcp_tool_policy()`, `set_mcp_planning_tool()`, and `masked_mcp_settings()`.

- [ ] Write tests for valid stdio/HTTP definitions, missing required fields, policy and planning binding persistence, removal, and masking.
- [ ] Run `python -m pytest -q tests/test_mcp.py` and verify failures are caused by missing MCP configuration APIs.
- [ ] Implement immutable validation and local-config updates while preserving unrelated config sections.
- [ ] Run the focused tests and confirm they pass.

### Task 2: SDK Gateway And Normalization

**Files:**
- Create: `src/nexus/mcp/client.py`
- Create: `src/nexus/mcp/models.py`
- Test: `tests/test_mcp.py`

**Interfaces:**
- Produces: `MCPGateway.list_tools(server)`, `MCPGateway.call_tool(server, tool, arguments)`, `MCPToolSchema`, and `MCPCallResult`.
- Consumes: validated server dictionaries from Task 1.

- [ ] Add failing fake-session tests for initialize/list/call, schema fields, text and structured content, `isError`, and missing SDK behavior.
- [ ] Run focused tests and verify expected failures.
- [ ] Implement async SDK sessions for stdio and Streamable HTTP plus synchronous public wrappers.
- [ ] Normalize SDK objects without exposing SDK-specific types to callers.
- [ ] Run focused tests and confirm they pass.

### Task 3: Permissioned Manager, Retry, And Audit

**Files:**
- Create: `src/nexus/mcp/manager.py`
- Create: `src/nexus/mcp/audit.py`
- Test: `tests/test_mcp.py`

**Interfaces:**
- Produces: `MCPManager.servers()`, `discover()`, `call()`, `planning_context()`, and `audit_events()`.
- Consumes: Task 1 configuration and Task 2 gateway.

- [ ] Add failing tests for disabled servers, default ask, explicit approval, deny, allow, planning allowlist, eligible retries, non-retried tool errors, partial failures, and redacted audit events.
- [ ] Run focused tests and verify policy/retry failures.
- [ ] Implement manager orchestration and `.nexus/mcp_audit.jsonl` logging.
- [ ] Run focused tests and confirm they pass.

### Task 4: CLI Surface

**Files:**
- Modify: `src/nexus/cli.py`
- Test: `tests/test_mcp_cli.py`

**Interfaces:**
- Consumes: Task 1 configuration APIs and Task 3 manager.
- Produces: `config mcp` and runtime `mcp` command families.

- [ ] Add failing CLI tests for add/show/disable/remove, policies, planning bindings, discovery, approved calls, rejected calls, malformed arguments, and audit output.
- [ ] Run `python -m pytest -q tests/test_mcp_cli.py` and verify expected command failures.
- [ ] Add argparse definitions and command dispatch with structured JSON errors and nonzero exits.
- [ ] Run focused CLI tests and confirm they pass.

### Task 5: Planning Integration

**Files:**
- Modify: `src/nexus/cli.py`
- Modify: `src/nexus/service.py`
- Test: `tests/test_mcp_planning.py`

**Interfaces:**
- Consumes: `MCPManager.planning_context()`.
- Produces: `NexusService.daily_plan(..., mcp_context=None)` and `nexus plan day --live-mcp`.

- [ ] Add failing tests showing successful MCP context in local/LLM prompts and graceful partial/total MCP failure.
- [ ] Run focused tests and verify missing context behavior.
- [ ] Add MCP context to planning output, rendering, and prompts while preserving default behavior.
- [ ] Run focused planning tests and confirm they pass.

### Task 6: Real SDK Smoke Fixture And Regression

**Files:**
- Create: `tests/fixtures/mcp_echo_server.py`
- Modify: `tests/test_mcp.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Produces: installable `mcp` optional extra and a deterministic stdio echo fixture.

- [ ] Add a conditional end-to-end stdio test against the fixture.
- [ ] Add `mcp>=1.27,<2` to the `mcp` optional dependency group.
- [ ] Run the MCP tests with the SDK installed when available.
- [ ] Run `python -m pytest -q tests` and `python -m compileall -q src tests`.

### Task 7: Documentation And Release Checks

**Files:**
- Modify: `.gitignore`
- Modify: `README.md`
- Modify: `README_zh.md`
- Modify: `docs/architecture.md`
- Modify: `docs/roadmap.md`
- Modify: `docs/aios_task_checklist.md`
- Modify: `docs/file_inventory.md`

**Interfaces:**
- Produces: accurate bilingual usage and completed Phase 7 tracking.

- [ ] Ignore `.nexus/mcp_audit.jsonl` and verify local secrets/audits are untracked.
- [ ] Document setup, permissions, commands, planning behavior, limitations, and files in both languages.
- [ ] Mark only implemented Phase 7 checklist and roadmap items complete.
- [ ] Run `git diff --check`, credential-fragment scans, full tests, and CLI help smoke checks.
