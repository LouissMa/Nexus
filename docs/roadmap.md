# Nexus Development Roadmap

## Current Priority

Phase 15, General Task Execution Core, is the next implementation priority.
Existing Phase 13/14 foundations remain available; their unfinished interface
features are not prerequisites for the first general execution loop.
See [current capabilities and next-phase milestones](current_capabilities_and_next_phase.md).

## Phase 1: LifeAgent CLI MVP

Objective: prove the smallest useful loop of a personal AI manager.

- [x] Local Python CLI and JSON storage.
- [x] Long-term memories and keyword search.
- [x] Goals, check-ins, stale-goal review, and morning briefing.

## Phase 2: LLM Briefing

Objective: add natural generation without making local use depend on an API.

- [x] OpenAI-compatible LLM client.
- [x] Local provider/model tiers and masked configuration.
- [x] Structured briefing prompts, prompt inspection, and deterministic fallback.

## Phase 3: RAG Long-Term Memory

Objective: retrieve relevant context instead of relying only on recent records.

- [x] Deterministic local sparse embeddings and similarity retrieval.
- [x] Briefing, planning, and review context injection.
- [x] Inspectable retrieval metadata and offline behavior.

## Phase 4: Daily Planning, Review, and Coaching

Objective: support both the start and end of each day.

- [x] Persistent daily plans from active long-term goals.
- [x] Task status, blockers, unresolved items, and notes.
- [x] Evening reflection and tomorrow priorities.
- [x] Strict, gentle, academic, and startup Coach modes.

## Phase 5: RAG 2.0 Foundation

Objective: add production-oriented semantic retrieval.

- [x] FastEmbed and OpenAI-compatible embedding providers.
- [x] Local or remote Qdrant vector persistence.
- [x] Incremental indexing, re-indexing, and index status.
- [x] Dense+sparse hybrid retrieval with sparse fallback.
- [x] Retrieval-quality and fallback tests.

## Phase 6: Real Tool Integrations

Objective: connect approved real-world context through explicit read-only adapters.

- [x] Open-Meteo weather and recurring iCalendar events.
- [x] Todoist, GitHub, Notion, and read-only IMAP headers.
- [x] Permission-bounded local filesystem list/read/search.
- [x] Explicit enablement, masked credentials, and secret-safe audits.
- [x] Live briefing context with partial-failure behavior.

## Phase 7: MCP Tool Calling

Objective: use a standard permission layer for external tools.

- [x] stdio and Streamable HTTP MCP server configuration and discovery.
- [x] Tool schemas and official-SDK gateway.
- [x] Per-tool deny, ask, and allow policies.
- [x] One-shot approval, bounded retries, normalized results, and audits.
- [x] Explicit allow-policy Planning bindings with local fallback.

Nexus is both an MCP client and an explicitly launched stdio MCP server. The server exposes a fixed 12-tool catalog with seven bounded reads and five approval-gated mutations.

## Phase 8: Multi-Agent Coordination

Objective: separate specialist responsibilities without creating open-ended loops.

- [x] Memory, Tool, Planner, Reflection, and Coach Agents.
- [x] Shared artifacts, step/LLM/MCP/time budgets, and orchestration.
- [x] Allow-only autonomous MCP selection.
- [x] Partial-failure fallback and privacy-safe run traces.
- [x] Opt-in Agent planning, review, and briefing.

## Phase 9: Advanced Long-Term Memory

Objective: keep personal memory useful and maintainable at scale.

- [x] Importance scoring and user overrides.
- [x] Duplicate, supersession, and conflict handling.
- [x] Compression, summaries, archival, and source lineage.
- [x] Retention, expiry, privacy, forgetting, restore, and confirmed purge.
- [x] Eligibility enforcement and context-aware explainable re-ranking.

## Phase 10: Proactive Runtime, Dashboard, and Permissioned Automation

Objective: make Nexus available at configured times, expose its state locally, and execute fixed approved actions.

- [x] Local profile with display name and IANA time zone.
- [x] Configurable morning briefing, evening review, and stale-goal reminder jobs.
- [x] Restart-safe daily occurrence claims, grace windows, explicit retry/manual runs, cross-process state transactions, and bounded foreground loop.
- [x] Durable inbox-first notifications with cross-process-safe claims, bounded line recovery, console/webhook channels, quiet-hour deferral, flush, and partial-delivery status.
- [x] Runtime status, tick, run, start, notification, profile, and runtime CLI commands.
- [x] Responsive read-only dashboard with Today, Goals, Memory, Activity, and masked Settings.
- [x] Loopback-only HTTP server with exact routes, Host/Origin validation, bounded snapshots, packaged assets, and section failure isolation.
- [x] Named `browser`, `command`, `github_inspect`, and `status_report` automations.
- [x] deny/ask/allow policies, one-shot approval, mandatory browser host allowlists, fixed `shell=False` argument vectors, root boundaries, bounded timeout/output, and secret-safe audit.
- [x] Transactional cross-process-safe local configuration shared by all writers.

Phase 10 remains bounded automation. Runtime jobs are disabled until explicitly enabled.

Phase 11 Dashboard extensions:

- [x] Habit tracking panel.
- [x] Dedicated project-progress panel.
- [x] AI-suggestion panel.
- [x] Replan preview/apply dialog and six exact CSRF-protected actions.

## Phase 11: Adaptive Life Workspace

Objective: make Nexus easier to use every day while preserving local-first and permission-bounded behavior.

- [x] Habit cadence, check-ins, streaks, completion rates, archive, CLI, and Dashboard controls.
- [x] Project milestones, explicit/derived progress history, linked goals/tasks, archive, CLI, and dedicated Dashboard view.
- [x] Explainable Suggestions 2.0 from goals, tasks, habits, project milestones, live calendar conflicts/focus windows, and eligible RAG memories, with independent degradation, structure-safe LLM wording, CLI actions, and Dashboard source status.
- [x] Calendar-aware replan preview and stale-safe apply without calendar writes, including live read-only iCalendar constraints and explicit degradation.
- [x] Unified local-first `nexus ask` entry point with common Chinese/English intents, approval previews, and optional strict-JSON LLM intent parsing.
- [x] Allowlisted loopback Dashboard mutations protected by exact routes, Origin, CSRF, strict schemas, and request bounds.
- [x] Explicitly launched permissioned Nexus MCP stdio server with bounded reads, approval-gated mutations, policy overrides, and redacted audit.

The proposed safety and architecture contract is documented in `docs/superpowers/specs/2026-08-08-adaptive-life-workspace-design.md`.

## Phase 12: Research Companion MVP

Objective: give Nexus a bounded, evidence-oriented workflow for collaborative research.

- [x] Persistent research workspaces with questions, sources, notes, experiments, investigations, syntheses, and follow-ups.
- [x] Explicitly enabled read-only Crossref scholarly metadata search under ToolManager permission and audit.
- [x] RAG-enriched deterministic synthesis with stable evidence references, open questions, next actions, and independent degradation.
- [x] Evidence-matched follow-up answers with explicit uncertainty and structure-safe optional LLM wording.
- [x] CLI, unified conversation reads, and privacy-filtered ninth Dashboard Research view.

## Research Companion 2.0

Objective: let Nexus acquire and verify bounded research evidence, run explicitly approved validations, and coordinate a terminating research workflow.

- [x] PDF, Markdown, and TXT full-text ingestion with stable page/line-aware chunks and content-hash citation validation.
- [x] Explicit HTTPS page acquisition with private-network, credential, port, content-type, and response-size restrictions.
- [x] Explicit local repository indexing with ignored/generated directories, extension/file/byte bounds, line-aware references, and no code execution.
- [x] Restricted experiment runner with approval, executable allowlist, bounded root, no shell, timeout, minimal environment, and capped output. This is not an OS/container sandbox.
- [x] Deterministic Planner/Retriever/Analyst/Critic/Reflection research loop with cycle/time/result budgets, verified references, degradation, persistence, and terminal outcomes.
- [x] CLI, read-only unified-conversation corpus access, corpus-enriched synthesis/answers, and privacy-filtered Dashboard document/run summaries.

OCR, JavaScript-rendered or authenticated crawling, arbitrary shell execution, container isolation, and unbounded background research remain out of scope.

## Phase 13: Multimodal and Embodied Interfaces

Objective: explore additional interfaces around the stable Nexus core.

Current status: Voice Assistant MVP and Voice Assistant 2.0 continuous foreground turn-taking are complete; remaining multimodal interfaces are planned.

- [x] Explicit duration-bounded push-to-talk recording, local `faster-whisper` transcription, and operating-system speech output.
- [x] Voice conversation through the existing intent/approval path and narrated briefings through the existing briefing/runtime services.
- [x] Voice Assistant 2.0: explicit foreground continuous turn-taking with WebRTC VAD, stop phrases, idle/turn limits, temporary-audio cleanup, and approval stop.
- [ ] Wake-word activation, speech interruption, and background listening.
- [ ] Permissioned visual context.
- [ ] Family profiles.
- [ ] Smart-home adapters.
- [ ] Robotics adapter with simulation-first safety testing.
- [ ] Connect future voice/vision interfaces to permissioned Research Companion workflows.

Voice adapters keep audio local; `faster-whisper` may download its configured model on first use. Continuous turn-taking requires explicit `voice chat` startup and pauses listening while processing and speaking. This partial phase does not imply AGI, unattended listening, or autonomous home/robot control.

## Phase 14: Desktop Task Agent

Current status: foundation implemented; richer computer interaction remains planned.

- [x] Chinese/English file search and open intents shared by text and voice.
- [x] Bounded filename search including images, configured roots, metadata, and truncation.
- [x] In-session numbered candidates and approved Windows document opening.
- [x] Registered Windows application launch with no model-authored arguments.
- [x] Existing browser automation aliases, policy checks, and launch plus today's task list.
- [x] Explicit startup-request semantics, tests, and synchronized documentation.
- [ ] OCR, semantic image retrieval, and thumbnail candidates.
- [ ] Application discovery and desktop UI interaction.
- [ ] Connect desktop tools to the Phase 15 general execution core; richer reusable desktop workflows follow that foundation.
- [ ] Evaluate reusable OpenClaw components individually before integration.

## Phase 15: General Task Execution Core

Status: 15.1 contracts, 15.2 dynamic execution, 15.3 durable execution and 15.4a selected-source context implemented; shared text/voice entry and independent verification remain pending.

- [x] 15.1a: Unified input/output contracts, policy-aware catalog, bounded one-call dispatch, explicit side-effect/retry/adapter-timeout metadata, filesystem and named automation adapters, CLI and tests.
- [x] 15.1b: Initial pinned-source comparison of LangGraph, smolagents and OpenClaw; framework-neutral contract decision recorded.
- [~] 15.1c: LangGraph selected and tested for foreground execution, interrupt/resume and durable crash recovery; broader dependency review and candidate benchmarks remain pending.
- [x] 15.2: LangGraph model-driven decide/act/observe loop over registered tools, bounded decisions/context, cooperative deadlines, explicit clarification, approval stop and unverified completion reporting.
- [x] 15.3: SQLite run/action/result snapshots, single-use bound approvals, cooperative pause/cancel, restart recovery and explicit uncertain-action reconciliation. Independent artifact verification remains in 15.5.
- [~] 15.4: Selected goal/RAG/research context implemented; shared text/voice task entry and observable progress remain pending.

15.4 is split into selected-source context (15.4a) and shared text/voice entry
(15.4b). The [15.4a design](superpowers/specs/2026-09-13-execution-context-design.md)
documents the delivered 15.4a context behavior; 15.4b remains pending.
The [15.4b design](superpowers/specs/2026-09-14-shared-task-conversation-design.md)
specifies shared text/voice task sessions with text-only approvals. It is a
design for review, not a claim of background execution or voice interruption.
- [ ] 15.5: Verify artifacts and evaluate project inspection, file organization, and research preparation with unseen task variations and failure injection.

Success means executing new goals by composing tools, not adding one intent per
example. Missing LLM configuration must be reported explicitly. Existing local
commands remain available. Cost reporting is conditional on reliable provider
usage and pricing; step/call/time limits must work independently.
