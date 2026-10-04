# AGC Incremental Capture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce repeated historical I/O in ordinary Capture cycles while retaining complete Census accounting and all selected-item safety checks.

**Architecture:** Reconstructible source-discovery metadata and an unfinished-transaction workset accelerate the routine path. Full historical integrity remains an explicit audit with a separate bootstrap; neither metadata nor an expired audit authorizes sending. Background scheduling reads a bounded, validated work view; public/full reads and manual authorization retain their contracts.

**Tech Stack:** Python, current file-backed Capture store, native Windows-compatible locks, atomic JSON writes, pytest.

## Global Constraints

- User authorized implementation on the existing `main` branch; baseline `206e5b864336fc7472c70bab459737dc13c35faf` is immutable for comparisons.
- All synthetic data and benchmark artifacts live beneath `D:\tmp_test`; never use production source contents in tests.
- This execution does not install, push, send production Capsules, call a Judge, or change production configuration/scheduled tasks/formal memories.
- Preserve complete current 7-day Census semantics, durable pending revisions, native locks, leases/fencing, exclusions/Forget/quarantine, budget and selected Capsule validation.
- Derived state is metadata only, reconstructible, version/root/config bound, and never a replacement source of truth. Invalid/missing state must not authorize cache-based sends.
- Full audit validity is 24 hours; expiry alone reports `audit_due`, not a new automatic stop gate. Actual corruption fails closed at the proven scope.
- Do not add a database, daemon, history deletion/rewrite, ranking change, larger timeouts, or new Recall/Review/Eval/report features.
- Tests first, focused regression and independent review before declaring each task complete. No commits or pushes are necessary to run comparisons; preserve unrelated existing doc edits.

## Task 1: Durable incremental source discovery

**Files:** `agc_runtime/codex_source_adapter.py`, new `agc_runtime/capture_source_cache.py`, source wiring in `agc_runtime/capture_scanner.py` and `agc_runtime/capture_store.py`, required invalidation in `agc_runtime/capture_forget_service.py` / `agc_runtime/admin_service.py` (the actual restore entry point); tests `tests/test_capture_source_incremental.py` plus relevant existing source/scanner/Forget/restore tests. The managed-backup allowlist already excludes these derived files and is unchanged.

**Interfaces:** Keep `SourceAdapter.discover(hint, window)` and `DiscoveryBatch` compatible. A new optional metadata-cache capability on CodexSourceAdapter may be wired by CaptureScanner; other adapters remain unaffected. Cache state must be committed/referenced only after successful Census and receipt accounting, under the Capture lock with scan-state CAS. Source body loading for selected Capsules is unchanged.

- [x] RED: create real JSONL sources, cold scan and warm re-instantiation. Assert equal complete revision mappings while warm scans avoid parsing unchanged bodies. Assert append/new/truncate/replace/archive move, rolling window, unknown/partial tail, signature changed during scan, invalid digest/version/root and dirty markers reparse or safely fall back. Test crashes before and after checkpoint publication, Forget and restored roots.
- [x] Implement metadata-only per-locator entries using file identity, size and high-resolution timestamps; no mtime-only shortcut. Store identity/completion metadata, never message bodies. Enumerate the file set on each scan. Only reuse stable successful scans; changed/error/partial files are reparsed. Keep source-conflict detection and final complete-window filtering.
- [x] Publish derived state using existing atomic primitives and native lock boundaries. Hints reference validated metadata; an uncommitted scan must not advance the reusable checkpoint. Use a managed derived namespace and clear it transactionally on Forget; restore cannot trust a restored checkpoint. Preserve full-scan operation when hint is absent or `force_full=True`.
- [x] GREEN: run `tests/test_capture_source_incremental.py`, `tests/test_codex_source_adapter.py`, `tests/test_capture_scanner.py`, `tests/test_capture_forget.py`, `tests/test_capture_backup_restore.py` with unique `--basetemp D:\tmp_test\...`.
- [x] Independent task review; fix important findings and retain precise RED/GREEN evidence.

Task 1 receipt: 188 focused tests passed; independent review v3 Ready. Same 40-file input and exact full outputs in baseline/new scanner runs, warm body parses 40 -> 0. No production acceptance implied. Real Windows junction/hardlink redirect coverage; direct symlink creation unavailable on test token.

## Task 2: Bounded recovery and explicit full integrity audit

**Files:** `agc_runtime/capture_store.py`, new `agc_runtime/capture_maintenance.py`, `agc_runtime/capture_cli.py`, required Forget/restore integration; tests `tests/test_capture_incremental_recovery.py`, `tests/test_capture_maintenance.py` and existing transaction/lease/Forget tests.

**Interfaces:** Add `CaptureStore.recover_active_transactions(now=...)` without changing existing `recover_transactions` full behavior for callers that request it. Add a separate no-model maintenance/bootstrap entry point; its result names audit scope, completion time, validity and input generation. Mark unfinished work durably before the first receipt/ledger mutation; retire markers only after a durable terminal commit.

The explicit CLI entry is `audit --root <memory-root> --once`; the first successful audit establishes the baseline. Missing or invalid baseline in the new bounded API returns `capture_bootstrap_required`, not a successful empty recovery. Keep the ordinary Scanner/Runner on their existing recovery API until Task 3 integrates the new path. The audit must actually read cold Census members (a cached full snapshot by itself does not prove cold member integrity). Publication and the audited store snapshot must share the native Capture lock or a verified unchanged generation; merely checking a timestamp after dropping the lock is insufficient. Native locks are not reentrant, so do not nest their context managers.

- [x] RED: extracting without commit journal, crash before/after each publication step, failed transition settlement, valid live lease, stale/missing/corrupt index, old root bootstrap, audit age and concurrent generation change.
- [x] Implement bounded recovery against the durable active workset, preserving fencing and live leases. Do not infer no work from an empty journals directory. Missing/untrusted baseline requires explicit bootstrap, not repeated hidden full scans in every cycle.
- [x] Full audit checks complete historical relationships and persisted Source discovery state, publishes its successful baseline consistently, does not call a model or perform new historical cleanup. Expiry alone yields `audit_due`; integrity failures cannot be mislabeled healthy. Preserve current explicit full-read behavior.
- [x] GREEN: new recovery/maintenance tests plus existing store, transactions, leases, backup/restore and Forget regressions. Independent review.

Task 2 receipt: 235 affected tests passed; independent review v2 Ready. Audit explicitly verifies cold Census members and persisted ScanState, not raw Source bodies. Old interrupted roots use non-healthy recovery-needed inventory -> bounded repair -> second explicit audit. Torn workset/seal publication requires explicit bootstrap. No Scanner/Runner integration or production gain claimed yet.

## Task 3: Background scheduling integration and comparable validation

**Files:** `agc_runtime/capture_runner.py`, `agc_runtime/capture_scanner.py`, `agc_runtime/capture_store.py`, `agc_runtime/capture_cli.py`; tests `tests/test_capture_incremental_cycle.py`, `tests/test_capture_incremental_performance.py`, existing manual/background/CLI/budget/Trace tests; documentation in the existing design and bug record.

**Interfaces:** Add a background-only scheduling view with explicit non-full-audit semantics. Keep manual backfill preparation digests and full public read APIs intact. Validate selected receipt, ledger, Census/source bindings, exclusions, quarantine, lease and Capsule before egress. Avoid repeated full recovery/snapshots/catalog reconstruction during ordinary cycles.

- [x] RED: same fixed synthetic input/time/config yields the same revision set, receipt outcomes and candidate eligibility as baseline; selected corruption/exclusion/Forget still blocks; expired audit alone does not block; no baseline and inconsistent state do not silently send.
- [x] Route ordinary cycles through committed incremental source state, bounded active recovery and lightweight scheduling; preserve complete accounting and actual candidate ranking policy. No new production schedule in this task.
- [x] GREEN: focused new tests plus affected source, manual runner, background candidates, store, read/review, budget, backup/Forget, Trace and CLI regression suites.
- [x] Benchmark the exact baseline and new code on identical synthetic histories and deltas, cold and at least three warm runs. Record timings and deterministic work counts (body parses and file reads), exact output parity, scale, limitations and actual commands. Never claim production speed from synthetic timings.
- [x] Final independent review; document remaining deployment and natural-cycle verification as not performed. Production acceptance will require at least two natural completed cycles without changing the existing deadline.

Task 3 receipt: wider affected regression 385 passed before the final narrow fixes; after canonical catalog ordering and strict selected Census/Ledger checks, 161 directly affected tests passed. Reviewer independently reproduced the original failures, then confirmed 3 passed and **Ready** with no remaining Important/Critical. Final `cycle-new-accepted.json` matches `cycle-baseline-verified.json` across all four complete semantic outputs, excluding runtime only; all current runtime module fingerprints match the measured code. Methods/results/limits: [design sections 9–10](../specs/2026-10-03-agc-incremental-capture-design.md). Reports are under `D:/tmp_test/agc-incremental-20261004`. No commit, push, install, production model invocation or natural-cycle acceptance occurred.
