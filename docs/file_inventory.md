# Project File Inventory

This file explains the role of important Nexus files. Update it whenever a significant file is created, deleted, or changes responsibility.

## Root Files

- `README.md`: English product overview, synchronized quick start, current capabilities, credentials, Dashboard/MCP Server/Research Companion usage, security boundaries, and limitations.
- `README_zh.md`: Chinese version of the same user-facing structure and commands.
- `pyproject.toml`: Package metadata, `nexus` CLI entry point, core and optional dependency groups including `voice`, and packaged Dashboard HTML/CSS/JavaScript assets.
- `.gitignore`: Excludes Python/build/test output plus the complete local `.nexus/` personal runtime directory.

## Application Core

- `src/nexus/__init__.py`: Package marker and package description.
- `src/nexus/cli.py`: Parses memory, goals, Planning/Reflection, briefing, voice, configuration, integrations, MCP client/server, Agents, proactive runtime, notifications, Dashboard, and automation commands. Optional managers and voice providers remain lazy where possible.
- `src/nexus/service.py`: Application orchestration for memory/RAG, goals, tasks, planning, reflection, briefings, live context, MCP context, and Agent artifacts.
- `src/nexus/habits.py`: Habit validation, daily/weekday cadence, bounded idempotent check-ins, atomic increments, derived streak/completion summaries, archival, and cross-process-safe store mutation.
- `src/nexus/projects.py`: Project validation, goal/task links, authoritative milestone-derived progress with explicit progress for milestone-free projects, correction history, archival, and cross-process-safe store mutation.
- `src/nexus/research.py`: Research project validation and persistence; question/source/note/experiment relationships; permissioned literature import deduplication; RAG/corpus synthesis; evidence-grounded follow-ups; uncertainty; history bounds; and optional structure-safe LLM wording.
- `src/nexus/research_corpus.py`: PDF/Markdown/TXT extraction, explicit safe HTTPS acquisition, bounded repository indexing, project-scoped sparse chunk indexes, search, atomic replacement, removal, and page/line-aware citation validation.
- `src/nexus/research_experiments.py`: Explicitly approved restricted process execution with allowed roots/executables, no shell, timeout, minimal environment, capped output, and research experiment persistence.
- `src/nexus/research_loop.py`: Terminating Planner/Retriever/Analyst/Critic/Reflection research workflow, verified findings, degradation, budgets, terminal outcomes, and bounded trace persistence.
- `src/nexus/suggestions.py`: Deterministic local/calendar/RAG suggestion ranking, stable evidence IDs and source types, bounded context/degradation persistence, expiry/status lifecycle, allowlisted approved actions, and structure-safe optional LLM wording.
- `src/nexus/replanning.py`: Time-zone-aware calendar interval normalization, free-window allocation, preview integrity/freshness checks, and scheduling-field-only apply transactions.
- `src/nexus/conversation.py`: Static intent schemas, Chinese/English local parsing, strict optional LLM selection, approval previews, and registered service dispatch.
- `src/nexus/store.py`: Cross-process-safe JSON persistence for memories, goals, daily tasks, scheduler occurrence claims, and bounded scheduler run history; revision checks and atomic replacement prevent lost updates.
- `src/nexus/planning.py`: Daily-task construction, task statuses, and strict/gentle/academic/startup Coach profiles.
- `src/nexus/llm.py`: OpenAI-compatible chat-completions client, tier selection, timeouts, response normalization, and public errors.
- `src/nexus/config.py`: Canonical local configuration path and shared transactional mutation API. LLM, embedding, tool, profile, runtime, and voice writers use one OS-backed cross-process lock and atomic replacement.
- `src/nexus/file_lock.py`: Canonical path identity plus process-local and OS-backed lock-file transactions reused by state and notification persistence.

## Voice Assistant

- `src/nexus/voice.py`: Voice provider protocols and result models; bounded input/output validation; temporary-recording cleanup; deterministic speech rendering; and conversation/briefing orchestration through existing services.
- `src/nexus/voice_providers.py`: Lazy optional `sounddevice` recorder and `faster-whisper` transcriber plus bounded Windows/macOS/Linux system speech adapters using fixed commands and `shell=False`.

## Proactive Runtime and Notifications

- `src/nexus/runtime_config.py`: Immutable `ProfileSettings` and `RuntimeSettings`; IANA time-zone, `HH:MM`, quiet-hour, job, channel, optional LLM/tool/Agent, Coach, and webhook validation; masked serialization.
- `src/nexus/notifications.py`: Durable inbox-first JSONL notifications, cross-process-safe delivery claims, normal/overnight quiet hours, console/webhook delivery, deferred flush, bounded records/read buffers, redaction, and corrupt/oversized-line repair.
- `src/nexus/scheduler.py`: Morning briefing, evening review, and stale-goal reminder scheduling; local-time due/grace windows; restart-safe occurrence claims; explicit manual runs; bounded foreground loop; status and partial-failure history.

## Permissioned Automation

- `src/nexus/automation.py`: Named `browser`, `command`, `github_inspect`, and `status_report` definitions; deny/ask/allow policy enforcement; one-shot approval; mandatory browser host allowlists; fixed `shell=False` argument vectors; root/path identity checks; process-tree timeout and output bounds; deterministic sanitized reports; transactional configuration; bounded secret-safe audit.

## Dashboard

- `src/nexus/dashboard.py`: Privacy-filtered `DashboardSnapshot` aggregation and standard-library `DashboardServer`. Builds nine isolated sections including bounded Research summaries; bounds data; allows only loopback hosts and exact routes; enforces Host, Origin, CSRF, content type, and request limits.
- `src/nexus/dashboard_actions.py`: Strict allowlisted schemas and service delegation for habit check-in, project progress, suggestion accept/dismiss, and replan preview/apply.
- `src/nexus/dashboard/index.html`: Packaged nine-view Dashboard shell, semantic Research section, accessible navigation, confirmation/replan dialogs, loading/empty/error containers, and viewport metadata.
- `src/nexus/dashboard/dashboard.css`: Responsive desktop/mobile operational layout, stable action controls and progress bars, accessible focus/contrast, dialogs, section states, and eight-tab mobile scrolling.
- `src/nexus/dashboard/dashboard.js`: Safe `textContent` rendering for all views plus CSRF-protected habit, project, suggestion, and replan interactions with busy/error/confirmation states.
- `pyproject.toml` package data: Includes all three Dashboard assets in wheel and source distributions.

## Long-Term Memory and RAG

- `src/nexus/memory_lifecycle.py`: Legacy normalization, deterministic importance, duplicate matching, lifecycle eligibility, transitions, expiry, privacy, and compression planning.
- `src/nexus/memory_service.py`: Persistent add/merge, update, relationships, archive/restore/forget/purge, compression, retention maintenance, and vector-index refresh outcomes.
- `src/nexus/embeddings.py`: Embedding provider interface plus local FastEmbed and OpenAI-compatible providers.
- `src/nexus/rag.py`: Sparse retrieval, semantic indexing, dense+sparse fusion, lifecycle/privacy filtering, stale-vector rejection, explainable context re-ranking, metadata, re-indexing, and fallback.
- `src/nexus/vector_store.py`: Local/remote Qdrant collection, upsert, search, clear, and status adapter.

## Real Tool Integrations

- `src/nexus/integrations/__init__.py`: Public integration package exports.
- `src/nexus/integrations/core.py`: Tool contracts, HTTP normalization, permission checks, structured results, and secret-safe JSONL audit.
- `src/nexus/integrations/web_tools.py`: Open-Meteo, Todoist, GitHub, Notion, and fixed-origin Crossref literature read-only adapters.
- `src/nexus/integrations/personal_tools.py`: Recurring iCalendar, read-only IMAP headers, and allowed-root filesystem adapters.
- `src/nexus/integrations/manager.py`: Adapter registry, permissioned execution, audit orchestration, and live briefing context.

## MCP Client

- `src/nexus/mcp/__init__.py`: Public MCP client exports.
- `src/nexus/mcp/models.py`: Stable MCP errors, tool schemas, and normalized call results.
- `src/nexus/mcp/config.py`: MCP server, policy, and Planning-binding validation and masking. All add/disable/remove/policy/binding mutations use the shared configuration transaction.
- `src/nexus/mcp/client.py`: Official MCP SDK lifecycle for stdio and Streamable HTTP discovery/calls.
- `src/nexus/mcp/manager.py`: Registry, deny/ask/allow enforcement, bounded retries, partial-failure Planning aggregation, and allow-only Agent candidates.
- `src/nexus/mcp/audit.py`: Sanitized MCP discovery, permission, retry, call, and failure audit with bounded recent-query output.
- `src/nexus/mcp_server.py`: Static 12-tool Nexus MCP catalog, strict JSON-schema and date validation, deny/ask/allow enforcement, session approvals, 64 KiB result ceiling, content-free audit summaries, and official-SDK stdio lifecycle.

## Multi-Agent Coordination

- `src/nexus/agents/__init__.py`: Public Agent models and trace exports.
- `src/nexus/agents/models.py`: Shared run context, specialist results, step traces, run traces, and bounded resource counters.
- `src/nexus/agents/specialists.py`: Memory, Planner, Reflection, and Coach specialists with deterministic fallback and optional LLM generation.
- `src/nexus/agents/tool_agent.py`: Allow-only MCP candidate selection, deterministic bindings, strict-JSON LLM selection, complete input-schema validation, and partial failure.
- `src/nexus/agents/orchestrator.py`: Plan/review/briefing sequencing, artifacts, budgets, fallback, response assembly, and trace persistence.
- `src/nexus/agents/trace.py`: Recursively sanitized JSONL Agent-run persistence with bounded recent-query output and lookup.

## Documentation

- `docs/product_vision.md`: Product direction and long-term Personal AI Operating System vision.
- `docs/architecture.md`: Current component boundaries, voice/conversation/runtime flow, persistence, configuration transactions, Dashboard, automation, failure isolation, and future adapters.
- `docs/roadmap.md`: Phase 1-12 and Research Companion 2.0 implementation status plus partial Phase 13 voice completion and remaining multimodal direction.
- `docs/aios_task_checklist.md`: Detailed progress tracker, including the completed Phase 13 Voice Assistant MVP subset and remaining multimodal work.
- `docs/file_inventory.md`: This responsibility index.
- `docs/superpowers/specs/2026-07-17-mcp-client-design.md`: Phase 7 MCP design and safety contract.
- `docs/superpowers/plans/2026-07-17-mcp-client.md`: Phase 7 implementation plan.
- `docs/superpowers/specs/2026-07-26-multi-agent-coordination-design.md`: Phase 8 Agent boundaries, budgets, and safety contract.
- `docs/superpowers/plans/2026-07-26-multi-agent-coordination.md`: Phase 8 implementation plan.
- `docs/superpowers/specs/2026-07-27-advanced-long-term-memory-design.md`: Phase 9 lifecycle and retrieval design.
- `docs/superpowers/plans/2026-07-27-advanced-long-term-memory.md`: Phase 9 implementation plan.
- `docs/superpowers/specs/2026-07-27-proactive-runtime-dashboard-design.md`: Phase 10 runtime, notification, Dashboard, automation, policy, and success criteria.
- `docs/superpowers/plans/2026-07-27-proactive-runtime-dashboard.md`: Phase 10 test-driven implementation and release-verification checklist.
- `docs/superpowers/specs/2026-08-08-adaptive-life-workspace-design.md`: Phase 11 habits, projects, suggestions, calendar replanning, conversation, Dashboard mutation, and Nexus MCP Server safety contract.
- `docs/superpowers/plans/2026-08-08-adaptive-life-workspace.md`: Phase 11 test-driven implementation order, interfaces, verification, documentation, and release checklist.

## Phase 11 Tests

- `tests/test_habits.py`: Habit validation, check-in idempotency, cadence-aware streak/completion derivation, archive, and legacy-state normalization.
- `tests/test_habit_cli.py`: Habit add/list/check-in/archive CLI workflows and validation errors.
- `tests/test_projects.py`: Project validation, milestones, progress derivation, correction rules, archival, and legacy-state normalization.
- `tests/test_project_cli.py`: Project add/list/milestone/progress/archive CLI workflows and validation errors.
- `tests/test_suggestions.py`: Local/calendar/RAG suggestion ranking, stable IDs, sources, context degradation, expiry, approval, allowlisted actions, dismissal, and LLM structure protection.
- `tests/test_suggestion_cli.py`: Suggestion refresh/list/accept workflows, live-calendar opt-in/degradation, and approval errors.
- `docs/superpowers/plans/2026-08-12-ai-suggestions-2.md`: Test-driven AI Suggestions 2.0 implementation and release checklist.
- `docs/superpowers/specs/2026-08-12-research-companion-mvp-design.md`: Research Companion evidence, retrieval, privacy, degradation, and product-surface contract.
- `docs/superpowers/plans/2026-08-12-research-companion-mvp.md`: Test-driven Research Companion implementation and release checklist.
- `tests/test_research.py`: Research domain, persistence, evidence relations, investigation, RAG synthesis, follow-up uncertainty, degradation, and LLM structure protection.
- `tests/test_research_cli.py`: End-to-end Research Companion CLI, live-tool degradation, errors, archive, and masked literature configuration.
- `tests/test_research_corpus.py`: Full-text extraction, stable chunks, sparse search, re-index rollback, removal, and citation integrity.
- `tests/test_research_acquisition.py`: HTTPS safety policy, bounded HTML extraction, repository limits/ignores, and line references.
- `tests/test_research_experiments.py`: Approval, allowlist/root enforcement, argument safety, timeout, output caps, and persistence.
- `tests/test_research_loop.py`: Verified evidence, deterministic specialist traces, terminal outcomes, degradation, and persistence.
- `docs/superpowers/specs/2026-08-12-research-companion-2-design.md`: Research Companion 2.0 corpus, acquisition, execution, Agent, privacy, and failure contract.
- `docs/superpowers/plans/2026-08-12-research-companion-2.md`: Test-driven Research Companion 2.0 implementation and release checklist.
- `tests/test_replanning.py`: Calendar constraints, overlap/all-day handling, priorities, status preservation, shortening, degradation, and stale apply rejection.
- `tests/test_replanning_cli.py`: Replan preview/apply CLI workflow and persisted schedule verification.
- `tests/test_conversation.py`: Local and LLM intent parsing, schema rejection, mutation previews, low-risk check-ins, and approved dispatch.
- `tests/test_conversation_cli.py`: Unified `nexus ask` read, intent-inspection, preview, and approved mutation workflows.

## Phase 13 Voice Tests

- `tests/test_voice.py`: Voice contracts, bounds, input validation, temporary-file cleanup, speech rendering, conversation approvals, and briefing/speech degradation.
- `tests/test_voice_providers.py`: Lazy optional imports, PCM WAV recording, Whisper transcription/model caching, OS command construction, path validation, timeout/output bounds, and provider errors without real audio hardware.
- `tests/test_voice_cli.py`: Transactional voice configuration, exact parser/CLI composition, provider/error boundaries, conversation and briefing forwarding, and synchronized documentation assertions.

## Phase 10 Tests

- `tests/test_runtime_config.py`: Defaults, IANA zones, clock/quiet-hour validation, masking, atomic replacement, rollback, and cross-process partial-update coordination.
- `tests/test_notifications.py`: Inbox-first persistence, normal/overnight deferral, channel delivery, thread/process-safe flush, corrupt/oversized-line recovery, bounds, and partial failures.
- `tests/test_scheduler.py`: Due/grace windows, local dates, cross-process-safe state mutation and claims, three job workflows, explicit retry, run history, status, pruning, and failure isolation.
- `tests/test_automation.py`: Definition/policy validation, browser hosts, fixed no-shell commands, process-tree timeout/output bounds, root/identity checks, GitHub/report workflows, transactional concurrency, durable redacted audit, rotation, and corrupt-tail repair.
- `tests/test_dashboard.py`: Privacy filtering, bounded raw data, malformed/corrupt inputs, section isolation, exact HTTP routes, Host/Origin checks, loopback-only binding, MIME/security headers, responsive assets, and wheel/sdist packaging.
- `tests/test_runtime_cli.py`: Profile/runtime sparse configuration, masking, conflicts, runtime status/tick/run/start, notifications, Ctrl+C, and stable errors.
- `tests/test_automation_cli.py`: Automation set/list/remove, masked definitions, policy outcomes, one-shot approval, audit, and validation exit codes.
- `tests/test_dashboard_cli.py`: Snapshot privacy, loopback serving, startup/shutdown behavior, stable errors, and optional-section dependency isolation.
- `tests/test_dashboard_actions.py`: New life-section filtering plus exact POST routes, CSRF bootstrap, content type, Origin, body bounds, and allowlisted action dispatch.
- `tests/test_dashboard_workspace_assets.py`: Eight-view semantic assets, safe DOM mutation calls, CSRF headers, dialogs, stable controls, progress visualization, and mobile navigation assertions.
- `tests/test_mcp_server.py`: Static catalog/schema, bounded reads, validation, deny/ask/allow, session approval, unknown tools, and secret-safe audit behavior.
- `tests/test_mcp_server_cli.py`: CLI registration, approval validation, and real official-SDK stdio initialize/list/call lifecycle.

## Other Test Suites

- `tests/test_cli.py`: Core CLI/service, local RAG, planning, reflection, briefing, and LLM fallback.
- `tests/test_integrations.py`: Real-tool adapters, recurrence, permissions, filesystem boundaries, audit, and live briefing.
- `tests/test_mcp*.py`: MCP configuration, gateway, transports, CLI, Planning, policies, retries, and audits.
- `tests/test_memory*.py`: Lifecycle, service, safety, quality, policy propagation, CLI errors, re-ranking, and review regressions.
- `tests/test_agent*.py`: Agent models, specialists, Tool Agent, orchestration, budgets, privacy, CLI, and traces.

## Local Runtime Data

The complete `.nexus/` directory is ignored by Git and can contain personal or secret data.

- `.nexus/state.json`: Memories, goals, tasks, scheduler claims, and runtime history.
- `.nexus/config.local.json`: Profile/runtime, provider, embedding/Qdrant, tool, MCP, and automation settings.
- `.nexus/notifications.jsonl`: Durable notification inbox and channel delivery state.
- `.nexus/tool_audit.jsonl`: Read-only integration audit.
- `.nexus/mcp_audit.jsonl`: MCP discovery/call audit.
- `.nexus/agent_runs.jsonl`: Privacy-safe Agent traces.
- `.nexus/automation_audit.jsonl`: Named automation decisions and outcomes.
- `.nexus/qdrant/`: Local vector index.
- `.nexus/models/`: Local embedding model cache.
- `.nexus/*.lock`: Configuration and audit coordination locks.

## Generated and Cache Files

- `.pytest_cache/`, `.ruff_cache/`, `__pycache__/`: Test, lint, and bytecode caches.
- `build/`, `dist/`, `*.egg-info/`: Generated package artifacts.
- `.tmp/`, `.test-tmp/`, `test-output-*/`: Local test scratch/output.
- `.superpowers/`: Ignored implementation-session reports and ledgers; approved specs and plans remain under tracked `docs/superpowers/`.
