# Nexus MVP Architecture

The current version is a local CLI MVP. It intentionally avoids external APIs until the core product loop is proven.

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
  |-- Morning briefing
  |
  v
[JsonStore]
  |
  v
[.nexus/state.json]
```

## Current Modules

- `src/nexus/cli.py`: command-line interface and argument parsing.
- `src/nexus/service.py`: product logic for memory, goals, check-ins, review, and briefing.
- `src/nexus/store.py`: local JSON persistence.
- `tests/test_cli.py`: end-to-end CLI flow tests.

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

## MVP Data Flow

```text
Add memory
  -> save user context

Add goal
  -> save target and cadence

Check in
  -> update progress timestamp and note

Briefing
  -> load memories and active goals
  -> select up to three important goals
  -> run proactive review
  -> generate daily text summary
```

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
  |-- Goal engine
  |-- Briefing engine
  |-- Review engine
  |-- Coach mode controller
  |-- Integration adapters
  |
  +--> [Relational DB: goals, tasks, habits]
  +--> [Vector DB: long-term semantic memory]
  +--> [Scheduler: morning briefing, evening review, reminders]
  +--> [LLM API: reasoning and generation]
  +--> [External tools: calendar, weather, email, Notion, GitHub, health]
```

## Design Constraint

Nexus should not fake integrations. Until calendar, weather, email, and health data are connected, the CLI accepts explicit text inputs such as `--weather` and uses stored memories/goals as the main context.
