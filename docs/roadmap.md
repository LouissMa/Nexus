# Nexus Development Roadmap

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

Nexus is currently an MCP client. Exposing Nexus itself as an MCP server remains separate future work.

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

Phase 10 remains bounded automation. The dashboard is read-only, and runtime jobs are disabled until explicitly enabled.

Future Dashboard work:

- [ ] Habit tracking panel.
- [ ] Dedicated project-progress panel.
- [ ] AI-suggestion panel.

## Phase 11: Adaptive Life Workspace

Objective: make Nexus easier to use every day while preserving local-first and permission-bounded behavior.

- [~] Habit cadence, check-ins, streaks, completion rates, archive, and CLI completed; Dashboard controls remain.
- [ ] Project milestones, progress history, linked goals/tasks, and a dedicated Dashboard view.
- [ ] Explainable suggestions derived from goals, tasks, habits, projects, calendar, and RAG memories.
- [ ] Calendar-aware replan preview and stale-safe apply without calendar writes.
- [ ] Unified local-first `nexus ask` entry point with optional strict-JSON LLM intent parsing.
- [ ] Allowlisted loopback Dashboard mutations protected by Origin and CSRF checks.
- [ ] Explicitly launched permissioned Nexus MCP stdio server.

The proposed safety and architecture contract is documented in `docs/superpowers/specs/2026-08-08-adaptive-life-workspace-design.md`.

## Phase 12: Multimodal and Embodied Interfaces

Objective: explore additional interfaces around the stable Nexus core.

- [ ] Voice input, wake-word flow, and speech output.
- [ ] Permissioned visual context.
- [ ] Smart-home adapters and family profiles.
- [ ] Robotics adapter with simulation-first safety testing.
- [ ] Deeper research-companion workflows for literature, code, and experiments.

This is a long-term research direction. It does not imply that Nexus is AGI or that the current project can autonomously control a home or robot.