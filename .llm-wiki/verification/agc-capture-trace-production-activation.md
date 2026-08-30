# Verification: AGC Capture Trace Production Activation

## Result

AGC Runtime 0.4.3 source is locally ready for optional Capture tracing. The
installer can build an immutable `mcp+trace` deployment from the local Trace
Runtime repository and binds `AGENT_TRACE_DB` only in `agc-capture.cmd`.
Production remains on 0.4.2; no scheduled task, live configuration, installed
Runtime, or GitHub remote was changed.

## Contract And TDD Evidence

- Default installs remain `mcp` only and retain the one-line Capture launcher.
- Trace installs require `-EnableCaptureTrace -TraceRuntimeRoot <root>`.
- Invalid option combinations and drive-relative database paths fail before
  active mutation.
- The deployment key binds the install profile, Python identity, AGC source,
  and actual local Contracts and Trace package inputs.
- Trace activation changes only the Capture launcher; MCP, Hook, configuration,
  and scheduled-task XML remain unchanged.

RED failures were observed before each implementation boundary: unsupported
parameters, missing launcher environment, unchanged deployment identity, the
real Contracts package layout, and acceptance of `D:trace.sqlite3`. Focused
GREEN results included 6 core activation tests in 113.55 seconds, the immutable
profile test in 103.69 seconds, and the drive-relative regression in 1.22
seconds. The complete installer collection passed 48 tests in 353.04 seconds
before the final validation-only regression, which then passed independently.

## Repository Regression Evidence

The full AGC collection completed with 1370 passes and one stale test fixture
that still expected Runtime 0.4.2. After updating only that version fixture, its
exact test passed. Later installer changes were covered by focused RED/GREEN
tests, the six-test core gate, and the real cross-repository smoke below.

There was no single final rerun of the entire 1371-test collection after the
last small path-validation patch. This record therefore claims
`passed-agent-local`, not a production or published release gate.

## Static And Packaging Evidence

- `git diff --check`: passed; only PowerShell LF-to-CRLF notices were emitted.
- PowerShell parser: `scripts/install-local.ps1` parsed successfully.
- Strict UTF-8 byte decoding passed for all modified Python files.
- Final fast gate: 10 activation/path/version tests passed with 67 deselected in
  8.17 seconds under `D:\tmp_test\agc-043-final-fast`.
- Ruff through UTF-8 stdin passed for the modified version/contract files;
  `tests/test_capture_activation.py` retains a pre-existing unused `Path`
  import outside this change. Direct Ruff file reads fail with E902 on this
  protected workspace, including untouched files.
- A final build from the current source succeeded and produced
  `agent_global_context_runtime-0.4.3.tar.gz` and
  `agent_global_context_runtime-0.4.3-py3-none-any.whl` under
  `D:\tmp_test\agc-043-final-dist`.

## Cross-Repository Smoke

An isolated install under `D:\tmp_test\agc-043-real-smoke-2` used the actual
`D:\tmp\github\agent-runtime-modules` source and installed AGC 0.4.3,
Runtime Contracts 0.1.0, and Trace Runtime 0.1.0 into a distinct immutable
environment.

A controlled Capture-disabled cycle returned its expected business failure
while reporting `trace_status: recorded`. `agent-trace doctor` passed, and the
Snapshot contained one failed `agc.capture.cycle` root with only
`trace.root.started` and `trace.root.failed`. Its payload contained the
sanitized `capture_disabled` code and message, with no memory, Session, Prompt,
response, Capsule, observation, source-path, or Extractor content.

## Test Integrity

The installer tests invoke the real PowerShell script in subprocesses, inspect
exact launcher bytes and immutable deployment paths, and verify zero mutation
for rejected options. Synthetic local packages mirror the real repository
layout; the isolated smoke additionally exercises the actual Trace repository.
No mock substitutes for installer behavior or Trace persistence.

## Remaining Human Gate

Production installation, temporary scheduler quiescence, live Capture-cycle
inspection, and GitHub push remain separately authorized actions.
