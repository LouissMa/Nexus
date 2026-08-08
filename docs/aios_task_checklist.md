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
8. Adaptive life workspace: Dashboard 2.0, calendar replanning, conversation, and Nexus MCP Server. Design drafted; review next.
9. Long-term multimodal/embodied interfaces. Future.

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

Current status: `[x]` Permissioned MCP client completed.

- [x] stdio and Streamable HTTP configuration and discovery.
- [x] Official-SDK gateway, schemas, and normalized results.
- [x] Per-tool deny, ask, and allow policies.
- [x] One-shot approval for ask-policy calls.
- [x] Bounded transport retry and secret-safe audit.
- [x] Explicit allow-policy Planning bindings.
- [x] Local Planning fallback when MCP is unavailable.

Exposing Nexus as an MCP server remains future work.

## 4. Planning / Reflection

Current status: `[x]` Local Planning / Reflection completed.

- [x] `nexus plan day` and persistent task decomposition.
- [x] Task status, blockers, unresolved items, and notes.
- [x] `nexus review day` with today summary and tomorrow priorities.
- [x] Goals, check-ins, reminders, and RAG memory context.
- [x] Strict, gentle, academic, and startup Coach modes.

Calendar-aware automatic replanning remains future work.

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

Current status: `[~]` Read-only responsive Dashboard completed; deeper life-management panels remain future.

- [x] Packaged web Dashboard shell.
- [x] Responsive desktop/mobile navigation and stable controls.
- [x] Today view with tasks, schedules, reminders, and latest briefing/review.
- [x] Long-term goals view.
- [x] Eligible memory timeline.
- [x] Activity view for notifications, tools, MCP, Agents, and automations.
- [x] Masked Settings view.
- [x] Empty/error states and per-section failure isolation.
- [x] Loopback-only HTTP, exact routes, Host/Origin validation, bounded snapshots, and read-only API.
- [ ] Habit tracking panel.
- [ ] Dedicated project-progress panel.
- [ ] AI-suggestion panel.

Browser-authored state mutation and remote Dashboard hosting are intentionally outside the current version.

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

Current status: `[ ]` Design completed; implementation not started.

- [ ] Habit tracking model, CLI, check-ins, streaks, and Dashboard panel.
- [ ] Project model, milestones, progress history, CLI, and Dashboard panel.
- [ ] Explainable deterministic AI suggestions with optional LLM wording.
- [ ] Calendar-aware replan preview and conflict-safe apply.
- [ ] Unified `nexus ask` deterministic router with optional strict-JSON LLM parsing.
- [ ] Allowlisted loopback Dashboard mutation endpoints with CSRF protection.
- [ ] Permissioned Nexus MCP stdio server with read and mutation tools.
- [ ] Phase 11 audits, tests, English/Chinese documentation, and browser verification.

## 11. Long-Term Multimodal and Embodied Interfaces

Current status: `[ ]` Research direction, not started.

- [ ] Voice input, wake-word flow, and speech output.
- [ ] Permissioned visual context.
- [ ] Smart-home adapters and family profiles.
- [ ] Robotics adapter with simulation-first safety controls.
- [ ] Deeper research-companion workflows for literature, code, and experiments.

These interfaces should reuse the existing memory, planning, runtime, permission, configuration-transaction, and audit layers. They are not current AGI capabilities.

## Maintenance Rules

- [ ] Update this checklist after every important feature.
- [ ] Update `docs/file_inventory.md` after every important file change.
- [ ] Keep `README.md` and `README_zh.md` synchronized for user-facing changes.
- [ ] Run relevant tests and release checks before committing.
- [ ] Ask whether to push unless the user already requested a push.
- [ ] Never commit API keys or any file under `.nexus/`.