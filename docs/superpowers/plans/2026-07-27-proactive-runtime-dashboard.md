# Proactive Runtime and Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a proactive local runtime, durable notifications, a responsive
dashboard, and permissioned browser/local automation to Nexus.

**Architecture:** Focused runtime, notification, dashboard, and automation
modules reuse `NexusService`, existing tool managers, JSON state, and
secret-safe logs. Configuration remains local and ignored; all automation is
named and policy bounded.

**Tech Stack:** Python 3.11 standard library, existing Nexus service/tool/MCP
layers, HTML/CSS/JavaScript, pytest, Playwright.

## Global Constraints

- Default to local/offline operation and loopback-only dashboard hosting.
- Runtime jobs are disabled until explicitly configured.
- New automations default to `ask`; unattended execution requires `allow`.
- Command execution always uses an argument vector and `shell=False`.
- Never expose API keys, webhook URLs, command output, or personal memory text
  in audit records.
- Follow test-driven development for every behavior change.

---

### Task 1: Profile and Runtime Configuration

**Files:**
- Create: `src/nexus/runtime_config.py`
- Modify: `src/nexus/config.py`
- Test: `tests/test_runtime_config.py`

**Interfaces:**
- Produces: `ProfileSettings`, `RuntimeSettings`, `load_runtime_settings`,
  `update_profile_settings`, `update_runtime_settings`, and masked serializers.

- [x] Write failing tests for defaults, IANA zones, `HH:MM` validation,
  overnight quiet hours, job configuration, and secret masking.
- [x] Run `pytest tests/test_runtime_config.py -q` and confirm feature failures.
- [x] Implement immutable validated settings and local-config persistence.
- [x] Run `pytest tests/test_runtime_config.py -q` and confirm it passes.

### Task 2: Durable Notification Center

**Files:**
- Create: `src/nexus/notifications.py`
- Test: `tests/test_notifications.py`

**Interfaces:**
- Consumes: `RuntimeSettings`.
- Produces: `NotificationCenter.publish`, `flush_deferred`, `recent`, and
  `is_quiet_time`.

- [x] Write failing tests for inbox-first persistence, quiet-hour deferral,
  overnight ranges, webhook/console delivery, failure isolation, and flush.
- [x] Run `pytest tests/test_notifications.py -q` and confirm feature failures.
- [x] Implement bounded channels and durable JSONL records.
- [x] Run `pytest tests/test_notifications.py -q` and confirm it passes.

### Task 3: Proactive Scheduler

**Files:**
- Create: `src/nexus/scheduler.py`
- Modify: `src/nexus/store.py`
- Test: `tests/test_scheduler.py`

**Interfaces:**
- Consumes: `NexusService`, `NotificationCenter`, profile/runtime settings.
- Produces: `ProactiveScheduler.tick`, `run_job`, `run_forever`, and
  `scheduler_status`.

- [x] Write failing tests for due windows, local dates, occurrence claims,
  morning/evening/reminder dispatch, explicit retries, and partial failures.
- [x] Run `pytest tests/test_scheduler.py -q` and confirm feature failures.
- [x] Implement deterministic scheduler state and bounded foreground loop.
- [x] Run `pytest tests/test_scheduler.py -q` and confirm it passes.

### Task 4: Permissioned Automation

**Files:**
- Create: `src/nexus/automation.py`
- Test: `tests/test_automation.py`

**Interfaces:**
- Consumes: local config, `ToolManager`, `JsonStore`.
- Produces: automation validation/configuration, `AutomationManager.run`,
  built-in GitHub inspection/status report workflows, and audit inspection.

- [x] Write failing tests for policy gates, URL/host validation, `shell=False`,
  timeout/output limits, root-safe report writes, workflows, and audit
  redaction.
- [x] Run `pytest tests/test_automation.py -q` and confirm feature failures.
- [x] Implement named adapters and policy-bounded execution.
- [x] Run `pytest tests/test_automation.py -q` and confirm it passes.

### Task 5: Dashboard Snapshot and HTTP Server

**Files:**
- Create: `src/nexus/dashboard.py`
- Create: `src/nexus/dashboard/index.html`
- Create: `src/nexus/dashboard/dashboard.css`
- Create: `src/nexus/dashboard/dashboard.js`
- Test: `tests/test_dashboard.py`

**Interfaces:**
- Consumes: state, notification/audit/trace stores, masked settings.
- Produces: `DashboardSnapshot.build` and `DashboardServer`.

- [x] Write failing tests for privacy-filtered snapshots, corrupt logs,
  section errors, HTTP routes, MIME types, loopback defaults, and traversal
  rejection.
- [x] Run `pytest tests/test_dashboard.py -q` and confirm feature failures.
- [x] Implement the snapshot aggregator and standard-library HTTP server.
- [x] Build the responsive Today/Goals/Memory/Activity/Settings interface with
  fixed-size controls, accessible navigation, empty/error states, and no
  nested cards.
- [x] Run `pytest tests/test_dashboard.py -q` and confirm it passes.

### Task 6: CLI Integration

**Files:**
- Modify: `src/nexus/cli.py`
- Test: `tests/test_runtime_cli.py`
- Test: `tests/test_automation_cli.py`
- Test: `tests/test_dashboard_cli.py`

**Interfaces:**
- Consumes: all Phase 10 managers.
- Produces: `nexus config profile`, `nexus config runtime`, `nexus runtime`,
  `nexus notifications`, `nexus dashboard`, and `nexus automation` commands.

- [x] Write failing CLI tests for configuration, masked output, ticks/manual
  runs, inbox inspection, dashboard serving options, automation approval, and
  error exit codes.
- [x] Run the three Phase 10 CLI test files and confirm feature failures.
- [x] Wire parser and dispatch paths without changing existing command output.
- [x] Run the three Phase 10 CLI test files and confirm they pass.

### Task 7: Documentation and Release Verification

**Files:**
- Modify: `README.md`
- Modify: `README_zh.md`
- Modify: `docs/architecture.md`
- Modify: `docs/roadmap.md`
- Modify: `docs/aios_task_checklist.md`
- Modify: `docs/file_inventory.md`
- Modify: `.gitignore`

**Interfaces:**
- Produces: complete Phase 10 user and maintainer documentation.

- [x] Document setup, runtime lifecycle, quiet hours, Dashboard URL, automation
  policies, security boundaries, and current feature list in both languages.
- [x] Mark Phase 10 checklist items accurately and register every important
  new file.
- [x] Run Phase 10 tests, the full test suite, Ruff, AST parsing, and
  `git diff --check`.
- [x] Start the dashboard and verify desktop/mobile screenshots and layout
  behavior with Playwright.
- [x] Scan tracked release files for API-key-shaped secrets.
- [x] Request independent code review, fix findings with regression tests, and
  repeat verification.
- [x] Commit all completed work and push `main` to GitHub.



