# AI Suggestions 2.0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enrich deterministic Nexus suggestions with live calendar constraints and task-relevant RAG memories while retaining offline fallback, explainable sources, and approval boundaries.

**Architecture:** `NexusService` assembles bounded optional calendar and RAG context, then passes it into `SuggestionService`. `SuggestionEngine` remains deterministic: calendar and memory evidence create or re-rank bounded candidates, while LLM usage remains wording-only. CLI and Dashboard refresh through the same service pipeline, and dependency failures return useful base suggestions with degradation metadata.

**Tech Stack:** Python 3.11+, JsonStore, existing MemoryRetriever/Qdrant fallback, existing read-only Calendar Tool, pytest, Ruff.

## Global Constraints

- No calendar writes or automatic suggestion execution.
- Only eligible private memories returned by the existing RAG lifecycle may be used.
- Every enriched suggestion must retain bounded reasons, confidence, and source IDs.
- Calendar and RAG failures must preserve deterministic base suggestions.
- No API keys, URLs, raw credentials, or hidden memory payloads may enter operational audit logs.

---

### Task 1: Deterministic Calendar and Memory Candidates

**Files:**
- Modify: `src/nexus/suggestions.py`
- Modify: `tests/test_suggestions.py`

**Interfaces:**
- Consumes: `SuggestionEngine.generate(state, now, calendar=None, memories=None, limit=10)`.
- Produces: calendar-aware and memory-aware suggestion records using stable `calendar:*` and `memory:*` source IDs.

- [x] Add failing tests for a busy calendar, a useful free window, relevant RAG memory, stable ranking, bounded sources, and irrelevant/invalid context.
- [x] Run `python -m pytest tests/test_suggestions.py -q` and verify the new assertions fail because calendar and memory are currently discarded.
- [x] Implement normalized calendar windows and eligible memory candidates without changing the action allowlist.
- [x] Run `python -m pytest tests/test_suggestions.py -q` and verify green.

### Task 2: Context-Orchestrating Suggestion Service

**Files:**
- Modify: `src/nexus/suggestions.py`
- Modify: `src/nexus/service.py`
- Modify: `src/nexus/cli.py`
- Modify: `tests/test_suggestions.py`
- Modify: `tests/test_suggestion_cli.py`

**Interfaces:**
- Consumes: optional `calendar` records and `memory_result` from existing ToolManager and MemoryRetriever APIs.
- Produces: `NexusService.list_suggestions(..., calendar=None, enrich=True)` with a persisted bounded context/degradation summary.

- [x] Add failing service tests proving refresh injects RAG results and calendar events, and separately degrades when either dependency is unavailable.
- [x] Add failing CLI tests proving `suggestion refresh --live-tools` uses the configured read-only calendar and still works when it is disabled.
- [x] Implement a bounded suggestion query from active goals/tasks/habits/projects, retrieve RAG memory through `retrieve_memories_result`, and pass sanitized events/memories to the engine.
- [x] Add `--live-tools` to suggestion list/refresh and reuse the existing ToolManager calendar read path.
- [x] Run focused service and CLI tests and verify green.

### Task 3: Dashboard Integration and Explainability

**Files:**
- Modify: `src/nexus/dashboard.py`
- Modify: `src/nexus/cli.py`
- Modify: `src/nexus/dashboard/dashboard.js`
- Modify: `tests/test_dashboard_actions.py`
- Modify: `tests/test_dashboard_workspace_assets.py`

**Interfaces:**
- Consumes: refreshed enriched suggestions persisted by `SuggestionService`.
- Produces: Dashboard suggestion rows that expose context kind and explainable source count without exposing memory text unnecessarily.

- [x] Add failing Dashboard tests for safe calendar/RAG source metadata and source labels.
- [x] Implement bounded public context metadata and compact source labels in the Suggestions view.
- [x] Run Dashboard tests and verify green.

### Task 4: Documentation and Release Verification

**Files:**
- Modify: `README.md`
- Modify: `README_zh.md`
- Modify: `docs/architecture.md`
- Modify: `docs/roadmap.md`
- Modify: `docs/aios_task_checklist.md`
- Modify: `docs/file_inventory.md`

**Interfaces:**
- Produces: synchronized user documentation and a completed AI Suggestions 2.0 checklist entry.

- [x] Document commands, local/offline behavior, source explainability, permissions, and current limitations in English and Chinese.
- [x] Update architecture, roadmap, task checklist, and file responsibility index.
- [x] Run focused tests, `python -m pytest tests -q`, Ruff, format checks, `git diff --check`, and secret scans.
- [x] Review the final diff and prepare the exact feature files for the requested `main` commit and push.
