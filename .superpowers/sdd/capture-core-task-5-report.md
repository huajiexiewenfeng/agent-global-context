# Capture Core Task 5 Report

## Scope

Implemented Capture-aware managed backup/restore and exact user-authorized
Capture Hard Forget. Capture remains disabled; this work adds no Source,
Scanner, Runner, Hook, model, network, scheduler, or ordinary Recall behavior.

## Delivered

- `managed_backup` uses a deterministic Capture allowlist and declares Capture
  archive schema/capability metadata. It includes schema marker, Receipts,
  Observations, Ledger, Census, immutable manifests, content-free conflict and
  quarantine diagnostics, and suppression tombstones. It excludes cursor HMAC
  key, dirty/journal/staging/leases, queue/cache, scan state, budgets, and
  rebuildable/runtime state.
- Restore verifies archive paths, checksums, archive/Capture schema and
  capability versions, exact/case-fold duplicate names, compression limits,
  strict manifest fields, strict Capture paths/objects, Receipt/Observation
  immutable manifest bindings, Ledger bindings, and tombstones before it
  mutates the target root. Target snapshots, mutation, and rollback take locks
  in root-writer then Capture-writer order. Existing roots preserve their
  cursor key; restored fresh roots create it lazily on a cursor-issuing read.
- `agc.write capture_forget` is an exact strict union for an Observation ID or
  four-field Capture Key and requires `explicit_user_request`. It does not
  reuse formal-memory term forget.
- Observation forget removes the Observation and manifest reference, updates
  Receipt count/redaction/forgotten count, clears source and capsule hashes
  plus versions, and rewrites every managed archive.
- Revision forget scans the complete managed Capture tree under the root and
  identifies Observations from strict `Observation.source`, even when the
  immutable manifest is missing. It removes every strictly bound Receipt,
  Observation, Ledger, Census, manifest, lease/epoch, journal, staging, dirty,
  scan-state, and budget artifact, recursively rewrites managed nested backups,
  and leaves only a content-free suppression tombstone. The cursor secret,
  Capture schema marker, writer lock, private forget staging, and original
  Codex source task are outside the deletion set.
- A root-locked Capture forget transaction journals only active operation
  metadata, stores private before-images, atomically replaces primary files and
  archives, and rolls changed files back on failure. Cleanup removes and flushes
  before-images before unlinking the journal, so a cleanup failure preserves the
  recovery marker. Foreign/corrupt journal targets are quarantined without
  mutating their named path.
- Formal forget archive rewriting now preserves Capture archive capability
  metadata, keeping pre-existing formal backup/restore behavior compatible.

## Compatibility

Capture archives require a Capture-capable Runtime. Released Runtime 0.2.0
cannot be retroactively changed: Capture data must not be produced until a
Capture-capable Runtime is installed. After Capture data exists, rollback is a
feature-disable procedure rather than a binary downgrade to 0.2.0.

## Verification

```text
Review RED A: 3 failed, 5 passed
  schema-version child reached mutation; orphan manifest/ledger used unsafe
  generic errors. Backslash/casefold/zipbomb/duplicate-name/orphan-observation
  cases already failed closed.
Review GREEN A: 8 passed
Review RED C/D: 2 failed
  full-tree revision forget remains authorization-blocked; observation forget
  repeat expectation was corrected to accepted idempotency.
Review RED E: 2 failed, 7 passed
Review GREEN E: 9 passed
Review RED F: 2 failed, 2 passed
Review GREEN F + foreign journal + observation zero/repeat: 4 passed
Review RED G: 1 failed, 10 passed
Review GREEN G: 11 passed

Authorization gate resolved by direct user authorization on 2026-08-14.
Full-tree revision RED: 1 failed in 9.15s
Full-tree revision GREEN: 1 passed in 1.28s

Focused Task 5 and adjacent transaction/storage suite:
110 passed, 1 warning in 31.85s

Full Runtime, excluding the installer module and the known wheel-environment
test:
408 passed, 1 deselected, 1 warning in 61.74s

compileall agc_runtime tests: passed
git diff --check: passed
```

An interrupted Capture forget journal is recovered by the next exact
`capture_forget` request under the root writer lock before planning a retry.
Capture remains disabled until the later activation work.

## Authorization boundary

The user explicitly authorized this implementation scope on 2026-08-14. The
capability executes only for a future exact `capture_forget` request carrying
`authorization=explicit_user_request`; this implementation and its tests did
not operate on the deployed AGC profile or delete any original Codex task.
