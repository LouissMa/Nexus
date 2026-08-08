# Project File Inventory

This file explains the role of important Nexus files. Update it whenever a significant file is created, deleted, or changes responsibility.

## Root Files

- `README.md`: English product overview, synchronized quick start, current capabilities, credentials, Phase 10 runtime/dashboard/automation usage, security boundaries, and limitations.
- `README_zh.md`: Chinese version of the same user-facing structure and commands.
- `pyproject.toml`: Package metadata, `nexus` CLI entry point, core and optional dependency groups, and packaged Dashboard HTML/CSS/JavaScript assets.
- `.gitignore`: Excludes Python/build/test output plus the complete local `.nexus/` personal runtime directory.

## Application Core

- `src/nexus/__init__.py`: Package marker and package description.
- `src/nexus/cli.py`: Parses memory, goals, Planning/Reflection, briefing, configuration, integrations, MCP, Agents, proactive runtime, notifications, Dashboard, and automation commands. Phase 10 managers are built lazily so legacy commands do not initialize optional integrations.
- `src/nexus/service.py`: Application orchestration for memory/RAG, goals, tasks, planning, reflection, briefings, live context, MCP context, and Agent artifacts.
- `src/nexus/habits.py`: Habit validation, daily/weekday cadence, bounded idempotent check-ins, derived streak/completion summaries, archival, and cross-process-safe store mutation.
- `src/nexus/projects.py`: Project validation, goal/task links, milestone-derived and explicit progress, correction history, archival, and cross-process-safe store mutation.
- `src/nexus/suggestions.py`: Deterministic suggestion ranking, stable IDs, expiry/status persistence, allowlisted approved actions, and structure-safe optional LLM wording.
- `src/nexus/replanning.py`: Time-zone-aware calendar interval normalization, free-window allocation, preview integrity/freshness checks, and scheduling-field-only apply transactions.
- `src/nexus/conversation.py`: Static intent schemas, Chinese/English local parsing, strict optional LLM selection, approval previews, and registered service dispatch.
- `src/nexus/store.py`: Cross-process-safe JSON persistence for memories, goals, daily tasks, scheduler occurrence claims, and bounded scheduler run history; revision checks and atomic replacement prevent lost updates.
- `src/nexus/planning.py`: Daily-task construction, task statuses, and strict/gentle/academic/startup Coach profiles.
- `src/nexus/llm.py`: OpenAI-compatible chat-completions client, tier selection, timeouts, response normalization, and public errors.
- `src/nexus/config.py`: Canonical local configuration path and shared transactional mutation API. LLM, embedding, tool, profile, and runtime writers use one OS-backed cross-process lock and atomic replacement.
- `src/nexus/file_lock.py`: Canonical path identity plus process-local and OS-backed lock-file transactions reused by state and notification persistence.

## Proactive Runtime and Notifications

- `src/nexus/runtime_config.py`: Immutable `ProfileSettings` and `RuntimeSettings`; IANA time-zone, `HH:MM`, quiet-hour, job, channel, optional LLM/tool/Agent, Coach, and webhook validation; masked serialization.
- `src/nexus/notifications.py`: Durable inbox-first JSONL notifications, cross-process-safe delivery claims, normal/overnight quiet hours, console/webhook delivery, deferred flush, bounded records/read buffers, redaction, and corrupt/oversized-line repair.
- `src/nexus/scheduler.py`: Morning briefing, evening review, and stale-goal reminder scheduling; local-time due/grace windows; restart-safe occurrence claims; explicit manual runs; bounded foreground loop; status and partial-failure history.

## Permissioned Automation

- `src/nexus/automation.py`: Named `browser`, `command`, `github_inspect`, and `status_report` definitions; deny/ask/allow policy enforcement; one-shot approval; mandatory browser host allowlists; fixed `shell=False` argument vectors; root/path identity checks; process-tree timeout and output bounds; deterministic sanitized reports; transactional configuration; bounded secret-safe audit.

## Dashboard

- `src/nexus/dashboard.py`: Privacy-filtered `DashboardSnapshot` aggregation and standard-library `DashboardServer`. Builds Today, Goals, Memory, Activity, and Settings independently; bounds raw/serialized data; allows only loopback hosts, trusted Host/Origin, and exact read-only routes.
- `src/nexus/dashboard/index.html`: Packaged Dashboard shell, semantic sections, accessible navigation, loading/empty/error containers, and viewport metadata.
- `src/nexus/dashboard/dashboard.css`: Responsive desktop/mobile operational layout, stable controls, accessible focus/contrast, section states, and navigation behavior.
- `src/nexus/dashboard/dashboard.js`: Snapshot fetch, view switching, safe `textContent` rendering, schedules/tasks/reminders/latest briefing-review, goals, memory timeline, activity, and masked settings.
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
- `src/nexus/integrations/web_tools.py`: Open-Meteo, Todoist, GitHub, and Notion read-only adapters.
- `src/nexus/integrations/personal_tools.py`: Recurring iCalendar, read-only IMAP headers, and allowed-root filesystem adapters.
- `src/nexus/integrations/manager.py`: Adapter registry, permissioned execution, audit orchestration, and live briefing context.

## MCP Client

- `src/nexus/mcp/__init__.py`: Public MCP client exports.
- `src/nexus/mcp/models.py`: Stable MCP errors, tool schemas, and normalized call results.
- `src/nexus/mcp/config.py`: MCP server, policy, and Planning-binding validation and masking. All add/disable/remove/policy/binding mutations use the shared configuration transaction.
- `src/nexus/mcp/client.py`: Official MCP SDK lifecycle for stdio and Streamable HTTP discovery/calls.
- `src/nexus/mcp/manager.py`: Registry, deny/ask/allow enforcement, bounded retries, partial-failure Planning aggregation, and allow-only Agent candidates.
- `src/nexus/mcp/audit.py`: Sanitized MCP discovery, permission, retry, call, and failure audit with bounded recent-query output.

## Multi-Agent Coordination

- `src/nexus/agents/__init__.py`: Public Agent models and trace exports.
- `src/nexus/agents/models.py`: Shared run context, specialist results, step traces, run traces, and bounded resource counters.
- `src/nexus/agents/specialists.py`: Memory, Planner, Reflection, and Coach specialists with deterministic fallback and optional LLM generation.
- `src/nexus/agents/tool_agent.py`: Allow-only MCP candidate selection, deterministic bindings, strict-JSON LLM selection, complete input-schema validation, and partial failure.
- `src/nexus/agents/orchestrator.py`: Plan/review/briefing sequencing, artifacts, budgets, fallback, response assembly, and trace persistence.
- `src/nexus/agents/trace.py`: Recursively sanitized JSONL Agent-run persistence with bounded recent-query output and lookup.

## Documentation

- `docs/product_vision.md`: Product direction and long-term Personal AI Operating System vision.
- `docs/architecture.md`: Current component boundaries, persistence, configuration transactions, runtime, Dashboard, automation, failure isolation, and future adapters.
- `docs/roadmap.md`: Phase 1-10 implementation status, Phase 11 adaptive workspace, and Phase 12 research direction.
- `docs/aios_task_checklist.md`: Detailed progress tracker, including partial Dashboard expansion work.
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
- `tests/test_suggestions.py`: Suggestion ranking, stable IDs, sources, expiry, approval, allowlisted actions, dismissal, and LLM structure protection.
- `tests/test_suggestion_cli.py`: Suggestion refresh/list/accept CLI workflows and approval errors.
- `tests/test_replanning.py`: Calendar constraints, overlap/all-day handling, priorities, status preservation, shortening, degradation, and stale apply rejection.
- `tests/test_replanning_cli.py`: Replan preview/apply CLI workflow and persisted schedule verification.
- `tests/test_conversation.py`: Local and LLM intent parsing, schema rejection, mutation previews, low-risk check-ins, and approved dispatch.
- `tests/test_conversation_cli.py`: Unified `nexus ask` read, intent-inspection, preview, and approved mutation workflows.

## Phase 10 Tests

- `tests/test_runtime_config.py`: Defaults, IANA zones, clock/quiet-hour validation, masking, atomic replacement, rollback, and cross-process partial-update coordination.
- `tests/test_notifications.py`: Inbox-first persistence, normal/overnight deferral, channel delivery, thread/process-safe flush, corrupt/oversized-line recovery, bounds, and partial failures.
- `tests/test_scheduler.py`: Due/grace windows, local dates, cross-process-safe state mutation and claims, three job workflows, explicit retry, run history, status, pruning, and failure isolation.
- `tests/test_automation.py`: Definition/policy validation, browser hosts, fixed no-shell commands, process-tree timeout/output bounds, root/identity checks, GitHub/report workflows, transactional concurrency, durable redacted audit, rotation, and corrupt-tail repair.
- `tests/test_dashboard.py`: Privacy filtering, bounded raw data, malformed/corrupt inputs, section isolation, exact HTTP routes, Host/Origin checks, loopback-only binding, MIME/security headers, responsive assets, and wheel/sdist packaging.
- `tests/test_runtime_cli.py`: Profile/runtime sparse configuration, masking, conflicts, runtime status/tick/run/start, notifications, Ctrl+C, and stable errors.
- `tests/test_automation_cli.py`: Automation set/list/remove, masked definitions, policy outcomes, one-shot approval, audit, and validation exit codes.
- `tests/test_dashboard_cli.py`: Snapshot privacy, loopback serving, startup/shutdown behavior, stable errors, and optional-section dependency isolation.

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
