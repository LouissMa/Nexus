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

## Phase 5: RAG 2.0 Foundation

Objective: replace the local sparse-vector MVP with production-oriented semantic retrieval.

- [x] Add FastEmbed and OpenAI-compatible embedding providers.
- [x] Add local/remote Qdrant vector persistence.
- [x] Add `nexus memory reindex` and index status reporting.
- [x] Add incremental indexing for new memories.
- [x] Add dense+sparse hybrid retrieval and retrieval-quality tests.
- [x] Keep local sparse retrieval as an offline fallback.

## Phase 6: Real Tool Integrations

Objective: connect Nexus to useful external context through explicit adapters.

- [x] Add live weather through Open-Meteo.
- [x] Add iCalendar feeds with recurring-event expansion.
- [x] Add Todoist, GitHub, Notion, and read-only IMAP integrations.
- [x] Add permission-bounded local filesystem list/read/search.
- [x] Add local credential configuration, explicit enable/disable controls, and masked output.
- [x] Add success/failure audit records without secrets.
- [x] Add live weather/calendar/todo context to morning briefings.

The Phase 6 integration layer remains read-only by design. Phase 7 can call external MCP tools, including potentially mutating tools, only through explicit deny/ask/allow policies.

## Phase 7: MCP Tool Calling

Objective: give Nexus a standard, permissioned way to discover and call tools.

- [x] MCP server configuration and discovery over stdio and Streamable HTTP.
- [x] Tool schemas and an official-SDK gateway interface.
- [x] Per-tool deny, ask, and allow approval policies.
- [x] Secret-safe call logs, errors, bounded retries, and result normalization.
- [x] Let planning flows invoke explicitly approved tools with partial-failure fallback.

Nexus is an MCP client in this phase. Autonomous LLM tool selection belongs to the Multi-Agent Tool Agent phase; exposing Nexus itself as an MCP server remains separate future work.

## Phase 8: Multi-Agent Coordination

Objective: separate complex responsibilities without fragmenting the user experience.

- [ ] Memory Agent.
- [ ] Planner Agent.
- [ ] Tool Agent.
- [ ] Reflection Agent.
- [ ] Coach Agent.
- [ ] Orchestration, shared state, budgets, and traceability.

## Phase 9: Advanced Long-Term Memory

Objective: make memory useful and maintainable at personal scale.

- [ ] Memory importance scoring.
- [ ] Deduplication and conflict handling.
- [ ] Compression, summarization, and archival.
- [ ] Forgetting, retention, privacy, and user controls.
- [ ] Retrieval re-ranking using task and time context.

## Phase 10: Proactive Runtime and Dashboard

Objective: make Nexus available at the right time and make its state visible.

- [ ] Scheduler for morning briefings, evening reviews, and reminders.
- [ ] Notification channels and quiet hours.
- [ ] Web dashboard with Today, goals, tasks, memory, and tool activity.
- [ ] Permission, audit, and agent activity views.
- [ ] Browser and approved local automation.

## Phase 11: Multimodal and Embodied Interfaces

Objective: explore additional interfaces around the stable Nexus core.

- [ ] Voice input, wake-word flow, and speech output.
- [ ] Permissioned vision and household context.
- [ ] Smart-home adapters and family profiles.
- [ ] Robotics adapter with simulation-first safety testing.
- [ ] Research companion workflows for literature, code, and experiments.

This phase is a long-term research direction. It does not imply that the current project is AGI or can autonomously control a home or robot.
