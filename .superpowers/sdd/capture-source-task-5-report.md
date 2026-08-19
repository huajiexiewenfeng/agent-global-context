# Capture Source Census Task 5 Report

## Scope

Implemented explicit one-shot Census operations and truthful Scanner status
without enabling semantic Capture.

The public command is:

```text
agc-capture probe --root <memory-root>
agc-capture scan --root <memory-root> --mode census|incremental --once
agc-capture cycle --root <memory-root> --once
```

Every command writes exactly one schema-v2 `agc.capture` JSON envelope to
stdout. Recognized failures use fixed content-free codes and nonzero exit
status. The parser has no source-root, exclusion, model, daemon, Capsule,
Observation, Runner, or scheduler override surface.

Production scope:

- `agc_runtime/capture_cli.py`: deferred one-shot command and safe envelopes.
- `agc_runtime/capture_status_service.py`: durable Scanner diagnostics and a
  shared internal host-binding overlay.
- `agc_runtime/capture_scanner.py`: validated task-ID policy exclusions and a
  `force_full` hint boundary for explicit Census runs.
- `agc_runtime/runtime_config.py`: inert disabled-source shape validation that
  defers canonical filesystem identity to activation.
- `agc_runtime/mcp_server.py`: reuse the shared status binding only inside the
  already host-bound MCP route.
- `pyproject.toml`: `agc-capture = "agc_runtime.capture_cli:main"`.

Tests are in `tests/test_capture_cli.py`, `tests/test_capture_status.py`,
`tests/test_capture_scanner.py`, `tests/test_cli_contract.py`,
`tests/test_mcp_server.py`, and `tests/test_runtime_config.py`.

No live Codex profile or installed Memory Root was read, scanned, or changed.
All behavioral tests used synthetic temporary Memory Roots and source roots.

## Contract and Boundary Evidence

- `probe` works while disabled and does not create the Memory Root or Capture
  layout. Disabled configurations may retain absolute source declarations, but
  validation does not import Source/Scanner/adapter modules, resolve or hash a
  source root, or touch its filesystem.
- `scan` and `cycle` instantiate `CodexSourceAdapter` only after strict runtime
  config validation and the enabled + scanner-only + unpaused + configured
  source gates pass. Runner mode is refused.
- CLI arguments cannot supply a source root, exclusion, model, daemon, Capsule,
  or other semantic/hosting input. Source scope comes only from validated
  `capture.sources`; the Memory Root comes only from the exact CLI `--root`.
- Explicit Census mode forces a hintless seven-day discovery without deleting
  or overwriting durable scan state. Incremental mode and cycle use normal
  durable hint reconciliation. Each source is discovered once per run.
- Validated `capture.exclude.task_ids` are matched after discovery and before
  Receipt registration, including replay of durable Census truth. They create
  truthful `excluded` Receipt/Ledger state with
  `configured_task_exclusion`. There is no CLI injection surface.
- `project_ids` remain explicitly `not_assessed`: `RevisionRef` has no project
  identity at this plan boundary, so the implementation does not guess.
- Status distinguishes `not_assessed`, `absent`, `busy`, `corrupt`,
  `degraded`, and `ready` with fixed machine codes. It reports latest valid
  frozen-run/key counts, known/accounted/pending/silent-loss counts, dirty
  marker count, scan-state binding/version/time, exclusions, and operation
  eligibility without paths, locators, task titles, prompts, source content,
  or exception messages.
- An initialized layout with no Census or scan state is `absent` with Source
  Health `not_assessed`; it is never guessed healthy or ready.
- Direct admin status remains `memory_root.assessment=not_assessed` and scanner
  operation-ineligible. The MCP route proves only its constructor-bound root,
  ignores a request-supplied rogue root, and recomputes eligibility through the
  shared binding helper. The server still has exactly three tools.
- Busy and integrity-failed probe/scan operations exit nonzero. Probe may
  include the already content-safe status document in its failed envelope;
  raw validation and filesystem errors are never emitted.
- Sentinel source text has zero hits in command responses and zero persistence
  under the Memory Root. No model/provider, subprocess, network, extractor,
  Task Capsule, Observation, Candidate, formal-memory writer, daemon, Hook
  installation, or Runner path was added or invoked.

## TDD Evidence

The initial production-clean RED command was:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest `
  tests/test_capture_cli.py tests/test_capture_status.py `
  tests/test_cli_contract.py `
  tests/test_capture_scanner.py::test_configured_task_id_exclusion_applies_after_one_discovery_and_on_replay `
  -q -p no:cacheprovider `
  --basetemp 'D:\tmp\agc-capture-source-red-5'
```

Result: `17 failed, 7 passed`. The intended failures were the missing
`agc_runtime.capture_cli`, missing `agc-capture` entry point, absent Scanner
status diagnostics, and missing `excluded_task_ids` Scanner policy input.

Additional real RED cycles were recorded before their production changes:

- Busy/corrupt probe and MCP host-binding consistency: `3 failed`.
- Census `force_full` with durable hint preservation: `1 failed` because the
  argument did not exist.
- Disabled-but-configured direct status/probe import and filesystem boundary:
  `2 failed` on the deferred `capture_source` import.
- Initialized-but-unassessed Scanner state and lexical duplicate-source shape:
  `2 failed` (`ready` was guessed and the duplicate was accepted).

Each exact node was rerun GREEN after its minimal implementation. The combined
final focused run is recorded below.

## Verification Evidence

Focused Task 5, full Scanner, and runtime-config contracts:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest `
  tests/test_capture_cli.py tests/test_capture_status.py `
  tests/test_cli_contract.py tests/test_mcp_server.py `
  tests/test_capture_scanner.py tests/test_runtime_config.py `
  -q -p no:cacheprovider `
  --basetemp 'D:\tmp\agc-capture-source-focused-final-5'
```

Result: `72 passed in 35.69s`.

Task 4 Scanner/Ledger and disabled Core regression:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest `
  tests/test_capture_scanner.py tests/test_capture_ledger.py `
  tests/test_capture_core_end_to_end.py `
  -q -p no:cacheprovider `
  --basetemp 'D:\tmp\agc-capture-source-task4-core-5'
```

Result: `36 passed in 11.87s`.

Adjacent Capture/source/admin/runtime regression:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest `
  tests/test_capture_cli.py tests/test_capture_status.py `
  tests/test_cli_contract.py tests/test_mcp_server.py `
  tests/test_capture_core_end_to_end.py tests/test_capture_ledger.py `
  tests/test_capture_scanner.py tests/test_capture_transaction.py `
  tests/test_capture_store.py tests/test_capture_read_service.py `
  tests/test_capture_source_contracts.py tests/test_codex_source_adapter.py `
  tests/test_capture_hook.py tests/test_capture_backup_restore.py `
  tests/test_capture_contracts.py tests/test_capture_paths.py `
  tests/test_admin_service.py tests/test_runtime_config.py `
  -q -p no:cacheprovider `
  --basetemp 'D:\tmp\agc-capture-source-adjacent-final-5'
```

Result: `391 passed, 1 expected warning in 82.91s`. The warning is the existing
duplicate-name ZIP adversarial fixture.

Natural-order full repository suite:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest -q -p no:cacheprovider `
  --basetemp 'D:\tmp\agc-capture-source-full-5'
```

Result: `629 passed, 1 expected warning in 289.73s`. The warning is the same
duplicate-name ZIP fixture.

Offline wheel build:

```powershell
& '.\.venv\Scripts\python.exe' -m build --wheel --no-isolation `
  --outdir 'D:\tmp\agc-capture-source-wheel-5'
```

Result: `Successfully built agent_global_context_runtime-0.2.0-py3-none-any.whl`.

The wheel was installed with `pip --no-deps --target` into an isolated
`D:\tmp` directory. `importlib.metadata` found
`agc-capture = agc_runtime.capture_cli:main`; loading that installed entry
point and probing an absent synthetic root returned exit `0` and exactly one
accepted JSON object without creating the root. The loaded module path was
inside the isolated install target. The installed MCP server listed exactly:

```text
agc.admin
agc.read
agc.write
```

Final static gate compiled every changed Python file, ran `git diff --check`,
strictly decoded all 13 changed files as UTF-8 while rejecting a leading BOM,
and searched `capture_cli.py` for semantic/external imports and calls. Result:

```text
py_compile=clean
git_diff_check=clean
strict_utf8_no_bom=13_files
capture_cli_forbidden_boundary_hits=0
```

## Failure Classification

The repository venv launcher was initially blocked by the sandbox because its
base interpreter is under AppData. The approved rerun produced the real RED;
this was an environment-only launcher failure.

The first broad adjacent run reported `386 passed, 1 failed`. The existing
disabled-Core test failed its `sys.modules` precondition because newly added
enabled-status/MCP tests had imported deferred Source contracts earlier in the
custom module order. No disabled operation imported them. Module-scoped test
cleanup was added, the exact mixed order passed `18`, and the fresh adjacent
run passed all `391`; this was test-order pollution, not a product failure.

The first static forbidden-boundary expression matched the required fixed
machine code `capture_runner_unsupported`; it found no import or invocation.
The check was narrowed from a bare lexical module-name fragment to actual
semantic/external import and call forms, then the complete static gate passed.

## Review Remediation (2026-08-19)

The Task 5 review was resolved without widening the activation surface:

- Disabled source-root validation now applies ASCII-only case folding for its
  lexical duplicate check. It still rejects ASCII case aliases while keeping
  distinct `straße`/`strasse` and composed/decomposed Unicode names distinct.
  It performs no resolve, realpath, hashing, enumeration, or deferred Source,
  Scanner, or adapter import. Physical alias and junction identity remains the
  existing Task 1 `canonical_source_root` / `source_root_id_for` contract and
  runs only after explicit activation.
- `CaptureStore.read_snapshot` now validates the Ledger namespace and the
  Receipt/Ledger graph under the same Capture read lock. Fixed content-safe
  diagnostics cover malformed schema/JSON or filenames, missing Ledger,
  orphan Ledger references, and mismatched key, status, discovery time, or
  processed time. A matching `discovered` Receipt/Ledger pair is legitimate
  durable pending work and remains healthy.
- Scanner status now consumes locked snapshot data for frozen runs, scan
  states, dirty markers, quarantines, and conflict identities. Valid metrics
  and Source Health are filtered to the currently configured canonical Codex
  bindings. Thus a configuration switch from source A to source B cannot make
  B ready, degraded, dirty, or scanned based on A's durable state. Malformed
  artifacts that cannot be safely attributed still fail closed globally.
- Corruption uses the fixed public code `scanner_corrupt`; probe exits nonzero,
  writes exactly one JSON object to stdout, keeps stderr controlled, and never
  exposes a path, source content, filename, or raw exception.
- The existing wheel isolation test now imports `capture_cli` from the
  installed target, resolves the installed `agc-capture` console entry point
  through wheel metadata, executes it outside the repository, and verifies one
  accepted JSON object plus installed-module provenance.

Review RED was recorded against `6183cb8` with synthetic roots only:

```text
12 failed, 4 passed
```

The failures reproduced Unicode sharp-s collapse, absent Ledger namespace and
graph validation, the old scanner corruption code, corrupt/missing Ledger
probe acceptance, and source A metrics leaking into source B. The NFC and
junction/canonical-alias controls and legitimate discovered graph were already
green. After the minimum production changes, the same review set passed
`16 passed`.

Final focused review plus Task 4 Scanner, MCP three-tool, installed-wheel, and
canonical identity contracts:

```text
104 passed in 48.43s
```

A final lock-consistency RED then proved status was performing a second
Receipt/Ledger accounting read after releasing the snapshot lock (`1 failed`).
Accounting keys were moved into the same validated snapshot; the status,
store, read-service, disabled-core, and Scanner regression passed
`80 passed in 27.91s`.

Final natural-order full repository suite in the repository's Python 3.13
environment with a fresh short synthetic basetemp:

```text
644 passed, 1 expected warning in 310.83s
```

The warning remains the existing duplicate-name ZIP adversarial fixture. An
earlier full attempt used a Python 3.12 host with Python 3.13 native MCP
packages and was discarded as an interpreter mismatch; the proper repository
environment run above is authoritative. No live Codex profile was read or
scanned during any review test.
