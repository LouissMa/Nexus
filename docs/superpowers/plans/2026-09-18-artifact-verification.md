# Artifact Verification Implementation Plan

**Goal:** Independently check predeclared file acceptance without changing execution permissions.
**Architecture:** One deterministic verifier uses the existing registry read tool;
PersistentExecutor owns fixed acceptance and durable reports. CLI and task speech
project those results without declaring whole-goal success.
**Tech Stack:** Python, existing JSON/SQLite/tool registry; no new dependencies.
**Spec:** ../specs/2026-09-18-artifact-verification-design.md

## Constraints

1-20 checks, absolute paths, 16 KiB manifest, 16,000-byte reads, five-second
cooperative check budget, ten prior reports. Never read personal configuration in
tests, add write permissions, run arbitrary verification code or replay task tools.

## Tasks

- [x] Verifier: add tests/test_execution_verification.py first, then
  src/nexus/execution_verification.py exposing validate_acceptance(value) (deep
  JSON copy) and FileVerifier(registry).verify(acceptance) (bounded report).
  Test a real temporary report with `contains`, then change its contents and
  require failed; deny read and require unverifiable. Cover all manifest bounds.
- [x] Persistence: extend PersistentExecutor.start(..., acceptance=None), freeze
  the contract before context/model work; include it in the runtime prompt.
  Add verify(run_id) under the run lease and auto-verify on reported_complete.
  Test old tasks unchanged, restart verification with runtime=None, changed
  artifacts, no auto-resume and reports excluding source content.
- [x] Interfaces: CLI --acceptance inline JSON and executor verify RUN_ID; text
  and speech display only verdict/counts/time. Test CLI verification without
  LLM/embedding, malformed contracts before model initialization, and partial
  checks not producing a success exit status.
- [x] Review and documentation: run focused then full pytest tests with isolated
  --basetemp; update EN/ZH README, roadmap, checklist, architecture, inventory and
  capability baseline. Delivery follows verification: stage explicit files,
  commit and push main as requested, excluding personal state and test scratch.

Regression command: `python -m pytest tests/test_execution_verification.py
tests/test_execution_store.py tests/test_task_conversation.py -q -p no:cacheprovider`.
Full command: `python -m pytest tests -q -p no:cacheprovider`.

## Verification (2026-09-18)

- Final full suite: 642 passed, 5 skipped in 161.49 seconds.
- File verification suite: 40 passed, 1 skipped; Windows symlink creation unavailable.
- Independent review: acceptance-only first-question speech leak reproduced and
  fixed with a runtime regression. Follow-up found no remaining issues in that fix.
- Nested exponent overflow is rejected; CLI help and git diff --check validated.
- Scripted models and isolated temporary files only; no paid model/hardware claims.
