# Research Companion MVP Design

**Date:** 2026-08-12
**Status:** Approved for implementation
**Scope:** A local-first, persistent, evidence-oriented research workspace for literature, code, and experiments.

## 1. Objective

Research Companion turns Nexus from a general life assistant into a bounded research partner that can preserve a research question, search scholarly metadata through an explicitly enabled read-only tool, organize evidence, connect relevant long-term memory, track experiments, identify disagreements and gaps, and produce an inspectable synthesis and follow-up research plan.

The MVP is not an autonomous scientist. It does not browse without an explicit permissioned tool workflow, execute arbitrary code, judge scientific truth, or invent citations.

## 2. User Workflows

The CLI supports these workflows:

```text
nexus research create "RAG evaluation" --question "How should Nexus evaluate retrieval quality?"
nexus research list
nexus research show <research-id>
nexus research question-add <research-id> "Which metrics fit personal memory retrieval?"
nexus research source-add <research-id> --type paper --title "..." --locator "https://..." --note "..."
nexus research note-add <research-id> "Hybrid retrieval improved recall in the first trial."
nexus research experiment-add <research-id> --title "Dense vs hybrid" --method "..." --result "..." --status completed
nexus research investigate <research-id> --query "personal memory retrieval evaluation" --live-tools
nexus research synthesize <research-id>
nexus research synthesize <research-id> --llm --model-tier complex
nexus research ask <research-id> "What evidence is still missing?"
nexus research archive <research-id>
```

The permissioned scholarly search tool is configured explicitly:

```text
nexus config tool set literature --mailto "researcher@example.com"
nexus tool literature --query "retrieval augmented generation evaluation" --limit 5
```

`literature` uses the public Crossref REST API, stores only bounded bibliographic metadata, and does not download papers. The optional email identifies the client to Crossref; it is masked in configuration output. A disabled tool never performs network access.

The Dashboard adds a Research view for scanning active workspaces, questions, evidence counts, experiments, open questions, and the latest synthesis. The MVP Dashboard remains read-only for research records; authoring happens through the CLI and registered service interfaces.

The unified conversation entry point supports bounded read intents for listing and showing research workspaces. `research ask` answers a follow-up from the persisted evidence and RAG context, reports its references and uncertainty, and can optionally use the configured LLM for wording. Mutation-rich research authoring remains explicit through `nexus research` commands in this phase.

## 3. Domain Model

Research records are stored in the existing `JsonStore` under `research_projects`.

Each project contains:

- `id`, `title`, `objective`, `status`, `created_at`, and `updated_at`.
- A bounded list of research questions, each with an ID, text, status, and timestamps.
- A bounded source catalog with ID, type, title, optional locator, user note, and timestamps.
- A bounded notebook with ID, text, optional source IDs, tags, and timestamps.
- A bounded experiment log with title, hypothesis, method, result, status, optional source IDs, and timestamps.
- A bounded investigation history with query, imported source IDs, tool/RAG status, degradation flags, and timestamps.
- A bounded synthesis history containing a deterministic structure, evidence references, RAG metadata, generation mode, degradation flags, and timestamps.
- A bounded follow-up history containing the user question, deterministic or LLM-assisted answer, evidence references, uncertainty, degradation flags, and timestamps.

Allowed source types are `paper`, `web`, `book`, `code`, `dataset`, and `other`. Source locators are stored as user-provided references; adding one does not fetch it.

Allowed experiment states are `planned`, `running`, `completed`, and `blocked`. Research project states are `active` and `archived`.

All text, list sizes, source references, and history lengths have explicit bounds. Unknown IDs, invalid relationships, and oversized values fail before persistence. Store mutations use the existing cross-process transaction behavior.

## 4. Synthesis Contract

`ResearchService.investigate` performs this pipeline:

1. Validate a bounded query and load the active workspace.
2. Retrieve eligible long-term memories through the existing RAG lifecycle.
3. When `--live-tools` is explicit, call the enabled `literature` adapter through `ToolManager` with `read` permission.
4. Normalize returned papers into source records with stable DOI-based deduplication.
5. Persist imported sources and an investigation record. Tool and RAG failures degrade independently.

`ResearchService.synthesize` then performs this pipeline:

1. Load and normalize the selected active research workspace.
2. Build a bounded retrieval query from the objective, active questions, source titles/notes, notebook entries, and experiment summaries.
3. Retrieve up to five eligible memories through the existing RAG lifecycle.
4. Produce a deterministic synthesis with these sections:
   - `research_question`
   - `current_findings`
   - `evidence` with stable source, note, experiment, or memory references
   - `agreements_and_conflicts`
   - `experiment_summary`
   - `open_questions`
   - `next_actions`
5. Persist the synthesis and retrieval/degradation metadata.
6. If `--llm` is explicitly requested and an LLM is configured, ask it to rewrite only the narrative fields inside an exact JSON envelope. Structural IDs, evidence references, status, and next-action count remain authoritative from the deterministic result.
7. If RAG or LLM generation fails, return and persist the deterministic synthesis with independent degradation markers.

A source title alone is not treated as proof of a claim. Findings come from user notes, experiment results, and eligible RAG memories. When those are absent, the synthesis reports insufficient evidence and moves the topic into open questions.

`ResearchService.ask` builds a bounded follow-up context from the latest synthesis, sources, notes, experiments, and fresh RAG results. The deterministic answer returns matching evidence excerpts and explicitly states when evidence is insufficient. Optional LLM wording must preserve the exact reference IDs and uncertainty classification.

## 5. Component Boundaries

### `research.py`

Owns validation, normalization, IDs, persistence, archive behavior, deterministic synthesis, evidence references, and bounded LLM rewriting. It depends on `JsonStore` and receives a retrieval callback and optional LLM rather than constructing provider configuration itself.

### `service.py`

Exposes ResearchService operations through `NexusService`, builds the existing RAG retrieval callback, and preserves local sparse fallback behavior.

### `integrations/web_tools.py` and `integrations/manager.py`

Add a read-only `LiteratureTool` backed by Crossref `/works?query.bibliographic=...`. It accepts only a bounded query and result limit, normalizes title, authors, year, DOI, type, publisher, abstract snippet, and canonical URL, and participates in existing enablement, permission, timeout, redacted audit, and partial-failure behavior.

### `cli.py`

Defines the explicit research command tree, literature tool/config commands, parses timestamps/options, maps public errors to stable JSON, and never initializes the LLM unless `--llm` is requested.

### `conversation.py`

Adds allowlisted `list_research` and `show_research` read intents. It does not add generic research mutations or arbitrary tool execution.

### `dashboard.py` and Dashboard assets

Expose only bounded, privacy-filtered research summaries. Raw hidden memories, provider credentials, complete source documents, and LLM prompts are not included in the snapshot.

## 6. Safety and Privacy

- Local deterministic operation requires no API key.
- RAG returns only memories eligible under the existing lifecycle and privacy scope.
- LLM use is explicit and optional; provider failures do not block synthesis.
- User-provided URLs and paths are metadata, not implicit permission to fetch or read.
- Literature search is read-only, explicitly enabled, bounded to Crossref's fixed HTTPS origin, and recorded by the existing tool audit.
- No arbitrary browser, shell, filesystem, MCP, or caller-selected network origin is introduced.
- Dashboard rendering uses `textContent`; research data never becomes HTML.
- Audit/degradation metadata contains IDs and status only, not credentials or full prompts.
- Archival is reversible in storage terms; destructive purge is outside this MVP.

## 7. Error Handling

Validation errors use stable public messages and do not partially mutate state. Missing projects and invalid evidence references fail explicitly. Legacy state without `research_projects` normalizes to an empty collection.

RAG and LLM failures are independent:

- `rag_unavailable`: synthesis continues without memory evidence.
- `literature_unavailable`: investigation continues with local and RAG evidence.
- `llm_unavailable` or `llm_rejected`: deterministic wording is retained.

Malformed LLM JSON, changed evidence IDs, additional fields, or oversized output is rejected as a wording failure.

## 8. Testing Strategy

Implementation follows red-green-refactor cycles.

- Domain tests cover validation, persistence, bounds, evidence relationships, investigation/import deduplication, follow-up answers, archival, deterministic synthesis, RAG context, degradation, LLM structure protection, and legacy normalization.
- Integration tests cover Crossref request bounds, response normalization, fixed origin, explicit permission, timeout errors, and secret-safe audit.
- CLI tests cover every command, optional LLM initialization, JSON envelopes, and error exits.
- Conversation tests cover exact local/LLM schemas and read dispatch.
- Dashboard tests cover privacy filtering, section isolation, safe rendering, responsive navigation, and packaged assets.
- Release verification runs focused tests, the full test suite, Ruff, format checks for touched Python files, `git diff --check`, generic secret scans, and desktop/mobile browser checks.

## 9. Acceptance Criteria

The MVP is complete when a user can create a persistent research workspace, search and import bounded scholarly metadata through an explicitly enabled permissioned tool, add questions/sources/notes/experiments, generate an evidence-referenced deterministic synthesis enriched by eligible RAG memory, ask evidence-grounded follow-up questions, optionally improve wording through a configured LLM, inspect the work through CLI/conversation/Dashboard surfaces, and continue to receive useful output when literature, RAG, or LLM dependencies fail.

English and Chinese READMEs, architecture, roadmap, task checklist, and file inventory must describe the same shipped scope. The final verified commit is pushed to `origin/main` without local runtime data or credentials.

## 10. Deferred Work

- Full-text paper downloading, parsing, and citation verification.
- General web search and browser-driven source acquisition.
- PDF/document ingestion and chunk-level scholarly citations.
- Code repository indexing and sandboxed experiment execution.
- Collaborative research workspaces and remote synchronization.
- Autonomous multi-Agent research loops.
- Citation-style export, BibTeX, and publication drafting.

These are candidates for Research Companion 2.0 and must reuse existing permission, tool, MCP, memory, and audit boundaries.
