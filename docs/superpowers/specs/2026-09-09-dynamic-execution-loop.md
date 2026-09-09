# Dynamic Execution Loop

Phase 15.2 provides a foreground LangGraph decision/action loop over ToolRegistry.
It requires the optional executor extra and an explicitly configured text LLM.

`nexus executor run GOAL` -> decide -> validated next-action JSON -> tool call ->
observation -> decide again or terminate. Actions are tool, ask_user, fail, or
finish with successful observation numbers. Models cannot supply approval.
Existing allow-policy tools may run; ask-policy tools stop before side effects.

## Limits

- Default 12 decisions (range 1-50), 120-second time budget (range 1-600).
- The deadline is cooperative: passed to the LLM and checked between steps.
  Tools retain adapter timeouts; a blocking tool without a timeout can overrun it.
- Goals: 4,000 characters; model responses: 16 KiB; prompts: 128 KiB.
- Only eight recent observations enter each prompt. Data over 6,000 characters
  becomes an explicitly truncated excerpt. Full bounded observations remain in
  the returned run state.
- Identical calls are capped at two for idempotent reads and one otherwise.
  Unknown side effects stop with needs_review. No automatic replay occurs.

## Outcomes

Completion returns reported_complete with verification=tool_references_only.
Successful reference numbers are checked, but factual correctness, user acceptance,
and generated artifacts are not independently verified. Other states include
waiting_approval, waiting_input, failed, model_failed, invalid_completion,
repeated_action, no_tools, context_limit, budget_exhausted, needs_review, cancelled.
Interrupted tools retain unknown outcomes and the pending action.

Run state is in memory only. There is no product resume/checkpoint command yet;
rerunning starts a new task and may repeat prior work. RAG, MCP, shared voice task
state, general report writing and independent artifact verification remain future
adapters/stages. Existing executor tools/call commands remain available.

Tool observations can be sent to the configured LLM. The prompt marks tool data
as untrusted; this is guidance, not a guarantee against prompt injection. Tool
permissions remain enforced by the registry. LangSmith tracing is disabled around
graph execution. Automated tests use scripted models, not paid provider calls.

## Runtime Validation

LangGraph 1.2.11 is the selected optional foreground graph runtime. Tests execute
real LangGraph and real filesystem adapters, including observation-driven decisions,
approval stop, invalid actions, repeat limits, uncertainty, cancellation and CLI.
A separate InMemorySaver/interrupt/Command test resumes in process and verifies
that the preceding completed node is not replayed. This is not crash recovery or
product approval resume; those remain Phase 15.3.

Installed package metadata reports MIT for langgraph, langgraph-checkpoint,
langchain-core and langsmith. No third-party source is vendored. The local install
was checked for dependency conflicts; AnyIO 4.10.0 and typing_extensions 4.13.2
preserve compatibility with this machine's existing Selenium. Unrelated d2l and
mlfromscratch conflicts remain in the shared Python environment.
