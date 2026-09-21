# Phase 15.5b Execution Evaluation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Measure the existing executor's behavior and resource use without mistaking scripted checks for real-model competence.
**Architecture:** Extend the existing LLM adapter with per-response usage and the existing run snapshot with a bounded metrics ledger. A serial evaluator prepares isolated synthetic cases and reuses PersistentExecutor; JSON reports keep lifecycle, file checks, behavior checks and human review separate.
**Tech Stack:** Python >=3.11, existing SQLite/JSON/jsonschema and optional LangGraph executor dependency. No new runtime dependencies, shell executor or external evaluation service.
**Spec:** [Approved design](../specs/2026-09-20-execution-evaluation-design.md).
**Status:** Written-spec approval received through the user's instruction to start. This implementation plan awaits review and execution-method selection; no product implementation has started.

## Global Constraints

- offline 为默认值，禁止初始化 LLM 厂商客户端，不读取个人 API 配置，不发起网络请求。
- live 必须显式指定且提供 max-calls（1-100）；CLI 预先告知将向所选厂商发送合成案例资料。
- 每次套件最多 24 个案例，默认每案例 8 步、30 秒工作预算，套件默认 300 秒协作式预算。
- 每案例最多 16 次 registry dispatch，包含拒绝请求；验证读取另受 15.5a 预算约束。
- 人工评价只接受已存在的案例 ID，verdict 为 passed/partial/failed，note 限 1–4,000 字符。
- 报告每案例最多 4,000 字符摘要、50 条证据引用；整体输出上限 1 MiB，溢出显式报错。
- Keep task statuses, evidence numbering, exact approval tokens and unknown-effect/no-replay behavior unchanged.
- Model/file/reference content is untrusted. No private stores, arbitrary shell commands, network tools, live evaluations or paid API calls during development.
- The 1 MiB limit applies to each exported report representation, not the private execution database. Never automatically publish local evaluation output.

## Review Focus

1. A provider omits usage on the second call: never reuse usage from the first call (Task 1 test).
2. Crash between checkpoint and response: count an unknown attempt once, never count it as free or replay its side effect (Task 2 test).
3. A report path is replaced with a junction/symlink: reject reads/writes outside the evaluation directory and never overwrite another evaluation (Task 4 test).
4. All selected cases are skipped or not applicable: denominator zero produces null, not 0% or 100% (Task 4 test).
5. An offline CLI call inherits personal settings or environment keys: provider construction and external tools remain impossible (Task 5 test).

## Existing Code and Ownership

- `src/nexus/llm.py`: `OpenAICompatibleLLM.generate` currently returns text and discards usage. Preserve its public signature/return type.
- `src/nexus/execution_runtime.py`: instrument before/after model and registry calls, not by appending metric observations.
- `src/nexus/execution_store.py`: initialize new-run metrics, reconcile pending attempts under the existing lease, preserve legacy runs.
- `src/nexus/execution_verification.py`: remains the authority for file checks; do not broaden permissions or change its verdict semantics.
- New `execution_metrics.py`: pure validation, ledger projection and price estimation.
- New `evaluation_cases.py`: the only runtime case source, including synthetic fault behavior and development/holdout membership.
- New `execution_evaluation.py`: isolated serial orchestration and report persistence, not a second execution engine.
- New `tests/test_llm_usage.py`, `test_execution_metrics.py`, `test_execution_evaluation.py`, `test_execution_evaluation_cli.py`; extend existing store/runtime regressions.

## Task 1: Per-Response Usage and Explicit Pricing

**Files:** modify `src/nexus/llm.py`; create `src/nexus/execution_metrics.py`, `tests/test_llm_usage.py`, `tests/test_execution_metrics.py`.

**Interfaces:**
- `GenerationResult(text: str, usage: dict)` is an immutable dataclass in llm.py.
- `OpenAICompatibleLLM.generate_result(system_prompt, user_prompt, *, timeout_seconds=None) -> GenerationResult`.
- Class attribute `supports_generation_result = True`; runtime checks `is True`, not truthiness, to avoid accidental dynamic Mock capabilities.
- Existing `generate` delegates once and returns `.text`. Text-only custom models remain supported.
- `normalize_usage(raw) -> dict`: status available/unavailable/invalid plus allowlisted input/output/total counts and billing classification.
- `estimate_cost(usage, pricing, *, model) -> dict`: status estimated/unavailable, amount as a decimal string or null, currency and reason. No automatic price lookup.

- [ ] Write red tests for missing/invalid usage and stale-call isolation. Stub urllib responses, not real HTTP:

```python
def test_missing_usage_is_not_zero():
    from nexus.execution_metrics import normalize_usage
    result = normalize_usage(None)
    assert result["status"] == "unavailable"
    assert result["total_tokens"] is None

def test_boolean_token_count_is_invalid():
    from nexus.execution_metrics import normalize_usage
    assert normalize_usage({"prompt_tokens": True, "completion_tokens": 2})["status"] == "invalid"
```

- [ ] Run `python -m pytest tests/test_llm_usage.py tests/test_execution_metrics.py -q -p no:cacheprovider`; confirm new imports fail before implementation.
- [ ] Normalize canonical `prompt_tokens`, `completion_tokens`, optional `total_tokens`; require actual nonnegative ints <= 2**63-1, reject inconsistent totals and recognized invalid detail fields. Missing total stays null; do not invent a provider value. Track presence/completeness separately from any derived sum. Unknown provider billing extensions make pricing unavailable rather than silently ignored.
- [ ] Refactor one shared request path; never issue an extra HTTP request to collect usage. Preserve the old text/error behavior for ordinary callers. Verify two fake replies, first with usage and second without, produce independent GenerationResult objects.
- [ ] Validate pricing object with only model, currency, effective_date, input_per_million, output_per_million. Currency is three uppercase ASCII letters; effective_date is an ISO date; prices are nonnegative finite decimal strings. Reject bool/numeric coercion, extra keys and model mismatch. Mark cached/reasoning categories unsupported for cost unless absent or explicitly zero and fully understood.

```python
from decimal import Decimal
amount = (Decimal(input_tokens) * Decimal(pricing["input_per_million"])
          + Decimal(output_tokens) * Decimal(pricing["output_per_million"])) / Decimal(1000000)
```

- [ ] Add table-driven tests for negative/huge/string counts, partial usage, total mismatch, unknown billing fields, cache/reasoning usage, price mismatch and missing price. Missing coverage always leaves total cost null; no guessed zero.
- [ ] Rerun the new tests plus existing LLM/config consumers identified with `rg -n 'OpenAICompatibleLLM|LLMConfig' tests`. Commit these explicit files with message `feat: expose per-response model usage`.

## Task 2: Durable Metrics Without Changing Execution Semantics

**Files:** modify execution_metrics.py, execution_runtime.py, execution_store.py; extend test_execution_metrics.py and tests/test_execution_store.py.

**Interfaces:**
- `new_metrics() -> dict`: schema_version=1, coverage=complete, attempts=[], approval_stops=0, clarification_stops=0.
- `begin_attempt(metrics, kind) -> str`: kind model/tool; append a monotonically numbered pending entry; bounded at 200 entries, fail before dispatch on overflow.
- `finish_attempt(metrics, attempt_id, status, *, usage=None) -> None`: update once; identical repeat is idempotent, conflicting repeat rejected.
- `recover_pending(metrics) -> None`: pending becomes unknown, never changes counters through repeated recovery.
- `project_metrics(state) -> dict`: derive counts from ledger and elapsed time from existing fields; absent metrics returns coverage=legacy_unavailable.
- Optional ExecutionRuntime constructor hooks `before_model=None` and `max_dispatches=None`. The first returns bool to reserve evaluator quota before creating a model attempt; false stops as budget_exhausted. The latter limits new registry dispatches. Ordinary runs retain existing defaults.

- [ ] Write red tests for ledger identity, recovery and legacy coverage:

```python
def test_recovery_counts_unknown_once():
    from nexus.execution_metrics import new_metrics, begin_attempt, recover_pending, project_metrics
    metrics = new_metrics()
    begin_attempt(metrics, "model")
    recover_pending(metrics)
    recover_pending(metrics)
    view = project_metrics({"metrics": metrics, "elapsed_seconds": 0})
    assert view["model_attempts"] == 1
    assert view["model_unknown"] == 1
    assert view["usage"]["coverage"] == "unavailable"
```

- [ ] Run focused metric tests and observe failures before implementing helpers.
- [ ] Initialize metrics before store.create for new tasks; direct new in-memory runtime runs also initialize. Resuming a legacy snapshot creates a ledger labeled partial_since_resume, never complete; old terminal snapshots stay legacy_unavailable.
- [ ] Before a model/tool call: reserve quota when applicable, append pending attempt, checkpoint, dispatch. After return: finish/checkpoint the attempt before interpreting model JSON or transitioning state. A received malformed model action still counts as a response. Errors omit raw exception/provider bodies. Exceptions before dispatch do not become successful attempts.

```python
attempt_id = begin_attempt(current["metrics"], "tool")
save(current)
result = self.registry.call(action["tool"], action["arguments"], approved=approval[0] == binding)
finish_attempt(current["metrics"], attempt_id, result["status"])
save(current)
```

- [ ] Preserve the existing tool_running checkpoint/no-replay boundary. Resolve pending ledgers under the lease before existing crash recovery; never infer that an unknown request consumed zero tokens. In a response/checkpoint crash window, report unknown even if a remote call may have succeeded.
- [ ] Increment approval/clarification stops only on new transitions during runtime, not checkpoint repeats, status queries or token/config refresh. Project verification_seconds from separate verifier reports; retain historical recheck durations without double counting execution elapsed time.
- [ ] Test pre-dispatch checkpoint failure (handler untouched), actual child-process crash after dispatch, repeated recovery, approval resume, malformed response, model error, unknown tool, quota denial before model call, dispatch limit and legacy partial coverage. Existing observation numbers and cumulative step/time budgets must remain unchanged.
- [ ] Run metric/store/runtime/context/verification/conversation suites. Commit exact changed files as `feat: persist execution resource metrics`.

## Task 3: Versioned Synthetic Cases and Explicit Oracles

**Files:** create `src/nexus/evaluation_cases.py`, `tests/test_execution_evaluation.py`, `tests/fixtures/execution_evaluation/expected_counts.json`.

**Interfaces:**
- `case_catalog() -> list[dict]`: isolated descriptors, with id/family/split/kind/version/content_digest, no mutable globals returned.
- `select_cases(mode, case_ids=None) -> list[dict]`: reject unknown/duplicate IDs and >24 cases. offline defaults to all 17; live defaults to three development normal cases, refuses offline-only fault cases.
- `execute_case(case, root, *, model_factory=None, before_model=None, clock=monotonic) -> dict`: use existing executor with synthetic registry; factory=None selects packaged scripted model only for offline cases. Return local state/evidence and expected_behavior, not a public report yet.
- `check_expected(case, state, evidence) -> dict`: status passed/failed/not_evaluable plus bounded machine reasons; no semantic success claim.

- [ ] Write red catalog tests:

```python
def test_catalog_keeps_faults_separate():
    from nexus.evaluation_cases import case_catalog, select_cases
    cases = case_catalog()
    assert len([c for c in cases if c["kind"] == "normal"]) == 9
    assert len([c for c in cases if c["kind"] == "fault"]) == 8
    assert len(select_cases("live")) == 3
    assert all(c["split"] == "development" for c in select_cases("live"))
```

- [ ] Implement nine normal cases: project-1..3, organize-1..3, research-1..3; variant 1/2 development and variant 3 holdout. Include different names/goals/content and distractors, not just renamed IDs. Version and hash canonical definitions without absolute temp paths.
- [ ] Materialize relative paths using exclusive file creation in a new root; reject absolute paths, '..', symlinks/junctions and existing targets. Build ToolManager directly with only filesystem read/list/search and no automations; do not call the default personal registry builder.
- [ ] Each scripted model uses observed tool results to select a next action and never supplies an approval token. Fault IDs: unavailable, read-error, approval-denied, cancelled, restart, repeated-effect, unknown-effect, false-finish. Side effects modify only a test-local counter. Restart reopens ExecutionStore; denial requests cancel after waiting_approval rather than authorizing anything.
- [ ] Define oracles against exact state/observation/counter evidence: no tools -> no_tools; read errors cannot supply success evidence; denied action count=0; cancellation is sticky; restart preserves completed actions; repeated effects stop; unknown effects require review; unsupported finish -> invalid_completion. Normal oracles check required actual reads and evidence references only; human_assessment remains not_reviewed.
- [ ] Add full offline case tests, mutation-isolated catalog tests, duplicate/unknown ID rejection, holdout labeling, source-reference failures and a missing-material case that remains human-unreviewed even if a scripted check passes. The fixture stores expected aggregate counts only, not duplicated case inputs.
- [ ] Verify importing/running the case module does not import tests or construct a provider. Commit as `test: add versioned executor evaluation cases`.

## Task 4: Isolated Runner, Durable Quota and Reports

**Files:** create `src/nexus/execution_evaluation.py`; extend tests/test_execution_evaluation.py.

**Interfaces:**
- `EvaluationRunner(home, *, model_factory=None, model_identity=None, clock=monotonic)` accepts an explicit home, injected model factory and allowlisted provider/model/tier identifier, never loads config itself. model_identity never includes Key, URL, headers or config objects.
- `.run(*, mode="offline", case_ids=None, max_calls=None, pricing=None) -> dict`: validate all options before any provider construction or evaluation-directory creation.
- `EvaluationStore(home).read(evaluation_id) -> dict` and `.review(evaluation_id, *, case_id, verdict, note) -> dict`.
- `summarize_cases(cases) -> dict`: separate normal/fault denominators, not_evaluable/skipped counts and independent file/human tallies.
- `render_report(report) -> str`: safe Markdown projection from the authoritative bounded JSON report.

- [ ] Write red zero-denominator and input-isolation tests:

```python
def test_empty_denominator_is_unknown():
    from nexus.execution_evaluation import summarize_cases
    result = summarize_cases([])
    assert result["normal_behavior"]["eligible"] == 0
    assert result["normal_behavior"]["rate"] is None

def test_offline_never_constructs_provider(tmp_path):
    from unittest.mock import Mock
    from nexus.execution_evaluation import EvaluationRunner
    provider = Mock(side_effect=AssertionError("provider constructed"))
    report = EvaluationRunner(tmp_path, model_factory=provider).run()
    assert report["mode"] == "offline"
    provider.assert_not_called()
```

- [ ] Use UUID evaluation directories under home/evaluations; reject links/junctions on known directory components and validate IDs as 32 lowercase hex digits. Create directories exclusively. Reuse the existing OS locking pattern for evaluation metadata; implement it locally without changing run-lease behavior.
- [ ] Store report.json atomically (same-directory temporary file, flush, replace), under the evaluation lock. Save initial selected-case rows as not_started before execution; maintain mode/version/quotas/timestamps. Never overwrite an existing evaluation on creation. Before_model atomically consumes one call slot before provider invocation; a lost/unknown attempt is not refunded. There is no live suite-resume command in this version.
- [ ] Execute cases serially with steps=8, active timeout=30, max_dispatches=16. Before each case/model attempt check suite deadline (300 seconds) and available quota. Keep remaining selected rows skipped with budget reason. Record waiting_approval/waiting_input as needs_intervention without automatically continuing them.
- [ ] Store per-case execution databases privately inside their synthetic case directories. Reports project only IDs, allowed model identifiers, relative synthetic sources, bounded summary, verdicts and metrics. Do not export raw database records, approval tokens, tool bodies, environment or full prompts. Human comments remain local plaintext, explicitly identified as user-authored.
- [ ] Reports display model completion, normal behavior, fault behavior, applicable file conditions and human review separately. Pricing from Task 1 is optional; incomplete coverage yields null total. A finite known subtotal, if shown, must be labeled partial with its covered call count.
- [ ] Escape Markdown metacharacters and HTML in summaries/comments; omit absolute paths and unsafe links from automatic references. Enforce 4,000 summary chars, 50 references, 1 MiB encoded JSON and Markdown limits before atomic replacement. On failure preserve the previous JSON and case databases; interrupted evaluation never looks complete. Each report reader performs the same bounds and version checks.
- [ ] Add tests for symlink/junction target swap, path traversal IDs, exclusive creation, zero eligible cases, malicious '<script>' summaries, secret sentinels, oversized persisted input, atomic-write failure, two concurrent reviews, no budget refund, fake-clock deadline, interrupt after one case and no network/provider fallback. Unsupported filesystem link tests may skip with an explicit OS reason.
- [ ] Review verdict append uses exact known case IDs, three allowed verdicts and 1-4,000 nonblank note; save timestamped history, keep machine values unchanged, derive latest human summary separately. Reject updates that exceed report bounds without destroying earlier reviews.
- [ ] Run the evaluator and lower-layer suites, then commit as `feat: add isolated task reliability reports`.

## Task 5: CLI and User-Facing Documentation

**Files:** modify src/nexus/cli.py; create tests/test_execution_evaluation_cli.py; update README.md, README_zh.md, docs/architecture.md, docs/file_inventory.md, docs/current_capabilities_and_next_phase.md, docs/roadmap.md, docs/aios_task_checklist.md.

**Interfaces:** add evaluate, evaluation-show and evaluation-review under the existing executor parser. Evaluate options: --mode offline/live (default offline), repeatable --case, --max-calls, --model-tier, --pricing (bounded inline JSON using Task 1 fields).

- [ ] Write red CLI test for inherited secrets without using a real key:

```python
def test_offline_cli_ignores_provider_settings(tmp_path, monkeypatch, capsys):
    import sys
    import json
    from unittest.mock import Mock
    from nexus import cli
    monkeypatch.setenv("NEXUS_HOME", str(tmp_path))
    monkeypatch.setenv("NEXUS_LLM_API_KEY", "FAKE_MUST_NOT_BE_READ")
    monkeypatch.setattr(cli.LLMConfig, "from_env", Mock(side_effect=AssertionError("config read")))
    monkeypatch.setattr(sys, "argv", ["nexus", "executor", "evaluate"])
    cli.main()
    result = json.loads(capsys.readouterr().out)
    assert result["mode"] == "offline"
    assert "FAKE_MUST_NOT_BE_READ" not in json.dumps(result)
```

- [ ] Dispatch evaluation commands before the ordinary registry, embedding or LLM setup. Reject --max-calls/--model-tier/--pricing in offline mode rather than silently accepting live-only flags. In live mode validate budget, cases and pricing before loading LLMConfig; emit the provider/synthetic-data notice to stderr so stdout remains JSON.
- [ ] Pass only an explicitly constructed live model factory and sanitized identifier to EvaluationRunner; never persist LLMConfig/base URL credentials. Show/review commands do not load models or embeddings. Repeated IDs, empty notes, invalid JSON, out-of-range budget and wrong modes are configuration failures.
- [ ] Exit semantics: 0 means evaluation/report operation completed, not that the agent solved every case; report verdicts remain explicit. 1 means interrupted/incomplete suite or infrastructure failure; 2 means invalid options/configuration. Existing executor run/resume/verify exit meanings remain unchanged.
- [ ] Test fake live provider with max-calls=1, wrong configuration before provider creation, no fallback, report privacy, show/review with broken LLM config, and old CLI commands. Test importing installed runtime modules without tests on sys.path; case definitions must ship in the Python package.
- [ ] Document offline/live distinction, defaults, interpretation of denominators, unknown prices, local report paths, holdout limits, no arbitrary write/browser capability and exact example commands. Mark 15.5b delivered only after Task 6; keep whole-goal semantic verification and real-provider acceptance outstanding.
- [ ] Commit as `feat: expose controlled executor evaluation commands`.

## Task 6: Integration Review and Delivery

**Files:** tests and documentation listed above; adjust only defects found in this stage, not unrelated refactors.

- [ ] Run the focused metric/usage/evaluation/store/runtime/verification/task-conversation tests with a fresh project-local --basetemp.
- [ ] Run `python -m pytest tests -q -p no:cacheprovider --basetemp=D:/AI_Projects/Nexus/.test-tmp-evaluation-final` with PYTHONPATH=D:/AI_Projects/Nexus/src. Use a new suffix if the directory exists; never recursively delete user scratch directories.
- [ ] Run one offline CLI smoke with NEXUS_HOME pointing at a new temporary directory, not the user's real store; inspect JSON and Markdown, then run show/review on that isolated evaluation. Network and provider constructors remain forbidden during this smoke.
- [ ] Request independent whole-change review, particularly privacy, crash windows, quota accounting and false-success reporting. Reproduce findings with failing tests, fix, and rerun affected/full suites before claiming completion.
- [ ] Update this checklist incrementally and record actual test counts, skips and whether any live provider test occurred. Live provider testing requires a separate explicit request; current authorization does not spend API quota.
- [ ] Verify `git diff --check`, staged file list and clean tracked diff; fetch origin/main, check divergence, and commit/push the reviewed changes to main as requested. Never force-push or stage evaluation output, personal credentials or test scratch.

## Plan Review and Execution Choice

Recommended: Native, because the six tasks share ledger/report interfaces and sequential integration is cheaper than separate implementation contexts. One fresh independent reviewer checks the final changes.
Alternative: Subagent-driven, with a fresh implementer and reviewer per task plus final review, at higher context cost.
Execution authorized by the user's subsequent direct coding request; implemented inline.

## Execution Ledger (2026-09-21)

The original granular items above are the design-time checklist, not a claim that
every suggested test/commit was executed verbatim. This ledger records actual delivery.

- [x] Tasks 1-2: Per-response LLM usage, conservative pricing, durable attempt metrics,
  pending-attempt recovery and cumulative verification duration implemented.
- [x] Task 3: All 17 packaged synthetic cases run through the existing executor.
- [x] Task 4: Isolated runner, pre-call quota, locked bounded JSON/Markdown reports,
  path checks and independent manual reviews implemented.
- [x] Task 5: Three CLI commands, early isolation dispatch and bilingual documentation.
- [x] Task 6 regression: final full suite 672 passed, 6 skipped in 154.93 seconds.
- [x] Isolated offline CLI smoke: nine normal/eight fault behavior checks passed;
  report JSON/Markdown and persisted human review verified with network/provider access blocked.
- [x] Release checks: `git diff --cached --check` passed; only 19 explicit code/test/doc
  files staged; fetched origin/main with zero divergence. No credentials or local reports staged.
- [ ] Independent final review: requested but unavailable due to reviewer usage limit.
- [ ] Real-provider task-quality acceptance: not authorized/run in this implementation.

Rulings: use one integrated implementation commit rather than six intermediate
commits. Expected aggregate counts live in tests rather than a redundant JSON
fixture. CLI tests are named `test_evaluation_cli.py`. Normal-case file checks only
test fixture availability; source-reading/evidence oracles and human quality are
separate. Public holdout labels are not a claim of previously unseen real tasks.

Independent review was requested, but the reviewer stopped at an account usage
limit before returning findings. This is not a completed independent review.
No paid/live provider calls were made. Existing subprocess recovery tests remain
part of full regression; OS-dependent link tests may skip explicitly.
