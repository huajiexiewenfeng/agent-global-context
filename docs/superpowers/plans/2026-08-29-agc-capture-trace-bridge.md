# AGC Capture Trace Bridge Implementation Plan

> **Execution:** Follow this plan task by task with test-driven development. Keep all temporary environments and databases under `D:\tmp_test`.

**Goal:** Add an optional, metadata-only, failure-open Trace Runtime bridge around scheduled AGC Capture Runner cycles.

**Architecture:** `agc_runtime.capture_cli._run_runner` remains the only integration boundary. A new `agc_runtime.capture_trace` module owns opt-in detection, metadata allowlisting, lazy Trace Runtime imports, lifecycle event emission, and failure suppression. Existing Capture business logic remains unaware of Trace.

**Tech Stack:** Python 3.10+, pytest, setuptools, optional `agent-trace-runtime` 0.1.x, SQLite-backed Trace Runtime.

---

## Task 1: Specify bridge behavior with failing unit tests

**Files:**
- Create: `tests/test_capture_trace.py`
- Test: `tests/test_capture_trace.py`

1. Add tests proving that absent `AGENT_TRACE_DB` returns `disabled` without importing Trace Runtime.
2. Add tests proving that an empty successful result returns `suppressed` without importing or persisting anything.
3. Add a fake Trace backend and tests for significant success and sanitized failure lifecycle pairs.
4. Assert the fixed principal, root name, workflow span kind, shared identifiers, timestamps, and exact terminal metadata allowlist.
5. Add tests proving forbidden content and unexpected mapping keys are not persisted.
6. Add tests proving import, validation, and append failures return `unavailable` and never raise.
7. Run the focused test file and observe RED because `agc_runtime.capture_trace` does not exist.

## Task 2: Implement the minimal optional bridge

**Files:**
- Create: `agc_runtime/capture_trace.py`
- Test: `tests/test_capture_trace.py`

1. Define the four public statuses: `disabled`, `suppressed`, `recorded`, and `unavailable`.
2. Implement explicit `AGENT_TRACE_DB` detection without reading or exposing unrelated environment values.
3. Implement exact success/failure metadata allowlisting and the significant-cycle predicate.
4. Lazily import only the Trace Runtime public API after enablement and significance checks.
5. Emit one `trace.root.started` followed by one terminal root event using runtime source attribution and a fixed principal.
6. Catch every bridge exception internally and return `unavailable` without exception details.
7. Run the focused tests until GREEN, then run Ruff on the new module and test file.

## Task 3: Integrate the bridge at the Runner CLI boundary

**Files:**
- Modify: `agc_runtime/capture_cli.py`
- Modify: `tests/test_capture_cli.py`

1. Add failing tests for `run` and `runner-cycle` success responses carrying `trace_status`.
2. Add failing tests for sanitized Runner failures carrying `trace_status` without changing the original AGC error code, message, or exit code.
3. Capture one cycle start time before Runner work and pass only the stable action plus sanitized report/error data to the bridge.
4. Extend the local `_failed` helper only as needed to accept response data while preserving all existing call sites.
5. Ensure disabled, suppressed, recorded, and unavailable bridge results never alter Capture semantics.
6. Run focused CLI tests to GREEN, then run all Capture CLI and bridge tests together.

## Task 4: Declare optional packaging and document activation

**Files:**
- Modify: `pyproject.toml`
- Modify: `docs/capture-operations.md`
- Test: `tests/test_local_install.py` or create a focused packaging assertion if existing coverage is unsuitable

1. Add the optional extra `trace = ["agent-trace-runtime>=0.1,<0.2"]` without changing default dependencies or the AGC version.
2. Document that setting `AGENT_TRACE_DB` explicitly enables metadata-only Capture tracing when the optional package is installed.
3. Document empty-cycle suppression, content exclusions, failure-open behavior, and the four `trace_status` values.
4. Add or update a packaging assertion for the optional dependency declaration.
5. Run the packaging-focused tests and build a wheel into `D:\tmp_test`.

## Task 5: Verify both repositories with a controlled smoke

**Files:**
- Create only temporary artifacts under: `D:\tmp_test\agc-capture-trace-bridge`
- Modify no production configuration or scheduled task

1. Run the complete AGC pytest suite.
2. Run Ruff over all changed Python files and `git diff --check`.
3. Create an isolated virtual environment under `D:\tmp_test` and install the local Trace Runtime and AGC packages.
4. Run one controlled significant Capture cycle with a synthetic memory/source root and `AGENT_TRACE_DB` pointing under `D:\tmp_test`.
5. Inspect Trace Runtime events and Snapshot, proving one completed `agc.capture.cycle` root with only allowlisted metadata.
6. Run a controlled unavailable-store or missing-package case and prove the Capture result/exit code is unchanged.
7. Run LLM Wiki Doctor and separate new findings from pre-existing repository findings.

## Task 6: Close the development flow

**Files:**
- Modify: `.llm-wiki/requirements/agc-capture-trace-bridge.md`
- Create: `.llm-wiki/verification/2026-08-29-agc-capture-trace-bridge.md`
- Create: `.llm-wiki/handoff/2026-08-29-agc-capture-trace-bridge-handoff.md`

1. Record implementation commits and exact verification evidence.
2. Mark plan, development, testing, and archive steps complete only after fresh verification.
3. Run final `git diff --check`, focused tests, full tests, packaging checks, and status inspection.
4. Commit the verified implementation and project-finish artifacts on the current `main` branch.
5. Stop before production installation, scheduled-task mutation, version bump, release, or GitHub push; request separate user authorization for those actions.
