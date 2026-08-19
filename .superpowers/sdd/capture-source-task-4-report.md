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

- `agc_runtime/capture_ledger.py`
- `agc_runtime/capture_scanner.py`
- `agc_runtime/capture_store.py`

Tests:

- `tests/test_capture_ledger.py`
- `tests/test_capture_scanner.py`

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

## Contract Evidence

- The Scanner computes and freezes `[run_started_at - 7 days, run_started_at]`.
- A Census run and its exact sorted membership are atomically published before
  Receipt accounting. Same-run exact replay permits active/archive locator
  movement, while different membership conflicts and cannot overwrite the
  immutable run.
- Durable frozen Revision records are unioned with current discovery. A restart
  after Census publication but before Receipt creation reports pending/silent
  loss even when current discovery is empty; it neither advances a hint nor
  acknowledges the marker.
- Changed correctness metadata is quarantined and fails closed.
- Distinct roots remain distinct; duplicate configuration of the same binding
  is enumerated once.
- Every known key requires a strict matching Receipt and Ledger, or a valid
  suppression tombstone, before a hint advances or marker is acknowledged.
- Receipt-before-Ledger interruption replays and repairs the Ledger before
  progress can advance.
- Scan state is strict, binding-specific, atomically published, and guarded by
  an expected `state_version` with deterministic `scan_state_conflict`.
- Strict, binding/version-matched dirty markers force hintless discovery and
  remain pending until Receipt/Ledger durability. Invalid or unconfigured
  markers remain unacknowledged, stay outside the known-key denominator, and
  persist content-free Source Quarantine.
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
1 quarantined Receipt, 5 discovered Receipts, 1 authorized suppression
tombstone, and durable degraded Source Health. At this census-only boundary,
zero/8/>8/continued and policy-exclusion-like shapes remain truthfully
`discovered`: observation count, exclusion, retryability, and coalescing require
later extractor/policy or fingerprint semantics. The test explicitly proves no
false `complete`, `excluded`, `retryable`, or `coalesced` claim.

AC-06 performs an injected post-Census/pre-Receipt crash and actual restart,
late/out-of-order completion, dirty hintless recovery, active/archive replay,
exact replay, shrink diagnostic, anchor conflict, and same logical identity in
two different roots. It converges to 3 distinct accounted keys with no duplicate
Receipt or silent loss; shrink/anchor anomaly paths do not advance the affected
hint.

## Verification Evidence

Focused Task 4 plus Capture transaction suite:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest `
  tests/test_capture_ledger.py tests/test_capture_scanner.py `
  tests/test_capture_transaction.py -q -p no:cacheprovider `
  --basetemp 'C:\tmp\agc-capture-source-review-focused-1'
```

Result: `47 passed in 17.04s`.

Adjacent Capture Core/source suite:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest `
  tests/test_capture_ledger.py tests/test_capture_scanner.py `
  tests/test_capture_transaction.py tests/test_capture_store.py `
  tests/test_capture_read_service.py tests/test_capture_source_contracts.py `
  tests/test_codex_source_adapter.py tests/test_capture_hook.py `
  -q -p no:cacheprovider `
  --basetemp 'C:\tmp\agc-capture-source-review-adjacent-1'
```

Result: `124 passed in 28.40s`.

Full repository suite in the repository Python 3.13 venv:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest -q -p no:cacheprovider `
  --basetemp 'C:\tmp\agc-capture-source-review-full-1'
```

Result: `575 passed, 1 warning in 359.25s`. There was no full-suite failure to
classify. The warning is the expected duplicate-name ZIP adversarial fixture,
not a product failure, test-order failure, or environment failure.

A clean copied-source wheel build completed with
`Successfully built agent_global_context_runtime-0.2.0-py3-none-any.whl`.
An isolated `python -I` wheel-path import loaded `agc_runtime.capture_ledger`,
`capture_scanner`, `capture_store`, and `capture_transaction` from that wheel.

Final gates also include Python compilation of changed Python files,
`git diff --check`, and strict UTF-8/no-BOM validation of every changed file.

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
