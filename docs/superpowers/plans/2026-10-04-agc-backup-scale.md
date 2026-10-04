# AGC Backup Scale Implementation Plan

> **For agentic workers:** Execute inline with `executing-plans`; use a separate `requesting-code-review` reviewer before production activation. This is a small approved repair, not new Capture design.

**Goal:** Unblock the managed production backup without deleting history or weakening content, path, graph or Forget checks.

**Architecture:** Retain schema-v2 archives and canonical Census compaction. Raise the two metadata-capacity ceilings to 32,768 files / 8 MiB manifest while keeping all payload bounds. Prune only already-excluded generic UTF-8 subtrees and retain a complete, cheaper filesystem safety walk for archive collection.

**Tech Stack:** Python 3.13, pathlib/os.scandir, zipfile, pytest, existing immutable PowerShell installer.

## Global constraints

- Main checkout D:/tmp/github/agent-global-context; preserve unrelated changes; no branch switch.
- D:/tmp_test is the only test output root. No production Session/Capsule contents in reports.
- Production root, Trace DB, max-items 10, gpt-6.1-sol and 15-minute task stay unchanged.
- No raw data deletion, manual Capture, Judge invocation or formal memory promotion.
- Old small archives remain supported; a large archive needs the repaired reader. Preserve that exact recovery runtime before activation.

## Task 1: Bounded archive capacity and traversal regression fix

Files: agc_runtime/managed_backup.py; agc_runtime/admin_service.py;
tests/test_backup_capacity.py; tests/test_capture_backup_restore.py;
tests/test_capture_forget.py; tests/test_forget_service.py.
Interfaces remain `backup_files(paths)`, `manifest(files)`, `archive_bytes(files, manifest)`,
`read_verified_archive(path)`, `_strict_decode_managed(paths, issues)` and public backup/restore requests.

- [x] Add real 24,000-member archive round-trip and 5,000-member admin restore tests, a no-descendant-scan UTF-8 regression, and a cold Census cached-stat regression.
- [x] Run RED: `.venv/Scripts/python.exe -B -m pytest tests/test_backup_capacity.py tests/test_capture_backup_restore.py -k 'production_scale or prunes_excluded or cached_metadata' -q -p no:cacheprovider --basetemp D:/tmp_test/agc-backup-scale-red` (4 failures); corrected excluded-tree access guard rerun in `agc-backup-scale-red-prune` (3 failures).
- [x] Set `_MAX_ARCHIVE_FILES = 32768`, `_MAX_MANIFEST_SIZE = 8 * 1024 * 1024`; do not change other payload/ratio ceilings. Retain read-after-write archive verification.
- [x] In `_strict_decode_managed`, use top-down `os.walk`, pruning `.runtime/locks`, `.runtime/backups`, `.runtime/capture`; keep retained file validation and temporary-file behavior.
- [x] In archive collection, replace per-path repeated stat calls with a no-follow scandir walk. Reject every discovered symlink/reparse before descent. Check cold Census member size but canonicalize its content using the existing store API. Retain selected-file resolved-root check and post-read bounds.
- [x] GREEN: 8 focused checks passed in 83.30 s. Final five-file backup/restore/Forget/admin regression: 171 passed in 133.50 s, one expected duplicate-ZIP fixture warning, `--basetemp D:/tmp_test/agc-backup-scale-final`. Includes large-archive Forget rewriting and real cold-member/reparse cases. Unchanged installer retains earlier 55-pass / 301.98 s evidence; verify actual installed modules again during rollout.
- [x] Independent static review against c779494: Ready, no Critical/Important findings. Added the suggested cold-run-member and excluded-tree link regression coverage.
- [ ] Commit and push only this repair.

## Task 2: Resume the authorized production rollout

Files: existing immutable installer; local evidence D:/tmp_test/agc-production-20261004.

- [ ] Build/preserve a verified recovery runtime without switching stable launchers; keep dependency versions unchanged.
- [ ] Disable the exact Windows task, let its live worker finish naturally, acquire native locks; do not delete lock files.
- [ ] Run native managed backup using the repaired reader/writer. Verify all archive entries and restore into an isolated D:/tmp_test target; verify production formal-memory/config hashes unchanged.
- [ ] Refresh Trace SQLite backup using the existing online-backup helper; preserve the original DB.
- [ ] Install the exact reviewed build through install-local.ps1, verify installed hashes and existing root/Trace/config preservation.
- [ ] Establish a healthy standalone audit baseline; use bounded native recovery only if needed, never manual lock/data clearing.
- [ ] Re-enable the original task; observe two naturally triggered nonempty completed cycles using their receipts and terminal Trace. Keep pending/failure distinct from accepted.
- [ ] Use a quiet follow-up heartbeat if natural cycles outlive the interactive turn. Report meaningful success/failure only; do not count empty runs as extraction acceptance.
