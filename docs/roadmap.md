# Nexus Development Roadmap

## Phase 1: LifeAgent CLI MVP

Objective: prove the smallest useful loop of a personal AI manager.

- [x] Project structure and local Python CLI.
- [x] Local JSON storage.
- [x] Add long-term memories.
- [x] Search memories by keyword.
- [x] Add goals.
- [x] Goal check-ins.
- [x] Proactive review for stale goals.
- [x] Morning briefing command.

## Phase 2: LLM Briefing

Objective: make the morning briefing intelligent while keeping the offline MVP stable.

- [x] Add OpenAI-compatible LLM client.
- [x] Configure LLM through environment variables.
- [x] Build structured briefing context from memories, goals, reminders, and weather text.
- [x] Build inspectable system/user prompts.
- [x] Add `nexus briefing --llm`.
- [x] Add `nexus briefing --show-prompt`.
- [x] Keep safe fallback when LLM is not configured or fails.

## Phase 3: RAG Long-Term Memory

Objective: replace simple recent-memory recall with semantic memory retrieval.

- [ ] Add embedding interface.
- [ ] Store memory embeddings locally.
- [ ] Retrieve relevant memories by semantic similarity.
- [ ] Feed retrieved memories into the briefing prompt.
- [ ] Add tests for deterministic retrieval behavior.

## Phase 4: Daily Review and Coaching Modes

Objective: make Nexus useful at both the start and end of the day.

- [ ] Add evening review command.
- [ ] Generate "today summary + tomorrow plan".
- [ ] Add coach tone modes: strict, gentle, academic, startup.
- [ ] Add structured task priority and due dates.
- [ ] Improve reminders from simple cadence checks to richer progress signals.

## Phase 5: Life Dashboard

Objective: make the user's life context visible.

- [ ] Web dashboard.
- [ ] Today view.
- [ ] Long-term goals view.
- [ ] Memory timeline.
- [ ] Habit tracker.
- [ ] Project progress panel.
- [ ] AI suggestions panel.

## Phase 6: Tools, Automation, and Agents

Objective: evolve Nexus from assistant to permissioned personal operating layer.

- [ ] MCP tool calling.
- [ ] Browser automation.
- [ ] Local tool execution with permission boundaries.
- [ ] Planning agent.
- [ ] Reflection agent.
- [ ] Memory agent.
- [ ] Tool agent.
- [ ] Multi-channel delivery: CLI, web, mobile, chat, and notifications.
