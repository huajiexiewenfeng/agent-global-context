# AGC Project-Aware Observation Context Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use `executing-plans` for inline execution or `subagent-driven-development` when explicitly requested. This project defaults to inline execution because the user has a confirmed no-delegation preference.

**Goal:** Give Codex Capture a stable, opaque per-project scope and make quality-first review automatically gather related atomic Observations before proposing memory.

**Architecture:** A small pure resolver converts a validated absolute Session cwd into `project:cwd:` plus a SHA-256 digest without filesystem access or path persistence. `CodexSourceAdapter.load_capsule()` applies that scope only when the caller did not provide one; existing extractor and persistence contracts then carry it unchanged. Review stays agent-driven and non-promoting, but its workflow automatically expands exact project scopes through the existing Capture search filter.

**Tech Stack:** Python 3.11+, frozen dataclasses, pathlib pure paths, hashlib, pytest, Markdown Skill contracts, existing AGC Capture schema v1.

## Global Constraints

- Keep `CAPTURE_SCHEMA_VERSION = 1` and `capture-extractor-v1`; no migration or historical rewrite.
- Never persist or expose a raw Session cwd; only the opaque SHA-256 project scope may leave the adapter.
- Do not access the cwd directory, Git metadata, network, production Session data, or production Memory Root during development.
- Preserve atomic Observations, existing persistence safety, authorization digests, budgets, receipts, backup/restore, Hard Forget, and no-auto-promotion behavior.
- Cross-Session review expansion requires an exact non-null project scope; null scope and semantic similarity alone never authorize automatic merging.
- Route every pytest artifact to the operator-configured centralized test root through `$env:AGC_TEST_TMP_ROOT`; never use a repository-local pytest temp directory.

---

### Task 1: Deterministic opaque project-scope resolver

**Files:**
- Create: `agc_runtime/capture_project_scope.py`
- Create: `tests/test_capture_project_scope.py`

**Interfaces:**
- Consumes: untrusted `session_meta.payload.cwd` values.
- Produces: `project_scope_from_cwd(value: Any) -> str | None`.

- [ ] **Step 1: Write the failing resolver tests**

```python
import pytest

from agc_runtime.capture_project_scope import project_scope_from_cwd


def test_project_scope_normalizes_equivalent_windows_cwd_without_exposing_it():
    drive = "C:"
    left = project_scope_from_cwd(drive + r"\Synthetic\XPublisher\.")
    right = project_scope_from_cwd("c:/synthetic/xpublisher")
    assert left == right
    assert left is not None
    assert left.startswith("project:cwd:")
    assert len(left) == len("project:cwd:") + 64
    assert "work" not in left.casefold()


def test_project_scope_distinguishes_projects_and_supports_posix_paths():
    drive = "C:"
    assert project_scope_from_cwd(drive + r"\Synthetic\XPublisher") != project_scope_from_cwd(
        drive + r"\Synthetic\AgentGlobalContext"
    )
    assert project_scope_from_cwd("/work/x-publisher") == project_scope_from_cwd(
        "/work/./x-publisher"
    )


@pytest.mark.parametrize(
    "value",
    (None, "", "relative/project", "/", "C:" + "\\", " " + "C:" + r"\synthetic", "C:" + "\\bad\npath", "\ud800", "x" * 4097),
)
def test_project_scope_rejects_ambiguous_or_unsafe_cwd(value):
    assert project_scope_from_cwd(value) is None
```

- [ ] **Step 2: Run the resolver tests to verify RED**

```powershell
if (-not $env:AGC_TEST_TMP_ROOT) { throw 'AGC_TEST_TMP_ROOT is required' }
& '.\.venv\Scripts\python.exe' -m pytest tests/test_capture_project_scope.py -q -p no:cacheprovider --basetemp (Join-Path $env:AGC_TEST_TMP_ROOT 'project-scope-red')
```

Expected: collection fails with `ModuleNotFoundError: No module named 'agc_runtime.capture_project_scope'`.

- [ ] **Step 3: Implement the pure resolver**

```python
"""Content-safe project-scope derivation for Capture source metadata."""

from __future__ import annotations

import hashlib
import ntpath
import posixpath
from pathlib import PurePosixPath, PureWindowsPath
import re
import unicodedata
from typing import Any


_PREFIX = "project:cwd:"
_MAX_CWD_CODEPOINTS = 4096
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def project_scope_from_cwd(value: Any) -> str | None:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > _MAX_CWD_CODEPOINTS
        or _CONTROL.search(value)
    ):
        return None
    try:
        candidate = unicodedata.normalize("NFC", value)
        candidate.encode("utf-8")
    except UnicodeError:
        return None
    windows = PureWindowsPath(candidate)
    posix = PurePosixPath(candidate)
    if windows.is_absolute():
        normalized = ntpath.normcase(ntpath.normpath(candidate)).replace("\\", "/")
        if PureWindowsPath(normalized).parent == PureWindowsPath(normalized):
            return None
        domain = "windows"
    elif posix.is_absolute():
        normalized = posixpath.normpath(candidate)
        if normalized == "/":
            return None
        domain = "posix"
    else:
        return None
    digest = hashlib.sha256(f"{domain}\0{normalized}".encode("utf-8")).hexdigest()
    return f"{_PREFIX}{digest}"


__all__ = ["project_scope_from_cwd"]
```

- [ ] **Step 4: Run the resolver tests to verify GREEN**

Run the Step 2 command with basetemp suffix `project-scope-green`.

Expected: all tests in `tests/test_capture_project_scope.py` pass.

- [ ] **Step 5: Commit Task 1**

```powershell
git add agc_runtime/capture_project_scope.py tests/test_capture_project_scope.py
git commit -m "feat: derive opaque capture project scopes"
```

---

### Task 2: Propagate Session project scope through Capsule and Observation

**Files:**
- Modify: `agc_runtime/codex_source_adapter.py`
- Modify: `tests/test_capture_capsule_safety.py`
- Modify: `tests/test_capture_manual_backfill_end_to_end.py`

**Interfaces:**
- Consumes: `project_scope_from_cwd()` from Task 1 and validated target-turn records.
- Produces: `CodexSourceAdapter.load_capsule()` results whose `capsule.project_scope` is caller-provided scope or a safely derived scope.

- [ ] **Step 1: Write failing adapter boundary tests**

Add a test that injects a synthetic cwd into the existing `_write_source()` metadata and verifies derivation without disclosure:

```python
def test_codex_load_capsule_derives_opaque_scope_without_exposing_cwd(tmp_path: Path):
    from agc_runtime.capture_capsule import CapsulePolicy
    from agc_runtime.capture_project_scope import project_scope_from_cwd
    from agc_runtime.codex_source_adapter import CodexSourceAdapter

    private_cwd = "C:" + r"\Synthetic\XPublisher"
    source = tmp_path / "profile" / "sessions" / "task.jsonl"
    _write_source(source)
    source.write_text(
        source.read_text(encoding="utf-8").replace(
            '"title":"Capsule task"',
            f'"title":"Capsule task","cwd":{json.dumps(private_cwd)}',
        ),
        encoding="utf-8",
    )
    adapter = CodexSourceAdapter(tmp_path / "profile")
    ref = next(item for item in adapter.discover(None, _window()).revisions if item.key.revision_id == "turn-target")

    result = adapter.load_capsule(ref, CapsulePolicy())

    assert result.capsule.project_scope == project_scope_from_cwd(private_cwd)
    assert "synthetic" not in repr(result).casefold()
    assert "synthetic" not in json.dumps(result.capsule.to_mapping()).casefold()
```

Add a second test proving an explicit caller scope remains authoritative.

- [ ] **Step 2: Extend the manual backfill E2E before implementation**

In `test_manual_backfill_cli_prepares_authorizes_collects_and_replays`, add the same synthetic absolute cwd to both Session metadata records, compute `expected_scope = project_scope_from_cwd(cwd)`, make the fake extractor return that exact scope, and assert both committed Observations use it:

```python
from agc_runtime.capture_project_scope import project_scope_from_cwd

cwd = "C:" + r"\Synthetic\XPublisher"
expected_scope = project_scope_from_cwd(cwd)
assert expected_scope is not None

records[0]["payload"]["cwd"] = cwd
runner_records[0]["payload"]["cwd"] = cwd
fake_text = fake_text.replace(
    '"project_scope": "project:stable"',
    f'"project_scope": {json.dumps(expected_scope)}',
)

observations = [
    CollectedObservation.from_mapping(read_json(path))
    for path in paths.capture.observations.glob("co_*.json")
]
assert len(observations) == 2
assert {item.project_scope for item in observations} == {expected_scope}
```

Before implementation, persistence must filter the fake draft because the Capsule scope is still null.

- [ ] **Step 3: Run adapter and E2E tests to verify RED**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_capture_capsule_safety.py -q -p no:cacheprovider --basetemp (Join-Path $env:AGC_TEST_TMP_ROOT 'adapter-scope-red') -k 'derives_opaque_scope or explicit_caller_scope'
& '.\.venv\Scripts\python.exe' -m pytest tests/test_capture_manual_backfill_end_to_end.py -q -p no:cacheprovider --basetemp (Join-Path $env:AGC_TEST_TMP_ROOT 'scope-e2e-red')
```

Expected: the adapter scope assertion fails with `None`; the E2E reports zero accepted Observations or fails the expected-scope assertion.

- [ ] **Step 4: Implement per-revision scope application in the adapter**

Materialize the already bounded target records once, derive from the identity-validated `session_meta`, and preserve explicit policies:

```python
from dataclasses import replace
from agc_runtime.capture_project_scope import project_scope_from_cwd


def _session_project_scope(records: tuple[dict[str, Any], ...]) -> str | None:
    for record in records:
        payload = record.get("payload")
        if record.get("type") == "session_meta" and isinstance(payload, dict):
            return project_scope_from_cwd(payload.get("cwd"))
    return None


def load_capsule(self, ref: RevisionRef, policy: Any) -> Any:
    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule

    if not isinstance(policy, CapsulePolicy):
        raise CapabilityUnavailable("semantic_capture_not_installed")
    self._validate_ref(ref)
    try:
        records = tuple(self._iter_target_turn_records(ref))
        effective_policy = policy
        if policy.project_scope is None:
            effective_policy = replace(
                policy,
                project_scope=_session_project_scope(records),
            )
        return build_capsule(records, ref, effective_policy)
    except _SourceIdentityMismatch:
        raise ValueError("capsule_source_identity_changed") from None
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
        raise ValueError("capsule_source_unavailable") from None
```

- [ ] **Step 5: Run focused tests to verify GREEN**

Repeat Step 3 with `adapter-scope-green` and `scope-e2e-green` basetemps.

Expected: selected adapter tests pass; the full manual backfill E2E passes with two Observations sharing the opaque scope.

- [ ] **Step 6: Commit Task 2**

```powershell
git add agc_runtime/codex_source_adapter.py tests/test_capture_capsule_safety.py tests/test_capture_manual_backfill_end_to_end.py
git commit -m "feat: propagate codex session project scope"
```

---

### Task 3: Require grounded self-contained project wording

**Files:**
- Modify: `agc_runtime/codex_extractor.py`
- Modify: `tests/test_capture_extractor.py`

**Interfaces:**
- Consumes: existing `TaskCapsule.project_scope`, `task_title`, and safe user signals.
- Produces: stricter extractor instruction text; no schema or DTO change.

- [ ] **Step 1: Add the failing instruction contract**

Extend `test_capsule_prompt_requires_exact_bilingual_atomic_transformations`:

```python
instruction = payload["instruction"]
assert "self-contained project referent" in instruction
assert "Never derive a project name from opaque project_scope" in instruction
assert "Keep one atomic user predicate" in instruction
```

- [ ] **Step 2: Run the exact test to verify RED**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_capture_extractor.py::test_capsule_prompt_requires_exact_bilingual_atomic_transformations -q -p no:cacheprovider --basetemp (Join-Path $env:AGC_TEST_TMP_ROOT 'extractor-context-red')
```

Expected: failure because the three new instruction clauses are absent.

- [ ] **Step 3: Add minimal instruction clauses**

Append to `_EXTRACTION_INSTRUCTION`:

```python
"When task_capsule.project_scope is non-null and a safe task_title or user signal "
"explicitly supports a bounded project name, include that self-contained project referent "
"inside the statement object while keeping one atomic user predicate. Never derive a "
"project name from opaque project_scope, and never invent a referent absent from safe evidence. "
```

- [ ] **Step 4: Run extractor tests to verify GREEN**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_capture_extractor.py -q -p no:cacheprovider --basetemp (Join-Path $env:AGC_TEST_TMP_ROOT 'extractor-context-green')
```

Expected: all extractor tests pass.

- [ ] **Step 5: Commit Task 3**

```powershell
git add agc_runtime/codex_extractor.py tests/test_capture_extractor.py
git commit -m "feat: preserve project referents in capture drafts"
```

---

### Task 4: Make quality-first review project-aware

**Files:**
- Modify: `skills/agent-global-context/references/formalization-workflow.md`
- Modify: `tests/test_skill_adapter.py`

**Interfaces:**
- Consumes: existing `capture_search` project filter, receipt ids, non-null exact project scopes, and up to 20 unique Observation ids.
- Produces: review instructions that automatically collect related project observations and synthesize coherent proposals without automatic writes.

- [ ] **Step 1: Add failing Skill contract tests**

```python
def test_formalization_groups_receipts_and_expands_exact_project_scope():
    guidance = _guidance_text()
    text = guidance.casefold()
    assert "same receipt" in text
    assert 'filters.project' in text
    assert "exact non-null project_scope" in text
    assert "at most 20" in text
    assert "different non-null project scopes" in text
    assert "null project_scope" in text


def test_x_publishing_golden_case_is_one_project_proposal():
    guidance = _guidance_text()
    assert "X 发文开源项目" in guidance
    assert "规划文章的整体路线" in guidance
    assert "每篇文章撰写摘要" in guidance
    assert "参与开源项目" in guidance
    assert "one coherent project proposal" in guidance
```

- [ ] **Step 2: Run the Skill tests to verify RED**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_skill_adapter.py -q -p no:cacheprovider --basetemp (Join-Path $env:AGC_TEST_TMP_ROOT 'formalization-scope-red') -k 'formalization or x_publishing'
```

Expected: the new grouping and golden-case assertions fail.

- [ ] **Step 3: Update the formalization workflow**

Insert these rules before classification:

```markdown
2. Group selected observations from the same receipt. For every exact non-null
   `project_scope`, call `capture_search` again with `filters.project` and gather
   unreviewed related observations, bounded to at most 20 unique ids in one review.
   Paginate explicitly when more exist.
3. Never automatically combine different non-null project scopes. A null
   `project_scope` permits same-receipt grouping only; cross-Session semantic
   similarity becomes `needs_context`, not a silent merge.
```

Add the confirmed golden case:

```markdown
Project-context golden case: observations `规划文章的整体路线`, `每篇文章撰写摘要`,
and `参与开源项目` under the same exact project scope refer to the X 发文开源项目.
Review them as one coherent project proposal describing the open-source project and
its roadmap-first, summary-first writing workflow. Without that exact scope, do not
infer the relationship.
```

Renumber the existing workflow while preserving explicit preview and confirmation gates.

- [ ] **Step 4: Run Skill tests to verify GREEN**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_skill_adapter.py -q -p no:cacheprovider --basetemp (Join-Path $env:AGC_TEST_TMP_ROOT 'formalization-scope-green')
```

Expected: all Skill adapter tests pass.

- [ ] **Step 5: Commit Task 4**

```powershell
git add skills/agent-global-context/references/formalization-workflow.md tests/test_skill_adapter.py
git commit -m "docs: aggregate capture review by project scope"
```

---

### Task 5: Adjacent regression and lifecycle evidence

**Files:**
- Modify: `.llm-wiki/requirements/agc-project-aware-observation-context.md`
- Modify: `.llm-wiki/working-context/agc-project-aware-observation-context.md`

**Interfaces:**
- Consumes: Tasks 1–4.
- Produces: verified implementation evidence and an execution-ready handoff to `project-finish`.

- [ ] **Step 1: Run focused and adjacent Capture suites**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_capture_project_scope.py tests/test_capture_capsule_safety.py tests/test_capture_extractor.py tests/test_capture_manual_backfill_end_to_end.py tests/test_capture_read_service.py tests/test_skill_adapter.py -q -p no:cacheprovider --basetemp (Join-Path $env:AGC_TEST_TMP_ROOT 'project-context-focused')
```

Expected: zero failures.

- [ ] **Step 2: Run static integrity gates**

```powershell
& '.\.venv\Scripts\python.exe' -m compileall -q agc_runtime tests
git diff --check
& '.\.venv\Scripts\python.exe' -c "from pathlib import Path; import subprocess; files=[Path(p) for p in subprocess.check_output(['git','ls-files'], text=True).splitlines() if Path(p).is_file()]; bad=[]; [(bad.append(str(p)) if p.read_bytes().startswith(b'\xef\xbb\xbf') else p.read_bytes().decode('utf-8')) for p in files]; assert not bad, bad; print('utf8-no-bom', len(files))"
```

Expected: exit 0, no compile errors, no diff whitespace errors, and no BOM/decoder errors.

- [ ] **Step 3: Inspect scope and production boundaries**

```powershell
git status --short
git diff --stat HEAD~4..HEAD
git diff --name-only HEAD~4..HEAD
```

Expected: only files named by this plan and lifecycle documents changed; no production Memory Root, installer, release, scheduler, or config file appears.

- [ ] **Step 4: Update Flow Record with exact evidence**

Set Change Brief status to `executing` until `project-finish` performs final review. Record exact commands, pass counts, changed files, residual risks, and commits. Mark `development` and `testing` done only when matching evidence exists; keep `archive` pending.

- [ ] **Step 5: Commit verification evidence**

```powershell
git add .llm-wiki/requirements/agc-project-aware-observation-context.md .llm-wiki/working-context/agc-project-aware-observation-context.md
git commit -m "docs: record project-aware capture verification"
```

## Execution Handoff

- flow_id: `agc-project-aware-observation-context`
- active scope: resolver, Codex adapter propagation, extractor instruction, formalization workflow, focused tests, lifecycle evidence
- read-only scope: Runner, schema v1, Capture read/filter contracts, existing Capture Coverage requirement
- excluded scope: schema migration, fuzzy clustering, historical rewrite, production replay/model/install/release, task-aware ranking performance
- required method: TDD RED → GREEN per task, frequent commits, inline execution by default
- next gate: user confirms execution approach, then invoke `executing-plans`
