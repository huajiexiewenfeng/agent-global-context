# Capture Core Task 6 Report

## Status

`DONE_WITH_CONCERNS`

The disabled Capture Core release proof is implemented and all focused and
complete tests pass. No production behavior changed. The remaining concern is
an existing package-command mismatch: the brief requires `agc --version`, while
Runtime 0.2.0 implements `agc version`. The exact required spelling was run and
failed; the supported installed version action and every other package gate
passed.

## Scoped files

- Created `tests/test_capture_core_end_to_end.py`.
- Modified `tests/test_runtime_end_to_end.py`.
- Modified `.llm-wiki/requirements/agc-capture-coverage-mvp.md`.
- Modified `.llm-wiki/working-context/agc-capture-coverage-mvp.md`.
- Created this report.
- Production files changed: `0`.

## TDD RED

```powershell
& '.\.venv\Scripts\python.exe' -m pytest `
  tests/test_capture_core_end_to_end.py -q `
  --basetemp 'C:\tmp\agc-capture-core-e2e-red'
```

Exit `1`: `1 failed in 0.25s`. The deliberately incomplete scaffold failed at
`disabled Capture core E2E proof is not implemented`, proving the new release
proof did not exist before implementation.

## TDD GREEN and complete suite

```powershell
& '.\.venv\Scripts\python.exe' -m pytest `
  tests/test_capture_core_end_to_end.py tests/test_runtime_end_to_end.py -q `
  --basetemp 'C:\tmp\agc-capture-core-e2e-green'
```

Exit `0`: `6 passed in 8.81s`.

The repository venv lacks its declared setuptools backend. The final complete
command therefore used the Task 1 documented backend with the repository venv
first, preventing the bundled environment from shadowing the venv's compiled
dependencies:

```powershell
$env:PYTHONPATH='D:\tmp\github\agent-global-context\.venv\Lib\site-packages;C:\Users\admin\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\Lib\site-packages'
Remove-Item Env:PIP_NO_INDEX -ErrorAction SilentlyContinue
Remove-Item Env:PIP_NO_INPUT -ErrorAction SilentlyContinue
Remove-Item Env:PIP_DISABLE_PIP_VERSION_CHECK -ErrorAction SilentlyContinue
& '.\.venv\Scripts\python.exe' -m pytest -q `
  --basetemp 'C:\tmp\agc-capture-core-full-clean'
```

Exit `0`: `513 passed, 1 warning in 330.29s`. The warning is the expected
duplicate-name ZIP attack fixture.

An initial diagnostic ordering put the bundled backend first and inherited
offline pip flags. It exited `1` with `505 passed, 8 failed`: seven MCP imports
loaded a foreign pure-Python Pydantic ahead of the venv's compiled extension,
and one installer could not resolve its isolated setuptools requirement. No
product code was changed. The exact affected subset plus the wheel regression
passed `12 passed in 167.71s`, then the corrected complete command above passed.

## Package, install, and MCP evidence

A disposable source copy excluded `.git`, `.venv`, `build`, `dist`, egg-info,
pytest cache, and bytecode caches. With `PIP_NO_INDEX=1`, `PIP_NO_INPUT=1`, and
`PIP_DISABLE_PIP_VERSION_CHECK=1`, this command built the wheel:

```powershell
& '.\.venv\Scripts\python.exe' -m build --wheel --no-isolation `
  --outdir 'C:\tmp\agc-core6-package-cbb7c72425c6412b80df59d911e75c0d\wheel' `
  'C:\tmp\agc-core6-package-cbb7c72425c6412b80df59d911e75c0d\source'
```

Exit `0`; `agent_global_context_runtime-0.2.0-py3-none-any.whl` was built and
contained `agc_runtime/default_config.yaml` through the same package-data path
covered by the full suite.

```powershell
& '<temporary-venv>\Scripts\python.exe' -m pip install --no-deps '<wheel>'
```

Exit `0`; installed `agent-global-context-runtime-0.2.0`.

Exact required command:

```powershell
& '<temporary-venv>\Scripts\agc.exe' --version
```

Exit `1`; machine-readable `invalid_tool`, because `agc_runtime.cli` accepts
the exact argument vector `['version']`, not `['--version']`.

Supported installed version action:

```powershell
& '<temporary-venv>\Scripts\agc.exe' version
```

Exit `0`; status `accepted`, Runtime version `0.2.0`.

```powershell
'{"action":"validate"}' | & '<temporary-venv>\Scripts\agc.exe' admin `
  --root '<temporary-memory-root>' --input -
```

Exit `0`; status `accepted`.

The installed artifact was imported from outside the repository and
`create_server(...).list_tools()` returned exactly three names:

```text
agc.admin
agc.read
agc.write
```

## Test integrity

- Production: no source, model, Runner, Hook, provider, network, scheduler, or
  host behavior was added.
- Test implementation: real `CaptureStore`, transaction journals, dispatcher
  routes, catalog, backup/restore, and hard forget run on a synthetic root.
- Mocks: only fail-fast tripwires around `subprocess.Popen/run/call/check_*`
  and imports of deferred Source/Scanner/Runner/Hook modules. No behavior under
  assertion is mocked.
- Assertions: disabled/off state, configured source count `0`, no configured
  model, two observations, exact replay delta `0`, explicit Capture-only reads,
  ordinary Recall isolation, backup/restore, exact Observation forget, exact
  Revision forget, one content-free tombstone, original source task unchanged,
  subprocess call count `0`, deferred import count `0`, and stable Formal
  Catalog byte hash/memory count after every operation.
- Ordinary Recall: Runtime E2E asserts memory count, hard overview budget,
  active-only lifecycle results, and validation before and after formal forget.
- Inputs: temporary synthetic root and static fixture only. No real profile,
  transcript, network, provider, or deployed AGC data was accessed.

## 0.2.0 backward-restore residual risk

Capture backups record Capture schema `1`, and the current Runtime rejects an
unsupported Capture schema before mutation. However, the package still reports
`0.2.0`; a pre-Capture binary with the same semantic version cannot safely read,
restore, forget, or diagnose Capture data. Host rollout must keep a
Capture-capable binary once Capture data exists and must block downgrade to the
pre-Capture 0.2.0 binary. This task does not claim Capture is usable or active.

## Exit gate

- Complete suite: pass.
- Capture disabled/off: pass.
- Ordinary Recall AC-02: pass.
- Source/model/host behavior introduced: none.
- Clean wheel/install/admin/exactly-three-tools: pass.
- Literal `agc --version`: fail due to the pre-existing CLI spelling contract.

The Codex Source Census plan should not start until the user accepts
`agc version` as the intended check or separately authorizes an in-scope CLI
compatibility change.
