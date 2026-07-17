# Nexus / LifeAgent

> **A proactive personal AI assistant with long-term memory, planning, and reflection.**

Nexus is an open-source, local-first personal AI assistant that remembers goals, retrieves relevant context, builds daily plans, connects approved real-world tools, and helps users reflect and take action.

[English](./README.md) | [Chinese](./README_zh.md)

---

## Product Direction

Most AI assistants are passive. They wait for users to ask questions.

Nexus is different: it is designed to remember, plan, remind, review, and eventually act through approved tools.

The current project focuses on a dependable personal assistant core: memory, goals, planning, reflection, and optional LLM generation.

Over time, this core can become a **Personal AI Operating System** shared by CLI, web, voice, and vision interfaces. Permissioned integrations may later connect it to digital tools, home devices, and robotic systems. These are long-term directions, not current capabilities.

## Current Features

- **Memory**: Add, list, keyword-search, and RAG-retrieve long-term memories.
- **RAG 2.0 Long-Term Memory**: Use real neural embeddings, persistent Qdrant vector search, dense+sparse hybrid retrieval, re-indexing, and offline sparse fallback.
- **Permissioned Real Tools**: Read live weather, iCalendar events, Todoist tasks, GitHub repositories, Notion pages, IMAP headers, and approved local files.
- **MCP Tool Calling**: Configure stdio or Streamable HTTP MCP servers, discover schemas, apply deny/ask/allow policies, call tools, audit activity, and enrich daily planning.
- **Goal Tracker**: Add goals with descriptions and check-in cadence.
- **Goal Check-In**: Record progress notes for goals.
- **Proactive Review**: Detect stale goals and generate reminders.
- **Daily Planning**: Decompose active long-term goals into persistent, prioritized tasks for today.
- **Structured Task Tracking**: Update task status, blockers, unresolved items, and progress notes.
- **Daily Review / Reflection**: Review progressed goals, task outcomes, blockers, RAG memories, and tomorrow priorities.
- **Coach Modes**: Use strict, gentle, academic, or startup guidance for plans and reviews.
- **Morning Briefing**: Generate a template daily briefing from goals, reminders, weather text, and memories.
- **LLM Briefing**: Optionally use an OpenAI-compatible LLM for more natural briefings.
- **LLM Provider Config**: Save local provider/model settings, including `simple` and `complex` model tiers.
- **Prompt Inspection**: Use `--show-prompt` to inspect LLM context.
- **Local Storage**: Store MVP data in `.nexus/state.json` by default.

## Quick Start

```bash
python -m pip install -e .

nexus memory add "Louis is preparing for IELTS and wants to apply for an overseas CS/AI master's program." --tags identity study
nexus memory add "Louis is building Nexus as a personal AI OS." --tags project Nexus
nexus goal add "IELTS listening practice" --description "Complete one focused listening session" --cadence-days 1
nexus goal add "Develop Nexus" --description "Build the morning briefing module" --cadence-days 2
nexus briefing --name Louis --weather "weather is sunny, high 25 C"
```

## RAG 2.0 Long-Term Memory

Nexus now supports production-oriented semantic retrieval while preserving a dependency-free offline fallback.

Install the optional local RAG stack:

```bash
python -m pip install -e ".[rag]"
nexus config embedding set --provider fastembed --model sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
nexus memory reindex
nexus memory index-status
nexus memory retrieve "language exam preparation" --limit 3
```

FastEmbed runs locally and needs no API key. Its model is downloaded on first use. Vectors are persisted by Qdrant under `.nexus/qdrant/`, which is ignored by Git.

Nexus can also use OpenAI or another OpenAI-compatible embedding endpoint:

```bash
nexus config embedding set --provider openai --api-key "your-key"
nexus config embedding set --provider custom --base-url "https://provider.example/v1" --model "embedding-model" --api-key "your-key"
```

The retrieval pipeline combines dense semantic scores with local sparse scores. If the embedding model, API, or vector store is unavailable, Nexus reports the error in retrieval metadata and automatically continues with local sparse retrieval. New memories are indexed incrementally; run `nexus memory reindex` after changing the provider/model or migrating existing memories.

RAG 2.0 covers neural embeddings, vector persistence, re-indexing, hybrid retrieval, status metadata, and fallback behavior. Memory importance scoring, deduplication, compression, summarization, and retention policies remain Phase 9 work.

## Real Tool Integrations

Install the optional calendar dependencies:

```bash
python -m pip install -e ".[tools]"
```

Configure only the tools you want to enable:

```bash
nexus config tool set weather --location "Shanghai"
nexus config tool set calendar --calendar-url "https://calendar.example/private.ics"
nexus config tool set todo --token "your-todoist-token"
nexus config tool set github --repo "LouissMa/Nexus"
nexus config tool set notion --token "your-notion-token"
nexus config tool set email --host "imap.example.com" --username "you@example.com" --password "app-password" --mailbox INBOX
nexus config tool set filesystem --root "D:/AI_Projects/Nexus"
nexus config tool show
```

For private repositories or higher API limits, configure GitHub again with `--token "your-github-token"`.

Run integrations explicitly:

```bash
nexus tool weather
nexus tool calendar --days 2
nexus tool todo --limit 20
nexus tool github --limit 10
nexus tool notion --query "research"
nexus tool email --limit 10
nexus tool files list .
nexus tool files read README.md
nexus tool files search . --query "RAG"
nexus tool audit --limit 20
```

Use configured weather, calendar, and Todoist data in the morning briefing:

```bash
nexus briefing --name Louis --live-tools
nexus briefing --name Louis --live-tools --llm
```

Safety boundaries:

- Every tool must be explicitly configured and enabled.
- Phase 6 integrations remain read-only. MCP servers may expose mutating tools, so Nexus gates every MCP tool with deny/ask/allow policy.
- IMAP mailboxes are opened in read-only mode and only message headers are returned.
- Filesystem operations are limited to configured roots and reject path traversal or access outside those roots.
- Calendar feed URLs, tokens, and passwords are stored only in the ignored local config and masked in CLI output.
- Every success and failure is appended to the ignored local audit log at `.nexus/tool_audit.jsonl`.
- Run `nexus config tool disable <tool>` to revoke a tool without deleting its local settings.

## MCP Tool Calling

Install the official stable MCP Python SDK:

```bash
python -m pip install -e ".[mcp]"
```

Configure a local stdio server or a remote Streamable HTTP server:

```bash
nexus config mcp add research --transport stdio --command python --arg path/to/mcp_server.py
nexus config mcp add remote --transport streamable_http --url "https://mcp.example/mcp" --header "Authorization=Bearer your-token"
nexus config mcp show
```

Discover schemas and set a per-tool policy:

```bash
nexus mcp servers
nexus mcp tools research
nexus config mcp policy research search ask
nexus mcp call research search --arguments '{"query":"MCP research"}' --approve
nexus mcp audit --limit 20
```

Policies are `deny`, `ask`, and `allow`. Unknown tools default to `ask`; `ask` requires the one-shot `--approve` flag. Transport failures use bounded retries, while MCP-declared tool errors are never retried because a tool may have side effects.

To enrich Planning, explicitly bind a tool and set its policy to `allow`:

```bash
nexus config mcp policy research search allow
nexus config mcp planning-tool research search --arguments '{"query":"today research priorities"}'
nexus plan day --name Louis --live-mcp
```

Planning executes only explicit `planning-tool` bindings with an `allow` policy. Successful results and failures are returned in `mcp_context`; one failed server does not stop the local plan. Server definitions stay in ignored `.nexus/config.local.json`, masked CLI output never reveals URLs, headers, or environment secrets, and MCP audit records go to ignored `.nexus/mcp_audit.jsonl`.



## Daily Planning and Reflection

Create today's plan from active long-term goals:

```bash
nexus plan day --name Louis --coach-mode academic
nexus plan day --llm --model-tier complex --show-prompt
```

The first run creates up to three prioritized tasks and saves them in `.nexus/state.json`. Re-running the command on the same date returns the same tasks instead of creating duplicates.

Track execution and reflection data:

```bash
nexus task list
nexus task update <task_id> --status in_progress --note "Started the first practice set"
nexus task update <task_id> --blocker "Need calendar access" --unresolved "Reschedule this task tomorrow"
nexus task update <task_id> --status completed
nexus review day --name Louis --coach-mode strict
```

A blocker automatically marks the task as `blocked`. Daily Review carries blocked and unresolved work into tomorrow priorities. Coach modes are `strict`, `gentle`, `academic`, and `startup`.

## LLM Usage

Nexus works without an API key for local memory, goals, planning, task updates, check-ins, proactive/daily review, template briefing, and local RAG retrieval.

An API key is only required when you run LLM-backed features such as:

```bash
nexus briefing --llm
```

Never commit API keys to GitHub.

## Local LLM Configuration

For project testing, save provider/model settings locally:

```bash
nexus config llm set --provider deepseek --api-key "your-key" --simple-model v4flash --complex-model v4pro --default-tier simple
nexus config llm show
nexus config embedding set --provider fastembed --model sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
nexus config embedding show
```

The config is saved to:

```text
.nexus/config.local.json
```

This file is ignored by Git. API keys are masked in CLI output.

Model tier guidance:

- `simple`: cheap and fast. Good for briefings, short summaries, and simple suggestions.
- `complex`: stronger. Good for planning, deep review, architecture/code analysis, and multi-agent decisions.

```bash
nexus briefing --llm --model-tier simple
nexus briefing --llm --model-tier complex
```

## CLI Commands

```bash
nexus memory add "..." --tags study project
nexus memory list
nexus memory search IELTS
nexus memory retrieve "IELTS listening practice" --limit 5
nexus memory reindex
nexus memory index-status

nexus goal add "Develop Nexus" --description "Ship MVP features" --cadence-days 2
nexus goal list
nexus goal check-in <goal_id> "Finished today's session."

nexus plan day --name Louis --coach-mode academic
nexus task list
nexus task update <task_id> --status completed

nexus review
nexus review day --name Louis
nexus review day --llm --show-prompt --name Louis
nexus briefing --name Louis --weather "weather is sunny, high 25 C"
nexus briefing --llm --show-prompt --name Louis

nexus config llm set --provider deepseek --api-key "your-key" --simple-model v4flash --complex-model v4pro
nexus config llm show
nexus config embedding set --provider fastembed --model sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
nexus config embedding show
```

## Project Tracking

- [AIOS task checklist](./docs/aios_task_checklist.md): Tracks remaining work toward a J.A.R.V.I.S.-like AIOS.
- [Project file inventory](./docs/file_inventory.md): Explains important files and their responsibilities.
- [Architecture](./docs/architecture.md): Current system design and future architecture.
- [Roadmap](./docs/roadmap.md): Development phases and status.

## Development Workflow

When implementing new features:

1. Update the related code and tests.
2. Update `README.md` and `README_zh.md` for user-facing changes.
3. Update `docs/aios_task_checklist.md` when progress changes.
4. Update `docs/file_inventory.md` when important files are added or responsibilities change.
5. Run tests before committing when possible.
6. Ask whether to push unless the user explicitly asked for a push.
7. Never commit API keys or `.nexus/config.local.json`.

## Roadmap Summary

- **Phase 1**: CLI MVP: memory, goals, check-ins, proactive review, morning briefing. Done.
- **Phase 2**: LLM briefing and provider configuration. Done.
- **Phase 3**: Local RAG long-term memory MVP. Done.
- **Phase 4**: Persistent Daily Planning / Reflection and Coach modes. Done.
- **Phase 5**: RAG 2.0 with real embeddings, Qdrant persistence, hybrid retrieval, and re-indexing. Done.
- **Phase 6**: Permissioned read-only real tool integrations and live briefing context. Done.
- **Phase 7**: Permissioned MCP client with stdio/Streamable HTTP, discovery, policies, audit, retries, normalized results, and Planning context. Done.
- **Next**: Multi-agent coordination with Memory, Planner, Tool, Reflection, and Coach responsibilities.
- **Later**: Multi-agent coordination, advanced memory importance/compression, proactive triggers, and the dashboard.
- **Long-term direction**: Voice and vision interfaces, smart-home adapters, and optional robotics integration built on the same Nexus core.
