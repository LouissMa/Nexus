# AIOS Task Checklist

This checklist tracks the remaining work required to evolve Nexus into a J.A.R.V.I.S.-like Personal AI Operating System. Update this file whenever a feature is completed, changed, deferred, or split into smaller work.

Status legend:

- `[x]` Completed
- `[~]` In progress / MVP exists but needs deeper implementation
- `[ ]` Not started

## Completed Foundation

- [x] CLI MVP for memory, goals, check-ins, proactive review, and morning briefing.
- [x] LLM briefing mode with OpenAI-compatible API support.
- [x] Local LLM provider configuration with provider/model tiers and masked API key display.
- [x] Local RAG memory MVP using deterministic sparse embeddings.
- [x] Local JSON storage under `.nexus/state.json`.
- [x] Secret local config path ignored by Git: `.nexus/config.local.json`.

## 1. RAG Long-Term Memory

Current status: `[~]` Local MVP completed. Real vector retrieval is still future work.

- [x] Generate local memory embeddings when memories are added.
- [x] Add `nexus memory retrieve` for relevant memory retrieval.
- [x] Inject retrieved memories into briefing context and LLM prompt.
- [x] Include retrieval metadata such as query, strategy, and score.
- [ ] Add real embedding model support.
- [ ] Add vector database persistence.
- [ ] Add memory re-index command.
- [ ] Add memory importance scoring.
- [ ] Add memory compression/summarization for long-term scale.

## 2. Real Tool Integrations

Current status: `[ ]` Not started.

- [ ] Weather API integration.
- [ ] Calendar integration.
- [ ] GitHub integration.
- [ ] Notion integration.
- [ ] Email integration.
- [ ] Todo/task app integration.
- [ ] Local filesystem integration with permission boundaries.

## 3. MCP Tool Calling

Current status: `[ ]` Not started.

- [ ] Define MCP tool adapter interface.
- [ ] Add MCP server discovery/configuration.
- [ ] Add safe tool permission model.
- [ ] Add tool call logging.
- [ ] Let Nexus call approved MCP tools from planning flows.

## 4. Planning / Reflection

Current status: `[ ]` Not started.

- [ ] Add daily planning command.
- [ ] Break long-term goals into today's tasks.
- [ ] Add evening review command.
- [ ] Generate today summary and tomorrow plan.
- [ ] Track blockers and unresolved tasks.
- [ ] Add coach modes: strict, gentle, academic, startup.

## 5. Multi-Agent Architecture

Current status: `[ ]` Not started.

- [ ] Memory Agent: retrieves and summarizes relevant memory.
- [ ] Planner Agent: decomposes goals into plans.
- [ ] Tool Agent: selects and calls tools.
- [ ] Reflection Agent: reviews outcomes and blockers.
- [ ] Coach Agent: adapts tone and final response.
- [ ] Add orchestration layer for agent collaboration.

## 6. Proactive Trigger System

Current status: `[ ]` Not started.

- [ ] Add scheduler abstraction.
- [ ] Generate morning briefing automatically.
- [ ] Generate evening review automatically.
- [ ] Add reminder rules for stale goals.
- [ ] Add notification channels.
- [ ] Add user-configurable quiet hours.

## 7. Frontend Dashboard

Current status: `[ ]` Not started.

- [ ] Build web dashboard shell.
- [ ] Today tasks view.
- [ ] Long-term goals view.
- [ ] Memory timeline.
- [ ] Habit tracking panel.
- [ ] Project progress panel.
- [ ] AI suggestions panel.

## 8. Browser And Local Automation

Current status: `[ ]` Not started.

- [ ] Browser automation adapter.
- [ ] GitHub project inspection workflow.
- [ ] README/report generation workflow.
- [ ] Local command execution with explicit permission checks.
- [ ] Audit log for automated actions.

## Maintenance Rules

- [ ] After every important feature, update this checklist.
- [ ] After every new important file, update `docs/file_inventory.md`.
- [ ] After every user-facing feature, update both `README.md` and `README_zh.md`.
- [ ] Run tests before committing when possible.
- [ ] Ask the user whether to push, unless the user explicitly asked to push in the current request.
- [ ] Never commit API keys or local secret config files.
