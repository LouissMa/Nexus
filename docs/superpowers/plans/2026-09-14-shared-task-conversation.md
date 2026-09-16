# Shared Task Conversation Implementation Plan

**Goal:** One durable task shared by explicit text/voice task mode.
**Spec:** ../specs/2026-09-14-shared-task-conversation-design.md
**Architecture:** Add session pointers to existing SQLite; one deterministic router
uses a lazy executor factory. Both interfaces reuse the same run and permissions.
**Tech stack:** Existing Python/SQLite/voice adapters/LangGraph; no dependencies added.

## Tasks

- [x] Write failing tests for session persistence, numbered selection, revision
  conflicts, lazy controls and approval isolation in tests/test_task_conversation.py.
- [x] Implement ExecutionStore.task_session/update_task_session and a pre-execution
  on_created hook; implement TaskConversation.handle with bounded projections.
- [x] Add opt-in ConversationService/NexusService delegation; task CLI flags and
  early dispatch, lazy executor construction, task-aware voice speech/session policy.
- [x] Test real cross-interface run IDs and answers with fake audio; preserve
  old voice approval stop, budgets, context validation, leases and ordinary asks.
- [x] Review, run focused/full suites and synchronize EN/ZH docs and progress.

Verification (2026-09-16): full `python -m pytest tests -q -p no:cacheprovider`
with an isolated --basetemp: 602 passed, 4 skipped. Focused task/store/voice CLI
suite: 76 passed. Independent follow-up review found no remaining actionable
issues in the selection/approval-transition fixes. Audio tests use fake providers;
live microphone acceptance is not claimed. Delivery: commit and push main after
verification; never publish personal stores, configuration or test scratch data.

Interfaces: TaskConversation(store, executor_factory, session='default', run_id=None);
handle(text, approved=False) returns the existing conversation envelope plus
task_mode, task summary and bounded speech_text. Session updates require expected
revision and carry run_id/candidate ID snapshots. Router never accepts approval tokens.

Limits: session names [A-Za-z0-9_-]{1,64}; five candidates; input goal <=4,000
characters; task labels <=160 characters; defaults retain executor 12 steps/120s.
Test with scripted models and isolated stores. Commands: python -m pytest
tests/test_task_conversation.py tests/test_voice.py tests/test_voice_session.py
tests/test_execution_store.py tests/test_execution_context.py -q -p no:cacheprovider;
then python -m pytest tests -q -p no:cacheprovider with an isolated --basetemp.
