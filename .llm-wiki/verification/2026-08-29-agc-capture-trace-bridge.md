# Verification: AGC Capture Trace Bridge

## Result

The optional Capture-to-Trace bridge is implemented and verified locally. It
has not been installed into the production AGC Runtime and no scheduled task,
production configuration, version, release, or remote repository was changed.

## Implementation Evidence

- Design commit: `2d590aa`
- Plan commit: `d18a298`
- Implementation commit: `6780ffa`
- New boundary: `agc_runtime/capture_trace.py`
- Integration boundary: `agc_runtime/capture_cli.py::_run_runner`
- Optional dependency: `agent-trace-runtime>=0.1,<0.2`

## TDD Evidence

RED was observed for:

- missing `agc_runtime.capture_trace`;
- absent CLI `trace_status` on successful and failed Runner responses;
- absent `trace` optional dependency;
- the real Trace clock rejecting the Runner ISO timestamp string;
- malformed `status_deltas` escaping the failure-open boundary.

The final focused collection contains 32 Capture Trace and Capture CLI tests.
They pass after the implementation and the two regression fixes.

## Repository Regression Evidence

The complete collection contains 1366 tests. Two full runs each completed with
1365 passes and one environment-only failure:

1. The first used a pytest base path too long for the dedicated Windows
   long-path identity test. That exact test passed when rerun under a short
   operator-designated test root.
2. The second used the short root; its only failure was an SSL EOF while the
   installer integration test fetched a build dependency. That exact installer
   test passed on immediate isolated rerun in 149.27 seconds.

Together, the full runs and exact isolated reruns cover all 1366 collected
tests with no remaining product failure. One pre-existing duplicate ZIP member
warning remains unrelated to this change.

## Static And Packaging Evidence

- `git diff --check`: passed before the implementation commit.
- Ruff: both new files pass without ignored findings.
- Existing modified files pass when their pre-existing baseline findings are
  excluded; no new finding remains.
- Final wheel build: `agent-global-context-runtime` 0.4.2 succeeded.
- Package metadata keeps Trace optional and bounded to Runtime 0.1.x.

## Cross-Repository Smoke

An isolated environment installed locally built wheels for AGC 0.4.2, Trace
Runtime 0.1.0, and Runtime Contracts 0.1.0.

The significant Capture CLI boundary smoke produced:

- Capture exit code `0`;
- `trace_status: recorded`;
- lifecycle `trace.root.started` then `trace.root.completed`;
- Snapshot status `completed`;
- root name `agc.capture.cycle`, kind `workflow`;
- terminal payload restricted to the documented aggregate allowlist.

The unavailable-store smoke produced Capture exit code `0` and
`trace_status: unavailable`, proving Trace remained failure-open.

## Safety Review

The persisted events contained no Prompt, response, task/session/project ID,
source path, Capsule, observation statement, memory content, Extractor I/O,
raw exception, credential, or environment content. Empty successful cycles are
suppressed before Trace Runtime is imported.

## Doctor

The new design is registered through the Change Brief and the new committed
artifacts contain no local-only path. Repository-wide Doctor still reports
pre-existing orphan-design warnings and local-path findings in older AGC wiki
files; those were not expanded into this scoped feature.
