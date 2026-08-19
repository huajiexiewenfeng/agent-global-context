# Capture Source Census Task 4 Report

## Scope

Implemented the library-only Source Census control plane. The change adds
frozen seven-day Census persistence, durable pre-semantic Receipt/Ledger
accounting, optimistic root-bound scan state, explicit-adapter reconciliation,
source quarantine, dirty-marker acknowledgement after accounting, and
crash/replay convergence. It does not add or activate a CLI, scheduler, live
profile, extractor, model/provider, Capsule, Observation, MCP, or formal-memory
writer.

This review-fix hardens the original implementation with atomic immutable
run-plus-membership publication, durable frozen-truth reconciliation, strict
dirty-marker handling, persistent source health, and fail-closed diagnostic
hint handling. Scanner truth is now the union of all durable frozen Revision
records and current discovery.

Production files:

- `agc_runtime/capture_forget_service.py`
- `agc_runtime/capture_forget_transaction.py`
- `agc_runtime/capture_ledger.py`
- `agc_runtime/capture_scanner.py`
- `agc_runtime/capture_store.py`
- `agc_runtime/managed_backup.py`

Tests:

- `tests/test_capture_ledger.py`
- `tests/test_capture_scanner.py`
- `tests/test_capture_backup_restore.py`

`agc_runtime/capture_transaction.py` now also provides atomic immutable JSON
directory installation so a Census run and all of its membership become
visible in one rename.

## TDD Evidence

The first valid RED run used the bundled Python only because the repository
venv launcher was sandbox-blocked before escalation:

```powershell
& 'C:\Users\admin\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' `
  -m pytest tests/test_capture_ledger.py -q -p no:cacheprovider `
  --basetemp 'C:\tmp\agc-capture-source-red-4-ledger'
```

Result: `4 failed`. The failures were the intended missing production surface:
`freeze_census`, `load_scan_state`, `capture_ledger`, and `ready_revisions`.
The combined RED also failed collection because `agc_runtime.capture_scanner`
did not yet exist.

Additional RED cycles proved:

- receipt-only interruption did not yet fire the required crash point;
- a non-seven-day Census window was incorrectly accepted.

Both were then implemented and rerun GREEN.

Review-fix RED A-D:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest `
  tests/test_capture_ledger.py tests/test_capture_scanner.py `
  -q -p no:cacheprovider `
  --basetemp 'C:\tmp\agc-capture-source-review-red-4'
```

Result: `6 failed, 10 passed`. The intended failures covered non-atomic run
publication, loss of persisted pre-Receipt Census truth on empty rediscovery,
dirty markers not forcing hintless recovery, invalid/unconfigured markers not
persisting degraded health, and durable quarantine being forgotten on restart.
After the A-D implementation, the focused pair reached `16 passed`.

Review-fix RED E strengthened the exact AC-03/AC-06 nodes. Result:
`1 failed, 1 passed`; AC-06 showed a `file_shrink` /
`scan_hint_invalidated` diagnostic still advanced the hint once. After the
minimal binding-level fail-closed change, the exact nodes were
`2 passed in 4.18s`.

Second re-review RED was recorded independently for every finding:

- legacy upgrade: the expected pre-Receipt crash did not fire because legacy
  `.runtime/capture/census/*.json` truth was absent from Scanner accounting;
- frozen convergence: restart with empty discovery reported known `1`,
  accounted `0` instead of rebuilding the missing Receipt/Ledger;
- dirty marker: a stale marker incorrectly made the Census denominator `1` and
  left Source Health healthy;
- exclusion: `CaptureScanner(..., excluded_keys=...)` did not exist;
- managed backup: the roundtrip lacked the Census-run capability and hierarchy,
  while three malformed run-graph cases were accepted;
- strict run invariants: wrong seven-day windows and noncanonical run IDs were
  accepted by restore validation.

The corresponding targeted GREEN runs were Scanner groups `5 passed`, frozen
backup graph/roundtrip `7 passed`, and the legacy-preserving roundtrip
`1 passed`.

Third re-review RED was also recorded independently:

- authoritative Census hard forget: `2 failed`; the target member remained in
  a multi-member run and a target-only run remained present;
- interrupted Census staging: `1 failed`; backup rejected the hidden staging
  directory instead of excluding it;
- live frozen-run validation: `2 failed, 5 passed`; a self-consistent renamed
  but noncanonical run and a non-seven-day window entered durable truth.

The first attempt used pytest's default per-user temporary root and failed in
fixture setup with `PermissionError`. That was classified as environment-only,
then rerun with an explicit `D:\tmp` basetemp to obtain the product REDs above.

Final review RED covered a true mid-publication tree containing only a valid
`members/*.json` and no `run.json`: `4 failed`. Both unrelated and target-bearing
hidden stages incorrectly returned `capture_forget_target_not_found`, while the
rollback/restart variants failed at the same strict metadata check. After the
hidden-stage branch and backup-projection alignment, the exact group reached
`4 passed`.

## Contract Evidence

- The Scanner computes and freezes `[run_started_at - 7 days, run_started_at]`.
- A Census run and its exact sorted membership are atomically published before
  Receipt accounting. Same-run exact replay permits active/archive locator
  movement, while different membership conflicts and cannot overwrite the
  immutable run.
- Durable truth is the union of legacy `.runtime/capture/census/*.json`, every
  immutable Census-run member, and current discovery. Legacy files remain
  authoritative during the managed upgrade rather than being silently dropped.
- A restart after durable Census publication but before Receipt creation
  rebuilds the missing discovered Receipt/Ledger even when current discovery is
  empty. Only after that durable convergence may its hint advance and an
  overlapping marker be acknowledged.
- Changed correctness metadata is quarantined and fails closed.
- Distinct roots remain distinct; duplicate configuration of the same binding
  is enumerated once.
- Every known key requires a strict matching Receipt and Ledger, or a valid
  suppression tombstone, before a hint advances or marker is acknowledged.
- Receipt-before-Ledger interruption replays and repairs the Ledger before
  progress can advance.
- Scan state is strict, binding-specific, atomically published, and guarded by
  an expected `state_version` with deterministic `scan_state_conflict`.
- Strict, binding/version-matched dirty markers are hints only: they force
  hintless discovery but never enter the completed-Census denominator without a
  real `RevisionRef`. A stale marker remains pending, blocks progress, and
  persists content-free degraded health until discovery or durable Census truth
  resolves it.
- Explicit `excluded_keys` policy creates or converges a metadata-only
  `excluded` Receipt/Ledger with `configured_task_exclusion`; user-forget
  tombstones are not used as an exclusion substitute.
- Managed backup allowlists the complete `census-runs/<id>/run.json` and
  `members/*.json` hierarchy, validates canonical run ID/window, schema,
  membership, binding, filename, and graph references, and restores both legacy
  and immutable Census truth. The `capture-census-runs-v1` manifest capability
  fences older or unaware runtimes.
- Live and archived Census graphs share one validator for canonical run ID,
  exact seven-day half-open window, started/frozen ordering, binding, strict
  member references, and exact membership. A corrupt live run degrades Source
  Health and contributes no durable truth.
- Hidden `.tmp` Census staging directories left by interrupted atomic publish
  are explicitly excluded from backup enumeration, and archive validation
  rejects a temporary component at any depth. They contribute no truth and do
  not prevent a later canonical freeze from converging.
- An explicitly authorized revision Hard Forget rewrites every authoritative
  primary and nested-backup Census run, removes the target member and its task,
  revision, and Receipt identities, updates exact membership, removes a run
  when it becomes empty, and retains only the authorized content-free
  suppression tombstone. Observation-forget behavior is unchanged. The
  recoverable forget transaction is the atomic boundary; rollback and restart
  recovery recreate removed run directories from strict before-images.
- Hidden `.census-*.tmp` publication stages are non-authoritative. An unrelated
  partial stage remains byte-exact and cannot block forget or backup
  validation. If a strict member or a raw receipt/task/revision identity binds
  the stage to the target, the entire abandoned stage is scrubbed; transaction
  rollback and restart recovery restore it byte-exact if deletion is
  interrupted. Canonical non-hidden runs retain strict fail-closed validation.
- Durable Source Quarantines continue to degrade health after the transient
  adapter diagnostic disappears. Diagnostics also block hint advancement for
  the affected run.
- Scanner inputs are explicit `SourceAdapter` instances and revalidated
  `DiscoveryBatch` / `RevisionRef` DTOs. Scanner code does not probe or open
  target-turn content and imports no semantic or network subsystem.

The exact acceptance nodes exist and pass:

```text
tests/test_capture_scanner.py::test_ac_03_synthetic_seven_day_census_has_full_accounting
tests/test_capture_scanner.py::test_ac_06_reconciliation_recovers_missed_duplicate_and_moved_sources
```

AC-03 synthetic result: 7 known keys, 7 accounted keys, 0 silent loss,
1 quarantined Receipt, 1 explicit excluded Receipt, 5 discovered Receipts, and
durable degraded Source Health. At this census-only boundary, zero/8/>8 and
continued shapes remain truthfully `discovered`: observation count,
retryability, and coalescing require later extractor or fingerprint semantics.
The test explicitly proves no false `complete`, `retryable`, or `coalesced`
claim.

AC-06 performs an injected post-Census/pre-Receipt crash and actual restart,
late/out-of-order completion, dirty hintless recovery, active/archive replay,
exact replay, shrink diagnostic, anchor conflict, and same logical identity in
two different roots. It converges to 3 distinct accounted keys with no duplicate
Receipt or silent loss; shrink/anchor anomaly paths do not advance the affected
hint.

## Verification Evidence

Focused Task 4, Capture transaction, backup, and admin suite:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest `
  tests/test_capture_ledger.py tests/test_capture_scanner.py `
  tests/test_capture_transaction.py tests/test_capture_backup_restore.py `
  tests/test_admin_service.py -q -p no:cacheprovider `
  --basetemp 'C:\tmp\agc-task4-rereview-focused-1'
```

Result: `121 passed, 1 expected warning in 57.01s`.

Adjacent Capture Core/source suite:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest `
  tests/test_capture_core_end_to_end.py tests/test_capture_ledger.py `
  tests/test_capture_scanner.py tests/test_capture_transaction.py `
  tests/test_capture_store.py tests/test_capture_read_service.py `
  tests/test_capture_source_contracts.py tests/test_codex_source_adapter.py `
  tests/test_capture_hook.py tests/test_capture_backup_restore.py `
  tests/test_capture_contracts.py tests/test_capture_paths.py `
  tests/test_capture_status.py -q -p no:cacheprovider `
  --basetemp 'C:\tmp\agc-task4-rereview-adjacent-2'
```

Result: `317 passed, 1 expected warning in 70.50s`.

Full repository suite in the repository Python 3.13 venv:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest -q -p no:cacheprovider `
  --basetemp 'C:\tmp\agc-task4-rereview-full-1'
```

Result: `584 passed, 1 warning in 364.25s`. There was no full-suite failure to
classify. The warning is the expected duplicate-name ZIP adversarial fixture,
not a product failure, test-order failure, or environment failure.

A clean copied-source wheel build completed with
`Successfully built agent_global_context_runtime-0.2.0-py3-none-any.whl`.
An isolated `python -I` wheel-path import loaded `agc_runtime.capture_ledger`,
`capture_scanner`, `capture_store`, and `managed_backup` from that wheel.

Final gates also include Python compilation of changed Python files,
`git diff --check`, and strict UTF-8/no-BOM validation of every changed file.

Third re-review verification after the authorized Hard Forget integration:

```text
Hard Forget suite: 35 passed in 63.39s
Combined Task 4/forget/backup/admin gate: 164 passed, 1 expected warning in 215.07s
Adjacent Capture Core/source/forget gate: 360 passed, 1 expected warning in 249.41s
Natural-order full repository suite: 596 passed, 1 expected warning in 380.14s
```

The expected warning is still the duplicate-name ZIP adversarial fixture. A
wheel build completed with `Successfully built
agent_global_context_runtime-0.2.0-py3-none-any.whl`; isolated `python -I`
imports loaded `capture_ledger`, `capture_store`, `managed_backup`, and
`capture_forget_service` directly from that wheel.

Final hidden-stage verification:

```text
Exact partial-stage group: 4 passed in 2.32s
Hard Forget suite: 39 passed in 19.37s
Combined Task 4/forget/backup/admin gate: 168 passed, 1 expected warning in 70.69s
Adjacent Capture Core/source/forget gate: 364 passed, 1 expected warning in 82.51s
Natural-order full repository suite: 600 passed, 1 expected warning in 324.25s
```

The final source rebuilt the wheel successfully, and isolated `python -I`
loaded `capture_forget_service` from the wheel path. Compilation, cached diff,
strict UTF-8/no-BOM, and forbidden-boundary import checks were also clean.

## Failure Classification During Verification

An early full run used the bundled Python 3.12 runtime and reported eight
environment failures because that interpreter did not contain the repository's
`mcp` and `build` dependencies. Those were not product failures.

The same run exposed one real product boundary regression: an eager
`capture_source` import from `capture_store`. That import was made lazy, and a
fresh standalone disabled-Capture boundary test passed. A later full run exposed
collection-time test pollution because the new tests imported deferred Scanner
modules at module import time; the tests now lazy-load and unload those modules.
The review-fix full venv run above has zero failures.

During second re-review, a mixed boundary/capability run first failed at the
disabled-Capture test's `sys.modules` precondition because another selected test
module imported Source contracts during collection. Isolated rerun then exposed
a separate real product regression: `managed_backup` imported `capture_source`
unconditionally even for archives without Census runs. The product import was
scoped to the Census-run branch and the new backup tests now lazy-load/unload
their Source DTOs. Boundary/capability nodes pass in both module orders. A later
custom adjacent ordering still placed an existing non-self-cleaning Source
contract suite before the boundary and produced exactly one precondition
failure (`316 passed, 1 failed`); this was classified as test-order pollution.
The corrected adjacent order passed `317`, and the natural full-suite order
passed all `584` tests.

During third re-review, the first adjacent run reported exactly one failure
(`359 passed, 1 failed`). This was classified as a product boundary regression,
not environment or test order: revision forget imported `capture_source` even
when no Census-run existed. The helper now enumerates the namespace first and
returns without a deferred import when it is empty. The isolated disabled-mode
boundary then passed, the targeted Hard Forget/recovery nodes passed, the fresh
adjacent run passed all `360`, and the natural full run passed all `596`.

During final hidden-stage verification, one rerun produced a setup-only missing
lease file before the staged behavior executed (`3 passed, 1 failed`). It was
classified as an environment filesystem race in a reused Windows pytest temp
root. A new unique basetemp passed all four exact cases. A separate initial
GREEN attempt exposed a product issue: forget's durable backup projection still
included the unrelated temporary stage even though managed backup enumeration
excluded it. Projection now applies the same temporary-component exclusion;
fresh forget, focused, adjacent, and full runs are all clean.

## Final Receipt / Revision Metadata Truth Review

The final Task 4 review found that a schema-valid Receipt and Ledger could share
the frozen Revision key while the Receipt contradicted the Revision's
correctness metadata. Key/status-only accounting then repaired or trusted the
Ledger, acknowledged a matching dirty marker, and advanced the scan hint.

The regression matrix was written before the production fix. Against
`d0051c8`, the focused scanner run reported `7 failed, 11 passed`: the
`settled_at`, adapter version, source schema version, identity quality,
census-only attempt count, and false exclusion status cases all remained
accounted and advanced. The preservation case also demonstrated why Scanner
replay must not project an extractor-owned Receipt back into census-only state.
An archived clean-HEAD run of the added CaptureKey row failed because the
same-key path anomaly did not degrade Source Health, completing explicit RED
coverage for every required mapping.

The fix adds one strict `validate_receipt_revision_truth` boundary. It requires:

- Receipt key equals the frozen Revision key;
- Receipt `settled_at` equals Revision `completed_at`;
- adapter version, source schema version, and identity quality are equal;
- discovered, excluded, and census metadata-conflict quarantined Receipts keep
  the metadata-only status, zero-use, zero-attempt, no-extractor/no-result
  contract, including the configured exclusion and source-quarantine reasons.

The same validator now runs when a census Receipt is constructed, before an
existing Receipt is replayed, and whenever Receipt/Ledger accounting is checked
for report coverage, hint advancement, or dirty-marker acknowledgement. A
conflict records durable content-free Source Quarantine, keeps Source Health
degraded, leaves the conflicting Receipt byte-exact, does not repair its Ledger
into an accounted state, and blocks both marker acknowledgement and hint
advancement. Once an authorized repair restores Receipt truth, replay repairs
or confirms the Ledger and the pending marker/hint converge on the next scan.

This does not weaken later extractor or terminal Receipts. Their existing
schema invariants remain authoritative, and a revision conflict may change a
Receipt only through an allowed Capture transition. In particular, a valid
complete Receipt is preserved byte-exact while the Scanner fails closed and
degrades the source. There is no conflict with the existing RevisionRef-vs-
RevisionRef rule: an anchor-only conflict may still have a truthful quarantined
Receipt and remain explicit in accounting, while a Receipt that contradicts
frozen Revision fields is never accounted.

Fresh verification for this review fix:

```text
Focused Scanner + Ledger: 33 passed in 9.59s
Adjacent Capture source/core/forget: 372 passed, 1 expected warning in 75.03s
Natural-order full repository suite: 608 passed, 1 expected warning in 274.81s
Python compilation: clean
git diff --check: clean
Strict UTF-8 / no BOM for every changed file: clean
```

The warning remains the expected duplicate-name ZIP adversarial fixture. No
live Codex profile, installed AGC root, scheduler, CLI activation, transcript
content, extractor, model/provider, Capsule, Observation, or formal-memory
writer was read or changed by this review fix.
