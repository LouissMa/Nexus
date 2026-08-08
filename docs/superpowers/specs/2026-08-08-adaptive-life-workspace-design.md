# Adaptive Life Workspace Design

## Goal

Phase 11 turns the Phase 10 operational core into an adaptive life workspace. Users can track habits and projects, receive explainable suggestions, replan around calendar constraints, use one natural-language entry point, and expose approved Nexus capabilities through an MCP server.

The phase remains local-first and permission-bounded. It does not introduce arbitrary browser mutations, arbitrary LLM-authored commands, or an open-ended autonomous loop.

## Delivery Packages

1. **Dashboard 2.0:** habits, projects, deterministic suggestions, CLI workflows, and allowlisted loopback mutation endpoints.
2. **Adaptive Planning:** calendar-aware replanning and a unified natural-language router with deterministic local intents and optional LLM parsing.
3. **Nexus MCP Server:** read and mutation tools backed by the same service, validation, permission, and audit boundaries as CLI and Dashboard.

Voice, vision, smart-home, family accounts, robotics, remote Dashboard hosting, and cloud synchronization remain outside this phase.

## Architecture

```text
CLI / Dashboard / Conversation / Nexus MCP Server
                         |
                    NexusService
                         |
       +-----------------+------------------+
       |                 |                  |
 HabitService      ProjectService     ReplanningService
       |                 |                  |
       +----------- SuggestionEngine -------+
                         |
           JsonStore / RAG / ToolManager
                         |
       file transactions / permissions / audit
```

User-facing entry points contain transport and presentation logic only. Domain decisions live in focused services and are persisted through `JsonStore.mutate`, preserving cross-process revision and atomic-write guarantees.

## Persistent Model

`state.json` gains three backward-compatible top-level collections.

### Habits

Each habit contains `id`, `name`, optional `description` and `goal_id`, a daily or ISO-weekday cadence, `target_count`, status timestamps, and bounded check-ins. One habit has at most one normalized check-in per local date. Repeated check-in updates that date. Streaks and completion rates are derived from cadence and check-ins.

### Projects

Each project contains `id`, name, description, status, priority, target date, milestones with stable IDs, links to existing goals/tasks, and bounded progress entries. Progress derives from completed milestones when milestones exist; otherwise the latest explicit percentage is used. Progress is monotonic unless an explicit correction flag is supplied.

### Suggestions

Suggestions are bounded generated snapshots, not a hidden memory stream. Each item contains `id`, kind, title, reason, allowlisted action, confidence, source IDs, creation/expiry times, and status (`open`, `accepted`, `dismissed`). Acceptance invokes one allowlisted service action. Expired suggestions are excluded.

## Dashboard 2.0

The Dashboard adds Habits, Projects, and Suggestions while retaining Today, Goals, Memory, Activity, and Settings.

The loopback server adds exact JSON endpoints:

- `GET /api/snapshot`
- `POST /api/habits/{id}/check-in`
- `POST /api/projects/{id}/progress`
- `POST /api/suggestions/{id}/accept`
- `POST /api/suggestions/{id}/dismiss`
- `POST /api/replan/preview`
- `POST /api/replan/apply`

Mutation endpoints accept `application/json` only, reject bodies above 16 KiB, and validate Host, Origin, method, route, and schema. A random per-process CSRF token is embedded in the served page and required through `X-Nexus-CSRF`. There is no endpoint for credentials, arbitrary commands, arbitrary tool calls, or automation definitions.

The UI uses compact operational tables, timelines, progress bars, streak indicators, checkboxes, and confirmation dialogs. It remains responsive, keyboard accessible, and layout-stable.

## Suggestion Engine

The deterministic engine works offline. It ranks a bounded list from quiet goals, pending or blocked tasks, habit misses, project milestones and dates, calendar conflicts/free windows, and eligible RAG memories. Every suggestion includes a reason and source IDs. Suggestions never execute automatically. Optional LLM rewriting may improve wording but cannot alter the structured action, sources, confidence, or permission requirement.

## Calendar-Aware Replanning

Replanning consumes normalized read-only calendar events, profile time zone, today's tasks and estimates, quiet hours, and working hours. It computes free windows and returns kept, moved, shortened, and unscheduled tasks.

Rules:

1. Calendar events are immutable constraints.
2. Completed tasks never move.
3. In-progress tasks are kept when possible.
4. Higher priorities receive earlier suitable windows.
5. No task is deleted; tasks without capacity become `unscheduled` with a reason.
6. Apply requires the preview state revision and calendar fingerprint to match current inputs.

This phase does not write events back to calendar providers.

## Unified Conversation Entry Point

`nexus ask "..."` returns an envelope containing intent, confidence, approval requirement, result, and safe explanation.

Deterministic parsing handles showing today/goals/habits/projects/suggestions/runtime; adding memory/goal/habit/project; habit check-in and task/project progress; daily planning; replan preview; briefing; and review.

When local parsing is ambiguous and an LLM is configured, Nexus sends a bounded catalog of allowed intents and schemas. The model must return strict JSON, which Nexus validates before dispatch. It cannot name shell commands, arbitrary URLs, unregistered tools, or raw MCP calls.

Reads execute immediately. Mutations return a preview unless explicitly low-risk or the caller passes `--approve`. Destructive operations are not exposed through conversation.

## Nexus MCP Server

Nexus gains an optional stdio MCP server. Streamable HTTP serving remains future work because remote authentication is outside this local-first phase.

Read tools:

- `nexus_today`
- `nexus_search_memory`
- `nexus_list_goals`
- `nexus_list_habits`
- `nexus_list_projects`
- `nexus_get_suggestions`
- `nexus_preview_replan`

Mutation tools:

- `nexus_add_memory`
- `nexus_add_goal`
- `nexus_check_in_habit`
- `nexus_update_project_progress`
- `nexus_apply_replan`

The server starts only through `nexus mcp-server stdio`. Mutation tools default to `ask`; because stdio has no confirmation UI, `ask` fails unless the launch command includes a bounded one-session approval list. Inputs and outputs have schema, collection, text, and response-size limits. Audits contain tool name, decision, status, duration, and sanitized summaries, never raw memory text or secrets.

## Error Handling and Safety

- Legacy state normalizes without destructive migration.
- Invalid cadence, dates, progress, IDs, JSON, routes, origins, and CSRF fail before persistence.
- Calendar, tool, LLM, and RAG failures produce partial deterministic results.
- Replan apply rejects stale state or changed calendar fingerprints.
- Conversation dispatches only intents in the static registry.
- Dashboard section failures remain isolated.
- MCP tools use bounded inputs, normalized public errors, and secret-safe audit.
- All mutations use `JsonStore.mutate`; transports never write files directly.

## Testing

Tests use temporary `NEXUS_HOME`, injected clocks, deterministic calendar events, fake LLM clients, and in-memory MCP sessions. Coverage includes habit cadence/idempotency/streaks; project milestones and corrections; suggestion ranking/expiry/acceptance; free-window calculation and stale previews; local and LLM intent parsing and approval; Dashboard CSRF/routes/body limits/privacy/desktop/mobile behavior; MCP discovery, schemas, stdio lifecycle, policies, bounds, and audit; plus Phase 1-10 compatibility.

## Success Criteria

Phase 11 is complete when a user can track habits and projects from CLI and Dashboard, inspect and approve explainable suggestions, preview and apply a conflict-safe daily replan around real calendar events, use common workflows through `nexus ask`, and connect an external MCP client to an explicitly launched permissioned Nexus stdio server. Every capability retains offline fallback, local privacy, bounded data, cross-process-safe state, and auditable permission decisions.
