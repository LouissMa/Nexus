# Nexus MVP Architecture

The current version is a local-first CLI assistant with optional LLM generation, semantic RAG, permissioned real tools, a standards-based MCP client, and bounded multi-agent coordination. Core features remain usable offline. LLM calls occur only when the user passes `--llm`; agent coordination is opt-in through `--agents`.

## Current Architecture

```text
[User]
  |
  v
[Nexus CLI]
  |---------------- default ----------------> [NexusService]
  |
  +-- --agents --> [AgentOrchestrator]
                    |-- Memory Agent ----> [RAG / Qdrant]
                    |-- Tool Agent ------> [MCPManager / approved MCP tools]
                    |-- Planner Agent ---> [NexusService / JsonStore]
                    |-- Reflection Agent -> [NexusService / JsonStore]
                    |-- Coach Agent ------> [optional OpenAI-compatible LLM]
                    |
                    +--> [.nexus/agent_runs.jsonl]

[NexusService] --> [.nexus/state.json]
```

## Current Modules

- `src/nexus/cli.py`: CLI parsing for domain commands, MCP/tools/configuration, opt-in `--agents`, and agent trace inspection.
- `src/nexus/service.py`: Application orchestration for memory/RAG, goals, persistent daily planning, structured task updates, reflection, coach-aware prompts, and briefings.
- `src/nexus/embeddings.py`: FastEmbed and OpenAI-compatible neural embedding providers.
- `src/nexus/vector_store.py`: local/remote Qdrant persistence and collection operations.
- `src/nexus/rag.py`: sparse retrieval, semantic indexing, hybrid score fusion, metadata, re-indexing, and fallback.
- src/nexus/planning.py: daily-task decomposition rules, task status vocabulary, and Coach profiles.
- `src/nexus/llm.py`: OpenAI-compatible LLM client, environment-based configuration, HTTP request handling, and LLM errors.
- `src/nexus/store.py`: local JSON persistence.
- `src/nexus/integrations/core.py`: HTTP normalization, permission policy, tool results, and secret-safe audit logging.
- `src/nexus/integrations/web_tools.py`: Open-Meteo, Todoist, GitHub, and Notion adapters.
- `src/nexus/integrations/personal_tools.py`: recurring iCalendar, read-only IMAP, and bounded filesystem adapters.
- `src/nexus/integrations/manager.py`: tool registry, execution orchestration, auditing, and live briefing aggregation.
- `src/nexus/mcp/config.py`: MCP server validation, local configuration, tool policies, Planning bindings, and masking.
- `src/nexus/mcp/client.py`: official SDK lifecycle for stdio and Streamable HTTP, discovery, calls, and normalized results.
- `src/nexus/mcp/manager.py`: permission enforcement, bounded retries, audit orchestration, and partial-failure Planning aggregation.
- `src/nexus/mcp/audit.py`: secret-safe MCP JSONL audit trail.
- `src/nexus/agents/models.py`: shared run context, specialist results, budgets, step traces, and run traces.
- `src/nexus/agents/specialists.py`: Memory, Planner, Reflection, and Coach Agent implementations.
- `src/nexus/agents/tool_agent.py`: allow-only MCP candidate selection, strict JSON parsing, argument validation, calls, and partial failure handling.
- `src/nexus/agents/orchestrator.py`: plan, review, and briefing workflow sequencing, shared artifacts, fallback, and response assembly.
- `src/nexus/agents/trace.py`: privacy-safe agent JSONL persistence and trace lookup.
- `tests/test_cli.py`: end-to-end CLI flow tests plus LLM fallback and injected fake-LLM tests.

## Data Model

```text
Memory
- id
- text
- tags
- created_at

Goal
- id
- title
- description
- cadence_days
- status
- created_at
- last_check_in
- check_ins

CheckIn
- at
- note
```

## Briefing Flow

```text
nexus briefing
  -> load memories and active goals
  -> select recent memories
  -> select up to three important active goals
  -> run proactive review
  -> build briefing context
  -> render local template briefing
  -> return JSON
```


## Planning / Reflection Flow

```text
nexus plan day
  -> load active long-term goals
  -> sort goals by oldest progress
  -> create up to three prioritized daily tasks
  -> persist tasks in .nexus/state.json
  -> retrieve relevant memories
  -> render local plan or optional LLM plan with Coach mode

nexus task update <task_id>
  -> update pending / in_progress / completed / blocked status
  -> store blocker, unresolved items, and progress notes

nexus review day
  -> collect today's task state and goal check-ins
  -> collect blockers and unresolved items
  -> retrieve relevant long-term memories
  -> place carry-forward work into tomorrow priorities
  -> render local reflection or optional LLM reflection with Coach mode
```

Daily plans are idempotent per date: running `nexus plan day` again returns the existing tasks instead of creating duplicates.

## RAG 2.0 Memory Flow

```text
Configure
  -> choose local FastEmbed or an OpenAI-compatible embedding endpoint
  -> choose local Qdrant persistence or remote Qdrant

Add memory
  -> store deterministic sparse features in .nexus/state.json
  -> generate a neural embedding when semantic RAG is enabled
  -> incrementally upsert vector + public payload into Qdrant

Retrieve memory
  -> generate dense query embedding
  -> query Qdrant semantic candidates
  -> score local sparse candidates
  -> fuse dense and sparse scores
  -> return memories plus provider/model/strategy/score/error metadata
  -> automatically use sparse-only results if semantic retrieval fails

Re-index
  -> load all memories
  -> regenerate embeddings with the current provider/model
  -> recreate the Qdrant collection
  -> persist index metadata in .nexus/state.json

Briefing / Planning / Review
  -> build a task-specific retrieval query
  -> retrieve relevant long-term memories
  -> inject memories and retrieval metadata into local and LLM contexts
```

Local FastEmbed requires no API key but downloads its model on first use. Hosted embedding providers require their own API key. The local Qdrant index lives under `.nexus/qdrant/` and is not committed.

## LLM Briefing Flow

```text
nexus briefing --llm
  -> load memories, goals, reminders, weather text
  -> build structured briefing context
  -> build system prompt and user prompt
  -> if LLM is configured:
       call OpenAI-compatible chat completions API
       use model output as briefing
     else:
       keep local template briefing
       report configuration error in llm.error
  -> return JSON with briefing, context, llm status, and optional prompt
```

## LLM Configuration

The LLM layer is configured by environment variables:

```text
NEXUS_LLM_API_KEY          optional, takes priority over OPENAI_API_KEY
OPENAI_API_KEY             fallback API key
NEXUS_LLM_MODEL            default: gpt-4o-mini
NEXUS_LLM_BASE_URL         default: https://api.openai.com/v1
NEXUS_LLM_TIMEOUT_SECONDS  default: 30
```

## Real Tool Integration Flow

```text
nexus config tool set <tool>
  -> validate required settings
  -> save secrets in ignored .nexus/config.local.json
  -> explicitly enable read-only operations

nexus tool <tool>
  -> ToolManager
  -> PermissionPolicy checks tool + operation
  -> adapter calls Open-Meteo / iCalendar / Todoist / GitHub / Notion / IMAP / filesystem
  -> normalize result
  -> append secret-safe success or failure to .nexus/tool_audit.jsonl
  -> return structured JSON

nexus briefing --live-tools
  -> fetch configured weather
  -> expand upcoming one-off and recurring calendar events
  -> fetch active Todoist tasks
  -> keep partial results when one provider fails
  -> inject live context and provider errors into template and LLM prompts
```

Current tool adapters are read-only. Email uses a verified TLS context and opens the mailbox with `readonly=True`. Filesystem paths are resolved before access and must stay inside explicitly configured roots. Calendar URLs, tokens, and passwords are masked and never written to the audit log.

## MCP Client Flow

```text
nexus config mcp add <server>
  -> validate stdio command/arguments or Streamable HTTP URL/headers
  -> save the definition only in ignored .nexus/config.local.json
  -> mask URL, headers, and child-process environment in CLI output

nexus mcp tools <server>
  -> open the configured transport
  -> complete MCP initialization and capability negotiation
  -> list tools
  -> normalize names, descriptions, titles, and input JSON Schemas
  -> append a secret-safe discovery audit event

nexus mcp call <server> <tool>
  -> require enabled server
  -> apply deny / ask / allow policy
  -> require --approve for one ask-policy call
  -> call through the official MCP SDK
  -> retry only eligible transport failures within the configured bound
  -> never retry an MCP-declared tool error
  -> normalize text, structured content, non-text metadata, attempts, and timestamp
  -> append a secret-safe success, denial, or failure audit event

nexus plan day --live-mcp
  -> run only explicit planning-tool bindings with allow policy
  -> keep successful results when another binding fails
  -> inject normalized MCP context into the local plan and optional LLM prompt
  -> preserve normal local Planning when no MCP result is available
```

Nexus supports standard stdio and Streamable HTTP transports. Nexus remains an MCP client; Phase 8 adds allow-only autonomous selection above the Phase 7 permission layer.

## Multi-Agent Coordination Flow

```text
nexus plan day --agents
  -> create bounded AgentRunContext
  -> Memory Agent retrieves relevant RAG context
  -> Tool Agent discovers allow-policy MCP candidates
  -> Tool Agent runs explicit bindings or validates strict-JSON LLM selections
  -> Planner Agent creates/persists today's tasks
  -> Coach Agent applies the selected tone and optional LLM generation
  -> append privacy-safe run trace

nexus review day --agents
  -> Memory Agent -> Reflection Agent -> Coach Agent
  -> keep blockers, unresolved items, check-ins, and tomorrow priorities structured

nexus briefing --agents
  -> Memory Agent -> Tool Agent -> Planner Agent -> Coach Agent
  -> preserve Phase 6 live context and deterministic briefing fallback
```

A run is limited to 8 steps, 3 LLM calls, and 3 MCP calls under a shared 60-second deadline. MCP and production LLM request timeouts are clamped to the remaining time; the deadline is checked before and after specialist work. Agents share structured artifacts but never call one another directly; the Orchestrator owns sequencing and trace persistence. Only enabled MCP tools with explicit `allow` policy are eligible for autonomous Tool Agent calls. Agent traces under `.nexus/agent_runs.jsonl` exclude prompts, memory text, raw content, credentials, URLs, and argument values.

Default commands without `--agents` remain unchanged. Any specialist, LLM, RAG, MCP, or budget failure produces a partial trace and falls back to the existing local plan, review, or briefing when possible.
## Design Constraints

- Nexus does not fake integrations. Weather, iCalendar, Todoist, GitHub, Notion, IMAP headers, and bounded local files now use real adapters; unavailable providers remain explicit in structured errors.
- LLM usage must be optional. The local template path remains the stable fallback.
- The service layer owns product decisions. The CLI only parses arguments and wires dependencies.
- Prompt construction is inspectable on legacy LLM workflows with `--show-prompt`; agent workflows instead expose privacy-safe structured step traces.
- Multi-agent coordination is bounded orchestration, not an open-ended autonomous loop.

## Future Architecture

```text
[User]
  |
  v
[CLI / Web / Mobile / Chat / Voice gateway / Vision gateway]
  |
  v
[Backend API]
  |-- Memory engine
  |-- RAG retriever
  |-- Goal engine
  |-- Briefing engine
  |-- Review engine
  |-- Planning engine
  |-- Reflection engine
  |-- Coach mode controller
  |-- MCP tool adapters
  |-- Browser/local automation adapters
  |-- Smart-home adapters (long-term)
  |-- Robotics adapters (long-term, simulation-first)
  |
  +--> [Relational DB: goals, tasks, habits]
  +--> [Vector DB: long-term semantic memory]
  +--> [Scheduler: morning briefing, evening review, reminders]
  +--> [LLM API: reasoning and generation]
  +--> [External tools: calendar, weather, email, Notion, GitHub, health]
```
The architecture keeps one Nexus core across interfaces. Voice, vision, home, and robotics integrations are future adapters behind the same permission and audit boundaries; they are not part of the current CLI product.
