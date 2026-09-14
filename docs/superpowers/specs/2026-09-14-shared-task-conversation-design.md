# Shared Task Conversation: Phase 15.4b

Status: agreed direction; written design awaiting review. Not implemented.
Date: 2026-09-14.

## Product Direction

The target remains a Jarvis-like personal AI core: natural collaboration,
persistent context, proactive assistance and permissioned action, eventually
shared with visual, home and embodied interfaces. CLI flags and text approvals
are an initial control surface, not the intended final user experience.
This phase does not claim AGI, universal desktop control or full-duplex voice.

## Decision and Alternatives

Use one task conversation router shared by text and voice, backed by the existing
PersistentExecutor and ExecutionStore. Explicitly enter task mode; preserve normal
conversation behavior outside it. This is preferred over automatically executing
every unrecognized utterance (ambiguous intent) or separate text/voice runners
(duplicated state and permissions).

## User Experience

Proposed entry points, not yet available:

```powershell
nexus ask "开始任务：读取项目说明并总结限制" --task-mode
nexus ask "查看进度" --task-mode
nexus voice chat --task-mode
nexus ask "继续任务" --task-mode
```

Text and voice default to the same local task session named `default`.
`--task-session NAME` allows explicit separation; names are 1-64 ASCII letters,
digits, underscore or hyphen. Session names are local conversation labels,
not authenticated identities or multi-user privacy boundaries.
`--task-id ID` explicitly selects an existing durable run and binds the session.
Reject task-only flags outside task mode; preserve existing ask/voice flags.

The initial lifecycle vocabulary covers Chinese and English: start a task, list
tasks, select a task, show progress, continue, answer, pause and cancel.
Only explicit start intent creates a run; unrecognized speech/text never starts
execution. The task goal after the start marker remains open-ended and uses the
general executor, not a new fixed handler for each domain task.

## Session and Selection

Persist a session-to-run pointer in a new small table in executor.sqlite3, not
a second task database. Use existing SQLite transactions and validate run IDs.
The session owns no copy of observations, approvals or context; those stay in the run.

- A selected run is the stable target for later turns, including after restart.
- Without a selected run, list bounded candidates and ask the user to select one.
  Never choose the globally newest task merely because the user said "continue".
- Show at most five candidates with stable run IDs and bounded goal/status labels.
  Support displayed numbered selection only against a saved candidate-ID snapshot;
  if candidates are no longer available, ask again instead of guessing.
- Concurrent selection updates use a revision check. Reject a stale selection
  update rather than silently changing its target. Resolve each request to a fixed
  run ID; do not retarget an in-flight request if another interface changes selection.
- Existing executor runs can be selected. Starting a new task does not implicitly
  cancel the previous task. Existing per-run leases still exclude concurrent runners.

## Routing and Lazy Dependencies

Create `src/nexus/task_conversation.py` for lifecycle parsing, selection and safe
response projection. ConversationService delegates to it only in task mode.
NexusService.ask and CLI wiring pass explicit task options, not a global mode.
VoiceService uses that same ConversationService/router instance for each turn.

Inspection, listing, selection and pause/cancel must not construct an LLM,
Embedding provider or retriever. Build the configured executor only when starting,
resuming or answering a task. Keep model tier and execution budget behavior
consistent with executor commands; never replenish a resumed run's budgets.

Use deterministic parsing for lifecycle controls. A pending waiting_input question
accepts an explicit answer command or a non-control reply only when a task has
already been selected. Lifecycle commands take precedence over treating an
utterance as an answer. Outside waiting_input, an unrecognized utterance requests
clarification and does not resume, create, or mutate a task.

## Approval and Context

Task mode must not forward the existing generic `--approve` flag into executor
approval. Reject it in task mode with an actionable message. "Yes", "okay" and
their Chinese equivalents are never execution approval, whether typed or spoken.

For waiting_approval, show the exact pending action in text and direct the user to
the existing `executor show ID` / `executor resume ID --approval-token TOKEN`
flow. Do not add a second token mechanism or any voice-approval bypass. Approval
tokens and private tool output must not be spoken. After text approval, either
interface can query or continue the same run through its session binding.

For new tasks, task mode defaults to context-free execution. It cannot enable
personal/private memory consent from natural-language guesses. Existing contextful
runs retain their 15.4a snapshot and validation on resume; sensitive source changes
block before model/tool calls. New contextful runs can still be explicitly created
with the existing executor CLI and then selected in conversation.

## Progress and Voice Behavior

Responses retain the existing conversation envelope and add a bounded task view:
run ID, status, decision count, successful/failed observation counts, selected goal
label, latest brief action description and the next required user action.
Do not dump full snapshots or raw exceptions into ordinary conversation responses.
Context provenance stays available through executor show.

Speech describes whether Nexus is waiting for an answer, approval or manual review,
paused, cancelled, failed, budget-limited or model-reported complete. Never map
every nonempty result to "Request completed". Reported completion remains a model
claim, not independent verification of a file/window or external task outcome.

Waiting_input stays in the current voice conversation so the next turn can answer.
In task mode, waiting_approval may also stay in the bounded voice session for safe
status/control turns, but cannot approve. Preserve the existing stop-on-approval
behavior for ordinary non-task voice sessions. Preserve idle limits, turn budgets,
stop phrases and temporary audio cleanup.

Execution remains foreground and turn-taking. While a blocking model/tool call is
running, this microphone loop cannot simultaneously hear a new request. A second
text process can issue cooperative pause/cancel; the executor acknowledges it at
its existing boundaries. Full-duplex listening, barge-in and background workers
are explicitly deferred, not implied by "shared tasks".

## Errors and State Safety

Missing model configuration affects only execution, not progress/selection/control.
Unknown or ambiguous task selection never mutates a run. Invalid/stale approval,
stale context, busy lease, exhausted budget and uncertain effects retain existing
executor behavior. Surface bounded explanations without source or provider secrets.
Cancelled or completed tasks are not silently restarted. A session deletion or
selection change does not delete or modify a durable run's history.

## Files

- `src/nexus/task_conversation.py` (new): shared lifecycle router and task summary.
- `src/nexus/execution_store.py`: session pointers/candidate snapshots and revision
  checks, alongside the existing run store and leases.
- `src/nexus/conversation.py`, `src/nexus/service.py`: opt-in task delegation.
- `src/nexus/cli.py`: task mode/session/selection flags and lazy dependency wiring.
- `src/nexus/voice.py`, `src/nexus/voice_session.py`: task-aware safe speech and
  continued clarification/status turns without voice approval.
- `tests/test_task_conversation.py` (new), existing voice/executor tests: lifecycle,
  sessions, selection, permissions, shared state and backward compatibility.

## Acceptance

1. Text creates a run; voice queries that exact ID; a new service instance finds
   the same session binding after restart.
2. Missing/ambiguous selections ask for clarification and never execute a tool.
3. A question can be answered by either interface without creating another run.
4. No generic approval flag or spoken affirmation invokes an ask-policy tool.
5. Existing text-token approval executes once; later voice sees the saved result.
6. Listing/status/selection/pause/cancel work with no LLM or Embedding initialization.
7. Context revocation, unknown effects, budget limits and leases remain enforced.
8. Concurrent session selection cannot silently retarget an in-flight operation.
9. Speech omits tokens/raw tool data and distinguishes waiting/failure/uncertainty.
10. Non-task ask/voice behavior, idle limits, turn limits and audio cleanup are unchanged.

Use scripted models, isolated databases and fake audio adapters for automated
tests. Microphone usability and real speech-recognition accuracy must be reported
separately from unit-test success. Update both READMEs, checklist, roadmap,
architecture and inventory when implementation is delivered; do not mark the
feature complete merely because this design is committed.
