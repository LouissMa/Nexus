# Nexus Architecture

Nexus is a local-first personal AI assistant. The current system combines long-term memory, planning and reflection, optional LLM generation, permissioned real tools and MCP, bounded specialist agents, a proactive runtime, a read-only local dashboard, and named permissioned automation.

Core workflows remain usable without an API key. Network providers are activated only by explicit configuration or command flags.

## Current Architecture

```text
[User]
  |
  +--> [Nexus CLI] ------------------------------+
  |                                              |
  +--> [Loopback DashboardServer]                |
          | exact static routes                  |
          +--> [DashboardSnapshot]               |
                   |                             |
                   +--> state / scheduler        |
                   +--> notifications            |
                   +--> tool + MCP audits         |
                   +--> agent + automation traces|
                                                 v
                                      [Application Core]
                                      |-- NexusService
                                      |-- MemoryService / RAG
                                      |-- Planning / Reflection
                                      |-- ToolManager / MCPManager
                                      |-- AgentOrchestrator
                                      |
                                      +--> local .nexus data

[Runtime CLI / foreground loop]
  -> ProactiveScheduler
       -> briefing / review / stale-goal job
       -> NotificationCenter
            -> durable inbox
            -> optional console / webhook

[Automation CLI]
  -> AutomationManager
       -> deny / ask / allow gate
       -> fixed browser / argv / GitHub / status report
       -> bounded secret-safe audit
```

The scheduler, dashboard, and automation manager reuse existing services and stores. They do not bypass tool permissions or write through the browser.

## Core Modules

- `src/nexus/cli.py`: Parses all commands and lazily wires Phase 10 managers so legacy commands do not initialize optional runtime integrations.
- `src/nexus/service.py`: Owns memory/RAG delegation, goals, planning, task updates, reflection, briefings, and shared Agent artifacts.
- `src/nexus/habits.py`: Owns bounded daily/weekday habits, idempotent local-date check-ins, derived streak/completion metrics, and archival.
- `src/nexus/projects.py`: Owns bounded projects, goal/task links, milestones, derived or explicit progress, correction history, and archival.
- `src/nexus/suggestions.py`: Ranks explainable offline suggestions, persists expiry/status, executes allowlisted approved actions, and constrains optional LLM rewriting to wording fields.
- `src/nexus/replanning.py`: Normalizes immutable calendar constraints, allocates task windows, records shortened/unscheduled work, and applies previews only when state and calendar fingerprints remain fresh.
- `src/nexus/conversation.py`: Maps bounded Chinese/English requests to a static intent registry, validates optional strict-JSON LLM selections, previews mutations, and dispatches only registered Nexus services.
- `src/nexus/store.py`: Persists memories, goals, tasks, scheduler claims, and bounded scheduler run history in `.nexus/state.json` with revision checks, atomic replacement, and cross-process locking.
- `src/nexus/config.py`: Owns shared local configuration transactions for LLM, embeddings, tools, profile, and runtime settings.
- `src/nexus/file_lock.py`: Provides canonical process-local and OS-backed cross-process path transactions for state and notification files.
- `src/nexus/runtime_config.py`: Defines immutable profile/runtime settings, IANA time-zone and clock validation, job names, quiet hours, channel flags, and masked output.
- `src/nexus/notifications.py`: Implements inbox-first JSONL persistence, quiet-hour deferral, cross-process delivery claims, console/webhook delivery, bounded records/read buffers, corrupt-line repair, and deferred flush.
- `src/nexus/scheduler.py`: Implements deterministic `tick`, explicit job runs, the foreground loop, occurrence claims, status, and partial-failure reporting.
- `src/nexus/automation.py`: Validates named automations, enforces policies and path/host boundaries, runs fixed adapters, and stores bounded secret-safe audits.
- `src/nexus/dashboard.py`: Builds privacy-filtered section snapshots and serves exact read-only HTTP routes on loopback addresses.
- `src/nexus/dashboard/index.html`: Dashboard shell and accessible navigation.
- `src/nexus/dashboard/dashboard.css`: Responsive operational layout, mobile navigation, states, and stable control dimensions.
- `src/nexus/dashboard/dashboard.js`: Fetches snapshots and renders Today, Goals, Memory, Activity, and Settings with safe DOM text assignment.
- `src/nexus/memory_lifecycle.py`: Normalization, importance, duplicates, eligibility, transitions, compression planning, expiry, and retention rules.
- `src/nexus/memory_service.py`: Persistent memory lifecycle operations, relationships, index refresh, compression, maintenance, and purge enforcement.
- `src/nexus/embeddings.py`, `src/nexus/vector_store.py`, `src/nexus/rag.py`: Embedding providers, Qdrant persistence, hybrid retrieval, eligibility filtering, re-ranking, metadata, re-indexing, and local fallback.
- `src/nexus/integrations/`: Permissioned read-only weather, calendar, task, GitHub, Notion, email-header, and filesystem adapters plus tool auditing.
- `src/nexus/mcp/`: MCP configuration, official SDK transports, deny/ask/allow enforcement, retries, normalization, Planning bindings, and audit.
- `src/nexus/agents/`: Bounded Memory, Tool, Planner, Reflection, and Coach specialists, orchestration, budgets, fallback, and privacy-safe traces.

## Persistent Data

All personal runtime data defaults to `.nexus/` or the directory selected by `NEXUS_HOME`.

- `state.json`: memories, goals, daily tasks, scheduler claims, and scheduler run history.
- `config.local.json`: profile, runtime, LLM, embeddings, tools, MCP servers/policies, and named automation definitions.
- `notifications.jsonl`: durable notification inbox and delivery state with bounded individual records.
- `tool_audit.jsonl`, `mcp_audit.jsonl`, `automation_audit.jsonl`: sanitized activity records; automation audit rotation is bounded, and Dashboard reads expose bounded recent summaries.
- `agent_runs.jsonl`: privacy-safe Agent step and budget summaries.
- `qdrant/`: local semantic vector data.
- `models/`: local embedding model cache.
- `*.lock`: cross-process coordination files.

The repository ignores `.nexus/` as a whole. The JSON state remains authoritative for memory eligibility even when vector synchronization is degraded.

## Configuration Transactions

All writers that share `config.local.json` coordinate through one canonical lock path.

```text
CLI partial update
  -> acquire process-local + OS-backed cross-process lock
  -> read latest complete configuration
  -> merge only explicitly supplied fields
  -> validate the updated section and preserve unrelated sections
  -> write and flush a temporary file
  -> atomically replace config.local.json
  -> flush the containing directory where supported
  -> release lock
```

This transaction prevents stale profile/runtime updates from overwriting LLM, embedding, tool, MCP, or automation sections. Masked serializers never return API keys, webhook URLs, headers, command arguments, roots, or report paths.

State and notification files use the same canonical lock identity and an adjacent lock file. A state save holds the OS lock across revision comparison and atomic replacement. A notification publish or flush holds it across the durable `delivering` transition and external side effect, so another process cannot claim the same delivery. Notification readers stream bounded lines; oversized corrupt records are ignored and removed by the next record rewrite. The durable inbox is not silently truncated, so operators should archive old delivered notifications when storage growth matters.

## Planning, Reflection, and Memory Flow

```text
nexus plan day
  -> active goals -> prioritized persistent tasks
  -> retrieve eligible task-relevant memories
  -> optional approved MCP context
  -> local or optional LLM Coach response

nexus review day
  -> task outcomes + blockers + unresolved items + check-ins
  -> retrieve eligible relevant memories
  -> tomorrow priorities
  -> local or optional LLM Coach response

memory retrieve
  -> authoritative JSON lifecycle/privacy filter
  -> dense Qdrant candidates + local sparse candidates
  -> score fusion and stale-vector rejection
  -> importance/recency/task re-ranking
  -> public retrieval metadata and local fallback
```

Archive and forget are reversible. Permanent purge requires forgotten state and explicit confirmation. Derived summaries inherit and recompute source privacy/expiry policy.

## Proactive Runtime Flow

```text
nexus runtime start
  -> load immutable profile/runtime snapshot
  -> ProactiveScheduler.run_forever
  -> tick at poll interval
  -> convert current time to profile IANA time zone
  -> find enabled jobs inside due/grace window
  -> claim job + local date before execution
  -> run one workflow:
       morning_briefing -> briefing
       evening_review -> daily review
       stale_goal_reminders -> proactive review
  -> publish notification to durable inbox first
  -> deliver to console/webhook now or defer for quiet hours
  -> persist success / partial / error run status
```

Normal ticks do not retry an already claimed daily occurrence. `nexus runtime run <job>` is the explicit retry/manual path. Optional LLM, live-tool, and Agent enrichment are separate runtime flags and preserve existing provider and permission boundaries.

A channel failure produces a partial result and does not erase the generated message. Deferred records can be flushed after quiet hours.

## Dashboard Snapshot and HTTP Flow

```text
Browser GET /
  -> validate loopback Host and optional Origin
  -> require exact unencoded route
  -> serve packaged index.html / dashboard.css / dashboard.js

Browser GET /api/snapshot
  -> validate request
  -> build sections independently:
       Today -> tasks, reminders, scheduled jobs, latest briefing/review
       Goals -> active goal cadence and check-ins
       Memory -> bounded eligible memory timeline
       Activity -> bounded notification/tool/MCP/Agent/automation summaries
       Settings -> explicit allowlisted masked fields
  -> redact secrets and omit raw prompts, arguments, output, paths, and URLs
  -> enforce bounded nesting, collections, strings, and final response bytes
  -> return read-only JSON
```

The server accepts only loopback binds and rejects foreign `Host` or `Origin`, query/fragment aliases, encoded routes, traversal, and unknown paths. Each section catches its own dependency failure, so one malformed optional integration does not make the remaining dashboard unavailable.

The first dashboard has no mutation endpoints. State changes remain in the permissioned CLI.

## Automation Policy Flow

```text
nexus automation set <name> --definition <json>
  -> validate name, exact type fields, enabled flag, and policy
  -> validate fixed target and type-specific boundaries
  -> persist under the canonical config lock with atomic replacement

nexus automation run <name> [--approve]
  -> reload and freeze validated settings
  -> enabled check
  -> deny: block
  -> ask without --approve: block
  -> ask with --approve or allow: execute one fixed adapter
  -> append bounded secret-safe audit event
  -> return normalized result/error
```

Automation types:

- `browser`: fixed HTTP(S) URL plus mandatory non-empty matching host allowlist.
- `command`: fixed non-empty argument vector, `shell=False`, existing working directory inside allowed roots, bounded timeout/output, no caller-supplied suffix or environment.
- `github_inspect`: existing read-only GitHub integration with a bounded issue limit.
- `status_report`: deterministic Markdown generated from sanitized state and written only to a `.md` path under an allowed root.

Path identities and roots are checked before execution and rechecked around sensitive operations. Audit events never contain command output, URL query strings, environment values, raw state text, or filesystem targets.

## Failure Isolation

- Invalid profile, time, time zone, webhook, automation, root, or policy fails before persistence.
- Scheduler jobs persist running/success/partial/error state and isolate notification-channel failure.
- JSONL readers skip corrupt records; notification and automation readers also enforce hostile-line size bounds, and notification rewrites remove oversized corrupt lines.
- Dashboard sections fail independently and expose only normalized section errors.
- RAG falls back to local sparse retrieval when embeddings or Qdrant fail.
- Planning and Agent workflows preserve deterministic local fallback when optional LLM, MCP, tools, or specialists fail.
- Command timeout terminates the child process tree; output is consumed under a byte bound.
- Audit write failure is surfaced as degraded audit health rather than silently claiming complete auditability.

## Security and Scope

- Local/offline behavior is the default; jobs and external integrations require explicit opt-in.
- Read-only integrations and the dashboard do not become write APIs.
- `ask` actions require one-shot human approval; unattended automation requires explicit `allow`.
- Prompts, memory text, credentials, raw tool payloads, command output, URLs, and argument values are excluded from operational audits and traces.
- Phase 10 is bounded automation, not an open-ended autonomous loop.

Current limitations include no remote dashboard, browser-authored arbitrary mutations, arbitrary LLM-authored commands, voice/vision, smart-home control, or robotics. Habit and project workflows currently use the CLI; their dedicated Dashboard panels and AI suggestions remain future work.

## Future Architecture

Future interfaces should reuse the same memory, planning, permission, transaction, and audit layers:

```text
[CLI / Web / Mobile / Voice / Vision]
                  |
             [Nexus Core]
  memory | planning | runtime | permissions | audit
       |              |               |
 research tools   future habits   future home/robot adapters
                                     simulation-first
```

Voice, vision, home, and robotics integrations are long-term adapters, not current capabilities or an AGI claim.
