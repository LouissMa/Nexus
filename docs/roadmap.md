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

Objective: replace simple recent-memory recall with relevant local memory retrieval.

- [x] Add local embedding interface.
- [x] Store deterministic sparse memory embeddings locally.
- [x] Retrieve relevant memories by similarity.
- [x] Feed retrieved memories into briefing and review prompts.
- [x] Add tests for deterministic retrieval behavior.

Production-grade neural embeddings, vector database persistence, re-indexing, importance scoring, and memory compression remain future RAG work.

## Phase 4: Daily Planning, Review, and Coaching Modes

Objective: make Nexus useful at both the start and end of the day.

- [x] Add persistent daily planning command.
- [x] Decompose active long-term goals into prioritized daily tasks.
- [x] Add task status, blocker, unresolved-item, and note updates.
- [x] Add evening review command.
- [x] Generate today summary and tomorrow priorities.
- [x] Add coach tone modes: strict, gentle, academic, startup.
- [x] Feed structured task outcomes and blockers into Reflection prompts.

Calendar-aware scheduling, automatic replanning, and agentic execution remain future work.

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
