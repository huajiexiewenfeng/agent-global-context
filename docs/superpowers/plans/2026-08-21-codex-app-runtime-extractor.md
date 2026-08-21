# Codex App Runtime Extractor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let AGC resolve the current Windows Codex App Runtime through `executable: codex-app`, bind Capture to `gpt-5.6-sol`, and fail closed without npm/PATH fallback.

**Architecture:** Add one focused App Runtime resolver that searches only `%LOCALAPPDATA%\OpenAI\Codex\bin\*\codex.exe` and returns exactly one validated absolute executable. Keep literal executable parsing unchanged and delegate all version, sandbox, schema, model, provider, and output checks to the existing `CodexExtractor`.

**Tech Stack:** Python 3.10+, pathlib, stdlib `os`/`stat`, pytest 9.1.1, PowerShell installation and live verification.

## Global Constraints

- The exact selector is `codex-app`; no other string activates discovery.
- App Runtime discovery is Windows-only in this phase.
- Discovery must not use PATH, npm, registry, WindowsApps traversal, recursive broad search, or network access.
- Zero or multiple valid candidates fail closed with content-safe `capture_extractor_unavailable`.
- Literal executable commands remain backward compatible.
- The local deployment model boundary is exactly `gpt-5.6-sol` with provider `openai`.
- A resolved executable change must alter the existing executable identity and therefore invalidate earlier backfill authorization.
- No observation is promoted automatically to formal Memory.
- All test artifacts and pytest base directories remain under `D:\tmp_test`.

---

### Task 1: Bounded Windows Codex App Runtime resolver

**Files:**
- Create: `agc_runtime/codex_app_runtime.py`
- Create: `tests/test_codex_app_runtime.py`

**Interfaces:**
- Consumes: environment mapping containing optional `LOCALAPPDATA`; platform name matching `os.name`.
- Produces: `resolve_codex_app_command(*, environment: Mapping[str, str] | None = None, platform_name: str | None = None) -> tuple[str, ...]`.
- Raises: `RuntimeError("capture_extractor_unavailable")` for every fail-closed branch.

- [ ] **Step 1: Write failing resolver tests**

```python
def test_resolves_only_codex_exe_below_fixed_app_bin(tmp_path: Path):
    executable = tmp_path / "OpenAI" / "Codex" / "bin" / "version-a" / "codex.exe"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"runtime")
    assert resolve_codex_app_command(
        environment={"LOCALAPPDATA": str(tmp_path)}, platform_name="nt"
    ) == (str(executable.resolve()),)


@pytest.mark.parametrize(
    "environment,platform_name",
    (({}, "nt"), ({"LOCALAPPDATA": "relative"}, "nt"), ({}, "posix")),
)
def test_missing_invalid_or_non_windows_environment_fails_closed(
    environment: dict[str, str], platform_name: str
):
    with pytest.raises(RuntimeError, match="^capture_extractor_unavailable$"):
        resolve_codex_app_command(
            environment=environment, platform_name=platform_name
        )


def test_zero_or_multiple_candidates_fail_closed(tmp_path: Path):
    app_bin = tmp_path / "OpenAI" / "Codex" / "bin"
    app_bin.mkdir(parents=True)
    with pytest.raises(RuntimeError, match="^capture_extractor_unavailable$"):
        resolve_codex_app_command(
            environment={"LOCALAPPDATA": str(tmp_path)}, platform_name="nt"
        )
    for name in ("a", "b"):
        candidate = app_bin / name / "codex.exe"
        candidate.parent.mkdir()
        candidate.write_bytes(b"runtime")
    with pytest.raises(RuntimeError, match="^capture_extractor_unavailable$"):
        resolve_codex_app_command(
            environment={"LOCALAPPDATA": str(tmp_path)}, platform_name="nt"
        )
```

```python
def test_reparse_candidate_is_ignored_without_following_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    executable = tmp_path / "OpenAI" / "Codex" / "bin" / "version-a" / "codex.exe"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"runtime")
    monkeypatch.setattr(
        "agc_runtime.codex_app_runtime._is_reparse_point",
        lambda path: path == executable.parent,
    )
    with pytest.raises(RuntimeError, match="^capture_extractor_unavailable$"):
        resolve_codex_app_command(
            environment={"LOCALAPPDATA": str(tmp_path)}, platform_name="nt"
        )
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider `
  tests\test_codex_app_runtime.py `
  --basetemp D:\tmp_test\agc-codex-app-resolver-red
```

Expected: collection/import failure because `agc_runtime.codex_app_runtime` does not exist.

- [ ] **Step 3: Implement the minimal bounded resolver**

```python
from collections.abc import Mapping
import os
from pathlib import Path
import stat


_UNAVAILABLE = "capture_extractor_unavailable"


def _is_reparse_point(path: Path) -> bool:
    attributes = getattr(path.stat(), "st_file_attributes", 0)
    return bool(attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def _below(candidate: Path, parent: Path) -> bool:
    return candidate != parent and parent in candidate.parents


def resolve_codex_app_command(
    *,
    environment: Mapping[str, str] | None = None,
    platform_name: str | None = None,
) -> tuple[str, ...]:
    values = os.environ if environment is None else environment
    if (os.name if platform_name is None else platform_name) != "nt":
        raise RuntimeError(_UNAVAILABLE)
    raw_local = values.get("LOCALAPPDATA")
    if not raw_local or not Path(raw_local).is_absolute():
        raise RuntimeError(_UNAVAILABLE)
    try:
        local = Path(raw_local).resolve(strict=True)
        app_bin = (local / "OpenAI" / "Codex" / "bin").resolve(strict=True)
        if not local.is_dir() or not app_bin.is_dir() or not _below(app_bin, local):
            raise RuntimeError(_UNAVAILABLE)
        candidates: list[Path] = []
        for version_dir in app_bin.iterdir():
            if not version_dir.is_dir() or version_dir.is_symlink() or _is_reparse_point(version_dir):
                continue
            executable = version_dir / "codex.exe"
            if not executable.is_file() or executable.is_symlink() or _is_reparse_point(executable):
                continue
            resolved = executable.resolve(strict=True)
            if _below(resolved, app_bin):
                candidates.append(resolved)
        if len(candidates) != 1:
            raise RuntimeError(_UNAVAILABLE)
        return (str(candidates[0]),)
    except RuntimeError:
        raise
    except (OSError, ValueError) as error:
        raise RuntimeError(_UNAVAILABLE) from error
```

- [ ] **Step 4: Run resolver tests and verify GREEN**

Run the Step 2 command with base temp `D:\tmp_test\agc-codex-app-resolver-green`.

Expected: all resolver tests pass.

- [ ] **Step 5: Commit resolver**

```powershell
git add agc_runtime/codex_app_runtime.py tests/test_codex_app_runtime.py
git commit -m "feat(capture): resolve codex app runtime"
```

### Task 2: Integrate `codex-app` selector and App usage protocol

**Files:**
- Modify: `agc_runtime/capture_cli.py`
- Modify: `agc_runtime/codex_extractor.py`
- Modify: `tests/test_capture_cli.py`
- Modify: `tests/test_capture_extractor.py`
- Modify: `tests/fixtures/fake_codex_exec.py` only if a five-field end-to-end fixture is needed.

**Interfaces:**
- Consumes: `resolve_codex_app_command()` from Task 1.
- Produces: `_extractor_command("codex-app")` returning the resolved one-element command; literal strings retain current `shlex.split` behavior.
- Usage contract: exact App shape includes `cache_write_input_tokens` and validates it as a nonnegative integer.

- [ ] **Step 1: Write failing selector tests**

```python
def test_extractor_command_delegates_exact_codex_app_selector(monkeypatch):
    monkeypatch.setattr(
        "agc_runtime.codex_app_runtime.resolve_codex_app_command",
        lambda: (r"C:\app\codex.exe",),
    )
    assert _extractor_command("codex-app") == (r"C:\app\codex.exe",)


def test_extractor_command_does_not_treat_arguments_as_app_selector(monkeypatch):
    assert _extractor_command('codex-app --version') == ("codex-app", "--version")
```

- [ ] **Step 2: Run selector tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider `
  tests\test_capture_cli.py -k extractor_command `
  --basetemp D:\tmp_test\agc-codex-app-selector-red
```

Expected: exact selector returns literal `("codex-app",)` rather than the resolver result.

- [ ] **Step 3: Implement exact selector delegation**

```python
def _extractor_command(value: str) -> tuple[str, ...]:
    if value == "codex-app":
        from agc_runtime.codex_app_runtime import resolve_codex_app_command

        return resolve_codex_app_command()
    try:
        command = tuple(shlex.split(value, posix=True))
    except ValueError as error:
        raise ValueError("capture extractor executable is invalid") from error
    if not 1 <= len(command) <= 4:
        raise ValueError("capture extractor executable is invalid")
    return command
```

- [ ] **Step 4: Complete App usage regression coverage**

Keep the already observed RED/GREEN test for the valid five-field App Runtime usage. Add invalid value coverage:

```python
@pytest.mark.parametrize("value", (-1, True, "0"))
def test_app_runtime_usage_rejects_invalid_cache_write_tokens(value: object):
    *_unused, CodexExtractor = _extractor_api()
    with pytest.raises(ValueError, match="invalid usage"):
        CodexExtractor._parse_usage(
            {
                "input_tokens": 10,
                "cached_input_tokens": 0,
                "cache_write_input_tokens": value,
                "output_tokens": 2,
                "reasoning_output_tokens": 0,
            }
        )
```

- [ ] **Step 5: Run focused selector and Extractor tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider `
  tests\test_codex_app_runtime.py tests\test_capture_cli.py tests\test_capture_extractor.py `
  --basetemp D:\tmp_test\agc-codex-app-focused
```

Expected: all focused tests pass, including legacy literal command cases.

- [ ] **Step 6: Commit selector and usage support**

```powershell
git add agc_runtime/capture_cli.py agc_runtime/codex_extractor.py `
  tests/test_capture_cli.py tests/test_capture_extractor.py tests/fixtures/fake_codex_exec.py
git commit -m "fix(capture): bind codex app extractor protocol"
```

### Task 3: Operational documentation and lifecycle evidence

**Files:**
- Modify: `docs/capture-operations.md`
- Modify: `.llm-wiki/bugs/2026-08-21-extractor-help-read-only-token.md`

**Interfaces:**
- Documents the exact local configuration and fail-closed behavior.
- Records source tests, installed Runtime identity, live `gpt-5.6-sol` boundary, and residual limitations.

- [ ] **Step 1: Document App Runtime configuration**

Add this bounded example and explanation:

```yaml
capture:
  extractor:
    kind: codex_exec
    executable: codex-app
    model: gpt-5.6-sol
```

State that `codex-app` is Windows-only in this phase, never falls back to PATH/npm, and requires a fresh `prepare-backfill` after an App Runtime update.

- [ ] **Step 2: Update the Bug Brief before installation**

Record the resolver tests, focused test counts, exact commits, and status `verified-preinstall`. Do not include raw Session content or authentication details.

- [ ] **Step 3: Run documentation and diff checks**

```powershell
rg -n "codex-app|gpt-5.6-sol|fail" docs/capture-operations.md `
  .llm-wiki/bugs/2026-08-21-extractor-help-read-only-token.md
git diff --check
```

Expected: the selector, model, and fail-closed behavior are documented; `git diff --check` exits 0.

- [ ] **Step 4: Commit operational documentation**

```powershell
git add docs/capture-operations.md `
  .llm-wiki/bugs/2026-08-21-extractor-help-read-only-token.md
git commit -m "docs: document codex app capture runtime"
```

### Task 4: Full regression, install, configuration, and live acceptance

**Files:**
- Modify outside repository through explicit configuration updates: `D:\tmp_test\agc-history-pilot-20260821\memory\config.yaml`
- Modify outside repository through explicit configuration updates: `C:\Users\admin\.agent-global-context-v2\config.yaml`
- Installed artifact: `C:\Users\admin\.agent-global-context-runtime`

**Interfaces:**
- Installed stable launcher: `C:\Users\admin\.agent-global-context-runtime\bin\agc-capture.cmd`.
- Production formal-memory count must remain 24 before any explicit review/promotion.

- [ ] **Step 1: Run all relevant regression suites**

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider `
  tests\test_codex_app_runtime.py tests\test_capture_extractor.py `
  tests\test_capture_backfill.py tests\test_capture_manual_runner.py `
  tests\test_capture_manual_backfill_end_to_end.py tests\test_capture_cli.py `
  --basetemp D:\tmp_test\agc-codex-app-regression
```

Expected: all selected tests pass.

- [ ] **Step 2: Install the committed immutable Runtime**

```powershell
$repo = (Resolve-Path .).Path
& "$repo\scripts\install-local.ps1" `
  -RepositoryRoot $repo `
  -SkillsRoot 'C:\Users\admin\.agents\skills' `
  -CodexConfig 'C:\Users\admin\.codex-clean-20260710\config.toml' `
  -MemoryRoot 'C:\Users\admin\.agent-global-context-v2' `
  -InstallRoot 'C:\Users\admin\.agent-global-context-runtime' `
  -PythonExecutable "$repo\.venv\Scripts\python.exe"
```

Expected: installer exits 0, reports Runtime `0.3.0`, a new immutable venv, stable launchers, backup path, and restart required.

- [ ] **Step 3: Switch Pilot and production Capture configuration**

Set both extractor blocks to:

```yaml
extractor:
  kind: codex_exec
  executable: codex-app
  model: gpt-5.6-sol
```

Do not enable Hook or Runner and do not run production backfill while source health is degraded.

- [ ] **Step 4: Run installed Pilot capability preparation**

```powershell
& 'C:\Users\admin\.agent-global-context-runtime\bin\agc-capture.cmd' `
  prepare-backfill --root 'D:\tmp_test\agc-history-pilot-20260821\memory'
```

Expected: accepted response with `model_boundary` exactly `gpt-5.6-sol`, `provider_boundary` exactly `openai`, and healthy scanner.

- [ ] **Step 5: Add and process representative historical Sessions**

Copy up to three already identified historical Codex App Sessions containing explicit durable preferences or project decisions into the Pilot source, verify every SHA-256 against its original, run `scan`, create a fresh authorization digest with installed `prepare-backfill`, then run installed `backfill --max-items 3 --once`.

Expected: no protocol failure, zero silent loss, and at least one observation available for review. If a sample truthfully returns an empty/policy zero reason, keep that receipt and continue within the three-sample bound. Do not promote observations.

- [ ] **Step 6: Verify production invariants and repository state**

Use installed `agc.exe` to query production `overview` and `capture_status`.

Expected: formal `memory_count` remains 24; Scanner-only remains enabled; Hook and continuous Runner remain inactive; no Pilot paths appear in production configuration; repository is clean and `git diff --check` exits 0.

- [ ] **Step 7: Final lifecycle update and commit**

Update the Bug Brief to `verified-installed`, record test counts, immutable Runtime directory, live App Runtime version, model/provider boundaries, historical Session result, and production invariants. Commit only the lifecycle evidence.

```powershell
git add .llm-wiki/bugs/2026-08-21-extractor-help-read-only-token.md
git commit -m "docs: verify codex app extractor rollout"
```
