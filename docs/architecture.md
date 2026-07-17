# Nexus MVP Architecture

The current version is a local-first CLI assistant with optional LLM generation and optional semantic RAG. Core features remain usable offline. LLM calls occur only when the user passes `--llm`; hosted embeddings are optional because FastEmbed can run locally.

## Current Architecture

```text
[User]
  |
  v
[Nexus CLI]
  |
  v
[NexusService]
  |-- Memory operations
  |-- Goal operations
  |-- Goal check-ins
  |-- Proactive review
  |-- Briefing context builder
  |-- Template briefing renderer
  |-- LLM prompt builder
  |
  +--> [OpenAICompatibleLLM]
  |       |
  |       v
  |     [OpenAI-compatible Chat Completions API]
  |
  v
[JsonStore]
  |
  v
[.nexus/state.json]
```

## Current Modules

- `src/nexus/cli.py`: CLI parsing for `memory`, `goal`, `plan`, `task`, `review`, `briefing`, and `config`.
- `src/nexus/service.py`: Application orchestration for memory/RAG, goals, persistent daily planning, structured task updates, reflection, coach-aware prompts, and briefings.
- `src/nexus/embeddings.py`: FastEmbed and OpenAI-compatible neural embedding providers.
- `src/nexus/vector_store.py`: local/remote Qdrant persistence and collection operations.
- `src/nexus/rag.py`: sparse retrieval, semantic indexing, hybrid score fusion, metadata, re-indexing, and fallback.
- src/nexus/planning.py: daily-task decomposition rules, task status vocabulary, and Coach profiles.
- `src/nexus/llm.py`: OpenAI-compatible LLM client, environment-based configuration, HTTP request handling, and LLM errors.
- `src/nexus/store.py`: local JSON persistence.
- `tests/test_cli.py`: end-to-end CLI flow tests plus LLM fallback and injected fake-LLM tests.

## Data Model

```text
Memory
- id
- text
- tags
- created_at

Goal
- id
- title
- description
- cadence_days
- status
- created_at
- last_check_in
- check_ins

CheckIn
- at
- note
```

## Briefing Flow

```text
nexus briefing
  -> load memories and active goals
  -> select recent memories
  -> select up to three important active goals
  -> run proactive review
  -> build briefing context
  -> render local template briefing
  -> return JSON
```


## Planning / Reflection Flow

```text
nexus plan day
  -> load active long-term goals
  -> sort goals by oldest progress
  -> create up to three prioritized daily tasks
  -> persist tasks in .nexus/state.json
  -> retrieve relevant memories
  -> render local plan or optional LLM plan with Coach mode

nexus task update <task_id>
  -> update pending / in_progress / completed / blocked status
  -> store blocker, unresolved items, and progress notes

nexus review day
  -> collect today's task state and goal check-ins
  -> collect blockers and unresolved items
  -> retrieve relevant long-term memories
  -> place carry-forward work into tomorrow priorities
  -> render local reflection or optional LLM reflection with Coach mode
```

Daily plans are idempotent per date: running `nexus plan day` again returns the existing tasks instead of creating duplicates.

## RAG 2.0 Memory Flow

```text
Configure
  -> choose local FastEmbed or an OpenAI-compatible embedding endpoint
  -> choose local Qdrant persistence or remote Qdrant

Add memory
  -> store deterministic sparse features in .nexus/state.json
  -> generate a neural embedding when semantic RAG is enabled
  -> incrementally upsert vector + public payload into Qdrant

Retrieve memory
  -> generate dense query embedding
  -> query Qdrant semantic candidates
  -> score local sparse candidates
  -> fuse dense and sparse scores
  -> return memories plus provider/model/strategy/score/error metadata
  -> automatically use sparse-only results if semantic retrieval fails

Re-index
  -> load all memories
  -> regenerate embeddings with the current provider/model
  -> recreate the Qdrant collection
  -> persist index metadata in .nexus/state.json

Briefing / Planning / Review
  -> build a task-specific retrieval query
  -> retrieve relevant long-term memories
  -> inject memories and retrieval metadata into local and LLM contexts
```

Local FastEmbed requires no API key but downloads its model on first use. Hosted embedding providers require their own API key. The local Qdrant index lives under `.nexus/qdrant/` and is not committed.

## LLM Briefing Flow

```text
nexus briefing --llm
  -> load memories, goals, reminders, weather text
  -> build structured briefing context
  -> build system prompt and user prompt
  -> if LLM is configured:
       call OpenAI-compatible chat completions API
       use model output as briefing
     else:
       keep local template briefing
       report configuration error in llm.error
  -> return JSON with briefing, context, llm status, and optional prompt
```

## LLM Configuration

The LLM layer is configured by environment variables:

```text
NEXUS_LLM_API_KEY          optional, takes priority over OPENAI_API_KEY
OPENAI_API_KEY             fallback API key
NEXUS_LLM_MODEL            default: gpt-4o-mini
NEXUS_LLM_BASE_URL         default: https://api.openai.com/v1
NEXUS_LLM_TIMEOUT_SECONDS  default: 30
```

## Design Constraints

- Nexus should not fake integrations. Until calendar, weather, email, and health data are connected, the CLI accepts explicit text inputs such as `--weather`.
- LLM usage must be optional. The local template path remains the stable fallback.
- The service layer owns product decisions. The CLI only parses arguments and wires dependencies.
- Prompt construction is inspectable with `--show-prompt`, so future RAG and agent behavior can be debugged clearly.

## Future Architecture

```text
[User]
  |
  v
[CLI / Web / Mobile / Chat / Voice gateway / Vision gateway]
  |
  v
[Backend API]
  |-- Memory engine
  |-- RAG retriever
  |-- Goal engine
  |-- Briefing engine
  |-- Review engine
  |-- Planning engine
  |-- Reflection engine
  |-- Coach mode controller
  |-- MCP tool adapters
  |-- Browser/local automation adapters
  |-- Smart-home adapters (long-term)
  |-- Robotics adapters (long-term, simulation-first)
  |
  +--> [Relational DB: goals, tasks, habits]
  +--> [Vector DB: long-term semantic memory]
  +--> [Scheduler: morning briefing, evening review, reminders]
  +--> [LLM API: reasoning and generation]
  +--> [External tools: calendar, weather, email, Notion, GitHub, health]
```
The architecture keeps one Nexus core across interfaces. Voice, vision, home, and robotics integrations are future adapters behind the same permission and audit boundaries; they are not part of the current CLI product.
