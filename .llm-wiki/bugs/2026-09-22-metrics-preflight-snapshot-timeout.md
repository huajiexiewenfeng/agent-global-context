# Metrics research preflight snapshot timeout

- bug_id: metrics-preflight-snapshot-timeout
- parent_flow_id: agc-metrics-upgrade-v1
- status: fixing; production acceptance open
- Evidence: installed 0.4.5, main 4a3ca8d; two explicitly selected first turns
  timed out at 30.175s and 30.144s on 2026-09-22. Both stopped during the
  first live access check, in ledger and Census manifest reads respectively.
- Production Capture lock belonged to a live scheduled cycle and released
  naturally. Reproduction after release still timed out; not only contention.
- Active scope: snapshot read-ahead, Census manifest loading, focused tests.
- Excluded: Runner scheduling, metric definitions, global integrity weakening,
  cross-call approval caches, production install, Judge calls and source export.
- Plan: extend existing bounded read-ahead to Census manifest reads, preserving
  ordering, all validators, exception handling and joining before lock release.
- Verification: failing overlap test first; serial/parallel equality and corrupt
  Census denial; related access/forget tests; same two 30-second preflights.
- Success: real cases within the existing ceiling with identical safety gates.
  A synthetic pass or isolated speedup alone does not close this bug.

## Verification checkpoint

### Authorized production install, 2026-09-22, 22:37 local

- User approved the next-step install and old quarantine maintenance. Scheduler
  disabled through UAC; no Capture process was active, no process termination.
- The prior MCP check eventually completed with scanner/runner degraded,
  1,640 Census runs and accounting 5,658 known / 5,655 accounted / 3 pending.
  These pending records are not proof of permanent data loss; not repaired here.
- Pre-install minimal relevant regression: 26 passed in 7.21s (`bf2a23`).
  Existing wider 144-test result retained for unchanged source. Installer passed
  (`83a08c`), version remains 0.4.5, content deployment
  dea2c3afe5fdfbdf0d6d141977de8b30773ae11a2ff0df3adf81c7e5dc5e4b3d.
  Patch file hashes match source (`c4057e`); pip check reports no broken requirements.
- Verified Trace Python source files match prior installed files before invoking
  the installer; unrelated dirty runtime-modules files were not edited. Existing
  Trace DB path retained. Installer backup is
  C:/Users/admin/.agent-global-context-runtime/backups/20260922-223712-611-ed3cc59a101c48748246ccc109e3e0ef.
- Under native runner/write locks, checked journals/staging empty and the one
  quarantine's complete identity, wrote/fsynced/verified a byte-exact backup,
  then removed only that file. Backup:
  D:/tmp_test/agc-performance-install-20260922/backup-source-22409d1288d9cbae35b14b9245811318538375b38d672068d4f4d084937046c9.json.
  SHA256 21bd034a35b773f4dd9bdcd682d09d4835cfbd55ece5f8966cb2a15cc16bd6d9.
  Formal files (37) and Capture config hash unchanged (`c964fc`).
- Installed-package two-case preflight, with no-rebuild store and unchanged
  policy, failed: 30.080s / 30.862s, both access_check_1. First JSON read wait,
  second Census catalog digest json.dumps. Metadata-only result:
  D:/tmp_test/agc-performance-install-20260922/installed-preflight/preflight-result.json.
  Ready 0/2, model calls 0. No semantic/Judge or full-pipeline success claimed.
- Installed MCP handler overview accepted with 37 memories; this is a separate
  process check, not proof the current desktop session has reloaded the package.
  No commit/push, no formal memory mutation, no new metric or safety-gate changes.
- Final installed-adapter path audit (`936e7f`): sessions 5,155 + archived 507,
  no diagnostics, 112.065s. This is NOT a full scanner/reconciliation run; the
  historical source-content cause and pending accounting records remain open.
- Scheduler restored through UAC and read back (`8c87e8`): enabled=true,
  Ready, next run 2026-09-22 22:56:44 local; writer/runner locks both absent.
  Final formal/config hashes unchanged, source quarantines=0. Only the backed-up
  old source quarantine was removed; it is recoverable from the named backup.

### Follow-up diagnosis, 2026-09-22 evening

- Scheduler restoration was subsequently verified (`Enabled=true`). The patched
  two-case preflight did run after the previous cycle ended: both still timed
  out (30.155s receipt, 30.061s ledger), result under
  `D:/tmp_test/agc-metrics-preflight-census-parallel-20260922-205352`.
  Parallel Census alone is therefore insufficient, not merely unverified.
- Read-only sampling found 5,630 receipts, 5,630 ledgers and 1,639 Census runs.
  Receipt/ledger type-stat walks took 2.410s / 5.088s. Sampling is not a
  lock-consistent snapshot and cache/order effects prevent speedup claims.
- A 32-run Census profile (32,952 membership keys) observed 5,077,424 Unicode
  category calls across parsing and to_mapping revalidation. Profile timings
  include profiler overhead: read 0.105s, parse 0.019s, validate 1.928s,
  to_mapping 1.917s, digest 0.041s. Do not extrapolate as end-to-end latency.
- Narrow follow-up scope: capture_schema._identifier and focused tests. Add an
  equivalent fast path only for already valid plain ASCII identifiers; keep
  existing fallback and exact rejection messages for every other input. No
  validation removal, approval cache, production install or model invocation.
- Verification plan: first fail a real-call profile assertion, then compare
  acceptance/errors against the old parser, run contract/snapshot/access tests,
  compare the same sampled manifests, and retain real-case acceptance as open.
- Implemented the valid plain-ASCII identifier fast path. RED (`443647`):
  1 failed, 2 passed; old UUID parsing made 36 Unicode category calls where
  the new performance invariant requires zero. Exact acceptance/error parity
  covers all ASCII characters, invalid types, lengths, nullable and Unicode.
- GREEN (`567c00`): 144 passed in 8.70s across identifier, Capture contracts,
  source contracts, snapshot read-ahead, research access and Census end-to-end.
- Same 32 preloaded production manifests, installed/candidate/candidate/installed
  order (`e8f74b`): installed 1.5395s/1.0552s, candidate 0.4382s/0.4112s;
  validated mappings equal, median ratio 3.05x. This excludes disk I/O, global
  snapshot work and all model work; it is not a threefold cycle speedup claim.
- Writer lock was present at the end of that check. No new full preflight was
  started, no lock removal or process termination, no install/commit/push.
  The 30-second two-case end-to-end acceptance remains open.

- Existing serial Census loading failed the new overlap test (ac2985):
  1 failed, 3 passed. The initial fixture clock was corrected before this run.
- Implemented per-call bounded Census manifest read-ahead using the existing
  reader, ordered results and existing full validators. Defaults remain serial;
  only callers already requesting parallel snapshots opt into parallel Census.
- Related regression: 84 passed in 57.15s (20b6ae), snapshot read-ahead,
  research access/source, Census end-to-end and Capture forget. Diff check passed.
- Real-case attempt with repository code waited 30.028s for a production lock;
  both cases then returned blocked_existing_capture_lock (090d9c), so there is
  no measured production speedup or 30-second acceptance result for the patch.
- Outcome: implementation tested, real-case verification blocked; bug still open.
  No install, commit, push, Judge, source-content export, lock cleanup or Runner
  scheduling changes. Next needs a quiet verification window, not weaker gates.

## Quiet-window attempt, 2026-09-22

### Follow-up read-only diagnosis, 2026-09-22, after recovery

- Ran the adapter's path-only `_source_files` audit without reading Session
  bodies or calling discovery/extraction: 5,144 session files plus 507 archived
  files, no diagnostic codes. Binding matches the retained Source quarantine.
  Independent elevated directory enumeration confirmed 5,651 files, zero
  traversal errors and zero file reparse points. This is a point-in-time path
  check, not full content validation or proof of the original September 1 cause.
- The three most recently modified Census directories contain runs frozen at
  2026-09-22T13:08:01Z, 12:24:39Z and 12:06:34Z, with 854/844/850 revision keys;
  each run records source_quarantine_count=0. Existing source quarantine remains.
- `record_source_quarantine` retains an existing same-code record unchanged,
  including its creation time, and a subsequent clean scan does not remove it.
  Thus the old timestamp alone cannot prove lack of recurrence. Combined with
  current path checks and recent clean Census diagnostics, the retained record
  is the evidenced present deny gate, not an observed current locator escape.
- `_source_files` also labels OSError/RuntimeError during resolve as
  locator_escape; the stored code cannot distinguish path escape from a missing
  or inaccessible file. Do not claim the original cause has been reconstructed.
- Live Scheduler action matches the repository's batch launcher and has PT30M.
  Windows TaskScheduler Operational logging is disabled; no historic termination
  event was available. The 0.4.2 acceptance covered natural process-tree exit
  before 30 minutes, not timeout containment. Its timeout regression checks XML
  text, not descendant exit. A timeout/orphan relation remains a hypothesis.
- No production/configuration/code change in this follow-up; no model invocation
  or source-body export. Quarantine removal requires a separate explicit approval
  with backup and a stop-on-recurrence check. Permanent lifecycle repair and full
  Metrics acceptance remain open; do not widen timeouts as an unproven fix.

### Superseding controlled recovery, 2026-09-22 evening

- User explicitly authorized temporary scheduler disable, stopping the verified
  residual Capture process tree, checking interrupted state and restoring the
  scheduler. Formal memory deletion, quarantine cleanup and model calls excluded.
- Native Disable-ScheduledTask still failed access denied. Normal Windows UAC
  elevation succeeded; read-back confirmed Enabled=false, State=Disabled.
- Verified process identities/creation times and lineage: 49104 -> 99860 ->
  46832, all started 20:56:46 local; original parent 49524 absent and Scheduler
  COM had no running instance. Worker held runner lock, not a constant writer
  lock, and CPU/I/O still advanced. No additional descendants were found.
- Stopped exactly worker 46832 after identity recheck; launcher PIDs 99860 and
  49104 exited automatically. Native same-host dead-process lock recovery via
  capture_runner_lock reclaimed the stale runner lock. Both locks acquired and
  released successfully, residual Capture process count 0, journals/staging 0.
- One existing locator_escape Source quarantine (created 2026-09-01T12:56:48Z)
  remains untouched. Process recovery does not clear this independent deny gate.
- Quiet-window two-case preflight using repository patches returned in 21.610s
  and 21.695s, both research_source_quarantined at the first access check. No
  full source projection/Judge readiness is established. Metadata result:
  D:/tmp_test/agc-metrics-preflight-recovered-20260922-215637/preflight-result.json.
- Restored scheduler via normal UAC; final read-back (701fa2): Enabled=true,
  State=Ready, next run 2026-09-22 22:11:44 local, Capture process count 0,
  writer lock absent and runner lock absent. Recovery completed, no manual cycle.
- No root-cause lifecycle fix is deployed. Scheduler descendant containment,
  full snapshot performance and source quarantine investigation remain separate
  follow-ups; do not describe this one-time recovery as a permanent fix.

- User authorized temporary trigger disable, natural cycle completion and restore.
  Windows denied tool-side disable; user disabled it in administrator PowerShell.
  Read-back confirmed Enabled=false, State=Running.
- Existing cycle PID 48636 (started 20:11:46 local) remained alive at 20:42:04,
  CPU increased, and the Capture writer lock was absent in the final samples.
  Task settings PT30M did not establish observed process exit. Do not infer a
  deadlock or terminate this process from these observations alone.
- No patched preflight was launched while waiting for that cycle to finish.
  Quiet-window verification remains blocked; no new performance acceptance.
- Restore attempt also received Windows access denied (11720a). Read-back still
  Enabled=false, State=Running. User must restore in administrator PowerShell;
  never claim automatic Capture scheduling has resumed until confirmed.
