# Nexus / LifeAgent

> **A proactive personal AI operating system for daily life.**

Nexus is a J.A.R.V.I.S.-like personal AI assistant that remembers your goals, retrieves relevant long-term context, and helps you take action every day.

[English](./README.md) | [Chinese](./README_zh.md)

---

## Product Direction

Most AI assistants are passive. They wait for users to ask questions.

Nexus is different: it is designed to remember, plan, remind, review, and eventually act through approved tools.

The long-term vision is to build a **Personal AI Operating System**.

## Current Features

- **Memory**: Add, list, keyword-search, and RAG-retrieve long-term memories.
- **RAG Long-Term Memory**: Store local sparse embeddings and retrieve relevant memories for briefings.
- **Goal Tracker**: Add goals with descriptions and check-in cadence.
- **Goal Check-In**: Record progress notes for goals.
- **Proactive Review**: Detect stale goals and generate reminders.
- **Daily Review / Reflection**: Generate an evening review with completed goals, quiet goals, RAG memories, and tomorrow priorities.
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

## RAG Long-Term Memory

The current RAG MVP is local and does not require an external embedding API.

```bash
nexus memory retrieve "IELTS listening practice" --limit 3
nexus briefing --llm --show-prompt --name Louis
```

What happens:

- 
exus memory add` stores a deterministic local sparse embedding.
- 
exus memory retrieve` returns relevant memories with `retrieval_score`.
- 
exus briefing` builds a retrieval query from goals, reminders, weather text, and user context.
- If retrieval finds no relevant memories, Nexus falls back to recent memories.

Future work: replace the local sparse embedder with a real embedding model and vector database.

## LLM Usage

Nexus works without an API key for local memory, goals, check-ins, proactive review, template briefing, and local RAG retrieval.

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

nexus goal add "Develop Nexus" --description "Ship MVP features" --cadence-days 2
nexus goal list
nexus goal check-in <goal_id> "Finished today's session."

nexus review
nexus review day --name Louis
nexus review day --llm --show-prompt --name Louis
nexus briefing --name Louis --weather "weather is sunny, high 25 C"
nexus briefing --llm --show-prompt --name Louis

nexus config llm set --provider deepseek --api-key "your-key" --simple-model v4flash --complex-model v4pro
nexus config llm show
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
- **Phase 4**: Daily Review / Reflection MVP. Done.
- **Next**: Real integrations, MCP tool calling, multi-agent architecture, scheduler, dashboard, and browser/local automation.


