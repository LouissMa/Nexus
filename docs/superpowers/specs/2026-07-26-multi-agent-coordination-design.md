# Phase 8 Multi-Agent Coordination Design

## Goal

Add a bounded multi-agent execution layer to Nexus without replacing its stable
local-first behavior. Memory, planning, tools, reflection, and coaching become
separate specialists coordinated through one user-facing workflow.

## Product Surface

Existing commands gain an opt-in `--agents` mode:

- `nexus plan day --agents`
- `nexus review day --agents`
- `nexus briefing --agents`

The default command behavior remains unchanged. Agent runs can be inspected
without exposing prompts, secrets, raw tool payloads, or private memory text:

- `nexus agent runs [--limit N]`
- `nexus agent show <run_id>`

Agent mode works without an LLM. `--llm` enables model-assisted specialist
output while deterministic local behavior remains the fallback.

## Architecture

`src/nexus/agents` is a focused package with typed run state and five
specialists:

- Memory Agent retrieves task-relevant RAG memories and returns public retrieval
  metadata.
- Planner Agent turns active goals and context into prioritized daily tasks.
- Tool Agent discovers eligible context tools, selects only explicitly allowed
  MCP tools, validates arguments, and invokes them through `MCPManager`.
- Reflection Agent evaluates task outcomes, blockers, unresolved items, and
  check-ins.
- Coach Agent converts structured artifacts into the selected strict, gentle,
  academic, or startup response style.

`AgentOrchestrator` owns sequencing, budgets, error isolation, final response
assembly, and trace persistence. Agents do not call one another and do not
persist run records directly.

## Shared State And Artifacts

Each run receives an `AgentRunContext` containing:

- run ID, workflow name, start time, user name, and coach mode;
- current goals, tasks, reminders, external context, and relevant configuration;
- a mutable artifact map containing only structured outputs from completed
  steps;
- an `AgentBudget` and current usage counters.

Each specialist returns an `AgentResult` with status, summary, structured
artifact, optional public metadata, and a recoverable error. Results are
serializable and contain no live clients or SDK objects.

The orchestrator supports three workflows:

```text
plan:
  Memory -> Tool -> Planner -> Coach

review:
  Memory -> Reflection -> Coach

briefing:
  Memory -> Tool -> Planner -> Coach
```

The briefing Planner produces priorities and suggestions rather than persistent
daily tasks unless the normal planning command is used.

## Budgets

Every run has explicit limits:

- maximum agent steps: 8;
- maximum LLM calls: 3;
- maximum MCP tool calls: 3;
- maximum wall-clock duration: 60 seconds.

The budget object rejects work before a limit is exceeded. A rejected or failed
step is recorded and the workflow continues when a deterministic fallback is
available. CLI defaults are fixed for Phase 8; public budget flags are deferred
until real usage data justifies them.

## LLM Use

The LLM remains optional and uses the existing OpenAI-compatible client.

- Planner, Reflection, and Coach may each consume one LLM call.
- Memory retrieval never requires an LLM.
- Tool selection may consume one LLM call only when tool schemas are available,
  but the total workflow still respects the three-call budget.
- Structured model outputs are parsed as strict JSON. Invalid output becomes a
  recoverable agent error and falls back to deterministic behavior.

The Tool Agent never treats model output as authorization.

## Tool Safety

The Tool Agent operates above the existing Phase 7 MCP layer:

- only enabled MCP servers are considered;
- only tools with `allow` policy are eligible for autonomous selection;
- `ask` and `deny` tools are never called by an unattended agent run;
- tool arguments are validated against the discovered JSON Schema before call;
- calls are capped by the shared tool budget;
- MCPManager remains the final permission and audit enforcement point;
- a tool failure is isolated and cannot prevent local planning or briefing.

Configured Phase 7 planning bindings remain deterministic candidates. LLM
selection can choose from discovered allow-policy tools, but cannot invent a
server, tool, or permission.

## Traceability And Privacy

Run summaries append to ignored `.nexus/agent_runs.jsonl`. A trace contains:

- run ID, workflow, timestamps, final status, and duration;
- ordered step names, statuses, durations, budget usage, and error category;
- selected server/tool names and argument field names;
- retrieval strategy and candidate counts.

It excludes API keys, configuration secrets, full prompts, raw memory text,
email content, filesystem contents, raw MCP payloads, and tool argument values.
Trace writes are best effort and cannot break the user workflow.

## Integration Strategy

`NexusService` remains the application facade and source of existing local
domain behavior. The orchestrator calls small service context/building methods
and returns the same top-level response fields plus:

```json
{
  "agents": {
    "used": true,
    "run_id": "...",
    "status": "completed",
    "steps": [],
    "budget": {}
  }
}
```

Default non-agent responses remain backward compatible. Agent mode persists
daily tasks through the same state model, so task list/update and daily review
continue to work.

## Error Handling

- An unavailable LLM produces deterministic specialist output.
- RAG failure falls back to recent memories through the existing retriever.
- MCP discovery/call failure is recorded and planning continues.
- Invalid LLM JSON is not executed and triggers local fallback.
- Budget exhaustion skips optional work and returns partial status.
- Unexpected agent exceptions are converted to sanitized recoverable errors;
  programming errors remain visible in tests.

## Testing

- Unit tests for budgets, typed results, trace redaction, and JSON parsing.
- Specialist tests for Memory, Planner, Tool, Reflection, and Coach behavior.
- Tool Agent tests proving only `allow` tools run and argument values are absent
  from agent traces.
- Orchestrator tests for order, shared artifacts, partial failure, offline
  fallback, and budget exhaustion.
- CLI tests for all three `--agents` workflows and `agent runs/show`.
- Regression tests proving default commands are unchanged.
- Full suite, Ruff, compile/AST checks, secret scans, and real MCP smoke tests.

## Completion

Phase 8 is complete when all five agents are implemented, orchestration and
budgets are enforced, traces are inspectable and secret-safe, the three
user-facing workflows support agent mode, bilingual documentation and project
tracking are current, and all verification checks pass.
