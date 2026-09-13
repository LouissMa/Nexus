# Execution Context Implementation Plan

**Goal:** Deliver Phase 15.4a opt-in, bounded goal/RAG/research context.
**Architecture:** A separate builder projects canonical local sources; the existing
SQLite run stores the snapshot. Validation precedes resume and each execution boundary.
**Tech Stack:** Existing Python, JsonStore, RAG, SQLite and LangGraph; no dependencies added.
**Spec:** ../specs/2026-09-13-execution-context-design.md

## Constraints

Shared-only default; explicit sensitive consent; 3 goals, 5 memories, 1 research
project, 5 questions, 1,000 characters per text field, 16 KiB UTF-8 envelope.
No auto-refresh, re-index, extra LLM call, voice changes or permission changes.

## Tasks

- [x] Builder: write tests in tests/test_execution_context.py, run them failing,
  implement ExecutionContextBuilder.build(goal, goal_ids=(), research_id=None,
  memory_scope='shared', allow_sensitive=False) and validate(context) in
  src/nexus/execution_context.py. Use canonical JsonStore data and existing RAG
  eligibility rules; assert private sentinel absence and len(JSON bytes) <= 16384.
- [x] Integration: test PersistentExecutor with context_builder and context_options;
  preserve the snapshot on resume and block stale references before model/tool
  dispatch. Extend execution_runtime.py and execution_store.py; context references
  must not become successful tool observations.
- [x] CLI: add the reviewed opt-in flags to cli.py, validate contradictory options
  before constructing services, and construct embedding retrieval only for capture.
  Run parser, consent, prompt and backward-compatibility regression tests.
- [x] Delivery verification: updated EN/ZH README, checklist, roadmap, architecture,
  inventory and spec status. Executor tests: 61 passed. Final pytest tests:
  568 passed, 4 skipped. Review budget-order finding fixed and regression tested.
  Release target: commit the verified changes and push main.

Verification uses isolated temporary stores and scripted models, no paid API.
Run: python -m pytest tests/test_execution_context.py tests/test_execution_store.py
tests/test_execution_runtime.py tests/test_execution_tools.py -q -p no:cacheprovider.
Each implementation follows its failing test; check off tasks only after validation.
