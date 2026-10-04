# Capture extractor unavailable without Windows system proxy

## 2026-10-03 local-I/O diagnosis after repeated deadlines

- Current automatic worker started at 20:56:47 Asia/Shanghai. Nonblocking
  py-spy dumps at 20:58:16 and a 40-second, 2-Hz sample from 20:58:54 found
  scanner transaction recovery. All 79 sampled main-thread stacks were inside
  recovery reading receipt/manifest/observation JSON; the other 79 samples were
  the idle deadline watchdog. No sample errors; not a whole-cycle time share.
- At 20:59:56, 21:01:02 and 21:02:55, the same worker was in Codex source
  discovery (path resolution or source-file parsing), before extractor creation.
  These samples establish local work before model invocation, not the exact
  cause or timing breakdown of the previous killed cycle.
- Read-only namespace inventory: 6,826 receipts, 4,042 indexes, 434 observations,
  6,826 ledger objects, 1,993 Census runs; journals/staging both empty at sampling.
- Source confirms scanner and Runner each call full recovery; healthy completed
  manifests are read for validation and again for referenced IDs. Source adapter
  validates but does not use scan hints to narrow files and returns no next hint;
  it filters the seven-day window after source parsing. Full Runner snapshots and
  Census validation add more history-sized work.
- Isolated synthetic reproduction (10 completed receipts, no production data or
  model call): 50 JSON reads across 30 unique paths: receipts 10, indexes 20,
  observations 20; recovery report entirely zero. Raw output `a67f8e`.
- Hypothesis: repeated history-sized local I/O leaves too little margin under
  the existing cycle deadline. It is an evidenced bottleneck, not proof that
  every timeout has the same cause or that a particular model is slow.
- Next decision requested: define a bounded incremental hot path with a separate
  full-integrity audit, preserving send-time exclusion/forget/source validation.
  Do not implement a fourth unmeasured local speed tweak, skip validations,
  delete history, extend timeouts or add a database without approved scope.
- User approved defining the minimal incremental-processing plus independent
  full-audit boundary before implementation. See
  [boundary design](../../docs/superpowers/specs/2026-10-03-agc-incremental-capture-design.md).
  The proposed 24-hour audit-validity policy still needs a decision; no new
  production logic, configuration or schedule has been enabled.

## 2026-10-03 delivery closeout

- flow_id: agc-capture-reliability-closeout
- development: implemented and installed; ten changed runtime modules match
  deployed artifact `51e474b1ae39db746d3f00f29584dd7d204c7e3f900bb4f5d3e7ba3c779c1476`.
- Changes: system-proxy fallback, worker-owned deadline, bounded scanner
  registration/candidate selection, manifest read-ahead, identifier fast path,
  safe probe diagnostics and one bounded empty-probe timeout retry; pending
  review batches advance selection without accepting any memory or outcome.
- testing: passed-agent-local, 210 focused tests in 92.13 seconds, exit 0,
  raw command result `da3a2a` on 2026-10-03. Suites: probe diagnostics/retry,
  review pending/notification, background candidates, cycle deadline,
  identifier/path cost, snapshot read-ahead, extractor, manual Runner, CLI,
  Capture Trace and Skill adapter. No full-suite or CI-backed claim.
- Cross-regression: another 206 tests passed in 91.76 seconds, exit 0,
  raw output `f1cef9`: scanner/store/Census/Forget/backup/read service plus
  Metrics research access and Forget integration. One expected duplicate-ZIP
  warning comes from the adversarial archive fixture. Total selected: 416 passed.
- test integrity: production and tests changed together. New tests retain
  real filesystem/lock/child-process behavior; extractor/provider boundaries
  use fake children. Updated failure-code expectations reflect the new safe
  diagnostics; zero-proposal expectations reflect explicit human approval.
  No assertion was removed to conceal a production failure.
- production: consecutive scheduled cycles completed, including mixed results;
  visible backlog fell from 429 at 12:21 to 295 at 20:21 Asia/Shanghai.
  Item-level timeouts remain; period-wide coverage and speedup are not proven.
- report: human confirmed opening on 2026-10-03. Metadata calculation and
  re-render checks are retained; no real Judge or task-benefit score claimed.
- review: live status after notice repair is healthy, 396 unreviewed =
  20 pending confirmation + 376 undispatched; cooldown retained.
- model: local Capture configured for `gpt-6.1-sol` at explicit user request;
  actual automatic-cycle validation is pending. Independent review unchanged.
- latest production gate: the 20:26 local cycle after the model switch reached
  its 25-minute worker deadline; at 20:52 its verified process tree was absent
  and Scheduler returned 124. No new terminal Trace or completed receipts were
  observed for this cycle. Sampled process metadata did not establish a model
  invocation, so this is not proof of model incompatibility or model latency.
  New-model acceptance failed to complete; stage-level diagnosis remains open.
  The scheduler remains enabled; no duplicate/manual cycle or timeout increase.
- archive: code/tests/docs delivered in `069a200`, remote main SHA verified;
  runtime acceptance is partial. See [handoff](../handoff/agc-metrics-upgrade-v1-handoff.md).
- residual risks: item timeouts, long cycles, real Eval/preflight acceptance
  and evidence-backed task benefit remain open; not self-accepted limitations.

## 2026-10-02 bounded closeout investigation

- Scope confirmed by user: restore stable automatic Capture, remove pending-preview queue-head blocking without auto disposition, and accept a minimal real-metadata HTML report. No Judge invocation, formal memory promotion or Git push.
- Installed runtime remains 11ad963 / version 0.4.5 with gpt-6-sol. Last 24h snapshot showed 43 visible roots: 36 failed (35 extractor unavailable, one busy), seven completed; completed roots may include failed items. This is not full scheduler coverage or a quality metric.
- Current fixed empty-content probes succeeded in 13.38 and 24.51 seconds. Historical failures collapse resolver/probe causes to one code; intermittent timeout is a hypothesis, not yet proven. Do not replace the model or remove safety flags to make tests pass.
- Existing source changes are retained. Acceptance requires focused tests and consecutive scheduled-cycle evidence; diagnostic probes never load production Capsules.

### 2026-10-02 deployment checkpoint (23:56 Asia/Shanghai)

- Installed immutable runtime `ef30b50cdc6e80c81b05118a777b8eaa465a5ecbd12f2fb428204f897363dbba` (still 0.4.5), retaining Memory Root, Trace DB, gpt-6-sol and the existing automatic schedule. Source hashes and dependency consistency passed.
- Capability failures now retain allowlisted probe stage/reason in Trace without raw stdout/stderr; no timeout or retry policy change. Repeated current empty probes succeeded but do not prove the historical intermittent root cause fixed.
- 176 focused tests passed across probe/CLI/extractor, review/admin/skill and manual/background Runner coverage. No full-suite claim and no Git push.
- Previous runtime cycle ended at 23:35:57 with 10 attempted / 8 completed / 2 failed / 0 observations. The new runtime scheduled cycle began at 23:41:45; terminal result and consecutive-cycle acceptance remain pending.
- Review pending-confirmation bookkeeping deployed and one verified legacy preview batch migrated without disposition or formal-memory writes. Current App MCP is still the old process and requires restart verification. Real metadata HTML report computation passed; browser security prevented visual acceptance, which remains pending user inspection.

### 2026-10-03 first new-runtime automatic result

- The scheduled cycle started at 23:41:45 and recorded its terminal Trace at 23:59:34 local: 10 attempted, 8 completed, 2 failed, 2 observations, backlog 452, silent loss 0. This is one mixed-result cycle, not sustained recovery.
- Both retryable receipts report `extractor_process/process_timeout`; this item-level diagnosis does not explain historical capability-probe failures. No probe failure was reproduced during this turn.
- One non-persisted synthetic extraction with three fixed English preferences and a 90-second test ceiling succeeded in 21.19 seconds. Production timeouts remain unchanged because this did not reproduce a valid response exceeding 30 seconds.
- Still open: reproduce/resolve intermittent capability failure, verify consecutive scheduled cycles, restart App MCP and verify queue selection, and user-local HTML visual acceptance. The three-item goal is not complete.

### 2026-10-03 restarted App and deadline evidence

- After user restart, actual App MCP returned accepted/healthy pending-queue fields: 395 unreviewed = 10 pending confirmation + 385 undispatched, selecting the expected next digest `ca04668aaad69df2ce68fd93d067fb216127cd59ff1e779dd150750fd70a336e`. Formal-memory overview remains 37. App-side queue selection acceptance is now complete.
- The 09:23 local scheduled worker (46692) remained live until its 25-minute deadline and exited 124. No terminal Trace was emitted. A separate fixed empty probe succeeded in 18.32 seconds, but that alone does not prove the worker's probe outcome.
- Two nonblocking, no-locals stack samples at 09:45:41 and 09:46:01 respectively showed `recover_transactions -> _manifest_valid -> _read_manifest` and subsequent `read_snapshot -> _read_manifest`, both after the Runner's successful capability check. Thus this cycle's demonstrated blocker was pre-extraction local full-store I/O, distinct from historical unavailable probes.
- Minimal scoped optimization: only the background Runner's initial/post-recovery/final snapshots now request the existing bounded 4-worker reader. Manual backfill remains serial; recovery, locks, manifest/receipt/ledger validation, data schemas and timeout values are unchanged.
- New RED: background snapshot calls were `[1,1,1]` where 4 workers are required; manual mode passed. GREEN: 46 tests passed across manual/background Runner and snapshot read-ahead/corruption equivalence. Independent read-only review found no new concurrency blocker; no claim yet of production deadline recovery.
- Installed `6754f017bda615158566e0c5feaca453be49327b0779621fa7d24f6326992dc9` at 09:54. Byte comparison against prior deployment shows only `agc_runtime/capture_runner.py` changed; Trace and contracts package contents are identical. Source hash equality and pip check passed; existing Capture launcher now selects the new immutable runtime. Automatic-cycle result remains pending.

- bug_id: capture-system-proxy-timeout-20260923
- status: extractor fixed and installed; full automatic cycle blocked by separate performance/containment issue
- expected: Scheduled Capture uses the configured Codex App executable and `gpt-5.6-sol` through the host's enabled system proxy without sending raw Sessions.
- symptom: Scheduled `cycle` exited 1, with Trace `capture_extractor_unavailable`; Runner backlog was 2,123 on 2026-09-23.
- evidence: executable resolution and required CLI flags passed; an empty-drafts probe without proxy timed out at 30 and 60 seconds, including `Reconnecting... (request timed out)`. Process proxy variables were absent while the Windows user proxy was enabled and its local endpoint reachable. A temporary process-only proxy injection made the same probe succeed in 16.1 seconds.
- root cause: `CodexExtractor._environment()` passed explicit proxy variables but did not inherit the Windows system proxy, while `--ignore-user-config` suppressed the Codex App's proxy setting.
- active scope: `agc_runtime/codex_extractor.py`, `tests/test_capture_extractor.py`; preserve all other dirty changes and production memory/Trace data.
- fix: when no explicit HTTP(S) proxy environment is set on Windows, pass the enabled system proxy to the extractor child; explicit variables retain precedence.
- regression: new inheritance test failed on the prior code (`KeyError: HTTP_PROXY`), then 55 extractor tests and 37 Capture CLI/Codex App tests passed. A source-code probe without manual proxy injection succeeded in 15.2 seconds, with model `gpt-5.6-sol`.
- installation: existing rollback-capable installer published immutable Runtime `96156ddb8b940e5761449429c45746749cc74560d06a04e151391c831536cb80`; installed extractor hash matches source, `pip check` passed, existing Memory Root and Trace DB retained. Installed-package empty probe succeeded in 14.2 seconds. First scheduled cycle launched from the new executable at 2026-09-23 14:41 local.
- production observation: a synthetic, non-persisted Capsule extraction succeeded in 28.2 seconds with one draft and usage. The first scheduled production `cycle --max-items 10` ran past its 30-minute Task Scheduler limit before reaching a model subprocess; the Scheduler returned to Ready while the same worker remained alive with both locks. Thus the system-proxy fix is validated at the extractor boundary, not as a completed automatic cycle.
- containment: administrator confirmation disabled the exact scheduled task. With no model child, journal or staging files, the verified expired worker PID 60952 was stopped; AGC's native same-host dead-PID lock recovery acquired/released both locks. No manual lock deletion. Final read-only status: no Capture processes/locks/quarantines, 37 formal memories, 5,746 known/5,746 accounted/zero silent loss, Runner complete 3,607 and backlog 2,139.
- authorization boundary: a proposed production `run --max-items 1` was rejected before execution by auto-review because the precise Capsule content had not been newly authorized for external model transmission. Do not bypass via another entry point. Scheduler remains disabled pending user authorization and separate performance remediation.
- remaining verification: obtain exact consent for at most one safe Capsule production test; diagnose and fix the >30-minute scan/snapshot and orphan-on-timeout behavior; only then restore the task and observe a completed scheduled cycle and Trace result. No formal memory write or historical Capsule extraction occurred during this fix.

## 2026-09-26 recovery work

- User requested fixing automatic Capture and switching to `gpt-6-sol`. Production config was backed up before changing only the extractor model; review automation model was also changed, retaining its schedule, deduplication and no-auto-promotion instructions.
- Empty `gpt-6-sol` capability probe passed in 14.66 seconds; this is connectivity evidence, not production extraction evidence.
- Live scanner stack samples showed repeated filesystem resolution and per-receipt layout/lock overhead. Runner additionally loaded every pending Capsule before applying max-items. Fixed redundant leaf-parent resolution, bounded registration batches to 32 receipts, and background candidate lookahead to 32-128 receipts. Explicit manual backfill ranking is unchanged.
- Added a Windows worker-owned Job deadline at 25 minutes, earlier than the scheduler's 30-minute launcher timeout. Deadline tests verify worker and child termination; this does not claim immediate cleanup after an arbitrary early launcher stop.
- Regression: 139 targeted tests passed. A batch-lock conflict regression was caught and fixed before installation. `git diff --check` passed. Source scan completed with 6,161 known/accounted keys, zero silent loss and zero source quarantine.
- Installed immutable runtime `11ad963d4c84ed49a6c223c69138e8b7ef5589fd000ac611585e6cbbe07d659b`, retaining V2 root and Trace DB. Production max-items 1 acceptance was rejected before execution by auto-review: repair/model-change authorization is insufficient for transmitting a production Capsule to the new model. No workaround attempted; scheduler remains disabled pending explicit external-data authorization and successful acceptance. No formal memory promotion.

### Authorized production acceptance

- User subsequently explicitly authorized sending at most one safe production Capsule to OpenAI `gpt-6-sol`, then restoring ongoing automatic processing after success, without formal-memory promotion.
- Installed launcher `cycle --once --max-items 1` exited 0: accepted, attempted/completed/extractor calls each 1, failed 0, observations 0, trace_status recorded, no budget deferral or contention. Charged/reserved accounting was 6,000 tokens (not a claim of measured model consumption). Scan: 6,173 known/accounted, zero silent loss/quarantine; backlog reported 813.
- Full cycle took approximately 13 minutes, with Runner reporting 279,416 ms separately. Functional recovery is verified; full-cycle performance is still substantial and sustained scheduled throughput remains to be observed.
- Restoring the exact task initially returned Windows access denied. An explicit UAC elevation ran only Enable-ScheduledTask for AgentGlobalContext-Capture-25e9201ae2f5 and exited 0. Existing 15-minute schedule retained. No formal-memory write and no Git push.

## 2026-10-03 precise probe timeout reproduction

- The 09:56 scheduled cycle ended at 10:12 local with `probe_smoke/process_timeout` in Trace and Scheduler exit 1. This is a reproduced 30-second empty probe timeout, not proof of a particular network cause. Subsequent empty controls succeeded in 17.96, 10.96 and 11.94 seconds; increasing the normal timeout is not supported by these controls.
- Narrow fix: retry only a pure content-free smoke process timeout once, retaining the per-attempt bound and buffer clearing. Version/help, invalid output/auth, spawn/output-limit/nonzero failures and real Capsule extraction do not gain retries. A second timeout still fails closed.
- Regression: new retry tests RED 2 failed / 6 passed; after implementation, 104 focused probe, extractor and CLI tests passed. Consecutive production-cycle verification remains pending; synthetic tests do not prove sustained automatic recovery.
