# Phase 9 Advanced Long-Term Memory Design

## Goal

Make Nexus memory useful and maintainable at personal scale without requiring an
LLM, silently deleting user data, or breaking existing memory records.

## Scope

Phase 9 completes five capabilities:

1. Deterministic memory importance scoring with optional user override and pinning.
2. Exact/near-duplicate detection plus explicit supersede and conflict relations.
3. Deterministic compression into inspectable summary memories and reversible archival.
4. Retention, expiry, privacy, archive, restore, forget, and confirmed purge controls.
5. Retrieval filtering and explainable re-ranking using relevance, importance, recency,
   and task-context signals.

LLM-generated summaries, cross-user memory sharing, and background lifecycle jobs are
outside this phase. The future scheduler may invoke the same lifecycle APIs.

## Data Model

Existing records remain valid. Missing fields are normalized at read time.

- `importance`: float from `0.0` to `1.0`.
- `importance_source`: `automatic` or `user`.
- `pinned`: boolean; pinned memories never expire automatically.
- `privacy`: `private`, `personal`, or `shared`.
- `status`: `active`, `archived`, or `forgotten`.
- `expires_at`: optional UTC timestamp.
- `updated_at`: UTC timestamp.
- `duplicate_of`: optional memory ID.
- `supersedes`: optional memory ID.
- `conflicts_with`: list of memory IDs.
- `summary_of`: list of source memory IDs on compressed summary records.
- `archived_at`, `forgotten_at`: optional lifecycle timestamps.

`private` is the default and is eligible for local Nexus workflows. Retrieval callers
may request `private`, `personal`, or `shared`; a caller never receives a more private
scope than requested. Forgotten and expired records are excluded. Archived records are
excluded unless explicitly requested.

## Importance

Automatic scoring is deterministic and explainable. It combines content length,
high-signal tags, commitment/deadline language, and relationship/identity language.
The score is bounded to `0.1..0.9`. A user-provided score is bounded to `0.0..1.0`,
marked as `user`, and remains stable during maintenance. Pinning raises effective
retrieval importance to `1.0` but does not overwrite the stored user score.

## Duplicate And Conflict Handling

Normalized exact matches and high-overlap near matches are detected during add. Exact
duplicates are not stored again; the existing record receives `duplicate_count` and
`last_seen_at`. Near duplicates are stored with `duplicate_of` so the user can inspect
the relationship.

Nexus does not guess semantic contradictions. Users can explicitly mark a new memory
as superseding an older memory or link two existing memories as conflicting. Superseded
records are archived, preserving history and preventing stale facts from retrieval.

## Compression And Retention

Compression selects old, active, unpinned, low-importance memories. It never mixes privacy scopes, carries the earliest source expiry, and keeps source-ID lineage. It groups them by
month and primary tag, writes an inspectable deterministic summary memory, and archives
the sources. The operation supports dry-run and is idempotent for already summarized
source sets.

Retention maintenance archives expired memories and reports every affected ID.
Forgetting is reversible, removes records from retrieval, and cascades to derived summaries so copied excerpts cannot survive a source forget. Derived summaries cannot be restored while a source is forgotten or missing; source privacy/expiry changes propagate. Purge permanently removes only forgotten source records, recursively removes their derived summaries, and requires `--confirm`.

## Retrieval

Sparse and dense candidates are restricted to eligible source IDs. The final score is:

- relevance: 70%
- effective importance: 15%
- recency: 10%
- task-context tag overlap: 5%

Each result exposes component scores and `rerank_score`. Retrieval metadata reports
eligible/candidate counts, privacy/status filters, and the re-ranking strategy.

## CLI

- `nexus memory add TEXT --tags ... --importance N --privacy SCOPE --expires-at ISO --pin`
- `nexus memory show ID`
- `nexus memory update ID [--importance N] [--privacy SCOPE] [--expires-at ISO|none] [--pin|--unpin]`
- `nexus memory relate ID --supersedes ID`
- `nexus memory relate ID --conflicts-with ID`
- `nexus memory archive|restore|forget ID`
- `nexus memory purge ID --confirm`
- `nexus memory compress --older-than-days N --max-importance N [--dry-run]`
- `nexus memory maintain [--now ISO] [--dry-run]`
- `nexus memory retrieve QUERY --privacy SCOPE [--include-archived]`

All commands return structured JSON. Invalid IDs, timestamps, scores, relations, and
unsafe purge attempts fail with a clear non-zero exit.

## Compatibility And Safety

- Old state files load without migration commands.
- Embeddings stay private in CLI output.
- Memory adds and lifecycle mutations refresh the semantic index when enabled and expose a partial outcome when refresh fails; authoritative JSON filtering still rejects stale vectors. Local sparse retrieval
  remains available if the vector backend fails.
- No memory content is sent to an LLM by lifecycle operations.
- No automatic or default command permanently deletes memory.

## Verification

Unit tests cover scoring, normalization, duplicate detection, relations, lifecycle
transitions, compression, expiry, privacy filters, and re-ranking. CLI tests cover the
public commands and error paths. The full existing suite must remain green.
