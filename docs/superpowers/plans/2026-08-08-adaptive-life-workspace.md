# Adaptive Life Workspace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver habits, projects, explainable suggestions, calendar-aware replanning, a unified natural-language entry point, Dashboard 2.0 mutations, and a permissioned Nexus stdio MCP server.

**Architecture:** Focused domain services persist through `JsonStore.mutate` and are reused by CLI, Dashboard, conversation, and MCP transports. Deterministic local behavior is authoritative; optional LLM output can select a validated intent or rewrite wording but cannot invent actions.

**Tech Stack:** Python 3.11+, standard-library JSON/HTTP/date handling, existing OpenAI-compatible client, optional official `mcp` SDK, packaged HTML/CSS/JavaScript, pytest, Ruff, Playwright.

## Global Constraints

- Preserve all Phase 1-10 CLI and state compatibility.
- Keep core habit, project, suggestion, replan, and deterministic conversation flows API-key free.
- Persist every state mutation through `JsonStore.mutate`.
- Bound user text, collections, HTTP request/response bodies, LLM prompts, and MCP input/output.
- Dashboard remains loopback-only; mutation routes require trusted Host/Origin, exact route, JSON content type, and `X-Nexus-CSRF`.
- Calendar integration remains read-only.
- Conversation and MCP cannot execute arbitrary commands, URLs, automations, or unregistered tools.
- Update both READMEs, checklist, roadmap, architecture, and file inventory before release.
- Commit and push each independently verified task to `main`.

---

### Task 1: Habit Domain and CLI

**Files:**
- Create: `src/nexus/habits.py`
- Modify: `src/nexus/store.py`
- Modify: `src/nexus/service.py`
- Modify: `src/nexus/cli.py`
- Create: `tests/test_habits.py`
- Create: `tests/test_habit_cli.py`

**Interfaces:**
- Produces: `HabitService.add(name, description, cadence, weekdays, target_count, goal_id, now) -> dict`
- Produces: `HabitService.list(now, include_archived=False) -> list[dict]`
- Produces: `HabitService.check_in(habit_id, local_date, count, note, now) -> dict`
- Produces: `HabitService.archive(habit_id, now) -> dict`
- Produces: `habit_summary(habit, today) -> dict`

- [x] Write failing tests for daily/weekday validation, idempotent same-day check-in, derived streak/completion, archive, legacy normalization, and concurrent mutation.

```python
def test_same_day_check_in_updates_in_place(tmp_path):
    service = HabitService(JsonStore(tmp_path / "state.json"), timezone="Asia/Shanghai")
    habit = service.add("Read", "", "daily", (), 1, None, now=NOW)
    service.check_in(habit["id"], "2026-08-08", 1, "morning", now=NOW)
    result = service.check_in(habit["id"], "2026-08-08", 2, "evening", now=NOW)
    assert result["summary"]["today_count"] == 2
    assert len(result["habit"]["check_ins"]) == 1
```

- [x] Run `python -m pytest tests/test_habits.py tests/test_habit_cli.py -q` and confirm failures are caused by missing habit interfaces.
- [x] Implement bounded records, cadence calculations, service wrappers, and `nexus habit add|list|check-in|archive`.
- [x] Run focused tests, `python -m ruff check src/nexus/habits.py tests/test_habits.py tests/test_habit_cli.py`, and AST parsing.
- [x] Update checklist/file inventory, commit `feat: add habit tracking`, and push `main`.

### Task 2: Project Domain and CLI

**Files:**
- Create: `src/nexus/projects.py`
- Modify: `src/nexus/store.py`
- Modify: `src/nexus/service.py`
- Modify: `src/nexus/cli.py`
- Create: `tests/test_projects.py`
- Create: `tests/test_project_cli.py`

**Interfaces:**
- Produces: `ProjectService.add(...) -> dict`
- Produces: `ProjectService.add_milestone(project_id, title, target_date, now) -> dict`
- Produces: `ProjectService.update_milestone(project_id, milestone_id, status, now) -> dict`
- Produces: `ProjectService.update_progress(project_id, percent, note, correction, now) -> dict`
- Produces: `ProjectService.list(include_archived=False) -> list[dict]`

- [x] Write failing tests for milestone-derived progress, explicit progress, monotonic enforcement, correction, target-date validation, links, and mutation.
- [x] Run the focused tests and verify RED.
- [x] Implement project records and `nexus project add|list|milestone-add|milestone-update|progress|archive`.
- [x] Run focused tests, Ruff, and AST parsing.
- [x] Update docs, commit `feat: add project progress tracking`, and push.

### Task 3: Explainable Suggestion Engine

**Files:**
- Create: `src/nexus/suggestions.py`
- Modify: `src/nexus/store.py`
- Modify: `src/nexus/service.py`
- Modify: `src/nexus/cli.py`
- Create: `tests/test_suggestions.py`
- Create: `tests/test_suggestion_cli.py`

**Interfaces:**
- Produces: `SuggestionEngine.generate(state, now, calendar=None, memories=None, limit=10) -> list[dict]`
- Produces: `SuggestionService.list(now, refresh=False) -> list[dict]`
- Produces: `SuggestionService.accept(suggestion_id, approved, now) -> dict`
- Produces: `SuggestionService.dismiss(suggestion_id, now) -> dict`

- [x] Write failing tests for quiet goals, blocked tasks, streak risk, milestone deadlines, stable ranking/IDs, expiry, source IDs, acceptance allowlist, and dismissal.
- [x] Run focused tests and verify RED.
- [x] Implement deterministic generation and `nexus suggestion list|refresh|accept|dismiss`; keep optional LLM wording behind a structure-preserving adapter.
- [x] Run focused tests, Ruff, and AST parsing.
- [x] Update docs, commit `feat: add explainable life suggestions`, and push.

### Task 4: Calendar-Aware Replanning

**Files:**
- Create: `src/nexus/replanning.py`
- Modify: `src/nexus/service.py`
- Modify: `src/nexus/cli.py`
- Create: `tests/test_replanning.py`
- Create: `tests/test_replanning_cli.py`

**Interfaces:**
- Produces: `ReplanningService.preview(plan_date, events, working_hours, now) -> dict`
- Produces: `ReplanningService.apply(preview, events, now) -> dict`
- Preview fields: `id`, `state_revision`, `calendar_fingerprint`, `kept`, `moved`, `shortened`, `unscheduled`, `degradations`.

- [x] Write failing tests for free windows, overlapping/all-day events, priorities, completed/in-progress tasks, unscheduled reasons, calendar failure fallback, and stale apply.
- [x] Run focused tests and verify RED.
- [x] Implement deterministic interval allocation and `nexus replan preview|apply`; apply only scheduling fields and preserve task content/status.
- [x] Run focused tests, Ruff, and AST parsing.
- [x] Update docs, commit `feat: add calendar aware replanning`, and push.

### Task 5: Unified Conversation Router

**Files:**
- Create: `src/nexus/conversation.py`
- Modify: `src/nexus/service.py`
- Modify: `src/nexus/cli.py`
- Create: `tests/test_conversation.py`
- Create: `tests/test_conversation_cli.py`

**Interfaces:**
- Produces: `Intent(name, arguments, confidence, source, requires_approval)`
- Produces: `IntentRegistry.parse_local(text) -> Intent | None`
- Produces: `ConversationService.handle(text, approved=False, use_llm=False) -> dict`
- Envelope fields: `intent`, `confidence`, `source`, `requires_approval`, `preview`, `result`, `explanation`, `degradations`.

- [ ] Write failing tests for Chinese/English local intents, ambiguity, strict LLM JSON, unknown intent/schema rejection, preview-before-mutation, low-risk check-in, and LLM fallback.
- [ ] Run focused tests and verify RED.
- [ ] Implement static schemas/dispatch and `nexus ask TEXT [--llm] [--approve] [--show-intent]`.
- [ ] Run focused tests, Ruff, and AST parsing.
- [ ] Update docs, commit `feat: add unified conversation entrypoint`, and push.

### Task 6: Dashboard 2.0 Snapshot and Mutation API

**Files:**
- Modify: `src/nexus/dashboard.py`
- Modify: `src/nexus/cli.py`
- Modify: `tests/test_dashboard.py`
- Modify: `tests/test_dashboard_cli.py`

**Interfaces:**
- Extends sections with `habits`, `projects`, and `suggestions`.
- Produces: `DashboardActions.check_in_habit`, `update_project_progress`, `accept_suggestion`, `dismiss_suggestion`, `preview_replan`, and `apply_replan`.
- Produces exact POST routes with 16 KiB JSON bound and CSRF validation.

- [ ] Write failing tests for section privacy/isolation, exact POST routes, content type, body bound, Host/Origin/CSRF, normalized errors, and absence of generic mutation.
- [ ] Run Dashboard tests and verify RED.
- [ ] Implement bounded snapshot sections, per-process CSRF bootstrap, action adapter, and allowlisted POST dispatch.
- [ ] Run Dashboard and backward-compatibility tests, Ruff, and AST parsing.
- [ ] Commit `feat: add dashboard life workspace api` and push.

### Task 7: Dashboard 2.0 Frontend

**Files:**
- Modify: `src/nexus/dashboard/index.html`
- Modify: `src/nexus/dashboard/dashboard.css`
- Modify: `src/nexus/dashboard/dashboard.js`
- Modify: `tests/test_dashboard.py`

**Interfaces:**
- Consumes snapshot sections and POST endpoints from Task 6.
- Produces responsive Habits, Projects, and Suggestions views plus replan preview/apply dialog.

- [ ] Add failing asset/DOM tests for tabs, semantic controls, safe `textContent`, CSRF header, loading/error/confirmation states, stable dimensions, and keyboard navigation.
- [ ] Run Dashboard tests and verify RED.
- [ ] Implement compact views, progress/streak visualization, check-in/progress controls, suggestions, and replan dialog using packaged assets only.
- [ ] Run tests and start the local server with realistic demo data.
- [ ] Verify Playwright screenshots and overlap checks at 1440px desktop and 390px mobile.
- [ ] Update docs, commit `feat: add dashboard life workspace views`, and push.

### Task 8: Permissioned Nexus MCP Server

**Files:**
- Create: `src/nexus/mcp_server.py`
- Modify: `src/nexus/config.py`
- Modify: `src/nexus/cli.py`
- Modify: `pyproject.toml`
- Create: `tests/test_mcp_server.py`
- Create: `tests/test_mcp_server_cli.py`

**Interfaces:**
- Produces: `NexusMCPTools.list_tools() -> list[dict]`
- Produces: `NexusMCPTools.call(name, arguments, session_approvals=()) -> dict`
- Produces: `run_stdio_server(service, policy, approvals) -> None`.
- CLI: `nexus mcp-server stdio [--approve-tool NAME]`.

- [ ] Write failing tests for exact tool catalog/schemas, bounded arguments/results, read tools, mutation deny/ask/allow, session approvals, errors, audit redaction, and SDK lifecycle.
- [ ] Run focused tests and verify RED.
- [ ] Implement the static adapter and official-SDK stdio server without enabling HTTP.
- [ ] Run focused MCP server tests plus existing MCP client tests, Ruff, and AST parsing.
- [ ] Update docs, commit `feat: expose nexus mcp server`, and push.

### Task 9: Release Integration and Verification

**Files:**
- Modify: `README.md`
- Modify: `README_zh.md`
- Modify: `docs/architecture.md`
- Modify: `docs/roadmap.md`
- Modify: `docs/aios_task_checklist.md`
- Modify: `docs/file_inventory.md`
- Modify: this plan

**Interfaces:**
- Produces synchronized user and maintainer documentation and completed Phase 11 checklist.

- [ ] Run all focused Phase 11 tests and fix regressions.
- [ ] Run `python -m pytest tests -q`, `python -m ruff check src tests`, changed-file format checks, AST parsing, and `git diff --check`.
- [ ] Scan tracked source/docs for API-key-shaped secrets and the previously disclosed key.
- [ ] Verify README command parity and all new important files in the inventory.
- [ ] Run independent release review and fix Critical/Important findings with regression tests.
- [ ] Repeat desktop/mobile Playwright verification.
- [ ] Mark Phase 11 complete, commit `docs: complete adaptive life workspace`, and push `main`.
