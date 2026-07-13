# Nexus MVP Architecture

The current version is a local CLI MVP with an optional LLM briefing layer. It still works fully offline by default, and only calls an external LLM when the user explicitly passes `--llm` and configures an API key.

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
- `src/nexus/rag.py`: local sparse embedding and deterministic memory retrieval for the RAG MVP.
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

## RAG Memory Flow

```text
Add memory
  -> build local sparse embedding
  -> store memory + embedding in .nexus/state.json

Retrieve memory
  -> embed query locally
  -> score memories by cosine similarity
  -> return public memory fields + retrieval_score

Briefing
  -> build query from user name, weather, active goals, and reminders
  -> retrieve relevant long-term memories
  -> inject memories and retrieval metadata into the briefing prompt
  -> fall back to recent memories if no relevant result is found
```

The current RAG implementation is intentionally local and dependency-free. It proves the product loop before adding external embedding APIs or a vector database.
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
[CLI / Web / Mobile / Chat]
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
  |
  +--> [Relational DB: goals, tasks, habits]
  +--> [Vector DB: long-term semantic memory]
  +--> [Scheduler: morning briefing, evening review, reminders]
  +--> [LLM API: reasoning and generation]
  +--> [External tools: calendar, weather, email, Notion, GitHub, health]
```
