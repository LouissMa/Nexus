# AIOS Task Checklist

This checklist tracks the remaining work required to evolve Nexus into a J.A.R.V.I.S.-like Personal AI Operating System. Update this file whenever a feature is completed, changed, deferred, or split into smaller work.

Status legend:

- `[x]` Completed
- `[~]` In progress / MVP exists but needs deeper implementation
- `[ ]` Not started

## Agreed Implementation Order

1. Planning / Reflection. Completed.
2. RAG 2.0 foundation: real embeddings, vector database, and re-indexing. Completed.
3. Real tool integrations. Completed.
4. MCP tool calling and permissions. Completed.
5. Multi-Agent coordination. Completed.
6. Advanced memory importance, compression, and retention.
7. Proactive triggers and Dashboard.
8. Long-term multimodal, smart-home, and robotics interfaces after the core is dependable.

## Completed Foundation

- [x] CLI MVP for memory, goals, check-ins, proactive review, and morning briefing.
- [x] LLM briefing mode with OpenAI-compatible API support.
- [x] Local LLM provider configuration with provider/model tiers and masked API key display.
- [x] Local RAG memory MVP using deterministic sparse embeddings.
- [x] Planning / Reflection module with persistent daily tasks, blockers, unresolved items, and coach modes.
- [x] Local JSON storage under `.nexus/state.json`.
- [x] Secret local config path ignored by Git: `.nexus/config.local.json`.

## 1. RAG Long-Term Memory

Current status: `[x]` RAG 2.0 and the Phase 9 advanced memory lifecycle are completed.

- [x] Generate deterministic local sparse embeddings when memories are added.
- [x] Add `nexus memory retrieve` for relevant memory retrieval.
- [x] Inject retrieved memories into briefing, planning, and review contexts and LLM prompts.
- [x] Include query, strategy, provider, model, candidate counts, component scores, and errors in retrieval metadata.
- [x] Add a real embedding provider interface.
- [x] Add local FastEmbed support without an API key.
- [x] Add OpenAI-compatible hosted embedding support.
- [x] Add persistent local or remote Qdrant vector storage.
- [x] Add `nexus memory reindex` and `nexus memory index-status`.
- [x] Incrementally index newly added memories.
- [x] Add dense+sparse hybrid retrieval with local sparse fallback.
- [x] Add deterministic retrieval, re-index, empty-index, and secret-masking tests.

Completed in Advanced Long-Term Memory (Phase 9):

- [x] Add memory importance scoring.
- [x] Add deduplication and conflict handling.
- [x] Add memory compression/summarization for long-term scale.
- [x] Add retention, forgetting, privacy, and user controls.

## 2. Real Tool Integrations

Current status: `[x]` Permissioned read-only integration phase completed.

- [x] Weather integration through Open-Meteo geocoding and forecast APIs.
- [x] Calendar integration through private/public iCalendar feed URLs.
- [x] Expand recurring iCalendar events for courses and meetings.
- [x] Todo integration through the current Todoist API.
- [x] GitHub repository metadata and open-issue integration.
- [x] Notion page-title search integration.
- [x] Read-only IMAP email-header integration.
- [x] Local filesystem list/read/search with configured-root boundaries.
- [x] Store credentials only in ignored local config or environment variables.
- [x] Require explicit tool enablement and operation-level permissions.
- [x] Add secret-safe success/failure audit logging.
- [x] Add `nexus briefing --live-tools` for weather, calendar, and todo context.
- [x] Add deterministic tests plus a real Open-Meteo smoke test.

All Phase 6 adapters remain intentionally read-only. Phase 7 adds separately configured MCP tools with explicit policies, one-shot approvals, bounded transport retries, and normalized results.

## 3. MCP Tool Calling

Current status: `[x]` Permissioned MCP client phase completed.

- [x] Define MCP gateway, tool-schema, and normalized result interfaces.
- [x] Add stdio and Streamable HTTP server configuration and tool discovery.
- [x] Add deny, ask, and allow per-tool permission policies.
- [x] Add explicit one-shot approval for ask-policy calls.
- [x] Add secret-safe discovery/call logging, bounded transport retries, and error normalization.
- [x] Let `nexus plan day --live-mcp` call explicitly configured allow-policy planning tools.
- [x] Preserve local Planning when an MCP server or tool fails.
- [x] Add fake-gateway tests plus real stdio and Streamable HTTP protocol tests.

Deferred to later phases: autonomous LLM tool selection, a dedicated Tool Agent, and exposing Nexus itself as an MCP server.

## 4. Planning / Reflection

Current status: `[x]` Local Planning / Reflection module completed.

- [x] Add daily planning command: `nexus plan day`.
- [x] Break active long-term goals into persistent daily tasks.
- [x] Add evening review command: `nexus review day`.
- [x] Generate today summary and tomorrow priorities.
- [x] Include progressed goals, quiet goals, check-ins, reminders, and RAG memories.
- [x] Track task blockers and unresolved items as structured fields.
- [x] Add coach modes: strict, gentle, academic, startup.
- [x] Add task inspection and updates with `nexus task list` and `nexus task update`.

The local module is complete. Phase 8 now orchestrates agentic planning and permissioned MCP tool selection; calendar-aware scheduling and automatic replanning remain future work.

## 5. Multi-Agent Architecture

Current status: `[x]` Bounded multi-agent coordination completed.

- [x] Memory Agent: retrieves task-relevant RAG memories and public retrieval metadata.
- [x] Planner Agent: creates persistent plans and briefing priorities from shared artifacts.
- [x] Tool Agent: runs deterministic bindings or strict-JSON LLM selection over allow-policy MCP tools only, with complete JSON Schema validation for both paths.
- [x] Reflection Agent: reviews outcomes, blockers, unresolved items, check-ins, and tomorrow priorities.
- [x] Coach Agent: applies strict, gentle, academic, or startup tone with optional LLM generation.
- [x] Add orchestration for plan, review, and briefing workflows.
- [x] Add shared artifacts and explicit limits for steps, LLM calls, MCP calls, and runtime.
- [x] Add partial-failure isolation and deterministic local fallback.
- [x] Add privacy-safe JSONL traces plus `nexus agent runs/show` inspection.
- [x] Add opt-in `--agents` without changing default command behavior.

Phase 8 does not create open-ended autonomous loops. Human approval remains required for `ask` MCP tools, and browser/local automation remains a later permissioned phase.

## 6. Advanced Long-Term Memory

Current status: `[x]` Local-first memory lifecycle completed.

- [x] Add deterministic importance scoring plus user override and pinning.
- [x] Merge normalized exact duplicates and link near duplicates.
- [x] Add explicit supersedes and bidirectional conflict relations.
- [x] Add deterministic summary records and reversible source archival.
- [x] Separate compressed summaries by privacy, inherit expiry, and retain source lineage.
- [x] Cascade source forgetting to derived summaries so copied content cannot leak.
- [x] Propagate source privacy/expiry changes, reject direct derived-policy overrides, and recompute policy on restore.
- [x] Recursively remove derived summaries when a source is permanently purged.
- [x] Add expiry maintenance with dry-run previews.
- [x] Add private, personal, and shared retrieval scopes.
- [x] Add reversible archive, restore, and forget controls.
- [x] Require forgotten state plus explicit confirmation for permanent purge.
- [x] Reject stale vector IDs using authoritative JSON eligibility.
- [x] Report partial index-sync outcomes when add or mutation vector refresh fails.
- [x] Re-rank by relevance, importance, recency, and task/tag context.
- [x] Expose component scores and lifecycle filter metadata.
- [x] Preserve legacy state compatibility without destructive migration.
## 7. Proactive Trigger System

Current status: `[ ]` Not started.

- [ ] Add scheduler abstraction.
- [ ] Generate morning briefing automatically.
- [ ] Generate evening review automatically.
- [ ] Add reminder rules for stale goals.
- [ ] Add notification channels.
- [ ] Add user-configurable quiet hours.

## 8. Frontend Dashboard

Current status: `[ ]` Not started.

- [ ] Build web dashboard shell.
- [ ] Today tasks view.
- [ ] Long-term goals view.
- [ ] Memory timeline.
- [ ] Habit tracking panel.
- [ ] Project progress panel.
- [ ] AI suggestions panel.

## 9. Browser And Local Automation

Current status: `[ ]` Not started.

- [ ] Browser automation adapter.
- [ ] GitHub project inspection workflow.
- [ ] README/report generation workflow.
- [ ] Local command execution with explicit permission checks.
- [ ] Audit log for automated actions.

## 10. Long-Term Multimodal And Embodied Interfaces

Current status: `[ ]` Research direction, not started.

- [ ] Voice input and speech output.
- [ ] Permissioned visual context.
- [ ] Smart-home adapters and family profiles.
- [ ] Robotics adapter with simulation-first safety controls.
- [ ] Research companion workflows for literature, code, and experiments.

These interfaces should reuse the same Nexus memory, planning, permission, and tool layers. They are not current capabilities and should not be presented as AGI.

## Maintenance Rules

- [ ] After every important feature, update this checklist.
- [ ] After every new important file, update `docs/file_inventory.md`.
- [ ] After every user-facing feature, update both `README.md` and `README_zh.md`.
- [ ] Run tests before committing when possible.
- [ ] Ask the user whether to push, unless the user explicitly asked to push in the current request.
- [ ] Never commit API keys or local secret config files.
