# Nexus Architecture

Nexus is a local-first personal AI assistant. The current system combines long-term memory, planning and reflection, optional LLM generation, permissioned real tools and MCP, bounded specialist agents, an explicit local voice layer, a proactive runtime, a read-only local dashboard, and named permissioned automation.

Core workflows remain usable without an API key. Network providers are activated only by explicit configuration or command flags.

## Current Architecture

```text
[User]
  |
  +--> [Nexus CLI] ------------------------------+
  |       |                                      |
  |       +--> [VoiceService]                    |
  |              |-- recorder -> local WAV       |
  |              |-- transcript -> ConversationService
  |              |-- briefing -> NexusService / Runtime
  |              +-- response -> OS speech       |
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

- `src/nexus/cli.py`: Parses all commands and lazily wires runtime and voice providers so text commands do not initialize optional integrations or audio dependencies.
- `src/nexus/service.py`: Owns memory/RAG delegation, goals, planning, task updates, reflection, briefings, and shared Agent artifacts.
- `src/nexus/habits.py`: Owns bounded daily/weekday habits, idempotent local-date check-ins, derived streak/completion metrics, and archival.
- `src/nexus/projects.py`: Owns bounded projects, goal/task links, milestones, derived or explicit progress, correction history, and archival.
- `src/nexus/research.py`: Owns persistent research workspaces, evidence relationships, Crossref source import/deduplication, RAG/corpus-enriched deterministic synthesis, grounded follow-up matching, uncertainty, history bounds, and structure-safe optional LLM wording.
- `src/nexus/research_corpus.py`: Extracts PDF/Markdown/TXT, safe explicit HTTPS pages, and bounded repositories into project-scoped page/line-aware chunks; persists local sparse vectors and validates content-hash citations.
- `src/nexus/research_experiments.py`: Runs explicitly approved argument vectors inside an allowed root with executable allowlists, `shell=False`, timeout, minimal environment, and capped output. It is a restricted runner, not an OS sandbox.
- `src/nexus/research_loop.py`: Coordinates terminating Planner, Retriever, Analyst, Critic, and Reflection research steps with cycle/time/result bounds, exact reference validation, degradation, and sanitized persisted traces.
- `src/nexus/suggestions.py`: Deterministically ranks local state, calendar conflicts/focus windows, and eligible RAG memories; persists bounded context/expiry/status; executes allowlisted approved actions; and constrains optional LLM rewriting to wording fields.
- `src/nexus/replanning.py`: Normalizes immutable calendar constraints, allocates task windows, records shortened/unscheduled work, and applies previews only when state and calendar fingerprints remain fresh.
- `src/nexus/conversation.py`: Maps bounded Chinese/English requests to a static intent registry, validates optional strict-JSON LLM selections, previews mutations, and dispatches only registered Nexus services.
- `src/nexus/voice.py`: Defines recorder/transcriber/synthesizer contracts and result models, validates bounded audio paths, renders speech text, cleans temporary recordings, and composes voice conversation and briefing operations without owning intent or briefing logic.
- `src/nexus/voice_providers.py`: Lazily loads `sounddevice` and `faster-whisper`, records mono PCM WAV, transcribes locally, and invokes bounded OS speech commands with `shell=False`.
- `src/nexus/store.py`: Persists memories, goals, tasks, scheduler claims, and bounded scheduler run history in `.nexus/state.json` with revision checks, atomic replacement, and cross-process locking.
- `src/nexus/config.py`: Owns shared local configuration transactions for LLM, embeddings, tools, profile, runtime, voice, and Nexus MCP Server policy settings.
- `src/nexus/file_lock.py`: Provides canonical process-local and OS-backed cross-process path transactions for state and notification files.
- `src/nexus/runtime_config.py`: Defines immutable profile/runtime settings, IANA time-zone and clock validation, job names, quiet hours, channel flags, and masked output.
- `src/nexus/notifications.py`: Implements inbox-first JSONL persistence, quiet-hour deferral, cross-process delivery claims, console/webhook delivery, bounded records/read buffers, corrupt-line repair, and deferred flush.
- `src/nexus/scheduler.py`: Implements deterministic `tick`, explicit job runs, the foreground loop, occurrence claims, status, and partial-failure reporting.
- `src/nexus/automation.py`: Validates named automations, enforces policies and path/host boundaries, runs fixed adapters, and stores bounded secret-safe audits.
- `src/nexus/dashboard.py`: Builds privacy-filtered section snapshots and serves exact loopback HTTP reads plus six Origin/CSRF-protected life-workspace action routes.
- `src/nexus/dashboard_actions.py`: Validates allowlisted Dashboard action schemas and delegates habit, project, suggestion, and replan operations to Nexus services.
- `src/nexus/dashboard/index.html`: Eight-view Dashboard shell, accessible navigation, confirmation dialog, and replan dialog.
- `src/nexus/dashboard/dashboard.css`: Responsive operational layout, horizontally scrollable mobile navigation, progress states, dialogs, and stable control dimensions.
- `src/nexus/dashboard/dashboard.js`: Safely renders all eight views and calls only the six exact CSRF-protected Dashboard actions.
- `src/nexus/memory_lifecycle.py`: Normalization, importance, duplicates, eligibility, transitions, compression planning, expiry, and retention rules.
- `src/nexus/memory_service.py`: Persistent memory lifecycle operations, relationships, index refresh, compression, maintenance, and purge enforcement.
- `src/nexus/embeddings.py`, `src/nexus/vector_store.py`, `src/nexus/rag.py`: Embedding providers, Qdrant persistence, hybrid retrieval, eligibility filtering, re-ranking, metadata, re-indexing, and local fallback.
- `src/nexus/integrations/`: Permissioned read-only weather, calendar, task, GitHub, Notion, email-header, and filesystem adapters plus tool auditing.
- `src/nexus/mcp/`: MCP configuration, official SDK transports, deny/ask/allow enforcement, retries, normalization, Planning bindings, and audit.
- `src/nexus/mcp_server.py`: Exposes a static bounded Nexus tool catalog over official-SDK stdio, enforces read/mutation policy, and writes redacted server-side audit events.
- `src/nexus/agents/`: Bounded Memory, Tool, Planner, Reflection, and Coach specialists, orchestration, budgets, fallback, and privacy-safe traces.

## Persistent Data

All personal runtime data defaults to `.nexus/` or the directory selected by `NEXUS_HOME`.

- `state.json`: memories, goals, daily tasks, research/project metadata and histories, scheduler claims, and scheduler run history.
- `research_corpus/<project-id>/<document-id>.json`: local full-text chunks, sparse vectors, source locations, content hashes, and stable references; never served raw by Dashboard.
- `config.local.json`: profile, runtime, LLM, embeddings, tools, MCP servers/policies, and named automation definitions.
- `notifications.jsonl`: durable notification inbox and delivery state with bounded individual records.
- `tool_audit.jsonl`, `mcp_audit.jsonl`, `mcp_server_audit.jsonl`, `automation_audit.jsonl`: sanitized activity records; automation audit rotation is bounded, and Dashboard reads expose bounded recent summaries.
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

## Explicit Voice Flow

```text
nexus voice ask --record-seconds N
  -> require enabled VoiceSettings and enforce recording/audio bounds
  -> SoundDeviceRecorder writes a temporary local PCM WAV
  -> FasterWhisperTranscriber produces text and metadata locally
  -> ConversationService applies the existing intent schemas and approval rules
  -> VoiceService renders concise speech text
  -> SystemSpeechSynthesizer plays or saves through the available OS voice
  -> delete the temporary recording

nexus voice briefing
  -> reuse the existing briefing, optional LLM, live-tool, and Agent paths
  -> render the completed briefing for speech
  -> preserve structured text if speech is unavailable
```

Voice is an explicit interface beside conversation and runtime, not a second assistant core. Text commands do not need the voice extra or an API key. The initial adapters do not upload audio; `faster-whisper` may download the configured model on first use, while OS speech availability varies by platform. DeepSeek remains available only through the optional text-generation path and does not supply local STT/TTS. There is no continuous listener or wake-word process.

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
       Habits -> due state, check-ins, streaks, completion
       Projects -> milestones and explicit/derived progress
       Research -> bounded questions, source/document/experiment counts, latest synthesis, and latest research-loop outcome without raw chunks, paths, references, traces, output, or private notes
       Suggestions -> reason, confidence, source types, Calendar/RAG status, degradation
       Memory -> bounded eligible memory timeline
       Activity -> bounded notification/tool/MCP/Agent/automation summaries
       Settings -> explicit allowlisted masked fields
  -> redact secrets and omit raw prompts, arguments, output, paths, and URLs
  -> enforce bounded nesting, collections, strings, and final response bytes
  -> return privacy-filtered JSON

Browser POST exact allowlisted route
  -> validate loopback Host + same Origin + per-process CSRF
  -> require bounded JSON with the endpoint's strict schema
  -> dispatch habit/project/suggestion/replan service action
  -> return normalized result; no generic mutation route exists
```

The server accepts only loopback binds and rejects foreign `Host` or `Origin`, query/fragment aliases, encoded routes, traversal, and unknown paths. Each section catches its own dependency failure, so one malformed optional integration does not make the remaining dashboard unavailable.

The Dashboard exposes only six purpose-built mutations: habit check-in, project progress, suggestion accept/dismiss, and replan preview/apply. Lower project progress, suggestion acceptance, and replan apply require explicit UI confirmation. Arbitrary state writes remain unavailable.

## Nexus MCP Server Flow

```text
nexus mcp-server stdio [--approve-tool NAME]
  -> load local per-tool deny / ask / allow overrides
  -> advertise a static 12-tool JSON-schema catalog
  -> validate and bound every argument object
  -> allow seven read tools by default
  -> deny or require session approval for five mutation tools
  -> delegate only to registered Nexus services
  -> enforce a 64 KiB serialized result ceiling and append bounded content-free audit summaries
```

The server is local stdio only; it does not start HTTP or listen on a network interface. Session approvals exist only for the launched process. External clients cannot invent tool names, schemas, service methods, or arbitrary commands.

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
- Research acquisition, corpus retrieval, investigation, synthesis, follow-up, and bounded loops isolate extraction/network/index/RAG/LLM failures; the last valid index and available local evidence remain usable.
- Planning and Agent workflows preserve deterministic local fallback when optional LLM, MCP, tools, or specialists fail.
- Voice transcription failure stops before conversation dispatch; speech failure preserves completed conversation or briefing text as a structured degradation.
- Command timeout terminates the child process tree; output is consumed under a byte bound.
- Audit write failure is surfaced as degraded audit health rather than silently claiming complete auditability.

## Security and Scope

- Local/offline behavior is the default; jobs and external integrations require explicit opt-in.
- Read-only integrations remain read-only; Dashboard and Nexus MCP writes are limited to explicit allowlisted domain actions.
- `ask` actions require one-shot human approval; unattended automation requires explicit `allow`.
- Prompts, memory text, credentials, raw tool payloads, command output, URLs, and argument values are excluded from operational audits and traces.
- Phase 13 voice remains explicit, duration-bounded assistance, not continuous listening or an open-ended autonomous loop.

Current limitations include no remote dashboard, arbitrary browser mutations, arbitrary LLM-authored commands, continuous listening, wake word, visual context, family profiles, smart-home control, or robotics. Suggestions consume read-only calendar context only when explicitly requested and do not write calendar events. Research Companion searches bounded Crossref metadata only when explicitly enabled; full-text ingestion, general web research, code execution, citation verification, and autonomous research loops remain future work.

## Future Architecture

Future interfaces should reuse the same memory, planning, permission, transaction, and audit layers:

```text
[CLI / Web / Explicit Voice / future Mobile / Vision]
                  |
             [Nexus Core]
  memory | planning | runtime | permissions | audit
       |              |               |
 research tools   future habits   future home/robot adapters
                                     simulation-first
```

The explicit local Voice Assistant MVP is current. Continuous voice, vision, home, and robotics integrations remain future adapters, not current capabilities or an AGI claim.
