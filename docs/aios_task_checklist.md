# AIOS Task Checklist

This checklist tracks the work required to evolve Nexus toward a J.A.R.V.I.S.-like Personal AI Operating System. Update it whenever a feature is completed, changed, deferred, or split.

Status legend:

- `[x]` Completed
- `[~]` MVP exists but deeper work remains
- `[ ]` Not started

## Agreed Implementation Order

1. Planning / Reflection. Completed.
2. RAG 2.0: real embeddings, vector database, and re-indexing. Completed.
3. Real tool integrations. Completed.
4. MCP tool calling and permissions. Completed.
5. Multi-Agent coordination. Completed.
6. Advanced memory importance, compression, privacy, and retention. Completed.
7. Proactive runtime, local Dashboard, and permissioned named automation. Completed.
8. Adaptive life workspace: Dashboard 2.0, calendar replanning, conversation, and Nexus MCP Server. Completed.
9. Research Companion MVP. Completed.
10. Long-term multimodal/embodied interfaces. Future.

## Completed Foundation

- [x] CLI for memories, goals, check-ins, planning, task updates, review, and briefing.
- [x] Optional OpenAI-compatible LLM generation with local masked provider/model configuration.
- [x] Local-first JSON state and ignored personal runtime/configuration directory.
- [x] Structured local fallback for optional LLM, RAG, tool, MCP, and Agent failures.

## 1. RAG Long-Term Memory

Current status: `[x]` RAG 2.0 and advanced lifecycle completed.

- [x] Deterministic local sparse embeddings and `nexus memory retrieve`.
- [x] FastEmbed and OpenAI-compatible embedding providers.
- [x] Local or remote Qdrant persistence.
- [x] Incremental indexing, `memory reindex`, and `memory index-status`.
- [x] Dense+sparse hybrid retrieval with sparse fallback.
- [x] Briefing, planning, and review context injection.
- [x] Importance scoring, pinning, privacy, and expiry.
- [x] Duplicate, supersession, and conflict handling.
- [x] Compression, summaries, archive, restore, forget, and confirmed purge.
- [x] Stale-vector rejection and explainable task/time-aware re-ranking.

## 2. Real Tool Integrations

Current status: `[x]` Permissioned read-only integration phase completed.

- [x] Open-Meteo weather and recurring iCalendar events.
- [x] Todoist, GitHub, Notion, and read-only IMAP headers.
- [x] Permission-bounded local filesystem list/read/search.
- [x] Explicit configuration and operation-level permissions.
- [x] Credentials stored only in ignored local configuration or environment variables.
- [x] Secret-safe success/failure audit.
- [x] Live weather/calendar/todo briefing context with partial failure.

## 3. MCP Tool Calling

Current status: `[x]` Permissioned MCP client and Nexus MCP stdio server completed.

- [x] stdio and Streamable HTTP configuration and discovery.
- [x] Official-SDK gateway, schemas, and normalized results.
- [x] Per-tool deny, ask, and allow policies.
- [x] One-shot approval for ask-policy calls.
- [x] Bounded transport retry and secret-safe audit.
- [x] Explicit allow-policy Planning bindings.
- [x] Local Planning fallback when MCP is unavailable.
- [x] Fixed 12-tool Nexus MCP stdio server with seven read tools and five approval-gated mutations.

## 4. Planning / Reflection

Current status: `[x]` Local Planning / Reflection completed.

- [x] `nexus plan day` and persistent task decomposition.
- [x] Task status, blockers, unresolved items, and notes.
- [x] `nexus review day` with today summary and tomorrow priorities.
- [x] Goals, check-ins, reminders, and RAG memory context.
- [x] Strict, gentle, academic, and startup Coach modes.

- [x] Calendar-aware preview/apply replanning with live event refresh and stale-calendar rejection.

## 5. Multi-Agent Architecture

Current status: `[x]` Bounded multi-agent coordination completed.

- [x] Memory Agent.
- [x] Tool Agent with allow-only autonomous MCP candidates.
- [x] Planner Agent.
- [x] Reflection Agent.
- [x] Coach Agent.
- [x] Shared artifacts and step/LLM/MCP/time budgets.
- [x] Partial-failure isolation and deterministic local fallback.
- [x] Privacy-safe traces and `nexus agent runs/show`.
- [x] Opt-in `--agents` behavior.

This is bounded orchestration, not an open-ended autonomous loop.

## 6. Advanced Long-Term Memory

Current status: `[x]` Local-first lifecycle completed.

- [x] Deterministic importance plus user override and pinning.
- [x] Exact duplicate merge and near-duplicate links.
- [x] Explicit supersession and bidirectional conflicts.
- [x] Privacy-separated summaries with source lineage and inherited expiry.
- [x] Reversible archive/forget and confirmed forgotten-only purge.
- [x] Derived-summary privacy/expiry propagation and recursive purge.
- [x] Retention maintenance and dry-run previews.
- [x] Private, personal, and shared retrieval scopes.
- [x] Legacy-state normalization without destructive migration.

## 7. Proactive Trigger System

Current status: `[x]` Proactive local runtime completed.

- [x] Local profile with display name and IANA time zone.
- [x] Scheduler abstraction with deterministic `tick`, explicit `run`, status, and bounded foreground `start`.
- [x] Automatic morning briefing job.
- [x] Automatic evening review job.
- [x] Stale-goal reminder job.
- [x] Restart-safe `job + local date` occurrence claims and due/grace windows.
- [x] Cross-process-safe state revisions, scheduler claims, and atomic replacement.
- [x] Durable inbox-first notifications.
- [x] Cross-process-safe notification claims plus bounded corrupt/oversized-line recovery.
- [x] Optional console and bounded webhook delivery.
- [x] Normal and overnight quiet hours with deferred delivery and flush.
- [x] Partial-failure status when optional generation or delivery degrades.
- [x] Runtime jobs disabled until explicitly configured.

## 8. Frontend Dashboard

Current status: `[x]` Interactive local life-management Dashboard completed.

- [x] Packaged web Dashboard shell.
- [x] Responsive desktop/mobile navigation and stable controls.
- [x] Today view with tasks, schedules, reminders, and latest briefing/review.
- [x] Long-term goals view.
- [x] Eligible memory timeline.
- [x] Activity view for notifications, tools, MCP, Agents, and automations.
- [x] Masked Settings view.
- [x] Empty/error states and per-section failure isolation.
- [x] Loopback-only HTTP, exact routes, Host/Origin/CSRF validation, bounded snapshots, and six allowlisted actions.
- [x] Habit tracking panel with check-ins, streaks, and completion status.
- [x] Dedicated project-progress panel with progress bars and correction confirmation.
- [x] AI-suggestion panel with reasons, confidence, Calendar/RAG source types and degradation, accept, and dismiss.
- [x] Replan preview/apply dialog with explicit confirmation.

Generic browser-authored state mutation and remote Dashboard hosting are intentionally outside the current version.

## 9. Browser and Local Automation

Current status: `[x]` Named permissioned automation completed.

- [x] Fixed-URL browser adapter with mandatory matching host allowlist.
- [x] Read-only GitHub project inspection workflow.
- [x] Deterministic Markdown status-report workflow.
- [x] Fixed command argument-vector execution with `shell=False`.
- [x] Existing allowed-root boundaries for command working directories and report paths.
- [x] Bounded timeout, process-tree termination, and captured output.
- [x] deny/ask/allow policies with one-shot `--approve`.
- [x] No caller-supplied argument suffix or environment.
- [x] Bounded secret-safe durable audit with corrupt-tail tolerance.
- [x] CLI set/list/run/remove/audit operations with masked definitions.

Arbitrary LLM-authored commands and unattended ask-policy actions are intentionally unsupported.

## 10. Adaptive Life Workspace

Current status: `[x]` Phase 11 adaptive life workspace completed.

- [x] Habit model, CLI, atomic Dashboard increment check-ins, streaks, completion rates, and archive.
- [x] Project model, milestones, explicit/derived progress, correction history, links, archive, CLI, and Dashboard panel.
- [x] Explainable deterministic AI Suggestions 2.0 using local state, live read-only calendar conflicts/focus windows, and eligible RAG memories, with independent degradation, optional structure-safe LLM wording, CLI lifecycle, approved allowlisted actions, and Dashboard panel.
- [x] Calendar-aware replan preview and conflict-safe apply with state revision, calendar fingerprint, integrity check, and read-only live-calendar fallback.
- [x] Unified `nexus ask` deterministic Chinese/English router with mutation previews, low-risk check-ins, static schemas, and optional strict-JSON LLM parsing.
- [x] Allowlisted loopback Dashboard mutation endpoints with exact routes, Origin/CSRF protection, strict JSON schemas, and a 16 KiB body limit.
- [x] Permissioned Nexus MCP stdio server with seven bounded read tools, five approval-gated mutation tools, policy overrides, and content-free secret-safe audit summaries.
- [x] Phase 11 audits, focused tests, English/Chinese documentation, and desktop/mobile browser verification.

## 11. Research Companion

Current status: `[x]` Research Companion 2.0 completed with bounded acquisition, verified corpora, restricted experiments, and terminating research loops.

- [x] Persistent research projects, questions, scholarly sources, notes, experiments, investigation history, syntheses, and follow-ups.
- [x] Explicitly enabled read-only Crossref scholarly metadata search through existing permission and audit controls.
- [x] RAG-enriched investigation and synthesis with eligible memory only.
- [x] Stable evidence references, open questions, experiment summaries, next actions, and explicit insufficient-evidence outcomes.
- [x] Evidence-grounded follow-up questions with structure-safe optional LLM wording.
- [x] Full CLI workflow plus bounded English/Chinese unified-conversation reads.
- [x] Privacy-filtered ninth Dashboard Research view.
- [x] Independent Literature/RAG/LLM degradation without losing local research state.
- [x] Full-text PDF/Markdown/TXT ingestion and page/line-aware chunk citation verification.
- [x] Explicit HTTPS web-page acquisition with SSRF-oriented destination checks and bounded extraction.
- [x] Repository indexing without code execution and explicitly approved restricted experiment execution. The runner is not an OS/container sandbox.
- [x] Terminating Planner/Retriever/Analyst/Critic/Reflection research loops with shared bounds, verified references, degradation, and persisted traces.
- [x] Corpus-aware synthesis/follow-up answers, CLI lifecycle, read-only unified-conversation access, and privacy-filtered Dashboard document/run summaries.

## 12. Long-Term Multimodal and Embodied Interfaces

Current status: `[-]` Roadmap Phase 13 is partially complete: the Voice Assistant MVP subset is delivered, while the remaining multimodal and embodied work is not started.

- [x] Explicit duration-bounded push-to-talk recording, local `faster-whisper` transcription, and operating-system speech output.
- [x] Voice conversation through existing intent/approval handling and narrated briefings through existing briefing/runtime services.
- [ ] Continuous listening and wake-word activation.
- [ ] Permissioned visual context.
- [ ] Family profiles.
- [ ] Smart-home adapters.
- [ ] Robotics adapter with simulation-first safety controls.
- [ ] Connect future voice/vision interfaces to permissioned Research Companion workflows.

The delivered voice subset reuses conversation, briefing, runtime, permission, and configuration boundaries. Its initial adapters keep audio local, and it has no continuous listener or wake word. Remaining interfaces should reuse the existing memory, planning, runtime, permission, configuration-transaction, and audit layers. They are not current AGI capabilities.

## Maintenance Rules

- [ ] Update this checklist after every important feature.
- [ ] Update `docs/file_inventory.md` after every important file change.
- [ ] Keep `README.md` and `README_zh.md` synchronized for user-facing changes.
- [ ] Run relevant tests and release checks before committing.
- [ ] Ask whether to push unless the user already requested a push.
- [ ] Never commit API keys or any file under `.nexus/`.
