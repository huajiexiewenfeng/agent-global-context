# AGC Task-Aware Census Catalog Design

**Date:** 2026-08-23  
**Status:** Approved for implementation  
**Scope:** Capture Census read performance and quality-first historical backfill selection

## Context

The production Capture root contains 110 immutable Census runs with 74,175 member files but only 852 unique revisions across 70 Codex tasks. `CaptureStore.read_snapshot()` currently parses every member in every run and then parses the runs again for their manifests. This repeated I/O makes small, bounded backfills take minutes before or after model work.

Historical backfill also orders ready receipts by discovery time and receipt id. A batch can therefore spend most of its item limit on several low-value turns from one task while other tasks are not inspected. The existing Capsule and persistence gates correctly reject much noise, but they operate too late to make selection efficient.

The product priority is useful, correct candidate memory with low noise. This change must improve selection without weakening evidence, safety, review, authorization, or formal-memory boundaries.

## Goals

- Reduce normal Census snapshot reads from run-count-times-revision-count work to run-count-plus-unique-revision-count work.
- Preserve all existing frozen Census files as cold audit evidence.
- Maintain one canonical, content-free `RevisionRef` per unique `CaptureKey` for the hot read path.
- Select backfill work across tasks and prefer locally measurable durable signal.
- Limit one runner invocation to at most three selected revisions from the same task.
- Keep unselected revisions pending and recoverable rather than silently excluding or coalescing them.
- Preserve the exact external authorization, token-budget, review, and no-auto-promotion behavior.

## Non-Goals

- Deleting, rewriting, or compacting existing production frozen Census runs.
- Aggregating an entire Codex session into one model prompt.
- Loosening the pre-Capsule or persistence gates.
- Automatically promoting observations to formal memory.
- Sending any additional historical content during migration, indexing, ranking, or acceptance tests.
- Solving every future Census archival or adversarial-tamper problem in this release.

## Design

### 1. Canonical Census Catalog

Capture adds a derived `census-catalog` namespace below the managed Capture runtime root. It contains:

- an atomic `active.json` pointer to one immutable content-addressed generation under the deliberately short Windows-safe `g/<digest>` path;
- one canonical `RevisionRef` JSON object per unique `CaptureKey` inside that generation's `r/` directory;
- one generation manifest containing its format version, ordered frozen-run identities, unique revision count, and a deterministic digest over canonical revision metadata; and
- no transcript text, Capsule text, observation statement, path outside the already permitted opaque locator contract, or model content.

The catalog is derived data. Frozen Census runs remain the historical source of truth and are never modified by catalog construction.

### 2. Catalog Build and Validation

When no valid catalog exists, the store performs one full legacy read under the Capture write lock:

1. Decode and validate every frozen run and member using the existing rules.
2. Reject conflicting metadata for the same `CaptureKey` exactly as today.
3. Deduplicate valid revisions by key.
4. Write the complete catalog into a new immutable generation with the existing atomic directory installer.
5. Atomically publish `active.json` only after the generation is durable, then remove older inactive generations under the same lock.

Normal reads validate the catalog manifest against the ordered `run.json` manifests and their revision-key membership. If the run set or any run membership changes, or if the catalog is malformed, the catalog is stale. The store must rebuild it from frozen evidence before using it. A failed rebuild does not publish partial state and reports the existing fixed `invalid_frozen_census` diagnostic.

This validation reads run manifests plus unique catalog records, not every repeated member. It intentionally does not re-open all cold members on every status read. Existing backup verification, explicit catalog rebuild, and maintenance validation remain full-audit paths that revalidate cold members.

### 3. Incremental Maintenance

`freeze_census()` continues writing the existing immutable run format for compatibility. After a new run is durably frozen, it refreshes the catalog under the same Capture lock. Existing canonical revisions are reused; only new unique revisions add catalog records.

Crash safety rules:

- a frozen run may exist without an updated catalog;
- `active.json` may never point at a generation that is not durably present;
- readers detect the mismatch and rebuild;
- staging and inactive generation directories are ignored by hot reads and recoverable;
- no catalog state changes Receipt, Ledger, Observation, Review, or formal Memory truth.

### 4. Snapshot Read Path

`read_snapshot()`, `frozen_revisions()`, and runner preparation use the valid catalog for unique revision truth. `census_runs` is decoded directly from each `run.json`; the store no longer reads every run's members a second time merely to obtain run metadata.

Legacy roots without a catalog remain supported through automatic one-time construction. Backup and restore continue accepting older full frozen-run archives.

### 5. Task-Aware Local Ranking

The runner groups ready receipts by:

```text
(adapter_id, source_root_id, task_id)
```

For each candidate, the Source Adapter builds the existing privacy-cleaned Capsule locally. Ranking never calls the Extractor and never consumes provider tokens.

The deterministic ranking tuple, highest first, is:

1. contains a decision/result or reusable method;
2. number of decision/result and reusable-method units;
3. number of populated durable-signal categories;
4. number of user-signal units;
5. bounded total selected signal codepoints;
6. later `completed_at`;
7. stable receipt id tie-breaker.

An empty Capsule ranks below every non-empty Capsule. Existing pre-Capsule filtering remains authoritative, so acknowledgements, questions, logs, code-like payloads, unsafe content, and unsupported structures do not gain rank merely through length.

### 6. Fair Batch Selection

Selection is round-robin across ordered task groups. Within each group, candidates use the local ranking above. One invocation selects no more than three revisions from a task and never more than the caller's `max_items`.

Locally built `CapsuleResult` values for selected candidates are reused by the extraction loop so source files are not loaded twice. Unselected receipts keep their prior status. The runner does not mark them `excluded`, `coalesced`, or `complete`.

The limit is per invocation, not a permanent lifetime cap. This preserves coverage and lets later authorized batches consider remaining turns without introducing a new terminal receipt state.

If local Capsule loading fails during ranking, the candidate remains eligible for the existing source-error transition in the execution loop; ranking must not hide or silently consume it.

### 7. Authorization and Privacy Boundary

Local ranking may inspect more candidate turns than are ultimately selected, but no candidate content leaves the machine during ranking. The existing authorization digest, `max_items`, configured model/provider boundary, and token ceiling apply unchanged to Extractor calls.

The number of revisions sent externally cannot exceed `max_items`, and an empty Capsule still completes locally as `no_durable_signal` with zero model calls. No live production backfill is part of this implementation unless the user provides a fresh exact authorization.

## Compatibility

- No Capture schema version change is required for Receipts, Observations, Reviews, or frozen runs.
- Existing roots gain only derived catalog artifacts.
- Hard Forget continues targeting canonical `CaptureKey` identities and managed primary/backup data. The derived catalog is deleted within the same forget transaction and rebuilt from the rewritten frozen truth on the next read. This avoids retaining target identifiers or locators and keeps rollback exact.
- Existing `coalesced` semantics remain reserved for duplicate source representations and are not reused for low-ranked turns.
- Backup excludes the derived catalog and continues using its existing compact unique-revision projection. Restore rebuilds the catalog locally.

## Failure Handling

- Catalog conflict or corrupt cold evidence: fail closed with `invalid_frozen_census`; do not publish a catalog.
- Stale catalog: rebuild atomically.
- Interrupted catalog staging: ignore it on reads and clean it through existing transaction recovery conventions.
- Rank-time source unavailability: preserve the candidate as pending; never mark it complete, excluded, or coalesced. When selected by a later invocation, the existing runner source-error transition remains authoritative.
- Extractor or budget failure: unchanged Receipt state machine and settlement behavior.

## Testing

All test temporary state must be rooted under `D:\tmp_test`.

Required automated coverage:

1. Repeated frozen runs with the same revisions produce one canonical record per key.
2. A valid catalog lets snapshot reads avoid member-file decoding on the hot path.
3. Adding a frozen run invalidates or refreshes the catalog without losing earlier revisions.
4. Conflicting legacy member metadata prevents catalog publication.
5. Interrupted staging is ignored and a subsequent build converges.
6. Existing backup/restore and Hard Forget tests remain green.
7. Ranking prefers decisions and reusable methods over acknowledgements or weak user signals.
8. A batch selects at most three revisions per task and distributes capacity across tasks.
9. Selection is deterministic under shuffled input.
10. Unselected receipts remain pending.
11. Empty Capsules still avoid Extractor calls and token charges.
12. Existing authorization and `max_items` tests remain green.

## Acceptance

- Focused TDD tests pass.
- The full Capture regression suite passes.
- The package builds and installs into a new immutable runtime environment.
- On a copied or read-only production-scale Capture dataset, the first catalog build validates all historical evidence and a subsequent hot snapshot reads only run manifests plus unique catalog records.
- Hot snapshot wall time is seconds rather than minutes on the current production dataset.
- Acceptance performs zero Extractor/model calls and zero external content transfer.
- Production formal-memory count and hashes are unchanged.
- Runtime status reports the new installed version and the intended Codex App model boundary.

## Rollout

1. Implement on `codex/task-aware-census-catalog` using test-first changes.
2. Verify against synthetic repeated-run fixtures and the Capture regression suite.
3. Build a new patch release and install it into a content-addressed immutable venv.
4. Restart or reload the Codex App MCP runtime only when required for the installed route.
5. Run read-only production-scale catalog and snapshot acceptance without a backfill authorization.
6. Compare formal-memory hashes and Capture egress counters before and after installation.
