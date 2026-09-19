# Metrics preflight snapshot I/O

- flow_id: 2026-09-12-metrics-preflight-snapshot-io
- status: executing
- severity: real-case acceptance blocked
- scope: metrics access and opt-in Capture snapshot I/O; no production rollout

## Evidence and expectation

Two explicitly selected first turns exceed the test's 30-second ceiling. Diagnostic
3178ae stops in the first CaptureResearchAccess.check, read_snapshot receipt read.
The prior test run has 105 passing synthetic cases but zero ready real cases.
Metadata count: 4141 receipts, 2975 indexes, 263 observations. No data corruption
or shared cause with notification failures is established.

Expected: reduce serial small-file I/O without deleting any integrity, exclusion,
quarantine, conflict or forget check. The selected source and model policy remain
unchanged. Thirty seconds is a test ceiling, not an existing product SLA.

## Fix plan and boundaries

Add bounded, opt-in JSON read-ahead inside the existing Capture lock. Keep serial
snapshot reading as the default, preserve iteration/validation/error ordering, and
do not cache approval or documents across calls. Metrics alone opts into read-ahead.
No replacement source gate or selective/global-integrity relaxation. Benchmark and
retest the same cases; report any remaining Census/validation cost honestly.

Active: snapshot I/O helper, read_snapshot plumbing, metrics_research_access and
focused tests. Read-only: selected production sources and Capture state. Excluded:
Recall behavior, Runner configuration, Judge calls, installation, commit/push.

## Verification plan

Compare serial/read-ahead snapshots on healthy and corrupt fixtures; preserve
unrelated corruption denial and live forget/exclusion checks. Run focused tests,
then the same real-case preflight without printing or persisting source content.

## Flow Record

| Step | Status | Evidence |
|---|---|---|
| source | done | two real preflight timeouts and diagnostic 3178ae |
| design | done | preserve full checks; bounded parallel I/O only |
| plan | done | user approved continuing bounded repair |
| development | partial | bounded parallel I/O implemented; no production rollout |
| testing | partial | 76 focused tests pass; both real cases still exceed 30 seconds |
| archive | open | performance issue and overall metrics acceptance remain open |

## 2026-09-12 bounded-fix verification

- RED: 6 new tests failed before implementation (a7abbe).
- Initial GREEN: 28 passed (f8b456). Extended suite: 76 passed in 43.42s
  (28df07), including snapshot corruption and Capture forget coverage.
- Independent read-only review found no confirmed correctness/security regression.
  Non-blocking gap: early-exit joining of outstanding workers is established by
  context-manager order but lacks a dedicated regression test.
- Same two native first-turn digests retested without model calls or source export:
  both remain unready, at 30.072s and 30.178s respectively. First timeout is now
  ledger read-ahead; second is Census run-manifest filesystem validation. Neither
  completed its first live access check. These capped runs do not establish a
  reliable overall speedup.
- Metadata-only results: D:/tmp_test/agc-metrics-preflight-retest-20260912-c820/.
  Original baseline outputs were preserved. Process exited 0 after recording
  timeouts; that exit code does not mean real-case acceptance passed. Capture
  writer lock was absent at the post-run check.

The bounded I/O change alone is insufficient. Next investigation should quantify
the remaining full-snapshot/Census work before changing architecture. Do not
silently bypass integrity checks, cache access grants, expand into Recall tuning,
or call Judge to compensate for unavailable evidence.
