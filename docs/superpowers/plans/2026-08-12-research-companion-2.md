# Research Companion 2.0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver full-text research corpora, safe source acquisition, restricted experiments, and a terminating evidence-grounded multi-Agent research workflow.

**Architecture:** Add a focused corpus/index service beside `ResearchService`, then expose it through service and CLI boundaries. Add a separate restricted experiment runner and deterministic research-loop coordinator so acquisition, execution, and reasoning retain independent permission and failure boundaries.

**Tech Stack:** Python 3.11+, existing JsonStore and local multilingual sparse embedder, optional pypdf, urllib/HTMLParser, subprocess without shell, existing CLI/Dashboard/conversation patterns, pytest and Playwright CLI.

## Global Constraints

- Local-first and no API key required for deterministic operation.
- Only explicitly selected files, URLs, repositories, and commands may be processed.
- PDF/Markdown/TXT files are capped at 20 MiB; corpus text and result histories are bounded.
- Web acquisition is HTTPS-only and rejects private/reserved network destinations.
- Experiment execution requires approval, an executable allowlist, an allowed working root, `shell=False`, timeout, minimal environment, and capped output.
- Multi-Agent runs terminate by fixed cycle/time/evidence budgets and never trigger network or process side effects implicitly.
- Raw chunks, prompts, command output, secrets, and full local paths stay out of Dashboard and trace payloads.

---

### Task 1: Corpus Extraction, Persistence, Retrieval, And Citations

**Files:**
- Create: `src/nexus/research_corpus.py`
- Test: `tests/test_research_corpus.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Produces `ResearchCorpus(store, index_root)`, `ingest_file`, `list_documents`, `show_document`, `remove_document`, `reindex_document`, `search`, and `validate_reference`.
- Document metadata is stored in each research project; full chunks are stored under the Nexus home index root.

- [x] Write failing tests for Markdown/TXT extraction, mocked page-aware PDF extraction, deterministic chunk IDs, deduplication, size/type failures, search ranking, removal, re-index rollback, and stale/tampered references.
- [x] Run `python -m pytest tests/test_research_corpus.py -q` and confirm failures are caused by the missing module.
- [x] Implement bounded extraction, chunking, atomic project-scoped index persistence, sparse vector retrieval, and citation validation.
- [x] Run the focused tests and confirm green.

### Task 2: Safe Web And Repository Acquisition

**Files:**
- Modify: `src/nexus/research_corpus.py`
- Test: `tests/test_research_acquisition.py`

**Interfaces:**
- Adds `ingest_web(project_id, url, fetcher)` and `index_repository(project_id, root)`.
- Fetcher receives only a policy-validated URL and returns bounded bytes plus final URL/content type.

- [x] Write failing tests for HTML text/title extraction, HTTPS/private-IP/credential/port rejection, response limits, redirect revalidation, repository line citations, ignore rules, symlink escape, binary/large files, and deterministic re-indexing.
- [x] Verify RED with the focused acquisition tests.
- [x] Implement network policy, HTML extraction, immutable acquisition metadata, and bounded repository traversal without code execution.
- [x] Run focused corpus/acquisition tests and confirm green.

### Task 3: Restricted Experiment Runner

**Files:**
- Create: `src/nexus/research_experiments.py`
- Test: `tests/test_research_experiments.py`

**Interfaces:**
- Produces `RestrictedExperimentRunner.run(project_id, argv, cwd, approved, timeout_seconds)` and a structured persisted result.

- [x] Write failing tests for approval, executable allowlist, root containment, no-shell argument preservation, timeout, output caps, minimal environment, success/failure persistence, and secret-safe public summaries.
- [x] Verify RED.
- [x] Implement the restricted subprocess boundary and map results into existing research experiments.
- [x] Run focused tests and confirm green.

### Task 4: Bounded Multi-Agent Research Loop

**Files:**
- Create: `src/nexus/research_loop.py`
- Test: `tests/test_research_loop.py`
- Modify: `src/nexus/research.py`

**Interfaces:**
- Produces `ResearchLoop.run(project_id, question, max_cycles, use_llm, now)` with planner/retriever/analyst/critic/reflection steps, sanitized traces, and terminal reason.
- `ResearchService` accepts a corpus search callback and includes document findings in `ask` and `synthesize`.

- [x] Write failing tests for referenced findings, unsupported-claim rejection, no-evidence outcome, cycle/time/LLM budgets, deterministic termination, component degradation, and persistence.
- [x] Verify RED.
- [x] Implement specialists and coordinator with exact-reference validation and no side-effect tools.
- [x] Integrate document chunks into existing synthesis/answer evidence and run focused tests green.

### Task 5: Service, CLI, Conversation, And Dashboard Surfaces

**Files:**
- Modify: `src/nexus/service.py`
- Modify: `src/nexus/cli.py`
- Modify: `src/nexus/conversation.py`
- Modify: `src/nexus/dashboard.py`
- Modify: `src/nexus/dashboard/index.html`
- Modify: `src/nexus/dashboard/dashboard.js`
- Modify: `src/nexus/dashboard/dashboard.css`
- Test: `tests/test_research_cli.py`
- Test: `tests/test_conversation.py`
- Test: `tests/test_dashboard.py`
- Test: `tests/test_dashboard_workspace_assets.py`

**Interfaces:**
- Exposes document add/list/show/remove/reindex/search, web add, repository index, experiment run, and research run commands.
- Adds read-only corpus status/search conversation intents and privacy-filtered Dashboard summaries.

- [x] Write failing CLI, conversation, API, privacy, asset, and responsive navigation tests.
- [x] Verify RED.
- [x] Wire lazy dependencies, stable JSON errors, read-only conversation dispatch, and bounded Dashboard projections/rendering.
- [x] Run all surface tests and confirm green.

### Task 6: Documentation, Verification, And Release

**Files:**
- Modify: `README.md`
- Modify: `README_zh.md`
- Modify: `docs/architecture.md`
- Modify: `docs/roadmap.md`
- Modify: `docs/aios_task_checklist.md`
- Modify: `docs/file_inventory.md`
- Modify: this plan

- [x] Synchronize setup, commands, safety boundaries, limitations, and exact Research Companion 2.0 status in English and Chinese.
- [x] Run focused suites and `python -m pytest tests -q`.
- [x] Run Ruff, touched-file format checks, `git diff --check`, and added-line secret scans.
- [x] Verify desktop and 390px Dashboard Research views with zero browser console errors.
- [ ] Stage only intended source/tests/docs, commit, push `main`, and verify local HEAD equals `origin/main`.
