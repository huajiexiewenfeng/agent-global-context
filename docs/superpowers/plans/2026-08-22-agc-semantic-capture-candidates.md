# AGC Semantic Capture Candidates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Collect reviewable tentative observations from bounded colloquial or compound Codex App user statements, avoid model calls for empty Capsules, verify the installed Runtime, and merge the verified fix into `main`.

**Architecture:** Keep the deterministic direct-memory lane unchanged. Add a bounded semantic-input lane for scrubbed assertive plain-language user units; only `agent_inferred` plus `tentative` drafts may use that broader evidence. Short-circuit a Capsule with no semantic fields before budget reservation and extractor invocation, committing a zero-token `no_durable_signal` receipt through the existing atomic Capture Store transaction.

**Tech Stack:** Python 3.10+, frozen dataclasses, schema-constrained Codex App `gpt-5.6-sol` extractor, canonical JSON/SHA-256 Capture Store, pytest, setuptools wheel, PowerShell immutable Runtime installer.

## Global Constraints

- Work only on `codex/fix-semantic-capture-empty` until the verified merge step.
- Put pytest basetemps, wheels, Pilot roots, copied Sessions, and other disposable artifacts under `D:\tmp_test`.
- Preserve target-turn, main-task, subagent, secret, credential, code, private-path, and source-identity protections.
- Direct candidates retain exact deterministic proposition equivalence.
- Broader semantic evidence can produce only `assertion_mode=agent_inferred` and `confidence=tentative` observations.
- Every accepted draft must cite verbatim evidence present in the Capsule and preserve its exact `project_scope`.
- Do not automatically promote observations into formal memory.
- Do not run a live model call until the exact Pilot source, model, item limit, token ceiling, and new authorization digest receive explicit user approval.
- Production formal memory must remain at 24 items through Pilot acceptance.
- The authoritative design is `docs/superpowers/specs/2026-08-21-agc-semantic-capture-candidates-design.md`.
- Baseline evidence before implementation is `1289 passed, 3 failed`; the existing failures are `test_enable_scanner_is_digest_gated_transactional_and_idempotent`, `test_windows_canonical_source_identity_handles_case_unicode_long_paths_and_junctions` under a long basetemp, and `test_built_wheel_contains_default_and_installed_admin_init_works`. Relevant Capture suites must be green and the complete suite must add no failures.

---

### Task 1: Admit Bounded Semantic User Context into the Capsule

**Files:**
- Create: `.llm-wiki/bugs/2026-08-22-semantic-capture-empty.md`
- Modify: `tests/test_capture_capsule_safety.py`
- Modify: `agc_runtime/capture_safety.py`

**Interfaces:**
- Consumes: `_record()`, `_ref()`, `CapsulePolicy`, and `build_capsule()` from the existing Capsule safety tests.
- Produces: `_user_is_semantic_candidate(text: str) -> bool`; `pre_capsule_gate()` retains eligible semantic evidence in `TaskCapsule.user_signals` without weakening direct proposition parsing.

- [ ] **Step 1: Create the active Bug Brief before source edits**

Create `.llm-wiki/bugs/2026-08-22-semantic-capture-empty.md` with the reproduced symptom, expected two-lane behavior, production receipt evidence (`extractor_empty`, three calls, zero observations), active files, excluded automatic promotion, baseline results, and this plan as the Flow Record plan anchor. Set status to `in-progress`; do not copy Session text into the Bug Brief.

- [ ] **Step 2: Write the failing semantic-Capsule test and update the changed expectation**

Add this test to `tests/test_capture_capsule_safety.py`:

```python
def test_compound_chinese_project_decision_reaches_tentative_semantic_lane():
    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule

    evidence = (
        "我觉得这个可以分成两个任务，首先继续设计架构，"
        "第二个做一个最小的企业微信机器人接入。"
    )
    result = build_capsule(
        (_record("user", evidence),),
        _ref(),
        CapsulePolicy(project_scope="project:stable"),
    )

    assert result.capsule.user_signals == (evidence,)
    assert result.counts.dropped_safety_count == 0
```

Replace `test_user_signal_requires_a_declarative_subject_predicate_start` with a test that asserts the two existing arbitrary-prefix examples are retained as semantic inputs, while the existing direct persistence tests continue rejecting them as direct claims.

- [ ] **Step 3: Run the test and verify RED**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONPATH=(Get-Location).Path
& 'D:\tmp\github\agent-global-context\.venv\Scripts\python.exe' -m pytest `
  -p no:cacheprovider --basetemp 'D:\tmp_test\sc1-red' -q `
  tests/test_capture_capsule_safety.py::test_compound_chinese_project_decision_reaches_tentative_semantic_lane
```

Expected: FAIL because `result.capsule.user_signals` is empty.

- [ ] **Step 4: Implement the minimal semantic-input predicate**

Add a fixed minimum and an uncertainty guard beside the existing user proposition helpers in `agc_runtime/capture_safety.py`:

```python
_MIN_SEMANTIC_SIGNAL_CODEPOINTS = 12
_UNCERTAIN_USER_CONTEXT = re.compile(
    r"(?i)\b(?:undecided|considering|trying\s+to\s+determine|wonder(?:ing)?)\b|"
    r"(?:尚未决定|正在考虑|不确定)"
)


def _user_is_semantic_candidate(text: str) -> bool:
    normalized = _normalize_text(text)
    return (
        len(normalized) >= _MIN_SEMANTIC_SIGNAL_CODEPOINTS
        and not normalized.endswith(("?", "？"))
        and _HYPOTHETICAL.search(normalized) is None
        and _QUOTED_ASSERTION.search(normalized) is None
        and _UNCERTAIN_USER_CONTEXT.search(normalized) is None
        and _COMMAND.search(normalized) is None
    )
```

Change only the user branch in `pre_capsule_gate()`:

```python
if role == "user":
    if not (
        _user_has_high_signal(unit)
        or _user_is_semantic_candidate(unit)
    ):
        dropped_class += 1
        continue
    safe_records.append(
        SafeCapsuleRecord("user_signal", source_index, 0, unit)
    )
```

Do not change `_strip_prohibited_content`, secret scrubbing, turn matching, subagent filtering, assistant classification, or direct proposition grammars.

- [ ] **Step 5: Run the focused Capsule suite and verify GREEN**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONPATH=(Get-Location).Path
& 'D:\tmp\github\agent-global-context\.venv\Scripts\python.exe' -m pytest `
  -p no:cacheprovider --basetemp 'D:\tmp_test\sc1-green' -q `
  tests/test_capture_capsule_safety.py
```

Expected: all Capsule safety tests pass; uncertainty, secrets, structural payloads, questions, subagents, and cross-turn records remain excluded.

- [ ] **Step 6: Commit the first behavior slice**

```powershell
git add -- .llm-wiki/bugs/2026-08-22-semantic-capture-empty.md `
  tests/test_capture_capsule_safety.py agc_runtime/capture_safety.py
git commit -m "fix(capture): admit bounded semantic user context"
```

---

### Task 2: Persist Only Tentative Inferences from Broader Evidence

**Files:**
- Modify: `tests/test_capture_capsule_safety.py`
- Modify: `tests/test_capture_extractor.py`
- Modify: `agc_runtime/capture_safety.py`
- Modify: `agc_runtime/codex_extractor.py`

**Interfaces:**
- Consumes: semantic user evidence retained by Task 1; `ObservationDraft.confidence`; `_statement_proposition()`; `_capsule_evidence()`.
- Produces: `_provenance_supports_mode()` accepts non-deterministic user evidence only for an atomic `agent_inferred`/`tentative` draft; the extractor instruction explicitly selects this mode.

- [ ] **Step 1: Write failing persistence and prompt tests**

Add to `tests/test_capture_capsule_safety.py`:

```python
def test_compound_user_evidence_accepts_only_tentative_agent_inference():
    from agc_runtime.capture_capsule import CapsulePolicy, build_capsule
    from agc_runtime.capture_safety import persistence_gate

    evidence = (
        "我觉得这个可以分成两个任务，首先继续设计架构，"
        "第二个做一个最小的企业微信机器人接入。"
    )
    capsule = build_capsule(
        (_record("user", evidence),),
        _ref(),
        CapsulePolicy(project_scope="project:stable"),
    ).capsule
    inferred = _draft(
        "用户希望继续设计架构。",
        evidence,
        mode="agent_inferred",
        signal_type="decision_or_constraint",
        kind="goal",
        category="project",
    )
    direct = _draft(
        "用户希望继续设计架构。",
        evidence,
        mode="direct",
        signal_type="decision_or_constraint",
        kind="goal",
        category="project",
    )

    accepted = persistence_gate((inferred,), capsule)
    rejected = persistence_gate((direct,), capsule)

    assert len(accepted.accepted) == 1
    assert accepted.accepted[0].assertion_mode == "agent_inferred"
    assert accepted.accepted[0].confidence == "tentative"
    assert rejected.accepted == ()
    assert rejected.filtered_policy_count == 1
```

Extend the existing instruction assertion in `tests/test_capture_extractor.py`:

```python
assert "agent_inferred" in payload["instruction"]
assert "confidence=tentative" in payload["instruction"]
assert "Never label a colloquial or compound signal as direct" in payload["instruction"]
```

- [ ] **Step 2: Run both tests and verify RED**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONPATH=(Get-Location).Path
& 'D:\tmp\github\agent-global-context\.venv\Scripts\python.exe' -m pytest `
  -p no:cacheprovider --basetemp 'D:\tmp_test\sc2-red' -q `
  tests/test_capture_capsule_safety.py::test_compound_user_evidence_accepts_only_tentative_agent_inference `
  tests/test_capture_extractor.py::test_extractor_stdin_is_canonical_and_contains_no_filesystem_context
```

Expected: the inferred draft is policy-filtered and the new instruction substrings are absent.

- [ ] **Step 3: Implement mode-aware user provenance**

Inside `_provenance_supports_mode()` in `agc_runtime/capture_safety.py`, retain exact proposition equivalence for direct mode and add only this semantic alternative:

```python
semantic_user_support = (
    draft.assertion_mode == "agent_inferred"
    and draft.confidence == "tentative"
)
user_supported = (
    "user_signal" in provenance
    and "user_signal" in allowed
    and (
        _user_proposition(evidence) == proposition
        or semantic_user_support
    )
)
```

Do not relax atomic statement validation, exact evidence membership, assertive evidence checks, project scope equality, sensitivity checks, or the direct and behavior-observed paths.

- [ ] **Step 4: Update the schema-constrained extraction instruction**

Append this exact policy to `_EXTRACTION_INSTRUCTION` in `agc_runtime/codex_extractor.py`:

```python
"For a colloquial or compound user signal, split durable meaning into atomic "
"drafts, copy the full supporting signal as verbatim evidence, use "
"assertion_mode=agent_inferred and confidence=tentative, and preserve "
"project_scope. Never label a colloquial or compound signal as direct. "
```

Keep the existing direct transformation examples and untrusted-data instruction unchanged.

- [ ] **Step 5: Run focused and adjacent tests and verify GREEN**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONPATH=(Get-Location).Path
& 'D:\tmp\github\agent-global-context\.venv\Scripts\python.exe' -m pytest `
  -p no:cacheprovider --basetemp 'D:\tmp_test\sc2-green' -q `
  tests/test_capture_capsule_safety.py tests/test_capture_extractor.py
```

Expected: all tests pass, including existing direct Chinese canonicalization, adversarial evidence, secret, Unicode, and output-schema cases.

- [ ] **Step 6: Commit the persistence slice**

```powershell
git add -- tests/test_capture_capsule_safety.py tests/test_capture_extractor.py `
  agc_runtime/capture_safety.py agc_runtime/codex_extractor.py
git commit -m "fix(capture): collect tentative semantic candidates"
```

---

### Task 3: Complete Empty Capsules without Budget or Model Calls

**Files:**
- Modify: `tests/test_capture_manual_runner.py`
- Modify: `agc_runtime/capture_capsule.py`
- Modify: `agc_runtime/capture_runner.py`

**Interfaces:**
- Produces: `capsule_has_durable_signal(capsule: TaskCapsule) -> bool`.
- Consumes: `CaptureStore.begin_extraction()` and `CaptureStore.commit_extraction(..., reservation=None, settlement=None)`; existing receipt schema value `no_durable_signal`.

- [ ] **Step 1: Make the fake adapter configurable and write the failing zero-call test**

Add `user_signals: tuple[str, ...] = ("I prefer Rust.",)` to `FakeAdapter` and pass it into `TaskCapsule(user_signals=self.user_signals)`.

Add:

```python
def test_empty_capsule_completes_without_reservation_or_extractor_call(tmp_path: Path):
    paths, adapter, extractor, preparation = _prepared(tmp_path)
    adapter.user_signals = ()

    report = CaptureRunner(
        paths, (adapter,), extractor, preparation
    ).run_manual_backfill(
        authorization_digest=preparation.authorization_digest,
        max_items=20,
        now=RUN_AT,
    )

    receipt = json.loads(next(paths.capture.receipts.glob("*.json")).read_text("utf-8"))
    assert report.attempted_count == report.completed_count == 1
    assert report.observation_count == 0
    assert report.reserved_attempt_count == 0
    assert report.extractor_call_count == 0
    assert report.charged_tokens == 0
    assert extractor.extract_calls == 0
    assert receipt["status"] == "complete"
    assert receipt["zero_reason"] == "no_durable_signal"
    assert receipt["token_usage"] == {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
    }
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONPATH=(Get-Location).Path
& 'D:\tmp\github\agent-global-context\.venv\Scripts\python.exe' -m pytest `
  -p no:cacheprovider --basetemp 'D:\tmp_test\sc3-red' -q `
  tests/test_capture_manual_runner.py::test_empty_capsule_completes_without_reservation_or_extractor_call
```

Expected: FAIL because the Runner reserves budget and calls the Extractor.

- [ ] **Step 3: Add the Capsule semantic-signal helper**

Add to `agc_runtime/capture_capsule.py`:

```python
def capsule_has_durable_signal(capsule: TaskCapsule) -> bool:
    if not isinstance(capsule, TaskCapsule):
        raise _contract_error()
    return any(
        (
            capsule.user_signals,
            capsule.decisions_results,
            capsule.reusable_methods,
            capsule.next_steps,
        )
    )
```

Export it in `__all__`. Task title and file locators alone must not trigger a model call.

- [ ] **Step 4: Commit a zero-token terminal receipt before reservation**

Import `capsule_has_durable_signal` with `CapsulePolicy` inside `_run_manual_backfill_locked()`. Immediately after `adapter.load_capsule(...)`, add the no-signal branch before `budget.reserve(...)`:

```python
if not capsule_has_durable_signal(capsule_result.capsule):
    extracting = store.begin_extraction(
        lease, capsule_result, extractor_descriptor, now=now
    )
    terminal = CaptureReceipt.from_mapping(
        {
            **extracting.to_mapping(),
            "status": "complete",
            "updated_at": now,
            "observation_count": 0,
            "filtered_counts": {
                "safety": 0,
                "policy": 0,
                "over_limit": 0,
            },
            "duplicate_suppression_count": 0,
            "zero_reason": "no_durable_signal",
        }
    )
    store.commit_extraction(lease, (), terminal)
    completed += 1
    continue
```

Do not create a reservation or settlement for this branch. Preserve the zero token usage and existing usage-quality value bound to the receipt.

- [ ] **Step 5: Run Runner, Store, and transaction suites and verify GREEN**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONPATH=(Get-Location).Path
& 'D:\tmp\github\agent-global-context\.venv\Scripts\python.exe' -m pytest `
  -p no:cacheprovider --basetemp 'D:\tmp_test\sc3-green' -q `
  tests/test_capture_manual_runner.py tests/test_capture_store.py `
  tests/test_capture_transaction.py tests/test_capture_manual_backfill_end_to_end.py
```

Expected: all selected tests pass; non-empty Capsules still reserve, call, settle, and report `extractor_empty` when the fake Extractor returns no drafts.

- [ ] **Step 6: Commit the zero-call slice**

```powershell
git add -- tests/test_capture_manual_runner.py `
  agc_runtime/capture_capsule.py agc_runtime/capture_runner.py
git commit -m "fix(capture): skip model calls for empty capsules"
```

---

### Task 4: Verify Source, Package, and Installed Runtime

**Files:**
- Modify: `.llm-wiki/bugs/2026-08-22-semantic-capture-empty.md`
- Create: `.llm-wiki/verification/2026-08-22-semantic-capture-empty.md`
- Build artifact only: `D:\tmp_test\agc-semantic-capture-release-20260822\dist\*.whl`
- Install target: the content-addressed directory reported by the installer under `C:\Users\admin\.agent-global-context-runtime\venvs`

**Interfaces:**
- Consumes: committed branch source and `scripts/install-local.ps1`.
- Produces: focused/full regression evidence, clean wheel evidence, active immutable Runtime launcher, and installed source/hash evidence.

- [ ] **Step 1: Run the complete relevant Capture regression set**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONPATH=(Get-Location).Path
& 'D:\tmp\github\agent-global-context\.venv\Scripts\python.exe' -m pytest `
  -p no:cacheprovider --basetemp 'D:\tmp_test\sc-rel' -q `
  tests/test_capture_capsule_safety.py tests/test_capture_extractor.py `
  tests/test_capture_manual_runner.py tests/test_capture_manual_backfill_end_to_end.py `
  tests/test_capture_store.py tests/test_capture_transaction.py `
  tests/test_capture_contracts.py tests/test_capture_cli.py `
  tests/test_capture_backfill.py tests/test_codex_source_adapter.py `
  tests/test_codex_app_runtime.py
```

Expected: all selected tests pass with zero failures.

- [ ] **Step 2: Run the full repository suite with a short basetemp**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONPATH=(Get-Location).Path
& 'D:\tmp\github\agent-global-context\.venv\Scripts\python.exe' -m pytest `
  -p no:cacheprovider --basetemp 'D:\tmp_test\sf' -q
```

Expected: no new failures. If the two known CRLF byte-idempotence tests remain red, record their exact names as pre-existing baseline failures. The long-path test must pass with this short basetemp.

- [ ] **Step 3: Build and inspect a clean wheel from committed source**

Create `D:\tmp_test\agc-semantic-capture-release-20260822`, export committed `HEAD` with `git archive`, build with:

```powershell
& 'D:\tmp\github\agent-global-context\.venv\Scripts\python.exe' -m build `
  --wheel --no-isolation --outdir 'D:\tmp_test\agc-semantic-capture-release-20260822\dist'
```

Install the wheel into `D:\tmp_test\agc-semantic-capture-release-20260822\installed` with `pip --no-deps --target`, import `agc_runtime.capture_safety`, `agc_runtime.capture_runner`, and `agc_runtime.codex_extractor`, and verify the installed files contain the semantic-mode prompt, `capsule_has_durable_signal`, and the no-signal branch.

- [ ] **Step 4: Install the committed immutable Runtime**

Run:

```powershell
$repo = (Get-Location).Path
& "$repo\scripts\install-local.ps1" `
  -RepositoryRoot $repo `
  -SkillsRoot 'C:\Users\admin\.agents\skills' `
  -CodexConfig 'C:\Users\admin\.codex-clean-20260710\config.toml' `
  -MemoryRoot 'C:\Users\admin\.agent-global-context-v2' `
  -InstallRoot 'C:\Users\admin\.agent-global-context-runtime' `
  -PythonExecutable 'D:\tmp\github\agent-global-context\.venv\Scripts\python.exe'
```

Expected: exit 0; a new content-addressed venv is validated before stable launchers switch; the prior venv remains recoverable; production stays `scanner_only`, Hook disabled, and formal memory count 24.

- [ ] **Step 5: Record source and installed verification evidence**

Write `.llm-wiki/verification/2026-08-22-semantic-capture-empty.md` with exact test commands/counts, known baseline failures, wheel SHA-256, installed venv path, stable launcher target, installed/source file hashes, production Capture mode, and formal-memory count. Update the Bug Brief Flow Record through `testing`; keep live Pilot and archive pending.

- [ ] **Step 6: Commit verification records**

```powershell
git add -- .llm-wiki/bugs/2026-08-22-semantic-capture-empty.md `
  .llm-wiki/verification/2026-08-22-semantic-capture-empty.md
git commit -m "docs: verify semantic capture runtime"
```

---

### Task 5: Run an Authorized Isolated Pilot and Merge Main

**Files:**
- Pilot only: `D:\tmp_test\agc-semantic-capture-pilot-20260822\source\...jsonl`
- Pilot only: `D:\tmp_test\agc-semantic-capture-pilot-20260822\memory\config.yaml`
- Modify: `.llm-wiki/bugs/2026-08-22-semantic-capture-empty.md`
- Modify: `.llm-wiki/verification/2026-08-22-semantic-capture-empty.md`

**Interfaces:**
- Consumes: installed `C:\Users\admin\.agent-global-context-runtime\bin\agc-capture.cmd`, one hash-verified historical Session copy, and a fresh `prepare-backfill` authorization digest.
- Produces: at least one `agent_inferred`/`tentative` Pilot observation, zero silent loss, unchanged production formal memory, final documentation commit, and merged `main`.

- [ ] **Step 1: Prepare the isolated Pilot without calling the model**

Create the Pilot root under `D:\tmp_test`. Copy only:

```text
C:\Users\admin\.codex-clean-20260710\sessions\2026\08\16\rollout-2026-08-16T18-13-25-01a00a0f-d860-7df1-b466-f8eae35de520.jsonl
```

Preserve its relative `sessions\2026\08\16` layout, compare source and copy SHA-256, initialize the Pilot memory root, and configure `scanner_only`, the Pilot source root, `codex-app`, `gpt-5.6-sol`, one worker, and a maximum Pilot budget of 6,000 tokens. Run installed `scan` and `prepare-backfill`; these steps must make zero model calls.

- [ ] **Step 2: Request exact external-payload authorization**

Present the fresh digest, exact source Session, destination `OpenAI gpt-5.6-sol`, `max-items 1`, maximum 6,000 tokens, and no automatic promotion. Do not run `backfill` until the user explicitly approves that exact payload and destination.

- [ ] **Step 3: Run one authorized installed backfill item**

After approval, use the exact digest returned by the immediately preceding `prepare-backfill` response:

```powershell
$prepared = & 'C:\Users\admin\.agent-global-context-runtime\bin\agc-capture.cmd' `
  prepare-backfill --root 'D:\tmp_test\agc-semantic-capture-pilot-20260822\memory' `
  --max-items 1 | ConvertFrom-Json
$digest = $prepared.data.authorization_digest
& 'C:\Users\admin\.agent-global-context-runtime\bin\agc-capture.cmd' `
  backfill --root 'D:\tmp_test\agc-semantic-capture-pilot-20260822\memory' `
  --authorization-digest $digest --max-items 1 --once
```

Expected: one completed item, one extractor call, at least one observation, zero failure, zero silent loss, and charged usage no greater than 6,000 tokens.

- [ ] **Step 4: Inspect the candidate and production invariants**

Use installed read operations to verify the Pilot observation has `assertion.mode=agent_inferred`, `confidence=tentative`, exact Pilot project scope, and `processing_state=collected`. Verify production formal `memory_count=24`, production stays `scanner_only`, Hook remains disabled, and no Pilot path appears in production configuration or receipts. Do not promote the Pilot observation.

- [ ] **Step 5: Finalize lifecycle evidence and commit**

Set the Bug Brief status to `verified-installed`, finish the Flow Record, and add Pilot digest, item count, usage, observation ID, assertion mode, confidence, silent-loss count, production invariants, and residual risks to the verification record. Do not include Session text.

```powershell
git add -- .llm-wiki/bugs/2026-08-22-semantic-capture-empty.md `
  .llm-wiki/verification/2026-08-22-semantic-capture-empty.md
git commit -m "docs: verify semantic capture pilot"
```

- [ ] **Step 6: Run the completion audit on the branch**

Verify:

```powershell
git status --short
git diff --check main...HEAD
git log --oneline main..HEAD
```

Re-run the focused relevant Capture suite from Task 4 Step 1. Expected: clean status, clean diff, all relevant tests pass, and the branch contains the design, three behavior slices, and verification evidence.

- [ ] **Step 7: Merge the verified branch into main**

Confirm the primary checkout `D:\tmp\github\agent-global-context` is still clean and on `main`. Then run:

```powershell
git -C 'D:\tmp\github\agent-global-context' merge --ff-only `
  codex/fix-semantic-capture-empty
```

If `main` advanced and fast-forward is impossible, stop, inspect the divergence, merge `main` into the fix branch non-destructively, rerun the relevant suite, and only then merge. Never reset or discard either branch.

- [ ] **Step 8: Verify authoritative main state**

Run the relevant Capture suite against `main`, verify `git status --short` is clean, verify `main` contains every fix and evidence commit, and verify the installed Runtime hashes still match the merged source. Only after all requirements are proven should the active goal be marked complete.
