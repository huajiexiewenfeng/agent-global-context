# Managed backup production-scale compatibility

- bug_id / flow_id: agc-managed-backup-production-scale
- status: verified-code; production rollout pending
- authorization: user approved the minimal backup compatibility repair, then the existing backup/install/audit/two-natural-cycle rollout.
- route: requested_profile=frontier; effective_profile=full; task_class=high_risk (backup integrity and release); project-fix -> systematic-debugging -> TDD -> independent review -> verification.

## Evidence and cause

The managed archive has a 4,096-file / 1 MiB manifest ceiling. On 2026-10-04,
production metadata already contained 6,907 receipts, 6,907 ledgers, 444
observations, 38 reviews and 4,332 immutable indexes (about 13 MB), excluding
unique Census revisions and formal memory. The previously attempted backup
cannot fit. Profiling also found `_strict_decode_managed` walking/statting all
Capture history before excluding it from the generic UTF-8 pass.

## Approved design and scope

- Increase only the file and manifest ceilings to 32,768 entries and 8 MiB.
  Keep 64 MiB payload, 16 MiB per member, compression-ratio, path, graph,
  checksum and lock validation. Writer and reader use the same bounds.
- Prune the three already-excluded namespaces from generic UTF-8 traversal
  before visiting descendants. Keep the separate Capture validators intact.
- Use cached directory-entry metadata for backup traversal, including cold
  Census and excluded runtime descendants. Preserve link/reparse rejection
  and original Census-member size checks; do not bypass their safety walk.
- Archive schema stays v2. Existing small archives remain readable. Large
  archives require the repaired reader: preserve a verified recovery runtime;
  do not promise an untested downgrade to an older reader.
- Active: admin_service.py, managed_backup.py, focused tests and this plan.
  Excluded: Capture scheduling/model changes, review deduplication, deleting
  history/locks, formal memory writes, Trace/Eval changes, unrelated dirty bug note.

## Verification and rollout

See `docs/superpowers/plans/2026-10-04-agc-backup-scale.md`. Reproduce the old
count limit and excluded-tree walk, then verify large archive read/restore,
negative safety cases and hard-Forget backup rewriting. Production backup must
pass before launcher/config activation. All tests use D:/tmp_test.

| Step | Status | Evidence |
| --- | --- | --- |
| source/design | confirmed | Current limits, production metadata, prior backup stack samples |
| plan | approved | User's explicit continuation of the minimal repair |
| development/testing | verified | RED 4 capacity/stat failures + 3 excluded-walk failures; GREEN 8 focused tests; final 171 backup/restore/Forget/admin tests passed in 133.50 s |
| independent review | ready | No Critical/Important findings; minor cold-member/link coverage added and passed |
| release/field acceptance | pending | Native backup, install, audit baseline, two natural nonempty cycles |
