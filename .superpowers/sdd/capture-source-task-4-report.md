# Capture Source Census Task 4 Report

## Scope

Implemented the library-only Source Census control plane. The change adds
frozen seven-day Census persistence, durable pre-semantic Receipt/Ledger
accounting, optimistic root-bound scan state, explicit-adapter reconciliation,
source quarantine, dirty-marker acknowledgement after accounting, and
crash/replay convergence. It does not add or activate a CLI, scheduler, live
profile, extractor, model/provider, Capsule, Observation, MCP, or formal-memory
writer.

Production files:

- `agc_runtime/capture_ledger.py`
- `agc_runtime/capture_scanner.py`
- `agc_runtime/capture_store.py`

Tests:

- `tests/test_capture_ledger.py`
- `tests/test_capture_scanner.py`

`agc_runtime/capture_transaction.py` did not require modification; its existing
atomic JSON publication primitive was sufficient.

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

## Contract Evidence

- The Scanner computes and freezes `[run_started_at - 7 days, run_started_at]`.
- Census identity is durable by four-part `CaptureKey`; active/archive locator
  movement is replay, while changed correctness metadata is quarantined.
- Distinct roots remain distinct; duplicate configuration of the same binding
  is enumerated once.
- Every known key requires a strict matching Receipt and Ledger, or a valid
  suppression tombstone, before a hint advances or marker is acknowledged.
- Receipt-before-Ledger interruption replays and repairs the Ledger before
  progress can advance.
- Scan state is strict, binding-specific, atomically published, and guarded by
  an expected `state_version` with deterministic `scan_state_conflict`.
- Unkeyed adapter diagnostics remain outside the known-key denominator and
  persist a content-free Source Quarantine that degrades health.
- Scanner inputs are explicit `SourceAdapter` instances and revalidated
  `DiscoveryBatch` / `RevisionRef` DTOs. Scanner code does not probe or open
  target-turn content and imports no semantic or network subsystem.

The exact acceptance nodes exist and pass:

```text
tests/test_capture_scanner.py::test_ac_03_synthetic_seven_day_census_has_full_accounting
tests/test_capture_scanner.py::test_ac_06_reconciliation_recovers_missed_duplicate_and_moved_sources
```

AC-03 synthetic result: 7 known keys, 7 accounted keys, 0 silent loss,
1 content-free Source Quarantine, degraded Source Health, and all seven
pre-semantic Receipts truthfully `discovered`.

AC-06 replay result: first run accounted 1 key; restart/reconciliation
accounted 2 keys, treated the active/archive move as 1 replay, acknowledged
the late dirty marker only after durable accounting, and a third exact replay
created 0 Receipts with 0 silent loss.

## Verification Evidence

Focused Task 4 plus Capture transaction suite:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest `
  tests/test_capture_ledger.py tests/test_capture_scanner.py `
  tests/test_capture_transaction.py -q -p no:cacheprovider `
  --basetemp 'C:\tmp\agc-capture-source-green-4-venv'
```

Result: `41 passed in 9.81s`.

Adjacent Capture Core/source suite:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest `
  tests/test_capture_ledger.py tests/test_capture_scanner.py `
  tests/test_capture_transaction.py tests/test_capture_store.py `
  tests/test_capture_read_service.py tests/test_capture_source_contracts.py `
  tests/test_codex_source_adapter.py tests/test_capture_hook.py `
  -q -p no:cacheprovider `
  --basetemp 'C:\tmp\agc-capture-source-adjacent-4-venv'
```

Result: `118 passed in 24.33s`.

Full repository suite in the repository Python 3.13 venv:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest -q -p no:cacheprovider `
  --basetemp 'C:\tmp\agc-capture-source-full-4-venv-final'
```

Result: `569 passed, 1 warning in 349.39s`. The warning is the existing
intentional duplicate-name ZIP attack fixture.

A clean copied-source wheel build completed with
`Successfully built agent_global_context_runtime-0.2.0-py3-none-any.whl`.
An isolated wheel-path import loaded both `agc_runtime.capture_ledger` and
`agc_runtime.capture_scanner` from that wheel.

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
The final full venv run above has zero failures.
