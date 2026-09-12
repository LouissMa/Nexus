# Durable Execution (Phase 15.3)

Date: 2026-09-12. This extends the Phase 15.2 in-memory runtime design.

## Delivered Scope

The CLI creates a local run ID and stores goal, decisions consumed, observations,
pending action, repeat counters, active-time snapshots and status in SQLite.
`executor runs` lists the latest 100 runs; `show ID` inspects a snapshot.
`resume ID` continues the same run. `run` always creates a new one.
SQLite is separate from the personal JsonStore. No dependency was added.

## Checkpoints and Recovery

| Boundary | Durable phase | Recovery |
| --- | --- | --- |
| Before model call | deciding; decision already counted | Ask model again within remaining budget |
| After valid tool decision | tool_pending | Dispatch the pending action, subject to current policy |
| Before registry dispatch | tool_running | Unknown outcome after crash; stop for review |
| After successful/known tool result | idle; observation recorded | Continue planning without replaying the tool |
| Approval required | tool_pending / waiting_approval | Exact single-use token required |
| Clarification required | idle / waiting_input | Explicit bounded user answer required |

Snapshot failure before dispatch prevents the call. Failure after dispatch leaves
an uncertain durable marker, so resume never assumes that nothing happened.
Even a read interrupted at dispatch is conservatively held for review.
A per-run OS file lock excludes simultaneous runners and releases on process exit.
Lock files remain in the local home; deleting a live lock file is unsafe.
Pause/cancel requests use separate short SQLite transactions and survive snapshots.

Runtime statuses include created, running, waiting_approval, waiting_input, paused,
cancelled, needs_review, reported_complete, failed, model_failed, no_tools,
budget_exhausted, context_limit, repeated_action and invalid_completion.
These are not a universal workflow engine or an independent success assessment.

## Approvals and Controls

`resume ID --approval-token TOKEN` authorizes one pending occurrence only. A
SHA-256 fingerprint covers tool name, arguments, schema/contract, current policy
and adapter configuration. A configuration change rotates the token and requires
inspection again. A denied policy is never overridden. Raw adapter configuration
is not copied into the database. Registry policy checks still run at dispatch;
this does not create an atomic transaction with external service configuration.

`resume ID --answer TEXT` records a response to a pending question. Model prompts
include those answers separately from untrusted tool observations.
`pause ID` and `cancel ID` request cooperative stopping; inspect control_requested
as well as status. A blocked tool must return before the runner can acknowledge
the request. Cancellation cannot be cleared by resume. No process kill is implied.

Step and repeat counters are retained. The saved active-time budget excludes
human waiting and is not automatically replenished. Time since the last committed
checkpoint can be lost in a hard crash; this is not a strict billing guarantee.
The existing maximum decision/time limits remain 50 and 600 seconds.

## Uncertain Effects

`resolve ID --outcome completed|not-executed --note TEXT` records the user's
independent inspection. It never calls a tool or creates a successful tool result.
Completed clears the pending action and retains repeat protection. Not-executed
releases that attempt's repeat count and keeps the pending action for later resume,
with fresh approval when policy requires it. Partial/unknown effects should not be
resolved as either outcome until actually reconciled. No automatic rollback exists.

This protects against blind replay, not distributed exactly-once execution.
Independent artifact verification and richer outcome reconciliation remain 15.5.

## Privacy and Boundaries

Default path: `.nexus/executor.sqlite3`, overridden by `NEXUS_HOME`.
The local home is ignored by Git. A custom home must likewise not be published.
Snapshots contain plaintext goal, answer and tool data. Provider credentials are
not deliberately copied, but sensitive tool output can still enter a snapshot or
the configured model prompt. Protect the directory using operating-system access
controls. There is no encrypted vault, multi-user service, retention scheduler,
background executor, universal desktop control or automatic restart supervisor.
The dynamic registry still includes only authorized filesystem and named automations.
Shared RAG/research/voice interfaces belong to Phase 15.4.

## Validation

2026-09-12: executor tests 39 passed; full `pytest tests` suite 546 passed,
4 skipped (127.80 seconds). Root-wide discovery encountered pre-existing
inaccessible scratch directories; the full suite was run from the explicit
`tests` directory without modifying those scratch directories.

Tests use scripted models and isolated temporary homes, not paid APIs. They exercise
approval continuation with a new store/runtime, configuration changes, wrong and
cross-run tokens, questions, preserved budgets, control requests during dispatch,
exclusive leases, snapshot failure, and user reconciliation. A real subprocess
writes a test marker and exits with `os._exit`; a new runner must report needs_review
without invoking the action again. This is not a real desktop-application acceptance
test or a benchmark of a production model's task success rate.
