# Phase 8 Multi-Agent Coordination Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Build five bounded specialist agents and an orchestrator that power opt-in planning, review, and briefing workflows with inspectable privacy-safe traces.

**Architecture:** A new `nexus.agents` package owns typed run state, budgets, specialists, orchestration, and trace persistence. Existing service methods remain the stable local domain layer, while CLI `--agents` routes workflows through the orchestrator and preserves deterministic fallback.

**Tech Stack:** Python 3.11+, dataclasses, argparse, JSON/JSONL, existing RAG/LLM/MCP layers, pytest.

## Global Constraints

- Preserve default non-agent command behavior.
- Agent mode must work without an LLM or MCP server.
- Only MCP tools with explicit `allow` policy may be selected autonomously.
- Enforce limits of 8 agent steps, 3 LLM calls, 3 MCP calls, and 60 seconds.
- Never persist prompts, memory text, raw tool payloads, secret values, or tool argument values in agent traces.
- Keep `.nexus/agent_runs.jsonl` ignored by Git.

---

### Task 1: Agent Models, Budgets, And Trace Store

**Files:**
- Create: `src/nexus/agents/__init__.py`
- Create: `src/nexus/agents/models.py`
- Create: `src/nexus/agents/trace.py`
- Test: `tests/test_agents_core.py`

**Interfaces:**
- Produces: `AgentBudget`, `AgentRunContext`, `AgentResult`, `AgentStepTrace`, `AgentRunTrace`, and `AgentTraceStore`.

- [x] Write failing tests for budget consumption/exhaustion, result serialization, JSONL persistence, missing/corrupt files, and recursive secret/value redaction.
- [x] Run `python -m pytest -q tests/test_agents_core.py` and verify failures are caused by missing agent APIs.
- [x] Implement typed models, budget counters/deadline checks, public serialization, and best-effort JSONL trace persistence.
- [x] Run focused tests and confirm they pass.

### Task 2: Memory, Planner, Reflection, And Coach Agents

**Files:**
- Create: `src/nexus/agents/specialists.py`
- Modify: `src/nexus/service.py`
- Test: `tests/test_agent_specialists.py`

**Interfaces:**
- Produces: `MemoryAgent.run(context)`, `PlannerAgent.run(context)`, `ReflectionAgent.run(context)`, and `CoachAgent.run(context)`.
- Consumes: existing memory retriever, planning rules, review context, coach profiles, and optional `BriefingLLM`.

- [x] Add failing tests for relevant-memory artifacts, persistent plan tasks, structured reflection, four coach modes, optional LLM use, malformed model output, and local fallback.
- [x] Run focused tests and verify the specialist classes are missing.
- [x] Expose focused service context helpers without changing default responses.
- [x] Implement specialists with one typed result per run and budgeted optional LLM calls.
- [x] Run focused tests and confirm they pass.

### Task 3: Permission-Bounded Tool Agent

**Files:**
- Create: `src/nexus/agents/tool_agent.py`
- Modify: `src/nexus/mcp/manager.py`
- Test: `tests/test_agent_tool.py`

**Interfaces:**
- Produces: `ToolAgent.run(context)` and `MCPManager.agent_candidates()`.
- Consumes: discovered MCP schemas, tool policies, configured planning bindings, optional LLM, and shared budget.

- [x] Add failing tests for allow-only candidates, deterministic bindings, strict model JSON selection, schema validation, invented-tool rejection, call caps, partial failures, and trace-safe argument metadata.
- [x] Run focused tests and verify expected missing behavior.
- [x] Add public allow-policy candidate discovery to MCPManager.
- [x] Implement deterministic and optional model-assisted selection, validation, calls, and normalized artifacts.
- [x] Run focused tests and confirm they pass.

### Task 4: Orchestrator And Workflow Integration

**Files:**
- Create: `src/nexus/agents/orchestrator.py`
- Modify: `src/nexus/service.py`
- Test: `tests/test_agent_orchestrator.py`

**Interfaces:**
- Produces: `AgentOrchestrator.run_plan()`, `run_review()`, and `run_briefing()`.
- Consumes: all specialist agents, shared budget/context, `NexusService`, optional MCP manager, and trace store.

- [x] Add failing tests for workflow order, artifact sharing, error isolation, budget exhaustion, trace completion, daily-task persistence, and offline fallback.
- [x] Run focused tests and verify orchestrator APIs are missing.
- [x] Implement bounded step execution, sanitized traces, final response assembly, and workflow-specific fallback.
- [x] Run focused tests and confirm they pass.

### Task 5: CLI Agent Mode And Trace Inspection

**Files:**
- Modify: `src/nexus/cli.py`
- Test: `tests/test_agent_cli.py`

**Interfaces:**
- Produces: `--agents` on plan/review/briefing and `nexus agent runs/show`.
- Consumes: `AgentOrchestrator` and `AgentTraceStore`.

- [x] Add failing CLI tests for all agent workflows, offline behavior, run listing, run lookup, unknown run IDs, and compatibility without `--agents`.
- [x] Run focused tests and verify parsing/dispatch failures.
- [x] Add CLI options, orchestrator construction, structured output, and trace commands.
- [x] Run focused tests and confirm they pass.

### Task 6: Documentation, Tracking, And Release Verification

**Files:**
- Modify: `.gitignore`
- Modify: `README.md`
- Modify: `README_zh.md`
- Modify: `docs/architecture.md`
- Modify: `docs/roadmap.md`
- Modify: `docs/aios_task_checklist.md`
- Modify: `docs/file_inventory.md`

**Interfaces:**
- Produces: accurate bilingual Phase 8 usage, architecture, limitations, file ownership, and completion status.

- [x] Document agent workflows, safety, budgets, tracing, commands, examples, and limitations in both README files.
- [x] Update architecture diagrams, roadmap, checklist, inventory, and ignore rules.
- [x] Run focused agent tests, the complete test suite, Ruff, compile/AST compatibility checks, real MCP smoke tests, CLI help smoke checks, `git diff --check`, and secret scans.
- [x] Review every design requirement against implementation and mark only verified checklist items complete.
