# Capture Source Census Task 3 Report

## Implementation

- Added the silent `agc-capture-hook --root <memory-root>` Codex Stop Hook entry point.
- Validates the complete Stop envelope, resolves the transcript only as metadata, and never opens or reads transcript content.
- Persists only schema/adapter/source versions, opaque source/task/revision identities, a contained relative locator, observation time, and the `Stop` event.
- Added an immutable per-event dirty spool using a stable capture-key digest plus a nonce, a same-directory temporary file, file flush/fsync when available, atomic no-overwrite `os.link` installation, and best-effort directory fsync.
- Keeps malformed input, path/reparse escape, collision, permission failure, disk failure, invalid operation form, disabled/paused Capture, and unsupported fsync failure-open and silent.
- Added contract coverage for exact root binding, zero content persistence, replayed marker uniqueness, collision preservation, partial-file cleanup, and forbidden runtime-layer imports.
- Kept Capture runtime imports lazy in the hook test module so disabled Capture core remains independently releasable.

## Files

- `agc_runtime/capture_dirty.py`
- `agc_runtime/capture_hook.py`
- `tests/test_capture_hook.py`
- `pyproject.toml`
- `tests/test_cli_contract.py`
- `.superpowers/sdd/capture-source-task-3-report.md`

## RED

The interrupted workspace had no RED evidence in `.pytest_cache/v/cache/lastfailed`. The original pre-implementation RED could not be recreated from repository evidence. Tests were instead validated without changing repository files by running pytest through in-memory capability substitutions. These checks proved that the tests detected disabled behavior, but they were not historical pre-implementation RED evidence:

- Replacing `capture_hook.write_dirty_marker` with a no-op produced the expected two failures (`2 failed, 12 passed`): the metadata marker and immutable-collision tests both observed zero markers.
- Hiding `agc-capture-hook` from the in-memory `pyproject.toml` stream produced the expected CLI `KeyError: 'agc-capture-hook'` (`1 failed`).

A new unsupported-platform edge was then added before its production fix:

```powershell
& '.venv\Scripts\python.exe' -m pytest -q `
  --basetemp .tmp/red-fsync `
  tests/test_capture_hook.py::test_spool_still_installs_marker_when_fsync_is_unavailable
```

Output: `1 failed`; the Hook exited silently but installed zero markers because direct `os.fsync` lookup raised `AttributeError`.

## GREEN

Minimal fix: route file and directory durability through `_flush_file`, which invokes `os.fsync` when present, propagates real file fsync I/O failures, and tolerates platforms without the API.

Focused Task 3 command:

```powershell
& '.venv\Scripts\python.exe' -m pytest -q `
  --basetemp D:\tmp\agc-capture-task3-regression `
  tests/test_capture_core_end_to_end.py::test_disabled_capture_core_is_independently_releasable `
  tests/test_capture_hook.py tests/test_cli_contract.py
```

Output: `22 passed in 4.98s`.

Related Capture/source/schema/config/path/adapter command:

```powershell
& '.venv\Scripts\python.exe' -m pytest -q `
  --basetemp D:\tmp\agc-capture-task3-related-2 `
  tests/test_capture_source_contracts.py tests/test_capture_contracts.py `
  tests/test_runtime_config.py tests/test_paths_and_io.py `
  tests/test_codex_source_adapter.py tests/test_capture_hook.py `
  tests/test_cli_contract.py
```

Output: `168 passed in 24.34s`.

## Installed wheel entry point

- Built `agent_global_context_runtime-0.2.0-py3-none-any.whl` from a clean temporary source copy containing the Task 3 workspace changes.
- Installed it with dependencies into `D:\tmp\agc-capture-task3-wheel\venv`.
- Invoked the generated `agc-capture-hook.exe` with valid Stop JSON, malformed JSON, and invalid operation form.
- Valid event: exit `0`, stdout/stderr `0` bytes, requested-root marker count `1`, unrelated-root marker count `0`.
- Marker decoded as strict UTF-8, had no BOM, ended with a newline, and contained exactly the ten allowlisted metadata fields.
- Scanning every file in the synthetic memory root as bytes found `SENTINEL_HITS=0` for the last-assistant-message sentinel.
- The transcript content, absolute transcript path, cwd, model, and last assistant message were absent from the marker.

No live profile was read or modified.

## Full suite

The first full run exposed collection-time coupling from the new test module: `capture_hook` was imported before the disabled-core boundary test executed. After moving those imports into a module-scoped test fixture, the targeted regression passed.

Final unfiltered command:

```powershell
& '.venv\Scripts\python.exe' -m pytest -q `
  --basetemp D:\tmp\agc-capture-task3-full-2
```

Output: `557 passed, 1 warning in 272.69s`; the warning is the existing duplicate-name ZIP fixture warning.

## Gates and self-review

- `python -m compileall -q agc_runtime tests`: passed.
- `git diff --check`: passed.
- Strict UTF-8 decode and no-BOM gate: passed for all five changed source/test/config files before this report; the report was also written as UTF-8 without BOM.
- Forbidden Hook dependency scan (Scanner, Capture Store/transaction, extractor, MCP, formal Store/write service): zero matches.
- Hook content-read/source-enumeration API scan: zero matches.
- The Hook does not enumerate sources, execute Scanner/model/network work, perform semantic Capture, or activate Capture behavior.
- Scanner reconciliation remains correctness authority; dirty-marker loss never affects the foreground Stop operation.

## Review remediation — immutable install, pre-mutation containment, and test isolation

### Reproduced RED

Three review findings were reproduced against commit `336cab23c517bc71e7a1872f53ed2f78ea0634a7` before their fixes:

1. Reverse-order execution (`tests/test_capture_hook.py` before the disabled-core E2E) produced `1 failed, 16 passed`. The hook test fixture left deferred Capture modules in `sys.modules`, so the unchanged production boundary assertion failed.
2. An injected collision between the old `final.exists()` check and `os.replace` produced a completed marker that overwrote the competing destination. The regression failed on the expected content mismatch.
3. A pre-existing `memory/.runtime` junction targeting an outside directory allowed the old `dirty.mkdir(...)` call to create `capture/dirty` outside the memory root before containment was checked. The regression failed because the outside directory structure changed.

### Review implementation

- Replaced check-then-`os.replace` with `os.link(temporary, final)`. The fsynced temporary inode is exposed atomically, an existing destination makes the link fail without overwrite on Windows and POSIX, and Hook-level failure-open handling removes the temporary file.
- Added a read-only validation pass over every existing dirty-spool ancestor before any `mkdir` or file mutation. Each existing path must resolve to a directory strictly contained by the canonical memory root. The final created dirty directory is revalidated before file creation.
- Changed the hook test module fixture to remember its starting `sys.modules` set and remove only `agc_runtime` modules introduced by that fixture during teardown. The production disabled-core assertion was not weakened.
- Strengthened transcript non-read coverage across `Path.open`, `builtins.open`, and `os.open`.

### Review GREEN

- Filesystem regressions: `2 passed in 0.32s`.
- Reverse order (hook suite, then disabled-core E2E): `19 passed in 3.39s`.
- Related disabled-core/Capture source/schema/config/path/adapter/hook/CLI suite: `171 passed in 19.40s`.
- Rebuilt and installed wheel entry point: exit `0`, stdout/stderr `0` bytes, requested markers `1`, unrelated markers `0`, sentinel hits `0`, strict UTF-8 with no BOM.
- Final unfiltered suite: `559 passed, 1 warning in 294.59s`; the warning remains the existing duplicate-name ZIP fixture warning.

No live profile was read or modified during review remediation.
