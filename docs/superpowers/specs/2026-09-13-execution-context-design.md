# Execution Context Design: Phase 15.4a

Status: implemented and verified.
Date: 2026-09-13.

## Goal and Scope

Give the durable executor bounded, attributable context from explicitly selected
goals, relevant eligible memories and one explicitly selected research project.
Reuse existing Nexus services. Do not add another research engine, tool executor,
database, model provider, or automatic memory writer.

Text/voice task routing and progress interfaces are Phase 15.4b, not this change.
Artifact verification remains Phase 15.5. Context is background information,
never evidence that an execution action succeeded.

## Alternatives and Decision

1. Selected sources plus bounded RAG (chosen): user controls scope; retrieval
   provides relevance; existing execution behavior remains compatible.
2. Automatically load all personal context: convenient, but unacceptable default
   disclosure and prompt size risks.
3. Let the model retrieve everything through tools: flexible, but expands the tool
   and approval surface before the context privacy contract is established.

## CLI Contract

These options enable the delivered context capture path:

```powershell
nexus executor run "Review my next research step" --with-context --context-goal GOAL_ID --context-research RESEARCH_ID
```

- `--with-context` enables relevant memory retrieval, default scope `shared`.
- `--context-goal ID` is repeatable, at most three unique IDs.
- `--context-research ID` selects at most one research project.
- Source selection and memory scope options require `--with-context`; reject
  contradictory options before creating a run or sending model requests.
- `--context-memory-scope shared|personal|private` follows the existing hierarchy.
  Selecting personal/private additionally requires `--allow-sensitive-context`.
- The CLI help explicitly states that selected goal/research fields and eligible
  memories may be sent to the configured model. No localhost-based trust inference.
- Existing runs and new runs without `--with-context` behave as before and do not
  construct a retriever or inspect personal sources.
- `executor show ID` exposes context provenance and degradation flags alongside
  the normal snapshot. No new Dashboard or voice command is included here.

## Components and Data Flow

Create `src/nexus/execution_context.py` with an ExecutionContextBuilder that uses
the existing Nexus service and memory eligibility rules. Keep data selection,
projection, budgets and source validation separate from LangGraph decisions.

1. CLI validates explicit selections and consent; PersistentExecutor validates
   goal and execution budgets before context capture or run creation.
2. Builder loads only the selected goals and research project; it retrieves at
   most five eligible memories using the task goal as query/task context.
3. Builder returns a versioned context envelope with projected content,
   provenance, policy, capture time, truncation flags and safe degradation codes.
4. PersistentExecutor saves the envelope and references in the existing run
   snapshot before model execution. No separate context database is introduced.
5. ExecutionRuntime includes it as a distinct background_context prompt field,
   treated as untrusted data rather than instructions, tool permissions or success
   observations. Existing overall prompt limits remain enforced.

Initial envelope fields: version=1, policy, captured_at, goals, memories, research,
references, degradations, truncated. Each reference records source kind, ID and a
digest of the selected source projection plus eligibility-relevant fields.
Memory provenance includes source ID, safe retrieval strategy, relevance score
and selected privacy scope. Do not copy raw provider error strings or configuration.

## Projection and Budgets

- At most three selected goals: ID, title, description, status and available
  planning metadata. Do not copy unrelated check-in or personal history arrays.
- At most five memories: ID, text, bounded tags, privacy, relevant retrieval
  scores and eligibility metadata. Exclude archived, forgotten and expired items.
- One selected active research project: ID, title, objective, up to five open
  questions and existing summary counts. Do not include full papers, notes,
  experimental output, local file locators or arbitrary source metadata.
- Every text field is capped at 1,000 Unicode characters, with truncation marked.
- The whole envelope is capped at 16 KiB of UTF-8 JSON including metadata. Drop
  lower-ranked memories first, then trailing questions and descriptions; retain
  source identity and flags. If even the minimal envelope exceeds the limit,
  fail before a model call rather than silently exceed the budget.
- No extra LLM call to summarize context. Configured RAG query embedding may use
  its existing external provider; disclose this in help/docs. This feature never
  re-indexes or sends source text for embedding automatically.
  Context capture uses existing retrieval adapter limits; the runtime time budget
  starts when the execution loop begins, not when context capture begins.

## Privacy, Persistence and Recovery

Goals and research projects lack the memory privacy labels, so explicit ID
selection is the consent boundary for their projected fields. Default memory
retrieval is shared-only, even though existing service methods default to private.
Filtering happens before context assembly; never obtain all private results and
merely hide their labels. Sensitive-scope consent belongs to this run, not global
configuration, and does not change tool policies.

On resume, validate selected references against canonical local sources before
any model or tool dispatch. Reuse the original context instead of silently
re-running retrieval and expanding its scope. Removal, expiry, archiving, privacy
change or a changed projected source digest blocks continuation with a bounded
context-stale error. A temporarily unavailable canonical store also blocks safely.
Do not silently downgrade to context-free execution for an existing context run.

Run status, pending action and approval tokens are not rewritten on a failed
context check. Unknown tool outcomes retain the Phase 15.3 needs_review path;
context validation cannot make an interrupted write safe to replay. No automatic
refresh, task restart or replay is offered as a repair for stale context in 15.4a.
Initial capture and later validation cannot be atomic with all source stores or
external model requests; document that limitation rather than promise revocation
of information already transmitted.

Context remains in the existing plaintext local snapshot. Source deletion does
not erase old run snapshots; this feature blocks re-use, not historical erasure.
Never copy API keys/provider configuration. Existing .nexus Git exclusion remains.

## Failures and Compatibility

Missing/archived explicitly selected goals or research projects are input errors,
not silent substitutions. An empty memory result is valid. Initial memory
retrieval failure may yield a context envelope with `memory_retrieval_unavailable`
and no memories; never attach an exception string or claim RAG succeeded.
Existing retriever sparse fallback remains usable and must be identified as such.
Old snapshots without context follow the original resume path unchanged.

## File Responsibilities

- `src/nexus/execution_context.py` (new): context policy, projections, provenance,
  limits and canonical-reference validation using existing service interfaces.
- `src/nexus/execution_store.py`: optional context capture/validation hooks in
  PersistentExecutor while preserving approval and crash-recovery ordering.
- `src/nexus/execution_runtime.py`: bounded background_context prompt field and
  explicit instruction that context is not successful execution evidence.
- `src/nexus/cli.py`: proposed opt-in options, consent validation and lazy builder
  wiring; no behavioral change to context-free runs.
- `tests/test_execution_context.py` (new): policy, projection, bounds and source
  invalidation tests with isolated local data and injected retrievers.
- Existing execution tests: prompt integration, durable reuse, old snapshots,
  no tool replay, unchanged approval and context-free compatibility.

## Acceptance Tests

Verification on 2026-09-13: executor regression 61 passed; final full suite
568 passed, 4 skipped (157.49 seconds). Independent review found and verified
the fix for budget validation occurring after retrieval. Three regression cases
now prove invalid budgets initialize no retriever and persist no run.
An earlier full run had one intermittent failure in the existing interprocess
automation configuration test; its isolated rerun and both later full runs passed.
No paid model calls were used. Tests ran under explicit `tests` discovery with
isolated temporary directories, without publishing personal configuration.

1. Private/personal sentinel text is absent from default context and model prompts.
2. Widening memory scope without explicit sensitive consent fails before model use.
3. Only selected goal/research IDs appear; rich project contents are not leaked.
4. Archived, expired and forgotten memories remain excluded in both retrieval
   and resume, including semantic hits whose canonical records are no longer eligible.
5. Retrieval failure exposes only a safe code; empty/fallback results are explicit.
6. Large Chinese and English sources stay within UTF-8 budgets and mark truncation.
7. Reopening a run reuses the same snapshot; new relevant memories are not appended.
8. Source changes/deletion block continuation before model/tool calls without
   resetting approvals or replaying writes. Unknown effects still require review.
9. Background context cannot satisfy finish evidence references.
10. CLI consent/options and old context-free run/resume paths remain compatible.

Use scripted models and local temporary homes, not paid API requests. Run new
tests failing first, implementation, executor regression and full `pytest tests`.
Sync both READMEs, checklist, roadmap, architecture and inventory after delivery;
mark only 15.4a complete, leaving text/voice integration pending.
