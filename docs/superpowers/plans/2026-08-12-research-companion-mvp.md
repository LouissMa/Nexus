# Research Companion MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a persistent, evidence-oriented research partner that can search bounded scholarly metadata, combine it with user evidence and RAG memory, synthesize findings, answer follow-ups, and expose the workflow through CLI, conversation, and Dashboard surfaces.

**Architecture:** A focused `ResearchService` owns research state and deterministic evidence logic. The existing permissioned ToolManager gains a fixed-origin read-only Crossref adapter; `NexusService` supplies eligible RAG retrieval and optional LLM wording, while CLI, conversation, and Dashboard remain bounded adapters over the same service.

**Tech Stack:** Python 3.11+, JsonStore, existing RAG/LLM/ToolManager abstractions, Crossref REST JSON, standard-library Dashboard, pytest, Ruff, Playwright CLI.

## Global Constraints

- Local deterministic research workflows require no API key.
- Literature network access occurs only when the `literature` tool is explicitly enabled and `--live-tools` is requested.
- Crossref is the only fixed network origin introduced; caller-selected origins, arbitrary browsing, shell execution, and paper downloads remain unsupported.
- Every synthesized finding or follow-up answer retains bounded stable evidence references; insufficient evidence is explicit.
- RAG, literature, and LLM failures degrade independently without losing local research state.
- No credentials, full prompts, hidden memory payloads, or arbitrary source content enter audit records or Dashboard snapshots.
- All production behavior is introduced through a verified red-green TDD cycle.

---

### Task 1: Persistent Research Domain

**Files:**
- Create: `src/nexus/research.py`
- Modify: `src/nexus/store.py`
- Create: `tests/test_research.py`

**Interfaces:**
- Produces: `ResearchService(store, retriever=None, llm=None)` with `create`, `list`, `show`, `add_question`, `add_source`, `add_note`, `add_experiment`, and `archive`.
- Stores: bounded `research_projects` records with stable nested IDs and legacy empty-state normalization.

- [x] Write failing tests that create/list/show projects, add each evidence type, reject invalid/oversized fields and unknown evidence IDs, archive projects, preserve concurrent top-level state, and normalize legacy state.
- [x] Run `python -m pytest tests/test_research.py -q` and verify collection/service import failures.
- [x] Add `research_projects` to `DEFAULT_STATE` and implement `ResearchError`, validation constants, timestamps, stable IDs, bounded collection helpers, cross-process-safe mutations, and public deep-copy outputs.
- [x] Run `python -m pytest tests/test_research.py -q` and verify the domain tests pass.

### Task 2: Permissioned Scholarly Search

**Files:**
- Modify: `src/nexus/integrations/web_tools.py`
- Modify: `src/nexus/integrations/manager.py`
- Modify: `src/nexus/config.py`
- Modify: `src/nexus/cli.py`
- Modify: `tests/test_integrations.py`
- Modify: `tests/test_cli.py`

**Interfaces:**
- Produces: `LiteratureTool.execute("read", {"query": str, "limit": int}) -> {"works": list, "count": int}`.
- CLI: `nexus config tool set literature [--mailto EMAIL]`, `nexus tool literature --query QUERY --limit N`.

- [x] Write failing adapter tests asserting `GET https://api.crossref.org/works`, `query.bibliographic`, rows bounded to 1-20, normalized DOI/title/authors/year/type/publisher/abstract/url, malformed-record skipping, and non-read rejection.
- [x] Write failing CLI/config tests for explicit enablement, masked `mailto`, disabled-tool denial, query bounds, and secret-safe audit summaries.
- [x] Run the focused integration/CLI tests and verify missing adapter/parser behavior.
- [x] Implement `LiteratureTool`, register it in `build_tool_manager`, extend tool configuration validation/masking and CLI choices/dispatch, reusing `JsonHttpClient`, `PermissionPolicy`, and `AuditLogger`.
- [x] Run the focused integration/CLI tests and verify green.

### Task 3: Investigation, Synthesis, and Follow-Up

**Files:**
- Modify: `src/nexus/research.py`
- Modify: `src/nexus/service.py`
- Modify: `tests/test_research.py`

**Interfaces:**
- Produces: `investigate(project_id, query, literature_search=None, now=None)`, `synthesize(project_id, use_llm=False, now=None)`, and `ask(project_id, question, use_llm=False, now=None)`.
- `NexusService` supplies a callback wrapping `retrieve_memories_result(query, 5, task_context=..., now=...)` and optional configured LLM.

- [x] Write failing tests for RAG-only investigation, live literature import, DOI deduplication, independent `rag_unavailable`/`literature_unavailable`, deterministic evidence references, conflicts/open questions/next actions, follow-up matching, and insufficient-evidence output.
- [x] Write failing LLM tests that accept exact narrative JSON but reject changed references, unknown fields, malformed JSON, oversized output, and provider failure while retaining deterministic output.
- [x] Run `python -m pytest tests/test_research.py -q` and verify orchestration APIs are missing.
- [x] Implement bounded query assembly, retrieval normalization, source import, investigation history, deterministic synthesis, evidence matching, uncertainty classification, follow-up history, exact-envelope wording adapter, history pruning, and NexusService delegation.
- [x] Run `python -m pytest tests/test_research.py -q` and verify green.

### Task 4: Product Surfaces

**Files:**
- Modify: `src/nexus/cli.py`
- Modify: `src/nexus/conversation.py`
- Modify: `src/nexus/dashboard.py`
- Modify: `src/nexus/dashboard/index.html`
- Modify: `src/nexus/dashboard/dashboard.css`
- Modify: `src/nexus/dashboard/dashboard.js`
- Create: `tests/test_research_cli.py`
- Modify: `tests/test_conversation.py`
- Modify: `tests/test_conversation_cli.py`
- Modify: `tests/test_dashboard.py`
- Modify: `tests/test_dashboard_workspace_assets.py`

**Interfaces:**
- CLI command tree exactly matches the design specification, including `investigate --live-tools`, `synthesize --llm`, and `ask --llm`.
- Conversation adds bounded read intents `list_research` and `show_research`.
- Dashboard snapshot adds a ninth isolated `research` section with bounded summaries and no raw RAG payloads/prompts.

- [x] Write failing CLI tests for create/list/show/question/source/note/experiment/investigate/synthesize/ask/archive, stable JSON errors, lazy LLM initialization, and live-tool degradation.
- [x] Write failing conversation tests for English/Chinese list/show phrases, strict LLM intent schema, and registered read dispatch.
- [x] Write failing Dashboard/API/asset tests for research privacy filtering, section failure isolation, nine tabs, source/experiment counts, latest synthesis, safe `textContent`, and responsive navigation.
- [x] Run focused surface tests and verify missing parser/intent/section behavior.
- [x] Implement CLI dispatch and lazy dependencies, conversation schemas/dispatch, bounded Dashboard snapshot projection, and the ninth Research view using existing visual conventions and safe DOM APIs.
- [x] Run focused surface tests and verify green.

### Task 5: Documentation and Release

**Files:**
- Modify: `README.md`
- Modify: `README_zh.md`
- Modify: `docs/architecture.md`
- Modify: `docs/roadmap.md`
- Modify: `docs/aios_task_checklist.md`
- Modify: `docs/file_inventory.md`
- Modify: this plan as tasks complete

**Interfaces:**
- Documents exact setup, no-key local behavior, optional Crossref/LLM usage, commands, evidence limits, permission boundaries, degradation behavior, and deferred Research Companion 2.0 work in synchronized English and Chinese.

- [x] Update user documentation and all tracking/index files; mark only the shipped Research Companion MVP complete and keep full-text ingestion, general web search, code execution, and autonomous loops deferred.
- [x] Run focused research/integration/surface tests, then `python -m pytest tests -q`.
- [x] Run Ruff checks, touched-file format checks, `git diff --check`, generic secret scans, and compare README command coverage.
- [x] Start an isolated local Dashboard, seed research evidence through public service APIs, and verify desktop plus 390px mobile Research views and zero browser console errors with Playwright CLI.
- [ ] Review the exact diff, stage only Research Companion source/tests/docs, commit intentionally, push `main`, and verify local HEAD equals `origin/main`.
