# Capture Core Task 6 Report

## Status

`DONE`

The disabled Capture Core release proof and its review fixes are implemented.
The only production change is a backward-compatible CLI alias: both
`agc --version` and `agc version` return the same stable Runtime 0.2.0 envelope.
Capture remains disabled and no Source, model, provider, network, Runner, Hook,
scheduler, or host behavior was introduced.

## Scoped files

- Created `tests/test_capture_core_end_to_end.py`.
- Modified `tests/test_runtime_end_to_end.py`.
- Modified `tests/test_cli_contract.py`.
- Modified `agc_runtime/cli.py`.
- Modified `.llm-wiki/requirements/agc-capture-coverage-mvp.md`.
- Modified `.llm-wiki/working-context/agc-capture-coverage-mvp.md`.
- Created this report.
- Production files changed: `1` (`agc_runtime/cli.py`, version alias only).

## TDD RED

```powershell
& '.\.venv\Scripts\python.exe' -m pytest `
  tests/test_capture_core_end_to_end.py -q `
  --basetemp 'C:\tmp\agc-capture-core-e2e-red'
```

Exit `1`: `1 failed in 0.25s`. The deliberately incomplete scaffold failed at
`disabled Capture core E2E proof is not implemented`, proving the new release
proof did not exist before implementation.

The review-fix CLI regression was also observed RED before production code was
changed:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest `
  tests/test_cli_contract.py::test_dash_dash_version_is_a_compatible_json_envelope `
  -q --basetemp '<temporary-root>\agc-core6-version-red'
```

Exit `1`: `1 failed`; `agc --version` returned exit `2` with `invalid_tool`.
After the minimal alias change, the legacy and compatibility version tests
exited `0` with `2 passed in 1.48s`.

## TDD GREEN and complete suite

```powershell
& '.\.venv\Scripts\python.exe' -m pytest `
  tests/test_capture_core_end_to_end.py tests/test_runtime_end_to_end.py -q `
  --basetemp 'C:\tmp\agc-capture-core-e2e-green'
```

The final focused review command covered CLI, disabled Capture Core, and
ordinary Runtime E2E:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest `
  tests/test_cli_contract.py tests/test_capture_core_end_to_end.py `
  tests/test_runtime_end_to_end.py -q `
  --basetemp '<temporary-root>\agc-core6-review-focused'
```

Exit `0`: `11 passed in 11.59s`.

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

Exit `0`: `514 passed, 1 warning in 318.80s`. The warning is the expected
duplicate-name ZIP attack fixture.

An initial diagnostic ordering put the bundled backend first and inherited
offline pip flags. It exited `1` with `505 passed, 8 failed`: seven MCP imports
loaded a foreign pure-Python Pydantic ahead of the venv's compiled extension,
and one installer could not resolve its isolated setuptools requirement. No
product code was changed. The exact affected subset plus the wheel regression
passed `12 passed in 167.71s`, then the corrected complete command above passed.

## Package, install, and MCP evidence

A new disposable source copy was populated only from `git ls-files`, reading
the current working-tree bytes for those tracked files; `.git`, `.venv`, local
build output, caches, and untracked files therefore could not enter the build.
The already-installed local build backend was selected through `PYTHONPATH`,
and `--no-isolation` prevented dependency resolution during the build:

```powershell
& '.\.venv\Scripts\python.exe' -m build --wheel --no-isolation `
  --outdir '<new-temporary-root>\wheel' `
  '<new-temporary-root>\source'
```

Exit `0`; `agent_global_context_runtime-0.2.0-py3-none-any.whl` was built and
contained `agc_runtime/default_config.yaml` through the same package-data path
covered by the full suite.

```powershell
& '<temporary-venv>\Scripts\python.exe' -m pip install --no-deps '<wheel>'
```

Exit `0`; installed `agent-global-context-runtime-0.2.0`.

Exact required and legacy-compatible commands:

```powershell
& '<temporary-venv>\Scripts\agc.exe' --version
```

Exit `0`; status `accepted`, Runtime version `0.2.0`.

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

The installed MCP probe ran from the disposable directory, used `site.addsitedir`
only for already-installed third-party dependencies, asserted that
`agc_runtime.__file__` resolved under the disposable venv's `site-packages`,
and then executed `create_server(...).list_tools()`:

```powershell
& '<temporary-venv>\Scripts\python.exe' -c `
  "import asyncio,json,pathlib,site; site.addsitedir('<dependency-site>'); import agc_runtime; from agc_runtime.mcp_server import create_server; installed=pathlib.Path(agc_runtime.__file__).resolve(); assert str(installed).startswith('<temporary-venv>'); print(json.dumps({'provenance':str(installed),'tools':sorted(t.name for t in asyncio.run(create_server(pathlib.Path('<temporary-memory-root>')).list_tools()))}))"
```

Exit `0`; provenance was the wheel-installed `site-packages/agc_runtime`, and
the tool names were exactly:

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
- Mocks: fail-fast tripwires are installed before Runtime imports and init.
  They cover `subprocess.Popen/run/call/check_*`, planned Source/Scanner/
  Capsule/Extractor/Runner/Hook imports, source-root enumeration through
  `os.scandir`, `os.listdir`, and `Path.iterdir/glob/rglob`, plus socket and
  URL network calls. No behavior under assertion is mocked.
- Assertions: disabled/off state, configured source count `0`, no configured
  model, two observations, exact replay delta `0`, explicit Capture-only reads,
  ordinary Recall isolation, a non-no-op restore that removes a third
  post-backup Observation and returns the count from `3` to `2`, exact
  Observation forget, exact Revision forget, one content-free tombstone, and
  an outside-root source-task sentinel that remains byte-exact through both
  forget types. All boundary-call counts remain `0`, and the Formal Catalog
  byte hash/memory count stays stable after every operation.
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
- Literal `agc --version` and legacy `agc version`: pass from installed wheel.
- Text/package gates: strict UTF-8/no-BOM checked `132` tracked text files and
  exited `0`; `python -m compileall -q agc_runtime tests` exited `0`; and
  `git diff --check` exited `0`.

The Capture Core exit gate is satisfied. Capture is still inert and does not
become usable until the separately planned Source/Census stages are delivered.
