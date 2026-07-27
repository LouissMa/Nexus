# Proactive Runtime and Dashboard Design

## Goal

Phase 10 turns Nexus from an on-demand CLI into a local-first assistant that can
act at configured times, preserve notifications, expose its state in a web
dashboard, and run explicitly approved browser or local automations.

The phase remains bounded automation, not an open-ended autonomous loop.

## Scope

Phase 10 delivers:

1. A local user profile with display name and IANA time zone.
2. A scheduler for morning briefing, evening review, and stale-goal reminders.
3. Durable inbox notifications, optional console/webhook delivery, retry-safe
   run history, and quiet-hour deferral.
4. A local web dashboard for Today, goals, memories, notifications, tool/MCP
   audit, agent runs, scheduler status, and automation activity.
5. Named browser and local-command automations with deny/ask/allow policies,
   no shell execution, bounded output/time, and secret-safe audit records.
6. Built-in GitHub inspection and Markdown status-report workflows that reuse
   existing Nexus state and tool permissions.

Voice, smart-home, robotics, cloud accounts, remote dashboard hosting, arbitrary
LLM-authored commands, and unattended `ask` actions are outside this phase.

## Architecture

```text
                 +----------------------+
                 | Runtime CLI / daemon |
                 +----------+-----------+
                            |
                      Scheduler.tick
                            |
              +-------------+-------------+
              |             |             |
        Morning brief   Evening review   Stale review
              |             |             |
              +-------------+-------------+
                            |
                    NotificationCenter
                 inbox / console / webhook
                            |
                  .nexus/notifications.jsonl

Browser -> Local DashboardServer -> DashboardSnapshot
                                      |-- state.json
                                      |-- notifications
                                      |-- tool/MCP audits
                                      |-- agent traces
                                      +-- automation audit

CLI -> AutomationManager -> policy -> browser / command / built-in workflow
                                      |
                              automation_audit.jsonl
```

The scheduler, dashboard, and automation manager depend on existing service
interfaces. They do not call one another directly. Persistent data remains
under `NEXUS_HOME`; secrets and local policies remain in ignored
`config.local.json`.

## Configuration

`config.local.json` gains:

- `profile`: `display_name`, `timezone`.
- `runtime`: enabled jobs, local `HH:MM` times, grace period, poll interval,
  quiet hours, and notification channels.
- `automations`: named definitions with type, policy, timeout, and type-specific
  arguments.

Defaults are safe:

- Display name: `User`.
- Time zone: host local time zone when available, otherwise `UTC`.
- Runtime jobs are disabled until explicitly enabled.
- Inbox delivery is enabled; console and webhook are disabled.
- New automations default to `ask`.
- Dashboard binds to `127.0.0.1`.

Masked configuration output never includes webhook URLs, command environment
values, tokens, or other configured secrets.

## Scheduler Semantics

The scheduler exposes a deterministic `tick(now)` interface and a foreground
`run_forever()` loop. A job becomes due once its local scheduled time has
passed and remains eligible only within its configured grace period. Each
`job + local date` occurrence is claimed in state before execution, preventing
duplicate work after process restarts.

Runs have `running`, `success`, `partial`, or `error` status. A failed run is
recorded and can be retried explicitly with `nexus runtime run <job>`, but the
normal tick will not repeatedly spam the user on the same day.

Morning jobs call the existing briefing flow. Evening jobs call daily review.
Reminder jobs call proactive stale-goal review. Optional LLM, live-tool, and
agent settings are explicit runtime configuration, never inferred.

## Notifications and Quiet Hours

Every generated message is written to a durable local inbox before external
delivery. Quiet hours support normal and overnight ranges. During quiet hours,
non-urgent console/webhook delivery is marked `deferred`; the inbox record
remains visible. A later tick flushes deferred delivery after quiet hours.

Webhook calls use a bounded timeout and JSON payload. Delivery failures are
recorded per channel and make the scheduler result `partial`; they never erase
the generated briefing or review.

## Dashboard

The dashboard is a quiet operational interface, not a marketing page. It uses a
dense desktop layout and responsive mobile navigation with these views:

- Today: date, next scheduled jobs, tasks, reminders, latest briefing/review.
- Goals: active goals, cadence, latest check-in, and progress status.
- Memory: eligible memory timeline with privacy, importance, and tags.
- Activity: tool audit, MCP audit, agent traces, and automation audit.
- Settings: masked profile/runtime/permission summaries.

The first version is read-only. State changes continue through the permissioned
CLI, avoiding a browser-based mutation/CSRF surface. The HTTP server accepts
only loopback binds by default, applies response-size limits, serves packaged
static assets, and exposes JSON only under `/api/snapshot`.

## Automation Safety

An automation is a named, locally configured action:

- `browser`: opens a fixed `http` or `https` URL. Optional host allowlists must
  match the URL host.
- `command`: runs a fixed argument vector with `shell=False`, a bounded timeout,
  bounded captured output, an optional working directory inside configured
  roots, and no caller-supplied argument suffix.
- `github_inspect`: invokes the existing read-only GitHub adapter.
- `status_report`: writes a deterministic Markdown report to a configured path
  under an allowed root.

`deny` blocks execution, `ask` requires one-shot `--approve`, and `allow`
permits unattended scheduler/CLI execution. Audit records contain action names,
types, policy decisions, timestamps, status, duration, and sanitized summaries;
they never contain command output, URL query strings, environment values, or
secrets.

## Error Handling

- Invalid time zones, times, quiet-hour ranges, URLs, roots, and policies fail
  configuration before persistence.
- Corrupt JSONL audit/notification lines are skipped.
- Scheduler job failures are isolated and persisted.
- Dashboard snapshot sections fail independently and report section errors.
- Notification and automation exceptions are normalized into public errors.
- Command timeout terminates the child and records an error.
- Report paths outside allowed roots are rejected before writing.

## Testing

Tests use temporary `NEXUS_HOME` directories and injected clocks, HTTP senders,
browser openers, process runners, and service fakes.

Coverage includes:

- Schedule due/grace/deduplication and explicit runs.
- Time zones and overnight quiet hours.
- Durable notification deferral, flush, and partial delivery.
- Snapshot privacy and corrupt-log tolerance.
- Loopback dashboard HTTP routes and packaged asset rendering.
- Automation deny/ask/allow, URL validation, root boundaries, no-shell command
  execution, timeout/output bounds, and redacted audit.
- GitHub inspection and report workflows.
- CLI configuration and command smoke tests.
- Desktop and mobile Playwright screenshots with overlap checks.

## Success Criteria

Phase 10 is complete when a user can configure their identity and schedule,
leave `nexus runtime start` running, receive durable briefings/reviews/reminders
without duplicates, inspect all core state in a local responsive dashboard, and
run named approved automations with complete local auditability.
