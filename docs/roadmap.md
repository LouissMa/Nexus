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

- [ ] Weather integration.
- [ ] Calendar and todo integration.
- [ ] GitHub and Notion integration.
- [ ] Email and local filesystem integration.
- [ ] Add credentials, permission boundaries, and audit records.

## Phase 7: MCP Tool Calling

Objective: give Nexus a standard, permissioned way to discover and call tools.

- [ ] MCP server configuration and discovery.
- [ ] Tool schemas and adapter interface.
- [ ] Per-tool approval policy.
- [ ] Tool call logs, errors, retries, and result normalization.
- [ ] Let planning flows invoke approved tools.

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
