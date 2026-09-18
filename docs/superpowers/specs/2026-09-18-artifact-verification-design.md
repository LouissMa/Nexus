# Artifact Verification: Phase 15.5a

Approved scope: deterministic read-only file acceptance checks, agreed in chat.
This is not whole-goal semantic verification, a write tool or a desktop observer.

## Contract

User supplies `executor run --acceptance JSON` before execution. The object has
only `checks`: 1-20 check objects. Each has an absolute `path` (1-2000 characters)
and `kind`: exists, nonempty, contains (requires bounded value), or json_fields
(requires 1-30 top-level field names mapped to JSON types). Total JSON <=16 KiB.
Only defined keys are allowed. Conditions are copied into the durable run before
model calls, included as untrusted acceptance data in its prompt, and cannot be
changed by model finish actions or resume flags. There is no post-hoc attachment
of weaker conditions to an old run.

## Read and Evidence Boundary

Use the existing permissioned filesystem.read registry path, never unrestricted
filesystem reads. Each check reads at most 16,000 bytes. Read denial, unavailable
tools, unreadable/missing files and truncated input are explicitly unverifiable;
successful reads prove regular-file availability, not creation by this task.
Empty/text/JSON checks fail only when a complete read contradicts the condition.
JSON field checks cover top-level types, not arbitrary JSON Schema or semantics.
No raw file contents or excerpts are persisted in verification reports or spoken.
Paths and user criteria remain plaintext in the local task database.
A cooperative five-second verification budget limits new calls, not a hard
interrupt of an in-flight filesystem adapter. No automatic retry or side effects.
Existing filesystem adapter permission and OS-race limitations still apply.

## Lifecycle

After reported_complete, automatically check predeclared conditions while holding
the existing run lease. Keep lifecycle status reported_complete; separate
verification_report.status is passed, partial, failed or unverifiable. A mix
including passes is partial; with no passes a definite contradiction is failed,
otherwise unverifiable. No acceptance preserves legacy tool_references_only.
Persist a pending-verification marker before reads. Crashes never replay tools;
`executor verify RUN_ID` explicitly repeats only checks without loading an LLM.
It accepts only reported_complete runs with existing acceptance. Retain the latest
report and up to ten prior reports; reports are time-specific observations and
can become stale. Current read permissions apply again on every verification.

Text/voice progress shows verdict/counts/time, not file contents or criteria.
Acceptance-bearing model questions are text-only, including the first clarification.
CLI run/resume succeeds only if model reports completion and declared checks all
pass (legacy runs retain their prior exit behavior). Verification CLI returns
nonzero for incomplete verification. Unknown effects and cancelled tasks cannot
be turned into successful tasks by this read-only verifier.

## Acceptance

Test manifest validation, immutable copies, actual authorized files, empty/wrong
text/invalid JSON, type checks, missing files, denied paths/read permission,
truncation, budget, stale/rechecked artifacts, restart, no model on verify, legacy
behavior, approval/cancellation/context compatibility and safe speech. Use isolated
temporary files and scripted models, no paid APIs or personal stores.
Phase 15.5 broader unseen-task evaluations/cost reporting remain future work.
