# Advanced Long-Term Memory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete Phase 9 with explainable importance, lifecycle controls, compression, privacy-aware retrieval, and context re-ranking.

**Architecture:** Add a focused lifecycle module that normalizes legacy records and owns mutation rules. Keep retrieval in `rag.py`, but make it consume lifecycle eligibility and re-ranking helpers. Expose all user controls through `NexusService` and structured CLI commands.

**Tech Stack:** Python 3.11+, standard library, existing JSON store, existing embedding providers and Qdrant adapter, pytest, Ruff.

## Global Constraints

- Preserve legacy state compatibility.
- Work without an API key or LLM.
- Never permanently delete without explicit confirmation.
- Never expose stored sparse embeddings.
- Preserve local sparse fallback when semantic indexing fails.

---

### Task 1: Memory Lifecycle Domain

**Files:**
- Create: `src/nexus/memory_lifecycle.py`
- Create: `tests/test_memory_lifecycle.py`

**Interfaces:**
- Produces: normalization, scoring, duplicate detection, eligibility, relation, transition, compression, and maintenance helpers used by service and RAG.

- [x] Write failing tests for deterministic score bounds, legacy normalization, exact and near duplicates, privacy eligibility, reversible transitions, compression, and expiry maintenance.
- [x] Run `python -m pytest -q tests/test_memory_lifecycle.py` and confirm failures.
- [x] Implement the minimum domain functions and typed lifecycle errors.
- [x] Run the focused test file and confirm it passes.

### Task 2: Service Persistence And Mutation APIs

**Files:**
- Modify: `src/nexus/service.py`
- Modify: `src/nexus/store.py`
- Create: `tests/test_memory_service.py`

**Interfaces:**
- Consumes: lifecycle helpers from Task 1.
- Produces: `show_memory`, `update_memory`, `relate_memory`, `archive_memory`, `restore_memory`, `forget_memory`, `purge_memory`, `compress_memories`, and `maintain_memories`.

- [x] Write failing tests for add metadata, exact duplicate merge, relation persistence, semantic-index refresh, reversible forgetting, confirmed purge, dry-run compression, and legacy state reads.
- [x] Run `python -m pytest -q tests/test_memory_service.py` and confirm failures.
- [x] Implement service APIs and index refresh behavior.
- [x] Run the focused tests and confirm they pass.

### Task 3: Privacy-Aware Context Re-Ranking

**Files:**
- Modify: `src/nexus/rag.py`
- Modify: `src/nexus/agents/specialists.py`
- Create: `tests/test_memory_reranking.py`

**Interfaces:**
- Consumes: normalized lifecycle records and eligibility rules.
- Produces: filtered retrieval results with relevance, importance, recency, context, and final score metadata.

- [x] Write failing tests for forgotten/expired filtering, archived opt-in, privacy scopes, dense stale-ID rejection, importance ordering, recency ordering, and task-context boosts.
- [x] Run `python -m pytest -q tests/test_memory_reranking.py` and confirm failures.
- [x] Add retrieval policy arguments and explainable final ranking.
- [x] Run focused RAG and agent tests.

### Task 4: CLI Controls

**Files:**
- Modify: `src/nexus/cli.py`
- Create: `tests/test_memory_cli.py`

**Interfaces:**
- Consumes: service APIs from Task 2 and retrieval policy from Task 3.
- Produces: structured Phase 9 memory commands and safe errors.

- [x] Write failing CLI tests for add options, show/update/relate, archive/restore/forget/purge, compress, maintain, privacy retrieval, and invalid input.
- [x] Run `python -m pytest -q tests/test_memory_cli.py` and confirm failures.
- [x] Implement parser and dispatch branches.
- [x] Run focused CLI tests.

### Task 5: Documentation And Release Verification

**Files:**
- Modify: `README.md`
- Modify: `README_zh.md`
- Modify: `docs/architecture.md`
- Modify: `docs/roadmap.md`
- Modify: `docs/aios_task_checklist.md`
- Modify: `docs/file_inventory.md`

**Interfaces:**
- Produces: synchronized user documentation and completed Phase 9 tracking.

- [x] Document capabilities, commands, safety semantics, and current limitations in both READMEs.
- [x] Mark Phase 9 complete and update architecture, checklist, and file responsibilities.
- [x] Run `python -m ruff check src tests`.
- [x] Run `python -m pytest -q tests -p no:cacheprovider`.
- [x] Run CLI smoke tests with an isolated `NEXUS_HOME`.
- [x] Review the final diff against the design and fix all Critical or Important findings.
- [x] Commit and push `main`.
