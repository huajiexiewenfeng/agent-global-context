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

## Review fixes (2026-08-14)

The Task 5 review findings were resolved as follows:

- Restore now acquires the root writer lock and then the Capture writer lock
  before reading or verifying the selected archive, and keeps both locks
  through mutation or rollback. A deterministic two-thread regression proves
  that a stale restore cannot resurrect an Observation after Capture forget
  rewrites the managed archive.
- Exact Observation forget discovers its Receipt through the immutable
  manifest even when the canonical Observation file is missing, updates the
  primary graph, rewrites every nested managed backup, and removes every
  runtime JSON artifact with an explicit exact Observation binding.
- Recovery validates the complete journal, operation count, unique targets,
  image names, image existence, target scope, and all before-image bytes before
  its first target mutation. Corrupt recovery records are strict
  `SourceQuarantine` objects accepted by managed-backup validation.
- Restore prevalidates every restorable entry as strict UTF-8 before clearing
  current state. Rollback restores byte snapshots with atomic byte writes, so
  pre-existing non-UTF-8 files are restored exactly.
- Revision forget independently validates every manifest-referenced
  Observation's strict source Capture Key before deletion. Cross-bound
  manifests fail closed and preserve the foreign Observation.
- Managed backup excludes `.runtime/queue/` and `.runtime/cache/`, rejects
  symbolic links, Windows reparse points, and resolved root escapes before
  reading targets, and checks the archive file-size ceiling before
  `read_bytes()`.
- Formal term forget excludes all live and archived `.runtime/capture/` model
  paths from matching, deletion, rewriting, and verification. Root locking
  continues to serialize shared archive changes without bypassing exact
  Capture forget.
- Primary, rollback, recovery, restore-clear, and suppression deletes in the
  reviewed owned modules use the durable `safe_unlink` primitive. Repeated
  revision forget preserves the existing tombstone and backup bytes instead of
  churning timestamps or archives.

### Review RED evidence

```powershell
& 'D:\tmp\github\agent-global-context\.venv\Scripts\python.exe' -m pytest `
  'D:\tmp\github\agent-global-context\tests\test_capture_backup_restore.py' `
  'D:\tmp\github\agent-global-context\tests\test_capture_forget.py' `
  'D:\tmp\github\agent-global-context\tests\test_forget_service.py' -q `
  --basetemp 'C:\tmp\agc-task5-review-red'
```

Result: `14 failed, 57 passed, 1 skipped, 1 warning in 38.82s`. The first
cross-bound test fixture itself was rejected by the existing Observation model
because its Receipt did not match its source key. The fixture was corrected to
use a valid foreign Observation and foreign Receipt referenced by the target
manifest; the corrected regression then failed for the intended reason:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest `
  tests/test_capture_forget.py::test_revision_forget_fails_closed_on_foreign_observation_in_target_manifest `
  -q --basetemp 'C:\tmp\agc-task5-cross-red'
```

Result: `1 failed in 1.07s` because revision forget returned `accepted` and
deleted the cross-bound foreign Observation.

The local host cannot create an unprivileged file symlink, so the regression
was tightened to fall back to a real Windows junction. With both link/reparse
and resolved-escape defenses temporarily reverted to the original behavior:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest `
  tests/test_capture_backup_restore.py::test_backup_rejects_symbolic_link_before_reading_target `
  -q --basetemp 'C:\tmp\agc-task5-link-red-2'
```

Result: `1 failed in 7.69s` with `DID NOT RAISE ValueError`. Restoring the two
defenses and rerunning with `--basetemp C:\tmp\agc-task5-link-green-final`
produced `1 passed in 0.49s`.

### Final verification

```powershell
& '.\.venv\Scripts\python.exe' -m pytest `
  tests/test_capture_backup_restore.py tests/test_capture_forget.py `
  tests/test_admin_service.py tests/test_forget_service.py -q `
  --basetemp 'C:\tmp\agc-task5-focused-final'
```

Result: `81 passed, 1 warning in 33.43s`. The warning is intentionally
triggered by the duplicate-ZIP-entry attack regression.

```powershell
& '.\.venv\Scripts\python.exe' -m pytest `
  tests/test_capture_contracts.py tests/test_capture_paths.py `
  tests/test_capture_store.py tests/test_capture_transaction.py `
  tests/test_capture_read_service.py tests/test_capture_status.py -q `
  --basetemp 'C:\tmp\agc-task5-adjacent-review'
```

Result: `197 passed in 23.14s`.

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests `
  --ignore=tests/test_local_install.py `
  --deselect=tests/test_runtime_config.py::test_built_wheel_contains_default_and_installed_admin_init_works `
  -q --basetemp 'C:\tmp\agc-task5-runtime-final'
```

Result: `421 passed, 1 deselected, 1 warning in 74.82s`. Only the documented
local installer module and known wheel-environment integration test were
excluded.

```powershell
& '.\.venv\Scripts\python.exe' -m compileall -q agc_runtime tests
git diff --check
```

Result: both passed. A strict PowerShell byte scan over every changed Python
file decoded with `UTF8Encoding(false, true)`, rejected an `EF BB BF` prefix,
and rejected byte `0D`; result: `UTF-8 strict/no-BOM/LF: passed`.

All tests used temporary roots under `C:\tmp`; no deployed AGC profile or
original Codex source task was read, rewritten, or deleted.

## Second-review fixes (2026-08-14)

The second review findings were resolved with strict targeted regressions:

- Capture-forget recovery now accepts and rolls back a fully validated
  canonical recorded prefix from zero through `operation_count` before-images.
  Overflow, noncanonical image names, and all other invalid records still fail
  closed before mutation.
- Corrupt-journal recovery removes and durably flushes the dedicated private
  staging directory before quarantining and unlinking the recovery marker. An
  injected cleanup failure leaves both marker and staging evidence intact.
- Exact Observation forget removes the canonical
  `.runtime/capture/staging/<observation_id>.json` path even when its bytes are
  unparseable or omit the ID, while preserving an unparseable same-stem dirty
  artifact that lacks a strict binding.
- Restore validation rejects crafted `.runtime/queue` and `.runtime/cache`
  archive entries before target mutation.
- Backup creation enforces the reader's file-count, per-file-size, and
  aggregate-size limits before writing an archive that the reader would reject.

### Second-review RED evidence

```powershell
& '.\.venv\Scripts\python.exe' -m pytest `
  tests/test_capture_backup_restore.py tests/test_capture_forget.py -q `
  --basetemp 'C:\tmp\agc-task5-second-review-red'
```

Result: `10 failed, 47 passed, 1 warning in 24.57s`. The failures reproduced
the crafted queue/cache acceptance, three writer-limit gaps, end-to-end backup
limit acceptance, malformed canonical staging survival, two crash-prefix
quarantines, and masked corrupt-staging cleanup failure.

### Second-review targeted GREEN

```powershell
& '.\.venv\Scripts\python.exe' -m pytest `
  tests/test_capture_backup_restore.py tests/test_capture_forget.py -q `
  --basetemp 'C:\tmp\agc-task5-second-review-green-2'
```

Result: `58 passed, 1 warning in 22.87s`, including the additional invalid
overflow-record regression.

### Second-review final verification

```powershell
& '.\.venv\Scripts\python.exe' -m pytest `
  tests/test_capture_backup_restore.py tests/test_capture_forget.py `
  tests/test_admin_service.py tests/test_forget_service.py -q `
  --basetemp 'C:\tmp\agc-task5-second-focused-final'
```

Result: `92 passed, 1 warning in 35.68s`.

```powershell
& '.\.venv\Scripts\python.exe' -m pytest `
  tests/test_capture_contracts.py tests/test_capture_paths.py `
  tests/test_capture_store.py tests/test_capture_transaction.py `
  tests/test_capture_read_service.py tests/test_capture_status.py -q `
  --basetemp 'C:\tmp\agc-task5-second-adjacent-final'
```

Result: `197 passed in 17.27s`.

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests `
  --ignore=tests/test_local_install.py `
  --deselect=tests/test_runtime_config.py::test_built_wheel_contains_default_and_installed_admin_init_works `
  -q --basetemp 'C:\tmp\agc-task5-second-broad-final'
```

Result: `432 passed, 1 deselected, 1 warning in 79.65s`. The warning in all
relevant runs is intentionally triggered by the duplicate-ZIP-entry attack
regression.

```powershell
& '.\.venv\Scripts\python.exe' -m compileall -q agc_runtime tests
git diff --check
```

Result: both passed. A strict byte scan of every changed Python and report file
decoded with `UTF8Encoding(false, true)`, rejected an `EF BB BF` prefix, and
rejected byte `0D`; result: `UTF-8 strict/no-BOM/LF: passed`.

Every test used a temporary root under `C:\tmp`; no deployed AGC profile or
original Codex source task was accessed, rewritten, or deleted.

## Final re-review fixes (2026-08-14)

- Protected managed-runtime classification is now case-insensitive for
  `.runtime/capture`, locks, backups, queue, cache, temporary files, and the
  Capture cursor key. Noncanonical case variants are rejected before restore
  mutation; manifest paths, file-set equality, sizes, and hashes remain exact.
- Backup generation verifies the completed ZIP bytes with the same validator
  used by restore before returning them for publication. This enforces the
  compression-ratio, encoded-manifest, archive-size, entry-count, exact
  manifest, and Capture graph constraints symmetrically.
- Seven unused legacy private backup/archive helpers and their now-unused
  imports were removed from `admin_service` after a repository-wide caller
  search found only their definitions and one internal legacy-helper call.

### Final re-review RED evidence

```powershell
& '.\.venv\Scripts\python.exe' -m pytest `
  tests/test_capture_backup_restore.py -q `
  -k 'case_variant_protected_runtime_paths or archive_writer_rejects or unused_legacy_backup_helpers' `
  --basetemp 'C:\tmp\agc-task5-final-rereview-red'
```

Result: `5 failed, 27 deselected in 4.49s`. Both case-variant protected paths
were accepted by restore, both writer outputs escaped the reader-only limits,
and all seven dead helpers were still present.

### Final re-review targeted GREEN

The same command with
`--basetemp C:\tmp\agc-task5-final-rereview-green` produced
`5 passed, 27 deselected in 0.67s`.

An initial filesystem fixture for publication safety was rejected by ordinary
root validation before reaching the archive writer, so it was narrowed to
inject the exact collected file list into the real backup handler. With shared
writer verification temporarily reverted, the corrected regression was:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest `
  tests/test_capture_backup_restore.py::test_backup_creation_rejects_high_compression_ratio_before_publication `
  -q --basetemp 'C:\tmp\agc-task5-final-publication-red-3'
```

Result: `1 failed in 4.38s` because backup returned `accepted` and published
the reader-incompatible ZIP. Restoring writer verification changed the failure
to the generic `invalid_request` code (`1 failed in 1.16s`); the minimal handler
mapping then produced `1 passed in 0.46s` with
`--basetemp C:\tmp\agc-task5-final-publication-green-2`.

```powershell
& '.\.venv\Scripts\python.exe' -m pytest `
  tests/test_capture_backup_restore.py -q `
  -k 'case_variant_protected_runtime_paths or archive_writer_rejects or backup_creation_rejects_high_compression_ratio or unused_legacy_backup_helpers' `
  --basetemp 'C:\tmp\agc-task5-final-rereview-targeted-final'
```

Result: `6 passed, 27 deselected in 4.02s`.

```powershell
& '.\.venv\Scripts\python.exe' -m pytest `
  tests/test_capture_backup_restore.py -q `
  --basetemp 'C:\tmp\agc-task5-final-rereview-backup-green'
```

Result: `32 passed, 1 warning in 12.59s`.

### Final re-review verification

```powershell
& '.\.venv\Scripts\python.exe' -m pytest `
  tests/test_capture_backup_restore.py tests/test_capture_forget.py `
  tests/test_admin_service.py tests/test_forget_service.py -q `
  --basetemp 'C:\tmp\agc-task5-final-rereview-focused-final'
```

Result: `98 passed, 1 warning in 49.68s`.

```powershell
& '.\.venv\Scripts\python.exe' -m pytest `
  tests/test_capture_contracts.py tests/test_capture_paths.py `
  tests/test_capture_store.py tests/test_capture_transaction.py `
  tests/test_capture_read_service.py tests/test_capture_status.py -q `
  --basetemp 'C:\tmp\agc-task5-final-rereview-adjacent-final'
```

Result: `197 passed in 23.18s`.

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests `
  --ignore=tests/test_local_install.py `
  --deselect=tests/test_runtime_config.py::test_built_wheel_contains_default_and_installed_admin_init_works `
  -q --basetemp 'C:\tmp\agc-task5-final-rereview-broad-final'
```

Result: `438 passed, 1 deselected, 1 warning in 82.43s`. The warning is the
intentional duplicate-ZIP-entry attack regression.

```powershell
& '.\.venv\Scripts\python.exe' -m compileall -q agc_runtime tests
git diff --check
```

Result: both passed. The strict UTF-8/no-BOM/LF byte scan passed for every
changed Python, test, and report file. All tests used `C:\tmp` roots; no live
deployed AGC profile or original Codex source task was accessed or changed.

## Windows alias and source-name correctness fixes (2026-08-14)

- The shared archive-name validator now rejects Windows filesystem aliases in
  every component: trailing dots/spaces, alternate-data-stream colons, `CON`,
  `PRN`, `AUX`, `NUL`, `COM1` through `COM9`, and `LPT1` through `LPT9`,
  case-insensitively and with extensions. Standard DOS short-name aliases for
  `.runtime`, `.runtime/capture`, and `.runtime/backups` are also rejected,
  while an ordinary nonprotected POSIX name such as `contexts/draft~1.md`
  remains valid.
- Formal forget now validates the complete source ZIP name set in a first pass
  through the shared validator. Only after every name succeeds does it read,
  classify, or filter an entry. Parent traversal, dot segments, repeated
  separators, and Windows aliases therefore fail with the original backup and
  live Memory remaining byte-exact and untouched.

### Windows-alias RED evidence

```powershell
& '.\.venv\Scripts\python.exe' -m pytest `
  tests/test_capture_backup_restore.py::test_restore_rejects_windows_filesystem_aliases_before_clear `
  tests/test_forget_service.py::test_formal_forget_validates_every_source_archive_name_before_filtering `
  -q --basetemp 'C:\tmp\agc-task5-windows-alias-red'
```

Result: `16 failed in 13.97s`. Restore reached clear/mutation for trailing
dot/space, nested colon, reserved-device, and runtime short-name spellings;
formal forget accepted and filtered all four invalid source entry names.

The first minimal component validator produced `16 passed in 6.27s` with
`--basetemp C:\tmp\agc-task5-windows-alias-green`. A preservation regression
then proved its generic short-name rule was too broad:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest `
  tests/test_capture_backup_restore.py::test_archive_writer_preserves_nonprotected_posix_tilde_name `
  -q --basetemp 'C:\tmp\agc-task5-posix-tilde-red'
```

Result: `1 failed in 0.41s` because `contexts/draft~1.md` was rejected. With
the generic short-name rejection removed and three protected standard aliases
added, the contextual RED run produced `3 failed, 12 passed in 7.13s` using
`--basetemp C:\tmp\agc-task5-short-alias-red`. Narrowing short-name rejection
to `RUNTIM~N`, `.runtime/CAPTUR~N`, and `.runtime/BACKUP~N` produced
`15 passed in 6.25s` with
`--basetemp C:\tmp\agc-task5-short-alias-green`.

### Windows-alias final verification

```powershell
& '.\.venv\Scripts\python.exe' -m pytest `
  tests/test_capture_backup_restore.py::test_restore_rejects_windows_filesystem_aliases_before_clear `
  tests/test_capture_backup_restore.py::test_archive_writer_preserves_nonprotected_posix_tilde_name `
  tests/test_forget_service.py::test_formal_forget_validates_every_source_archive_name_before_filtering `
  -q --basetemp 'C:\tmp\agc-task5-windows-alias-targeted-final'
```

Result: `19 passed in 7.34s`.

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_forget_service.py -q `
  --basetemp 'C:\tmp\agc-task5-windows-alias-formal-final-2'
```

Result: `32 passed in 12.71s`.

```powershell
& '.\.venv\Scripts\python.exe' -m pytest `
  tests/test_capture_backup_restore.py tests/test_capture_forget.py `
  tests/test_admin_service.py tests/test_forget_service.py -q `
  --basetemp 'C:\tmp\agc-task5-windows-alias-focused-final-2'
```

Result: `123 passed, 1 warning in 59.54s`.

```powershell
& '.\.venv\Scripts\python.exe' -m pytest `
  tests/test_capture_contracts.py tests/test_capture_paths.py `
  tests/test_capture_store.py tests/test_capture_transaction.py `
  tests/test_capture_read_service.py tests/test_capture_status.py -q `
  --basetemp 'C:\tmp\agc-task5-windows-alias-adjacent-final-2'
```

Result: `197 passed in 19.78s`.

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests `
  --ignore=tests/test_local_install.py `
  --deselect=tests/test_runtime_config.py::test_built_wheel_contains_default_and_installed_admin_init_works `
  -q --basetemp 'C:\tmp\agc-task5-windows-alias-broad-final-2'
```

Result: `463 passed, 1 deselected, 1 warning in 102.92s`. The warning is the
intentional duplicate-ZIP-entry attack regression.

```powershell
& '.\.venv\Scripts\python.exe' -m compileall -q agc_runtime tests
git diff --check
```

Result: both passed. The strict UTF-8/no-BOM/LF byte scan passed for every
changed Python, test, and report file. All tests used `C:\tmp` roots; no live
deployed AGC profile or original Codex source task was accessed or changed.

## Remaining review fixes (2026-08-14)

- Archive names must now equal their exact `PurePosixPath.as_posix()` spelling
  in addition to the existing traversal, absolute-path, drive, and backslash
  checks. Repeated separators, dot segments, trailing separators, and their
  alias collisions therefore fail before restore mutation.
- `managed_backup.is_protected_capture_path` is the shared canonicalized,
  case-folded Capture classifier. Managed backup and formal forget use it for
  live planning, archive rewriting, and post-operation verification, so
  `.RUNTIME/capture` and separator aliases are never term-scanned or deleted.
- Formal forget no longer has an alternate ZIP writer. Rebuilt archives pass
  through `managed_backup.archive_bytes` and the same immediate verifier as
  normal backups. Compression-ratio, encoded-manifest, file-count, total-size,
  exact-manifest, and Capture-graph failures now abort plan construction before
  the journal or any managed path is mutated; the original backup stays byte
  exact.

### Remaining-findings RED evidence

```powershell
& '.\.venv\Scripts\python.exe' -m pytest `
  tests/test_capture_backup_restore.py::test_restore_rejects_noncanonical_archive_aliases_before_mutation `
  tests/test_forget_service.py::test_formal_forget_never_deletes_casefolded_capture_archive_path `
  tests/test_forget_service.py::test_formal_forget_rejects_unrestorable_rebuilt_archive_before_mutation `
  -q --basetemp 'C:\tmp\agc-task5-remaining-red'
```

Result: `6 failed in 3.63s`. Restore accepted the two protected aliases and an
ordinary alias collision. Formal forget deleted the case-folded Capture entry
and published rebuilt archives that violated compression-ratio and encoded
manifest limits.

### Remaining-findings targeted GREEN

The same command with
`--basetemp C:\tmp\agc-task5-remaining-green` produced
`6 passed in 2.25s`.

```powershell
& '.\.venv\Scripts\python.exe' -m pytest `
  tests/test_forget_service.py::test_forget_rewrites_backup_zip_and_injects_tombstone `
  tests/test_forget_service.py::test_formal_forget_never_scans_or_rewrites_capture_model_paths `
  -q --basetemp 'C:\tmp\agc-task5-remaining-formal-compat'
```

Result: `2 passed in 0.88s`.

### Remaining-findings final verification

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_forget_service.py -q `
  --basetemp 'C:\tmp\agc-task5-remaining-formal-final'
```

Result: `28 passed in 10.88s`.

```powershell
& '.\.venv\Scripts\python.exe' -m pytest `
  tests/test_capture_backup_restore.py tests/test_capture_forget.py `
  tests/test_admin_service.py tests/test_forget_service.py -q `
  --basetemp 'C:\tmp\agc-task5-remaining-focused-final'
```

Result: `104 passed, 1 warning in 46.45s`.

```powershell
& '.\.venv\Scripts\python.exe' -m pytest `
  tests/test_capture_contracts.py tests/test_capture_paths.py `
  tests/test_capture_store.py tests/test_capture_transaction.py `
  tests/test_capture_read_service.py tests/test_capture_status.py -q `
  --basetemp 'C:\tmp\agc-task5-remaining-adjacent-final'
```

Result: `197 passed in 16.97s`.

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests `
  --ignore=tests/test_local_install.py `
  --deselect=tests/test_runtime_config.py::test_built_wheel_contains_default_and_installed_admin_init_works `
  -q --basetemp 'C:\tmp\agc-task5-remaining-broad-final'
```

Result: `444 passed, 1 deselected, 1 warning in 81.93s`. The warning is the
intentional duplicate-ZIP-entry attack regression.

```powershell
& '.\.venv\Scripts\python.exe' -m compileall -q agc_runtime tests
git diff --check
```

Result: both passed. The strict UTF-8/no-BOM/LF byte scan passed for every
changed Python, test, and report file. All tests used `C:\tmp` roots; no live
deployed AGC profile or original Codex source task was accessed or changed.

## Fail-closed Windows 8.3 alias validation (2026-08-14)

- The shared archive-name validator no longer guesses which protected names a
  Windows short name might alias. Every path component matching a plausible
  8.3 short-name shape is rejected regardless of namespace, including numeric
  and hash/alphanumeric suffix forms. Restore, writer verification, and formal
  forget all use this shared validator.
- The previous `contexts/draft~1.md` compatibility is intentionally removed.
  An unambiguous ordinary tilde spelling such as
  `contexts/draft~notes~final.md` remains valid because it cannot be an 8.3
  short-name component.

### 8.3 alias RED evidence

```powershell
& '.\.venv\Scripts\python.exe' -m pytest `
  tests/test_capture_backup_restore.py::test_restore_rejects_windows_filesystem_aliases_before_clear `
  tests/test_capture_backup_restore.py::test_archive_writer_rejects_plausible_windows_short_name_alias `
  tests/test_capture_backup_restore.py::test_archive_writer_preserves_unambiguous_ordinary_tilde_name `
  tests/test_forget_service.py::test_formal_forget_validates_every_source_archive_name_before_filtering `
  -q --basetemp 'C:\tmp\agc-task5-83-alias-red'
```

Result: `7 failed, 19 passed in 13.56s`. The new arbitrary-namespace numeric
and hash/alphanumeric aliases were accepted by restore, archive writing, and
formal forget; formal forget rewrote the source backup instead of failing
closed.

### 8.3 alias targeted GREEN

The same command with `--basetemp C:\tmp\agc-task5-83-alias-green` produced
`26 passed in 9.43s`.

### 8.3 alias final verification

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_forget_service.py -q `
  --basetemp 'C:\tmp\agc-task5-83-formal-final'
```

Result: `34 passed in 12.09s`.

```powershell
& '.\.venv\Scripts\python.exe' -m pytest `
  tests/test_capture_backup_restore.py tests/test_capture_forget.py `
  tests/test_admin_service.py tests/test_forget_service.py -q `
  --basetemp 'C:\tmp\agc-task5-83-focused-final'
```

Result: `130 passed, 1 warning in 50.91s`.

```powershell
& '.\.venv\Scripts\python.exe' -m pytest `
  tests/test_capture_contracts.py tests/test_capture_paths.py `
  tests/test_capture_store.py tests/test_capture_transaction.py `
  tests/test_capture_read_service.py tests/test_capture_status.py -q `
  --basetemp 'C:\tmp\agc-task5-83-adjacent-final'
```

Result: `197 passed in 18.22s`.

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests `
  --ignore=tests/test_local_install.py `
  --deselect=tests/test_runtime_config.py::test_built_wheel_contains_default_and_installed_admin_init_works `
  -q --basetemp 'C:\tmp\agc-task5-83-broad-final'
```

Result: `470 passed, 1 deselected, 1 warning in 87.01s`. The warning is the
intentional duplicate-ZIP-entry attack regression.

```powershell
& '.\.venv\Scripts\python.exe' -m compileall -q agc_runtime tests
git diff --check
```

Result: both passed. The strict UTF-8/no-BOM/LF byte scan passed for every
changed Python, test, and report file. All tests used `C:\tmp` roots; no live
deployed AGC profile or original Codex source task was accessed or changed.
