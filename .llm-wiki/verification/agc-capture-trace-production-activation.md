# Verification: AGC Capture Trace Production Activation

## Result

AGC Runtime 0.4.3 is installed in production with optional Capture tracing.
The installer built immutable `mcp+trace` deployment `13728135...eac8a` from
the local Trace Runtime repository and bound `AGENT_TRACE_DB` only in
`agc-capture.cmd`. The existing scheduled-task definition was retained and
restored after installation. GitHub had not yet been pushed when this evidence
was recorded.

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

## Production Activation Evidence

- The scheduled task was disabled through an explicitly elevated Windows
  command, and the already-running 0.4.2 cycle was allowed to finish naturally.
- The production install created immutable Runtime
  `137281353a90221c48b622263082148362948c3f15b66b12486b75a4288eac8a`
  and backup
  `20260830-093914-864-75e27278c79b4d5eae05c6aab7ecb59c`.
- Package metadata reports AGC 0.4.3, Trace Runtime 0.1.0, and Runtime Contracts
  0.1.0; `pip check` reports no broken requirements.
- MCP and Hook launchers contain only the new executable path. The Capture
  launcher alone contains
  `AGENT_TRACE_DB=C:\Users\admin\.agent-trace-runtime\trace.sqlite3`.
- The 32-file formal-memory tree remained byte-identical with aggregate SHA-256
  `971ab1e70ad62dd25e0e46cd339e25a2a8650a1ebcc894b6bb63d45cbd9f84d9`.
- A no-content, Capture-disabled synthetic root exercised the production
  launcher without calling a model or reading historical Sessions. It returned
  `trace_status: recorded`; Trace Doctor passed and Snapshot
  `trc_agc_03988cfa23ca42b79f02214cd889ac6d` contains exactly the sanitized
  `trace.root.started` and `trace.root.failed` events.
- Re-enabling the existing task immediately launched its missed 09:41 trigger
  through the new 0.4.3 Capture executable. It completed with Task Scheduler
  result `0` and Trace
  `trc_agc_33e59a8f25f44a65aea45da9a0e16e12`: exactly one started and one
  completed event, no Trace errors, 10 attempted items, 2 completed items,
  1 budget deferral, 7 item-level failures, 0 observations, and 0 silent loss.
  The terminal payload contains only aggregate counters and status deltas.

## Remaining Human Gate

The current Codex task still holds its pre-install MCP process; a Codex restart
is required before foreground Recall uses 0.4.3. The authorized GitHub push is
the final operation after this closure record.
