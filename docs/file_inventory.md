# Project File Inventory

This file explains the role of important files in the Nexus project. Update it whenever a new important file is created, deleted, or meaningfully changes responsibility.

## Root Files

- `README.md`: English project overview, quick start, current features, LLM setup, RAG usage, development workflow, and roadmap summary.
- `README_zh.md`: Chinese project overview and usage guide. Keep it synchronized with `README.md` for user-facing changes.
- `pyproject.toml`: Python package metadata, CLI entry point, and optional `rag`, `tools`, and stable MCP SDK dependency groups.
- `.gitignore`: Ignores Python build/cache files, local secrets, and the local Qdrant index under `.nexus/qdrant/`.
- `褰撳墠鐩爣`: Local Chinese goal note file from earlier project planning.

## Source Code

- `src/nexus/__init__.py`: Package marker and short package description.
- `src/nexus/cli.py`: Command-line interface for memory, goals, planning, reviews, briefings, LLM/RAG configuration, Phase 6 tools, MCP configuration/discovery/calls, approvals, and audit inspection.
- `src/nexus/store.py`: JSON persistence for memories, goals, and persistent daily tasks in `.nexus/state.json` or `NEXUS_HOME/state.json`.
- `src/nexus/service.py`: Main application service for memory/RAG, goals, planning, reflection, briefings, live Phase 6 context, and normalized MCP planning context.
- `src/nexus/llm.py`: OpenAI-compatible LLM client. Reads provider settings, selects model tier, calls chat completions, and normalizes LLM errors.
- `src/nexus/config.py`: Local configuration for LLM, Embedding/Qdrant, and external tools; validates required settings and masks all configured secrets.
- `src/nexus/embeddings.py`: Embedding provider abstraction plus local FastEmbed and OpenAI-compatible embedding implementations.
- `src/nexus/rag.py`: RAG orchestration for sparse retrieval, semantic indexing, dense+sparse fusion, metadata, re-indexing, and automatic fallback.
- `src/nexus/vector_store.py`: Qdrant adapter supporting local persistence, remote Qdrant, collection lifecycle, upsert, search, clear, and status.
- `src/nexus/integrations/__init__.py`: Public entry point for the permissioned integration package.
- `src/nexus/integrations/core.py`: Shared tool contracts, HTTP client, permission checks, structured results, and secret-safe JSONL auditing.
- `src/nexus/integrations/web_tools.py`: Open-Meteo weather, Todoist, GitHub, and Notion read-only adapters.
- `src/nexus/integrations/personal_tools.py`: Recurring iCalendar, read-only IMAP email headers, and permission-bounded local filesystem adapters.
- `src/nexus/integrations/manager.py`: Adapter registry, permissioned execution, audit orchestration, and live briefing aggregation.
- `src/nexus/mcp/models.py`: Stable MCP errors, discovered tool schemas, and normalized call-result models.
- `src/nexus/mcp/config.py`: MCP server validation, local persistence, policy/planning bindings, and secret masking.
- `src/nexus/mcp/client.py`: Official MCP SDK gateway for stdio and Streamable HTTP lifecycle, discovery, calls, and result normalization.
- `src/nexus/mcp/audit.py`: Secret-safe JSONL audit records for MCP discovery, permissions, calls, retries, and failures.
- `src/nexus/mcp/manager.py`: MCP server registry, deny/ask/allow policy enforcement, bounded retries, audit orchestration, and Planning aggregation.
- `src/nexus/mcp/__init__.py`: Public entry point for Nexus MCP client support.
- src/nexus/planning.py: Planning domain rules. Defines persistent daily-task construction, valid task statuses, and strict/gentle/academic/startup Coach profiles.

## Documentation

- `docs/architecture.md`: System architecture, data flow, current modules, LLM flow, RAG memory flow, and future architecture.
- `docs/roadmap.md`: Development phases and implementation status.
- `docs/product_vision.md`: Product vision for Nexus / LifeAgent as a proactive Personal AI Operating System.
- `docs/aios_task_checklist.md`: Detailed AIOS / J.A.R.V.I.S. task checklist. Use this as the main progress tracker.
- `docs/file_inventory.md`: This file. Tracks file responsibilities and documentation ownership.
- docs/superpowers/specs/2026-07-17-mcp-client-design.md: Approved Phase 7 MCP client scope, safety rules, interfaces, CLI, and completion criteria.
- docs/superpowers/plans/2026-07-17-mcp-client.md: Test-driven Phase 7 implementation plan and verification sequence.

## Tests

- `tests/test_cli.py`: End-to-end CLI and service tests for memory, goals, RAG, planning, reflection, briefings, and LLM fallback/configuration.
- `tests/test_integrations.py`: Deterministic tests for all real-tool adapters, recurring events, permissions, audit redaction, filesystem boundaries, CLI execution, and live briefing context.
- `tests/test_mcp.py`: MCP configuration, policies, retries, planning bindings, and audit-redaction tests.
- `tests/test_mcp_gateway.py`: SDK gateway tool-schema and result-normalization tests with injected sessions.
- `tests/test_mcp_cli.py`: End-to-end MCP configuration, policy, binding, server-list, and JSON-validation CLI tests.
- `tests/test_mcp_planning.py`: Local and LLM Planning context injection and MCP failure-fallback tests.
- `tests/test_mcp_stdio.py` and `tests/test_mcp_http.py`: Real protocol tests against repository stdio and Streamable HTTP MCP fixtures.

## Local Runtime Data

- `.nexus/state.json`: Local runtime state for memories, goals, and daily tasks. This can contain personal user data.
- `.nexus/config.local.json`: Local private LLM, Embedding/Qdrant, Phase 6 tool, and MCP server/policy configuration. This file is ignored by Git and must not be committed.
- `.nexus/qdrant/`: Local persistent semantic-memory vector index. Ignored by Git.
- .nexus/tool_audit.jsonl: Secret-safe success/failure audit trail for external tool calls. Ignored by Git.
- .nexus/mcp_audit.jsonl: Secret-safe MCP discovery, permission, retry, call, and failure audit trail. Ignored by Git.
- `.nexus/models/`: Local FastEmbed model cache. Ignored by Git.
- `.tmp/`: Local scratch/test space. Ignored by Git.

## Generated / Cache Files

- `.pytest_cache/`: Pytest cache. Not part of product logic.
- `__pycache__/`: Python bytecode cache. Not part of product logic.
- `src/nexus_lifeagent.egg-info/`: Packaging metadata generated by editable install/build tools.
