# Execution Framework Evaluation

Reviewed on 2026-09-09. This is an initial source/interface comparison, not a
performance benchmark or a claim of completed Windows integration testing.

| Candidate | Pinned revision and inspected material | Fit and decision |
| --- | --- | --- |
| LangGraph | `0199b519e1f98bd9a108b91fc5ea3a489a728d9f`; [types.py](https://github.com/langchain-ai/langgraph/blob/0199b519e1f98bd9a108b91fc5ea3a489a728d9f/libs/langgraph/langgraph/types.py), repository README | Explicit checkpoints, commands, interrupts and retry/timeout types are relevant to durable execution. Candidate for 15.2/15.3; test replay and approval semantics before adoption. Repository reports MIT. |
| smolagents | `30bb1161095dbae2271e6bc3cc4c219cc3897a57`; [tools.py](https://github.com/huggingface/smolagents/blob/30bb1161095dbae2271e6bc3cc4c219cc3897a57/src/smolagents/tools.py), README, LICENSE | Tool input/output declarations are useful reference points. A schema-oriented adapter suits existing Nexus services; generated-code execution is not required for this increment. Pinned LICENSE is Apache-2.0. |
| OpenClaw | `7c6ca652ef75c7bea81659879424551fabfdafe3`; [common.ts](https://github.com/openclaw/openclaw/blob/7c6ca652ef75c7bea81659879424551fabfdafe3/src/agents/tools/common.ts), repository overview | Typed tool metadata, parameter preparation and tool-result helpers are useful references. Its TypeScript/runtime integration requires a separate interoperability assessment for Nexus's Python services. Pinned license verification and end-to-end integration testing remain pending. |

Revisions were resolved with read-only `git ls-remote ... HEAD`. Source inspection
was limited to the linked interfaces, not a whole-repository review. The OpenClaw
raw-file web fetch failed; the same pinned source was read with a direct HTTPS
request. At that initial review no framework was installed or executed. Maintenance and
Windows-runtime suitability have not been established by these reads alone.

## Current Decision

Implement framework-neutral Nexus tool contracts first, using the existing
`jsonschema` dependency. Preserve ToolManager/AutomationManager as permission and
execution owners. Phase 15.2 subsequently selects optional LangGraph 1.2.11 for
foreground graph execution after actual Windows tests. No external source is
copied. A durable executor/checkpointer choice still requires Phase 15.3 work.

This allows a later LangGraph or another runtime adapter to use the same tool
boundary. Avoiding framework coupling here is a scoped engineering choice, not
evidence that a custom runtime would outperform the candidates.

## Phase 15.2 Validation

Installed and ran LangGraph 1.2.11. Runtime tests cover a real decision/action
graph, Nexus tool adapters, permission stop, unknown side effects, repeats and
CLI. An in-memory checkpoint/interrupt/resume smoke test confirms the preceding
completed node is not replayed. Installed metadata reports MIT for LangGraph,
its checkpoint package, langchain-core and langsmith. This selects a foreground
runtime, not a complete persistence implementation or a benchmark winner.
No real-provider task-quality comparison was performed.

## Remaining Selection Work

- [ ] Inspect each candidate's actual execution and approval/recovery paths.
- [ ] Confirm licenses and dependency obligations for any code selected for reuse.
- [ ] Run the same Windows tool-call, interruption, resume and uncertain-write tests.
- [ ] Measure dependency footprint, cold start, failure recovery and integration effort.
- [ ] Record a runtime adoption decision before implementing framework-specific persistence.
