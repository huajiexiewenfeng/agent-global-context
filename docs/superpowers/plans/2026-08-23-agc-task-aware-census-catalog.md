# AGC Task-Aware Census Catalog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a derived canonical Census hot catalog and deterministic task-aware backfill selection so production-scale Capture reads finish in seconds and bounded batches prioritize useful memory evidence.

**Architecture:** Frozen Census runs remain immutable cold truth. `CaptureStore` atomically materializes one catalog record per unique revision and validates hot reads against run manifests; Hard Forget invalidates the entire derived catalog and backup excludes it. `CaptureRunner` locally builds and ranks privacy-cleaned Capsules, then round-robins task groups with a three-per-task invocation cap while preserving all unselected receipts.

**Tech Stack:** Python 3.11+, dataclasses, pathlib, canonical JSON/atomic directory publication already in `capture_transaction.py`, pytest, existing immutable wheel/venv installer flow.

**Execution status (2026-08-24):** Implementation, regression, packaging, production read-only acceptance, immutable Runtime 0.4.1 installation, Codex App restart, and live MCP verification are complete on `codex/task-aware-census-catalog`. The branch is synchronized to GitHub; merge or Pull Request remains a separate integration choice.

## Global Constraints

- Preserve all existing frozen Census files as cold audit evidence.
- Do not aggregate a whole Codex Session into one model prompt.
- Do not loosen pre-Capsule, persistence, authorization, review, token-budget, or formal-memory gates.
- Do not automatically promote observations.
- Do not send historical content during implementation or acceptance; no Extractor/model call without a fresh exact authorization.
- Limit each runner invocation to at most three selected revisions per task; unselected receipts remain pending.
- Root every test temporary directory under `D:\tmp_test` by setting `TEMP`, `TMP`, and pytest `--basetemp`.
- Use TDD: each production behavior is preceded by a focused test that is observed failing for the expected reason.

---

## File Structure

- Modify `agc_runtime/paths.py`: expose the managed `census_catalog` directory.
- Modify `agc_runtime/capture_store.py`: catalog schema, run-manifest signature, cold rebuild, hot read, incremental refresh, and snapshot integration.
- Modify `agc_runtime/capture_runner.py`: deterministic Capsule score, task grouping, fair selection, and selected Capsule reuse.
- Modify `agc_runtime/capture_forget_service.py`: discard derived catalog entries in revision forget projections.
- Modify `agc_runtime/capture_forget_transaction.py`: allow exact transactional writes/deletes inside `census-catalog`.
- Modify `agc_runtime/admin_service.py`: validate catalog through `CaptureStore` without treating it as durable backup truth.
- Modify `agc_runtime/managed_backup.py`: keep `census-catalog` outside the backup allowlist and prove that behavior.
- Modify `tests/test_capture_store.py`: catalog construction, deduplication, hot member avoidance, stale rebuild, conflicts, and staging recovery.
- Modify `tests/test_capture_manual_runner.py`: score order, task fairness, cap, determinism, selected Capsule reuse, and pending receipts.
- Modify `tests/test_capture_forget.py`: transactional catalog invalidation and no residual target identity.
- Modify `tests/test_capture_backup_restore.py`: derived catalog exclusion and restore rebuild.
- Modify `pyproject.toml` and `agc_runtime/__init__.py`: patch release version.
- Modify `docs/capture-operations.md`: explain one-time cold catalog build, hot reads, full audit, and task-aware selection.
- Update `.llm-wiki/bugs/2026-08-23-census-catalog-task-aware-backfill.md`, `.llm-wiki/working-context/2026-08-23-census-catalog-task-aware-backfill.md`, `.llm-wiki/verification/2026-08-23-census-catalog-task-aware-backfill.md`, `.llm-wiki/handoff/2026-08-23-census-catalog-task-aware-backfill-handoff.md`, `.llm-wiki/artifacts/index.md`, and `.llm-wiki/log.md`: lifecycle and verification evidence.

### Task 1: Canonical Census Catalog Contract and Cold Build

**Files:**
- Modify: `agc_runtime/paths.py`
- Modify: `agc_runtime/capture_store.py`
- Test: `tests/test_capture_store.py`

**Interfaces:**
- Produces: `CapturePaths.census_catalog: Path`
- Produces: `CaptureStore.rebuild_census_catalog() -> tuple[RevisionRef, ...]`
- Produces: private `CaptureStore._read_census_catalog(runs: Sequence[CensusRun]) -> tuple[RevisionRef, ...]`
- Produces: Windows-safe packed catalog layout `census-catalog/active.json` and `census-catalog/g/<catalog-id>/{manifest.json,revisions.json}`

- [ ] **Step 1: Write the failing deduplication and conflict tests**

Add tests that freeze two overlapping runs containing the same revision, call `rebuild_census_catalog()`, and assert one revision file plus a strict manifest. Add a second test with conflicting metadata for the same key and assert `ValueError("revision_metadata_conflict")` and no published catalog.

```python
revisions = store.rebuild_census_catalog()
assert revisions == (revision,)
active = read_json(paths.capture.census_catalog / "active.json")
generation = paths.capture.census_catalog / "g" / active["catalog_id"]
assert sorted(path.name for path in generation.iterdir()) == [
    "manifest.json", "revisions.json"
]
manifest = read_json(generation / "manifest.json")
assert manifest["catalog_schema_version"] == "census-catalog-v2"
assert manifest["revision_count"] == 1
```

- [ ] **Step 2: Run the tests and verify RED**

```powershell
$env:TEMP='D:\tmp_test'; $env:TMP='D:\tmp_test'
python -m pytest tests/test_capture_store.py -q --basetemp D:\tmp_test\agc-catalog-task1-red
```

Expected: fail because `CapturePaths.census_catalog` and `rebuild_census_catalog()` do not exist.

- [ ] **Step 3: Add the path and strict catalog helpers**

Add `census_catalog=root / "census-catalog"` to `CapturePaths.from_runtime()` and `directories()`. In `capture_store.py`, add constants and canonical digests:

```python
_CENSUS_CATALOG_SCHEMA_VERSION = "census-catalog-v2"

def _catalog_digest(values: Sequence[Mapping[str, object]]) -> str:
    return hashlib.sha256(canonical_json_bytes({"values": list(values)})).hexdigest()
```

Implement a full cold rebuild that calls the existing strict frozen-run reader, merges legacy Census records, rejects metadata conflicts with `same_revision_metadata`, and derives a content-addressed `catalog_id`. Install the immutable generation with `atomic_install_json_directory`, then publish `active.json` with `atomic_write_json`. Hot readers ignore inactive or interrupted generations; under the same lock, cleanup retains only the active generation.

- [ ] **Step 4: Run the focused tests and verify GREEN**

```powershell
$env:TEMP='D:\tmp_test'; $env:TMP='D:\tmp_test'
python -m pytest tests/test_capture_store.py -q --basetemp D:\tmp_test\agc-catalog-task1-green
```

Expected: all `test_capture_store.py` tests pass.

- [ ] **Step 5: Commit the catalog contract**

```powershell
git add agc_runtime/paths.py agc_runtime/capture_store.py tests/test_capture_store.py
git commit -m "feat: add canonical capture census catalog"
```

### Task 2: Hot Snapshot Reads and Incremental Catalog Refresh

**Files:**
- Modify: `agc_runtime/capture_store.py`
- Modify: `agc_runtime/admin_service.py`
- Test: `tests/test_capture_store.py`
- Test: `tests/test_capture_census_end_to_end.py`

**Interfaces:**
- Consumes: strict catalog layout from Task 1
- Produces: `CaptureStore.ensure_census_catalog() -> tuple[RevisionRef, ...]`
- Produces: private manifest-only `_read_census_run_manifest(path: Path) -> CensusRun`
- Changes: `read_snapshot()` and `frozen_revisions()` use the valid catalog

- [ ] **Step 1: Write failing hot-path and invalidation tests**

Instrument `agc_runtime.capture_store.read_json` after the first catalog build. Assert a second `read_snapshot()` reads `run.json` and catalog files but never a path whose parent is `members`. Freeze another run and assert the next read includes the new revision and refreshes the catalog. Create a hidden interrupted catalog stage and assert it is ignored.

```python
member_reads = []
original = capture_store.read_json

def counted(path):
    if path.parent.name == "members":
        member_reads.append(path)
    return original(path)

monkeypatch.setattr(capture_store, "read_json", counted)
snapshot = store.read_snapshot()
assert set(snapshot.census) == {first, second}
assert member_reads == []
```

- [ ] **Step 2: Run the tests and verify RED**

```powershell
$env:TEMP='D:\tmp_test'; $env:TMP='D:\tmp_test'
python -m pytest tests/test_capture_store.py tests/test_capture_census_end_to_end.py -q --basetemp D:\tmp_test\agc-catalog-task2-red
```

Expected: member reads are recorded because the snapshot still calls `frozen_revision_records()`.

- [ ] **Step 3: Implement manifest validation and hot reads**

Implement `_read_census_run_manifest()` without iterating member files. Validate `run.json`, directory identity, binding, seven-day window contract, and revision-key uniqueness. `ensure_census_catalog()` acquires the Capture write lock, compares catalog run digest and revision-key union to current run manifests, and performs one cold rebuild only when missing/stale/invalid. `read_snapshot()` obtains catalog revisions once and reuses the already decoded run manifests for both `census` and `census_runs`.

Update `freeze_census()` under the existing lock:

```python
prior = self._try_read_catalog_for_manifests(prior_runs)
atomic_install_json_directory(run_path, files, directories=("members",))
self._publish_catalog((*prior, *validated), runs=(*prior_runs, census))
```

If no prior valid catalog exists, perform the full cold rebuild after the run is durable. A crash between run publication and catalog refresh leaves a detectable stale catalog.

- [ ] **Step 4: Add admin validation of the derived namespace**

Make `_validate_capture()` call the strict catalog reader when `census-catalog` exists. Report only fixed safe Capture diagnostics. Do not add `census-catalog` to backup capabilities or durable Capture schema objects.

- [ ] **Step 5: Run focused tests and verify GREEN**

```powershell
$env:TEMP='D:\tmp_test'; $env:TMP='D:\tmp_test'
python -m pytest tests/test_capture_store.py tests/test_capture_census_end_to_end.py tests/test_capture_status.py -q --basetemp D:\tmp_test\agc-catalog-task2-green
```

Expected: all selected tests pass and the explicit hot-path test reports zero member reads.

- [ ] **Step 6: Commit hot read integration**

```powershell
git add agc_runtime/capture_store.py agc_runtime/admin_service.py tests/test_capture_store.py tests/test_capture_census_end_to_end.py
git commit -m "perf: read capture census through canonical catalog"
```

### Task 3: Hard Forget and Backup Boundaries

**Files:**
- Modify: `agc_runtime/capture_forget_service.py`
- Modify: `agc_runtime/capture_forget_transaction.py`
- Modify: `agc_runtime/managed_backup.py`
- Test: `tests/test_capture_forget.py`
- Test: `tests/test_capture_backup_restore.py`

**Interfaces:**
- Consumes: `CapturePaths.census_catalog`
- Produces: revision Hard Forget deletes the entire derived catalog transactionally
- Preserves: backup contains canonical projected Census truth but no `census-catalog` entries

- [ ] **Step 1: Write failing forget and backup tests**

Build a catalog, perform exact revision forget, and assert no catalog file survives, the target is absent from rewritten runs, and a subsequent snapshot rebuild contains only remaining revisions. Build a backup before forget and assert no archive name begins with `.runtime/capture/census-catalog/`. Restore and assert the catalog is rebuilt locally on first snapshot.

```python
response = dispatch_write(paths, _request({"type": "revision", **target.key.to_mapping()}))
assert response.status == "accepted"
assert not paths.capture.census_catalog.exists()
assert CaptureStore(paths).frozen_revisions() == (remaining,)
```

- [ ] **Step 2: Run the tests and verify RED**

```powershell
$env:TEMP='D:\tmp_test'; $env:TMP='D:\tmp_test'
python -m pytest tests/test_capture_forget.py tests/test_capture_backup_restore.py -q --basetemp D:\tmp_test\agc-catalog-task3-red
```

Expected: Hard Forget leaves derived catalog artifacts or rejects their unknown namespace.

- [ ] **Step 3: Invalidate the catalog inside the forget projection**

Add `census-catalog` to the exact primary namespace allowlist. In `_updated_revision()`, remove every entry with the prefix `.runtime/capture/census-catalog/` before the residual-needle fail-closed scan. The existing transaction then records before-images and deletes every catalog file with rollback support. Extend empty-directory cleanup only to the exact catalog root and never to `capture.root`.

- [ ] **Step 4: Keep the catalog outside backup truth**

Do not add `census-catalog` to `_CAPTURE_ALLOWLIST`. Add an explicit exclusion assertion in `managed_files()` so a future allowlist expansion cannot silently archive it. Restore creates normal Capture directories and lets `ensure_census_catalog()` rebuild from restored canonical Census projection/frozen truth.

- [ ] **Step 5: Run the focused tests and verify GREEN**

```powershell
$env:TEMP='D:\tmp_test'; $env:TMP='D:\tmp_test'
python -m pytest tests/test_capture_forget.py tests/test_capture_backup_restore.py -q --basetemp D:\tmp_test\agc-catalog-task3-green
```

Expected: all selected tests pass; target identifiers are absent from primary and backup projections; restored reads rebuild the catalog.

- [ ] **Step 6: Commit privacy and backup behavior**

```powershell
git add agc_runtime/capture_forget_service.py agc_runtime/capture_forget_transaction.py agc_runtime/managed_backup.py tests/test_capture_forget.py tests/test_capture_backup_restore.py
git commit -m "fix: invalidate derived census catalog on forget"
```

### Task 4: Deterministic Task-Aware Capsule Ranking

**Files:**
- Modify: `agc_runtime/capture_runner.py`
- Test: `tests/test_capture_manual_runner.py`

**Interfaces:**
- Produces: private `_capsule_rank(capsule_result: CapsuleResult, receipt: CaptureReceipt) -> tuple[object, ...]`
- Produces: private `_select_ready(revisions, receipts, adapters, policy, max_items) -> tuple[tuple[CaptureReceipt, CapsuleResult | None], ...]`
- Preserves: authorization validation and budget reservation occur only after final selection

- [ ] **Step 1: Extend the fake adapter for per-revision Capsules**

Add a `capsules_by_revision` mapping to `FakeAdapter`. Construct Capsules with distinct `user_signals`, `decisions_results`, `reusable_methods`, and `next_steps` so tests exercise real rank fields rather than mocked rank values.

- [ ] **Step 2: Write failing rank, fairness, determinism, and pending tests**

Create four revisions for task A and two for task B. Assert a `max_items=4` invocation selects no more than three from A, includes B, prefers A's decision/reusable-method turns over an acknowledgement-only turn, and leaves every unselected receipt in `discovered`. Run the same selector with reversed receipt input and assert identical selected keys.

```python
report = CaptureRunner(paths, (adapter,), extractor, preparation).run_manual_backfill(
    authorization_digest=preparation.authorization_digest,
    max_items=4,
    now=RUN_AT,
)
assert extractor.seen_revision_ids == [
    "a-decision", "b-decision", "a-method", "b-signal"
]
assert max(Counter(item.split("-", 1)[0] for item in extractor.seen_revision_ids).values()) <= 3
assert receipt_by_id["a-weak"].status == "discovered"
```

Expose behavior through `run_manual_backfill()` assertions in production tests; do not add a public test-only method to `CaptureRunner`.

- [ ] **Step 3: Run the tests and verify RED**

```powershell
$env:TEMP='D:\tmp_test'; $env:TMP='D:\tmp_test'
python -m pytest tests/test_capture_manual_runner.py -q --basetemp D:\tmp_test\agc-ranking-task4-red
```

Expected: extraction order follows discovery order and exceeds the intended per-task selection distribution.

- [ ] **Step 4: Implement the deterministic score**

Use only the existing cleaned `TaskCapsule` fields:

```python
strong = len(capsule.decisions_results) + len(capsule.reusable_methods)
categories = sum(bool(values) for values in (
    capsule.user_signals,
    capsule.decisions_results,
    capsule.reusable_methods,
    capsule.next_steps,
))
codepoints = sum(len(text) for values in (
    capsule.user_signals,
    capsule.decisions_results,
    capsule.reusable_methods,
    capsule.next_steps,
) for text in values)
rank = (
    bool(strong), strong, categories, len(capsule.user_signals),
    min(codepoints, 12_000), capsule.completed_at, receipt.receipt_id,
)
```

Sort higher signal and later completion first with an explicit stable tie-breaker. Keep empty Capsules last. Do not inspect raw records or add new semantic heuristics.

- [ ] **Step 5: Implement fair selection and Capsule reuse**

Group by `(adapter_id, source_root_id, task_id)`, locally call `load_capsule()` for ranking, order each group by rank, and round-robin groups until `max_items` or three items per task is reached. Cache successful `CapsuleResult` objects by `CaptureKey`; the execution loop consumes the cached result instead of calling `load_capsule()` again. A rank-time load failure remains pending unless it is selected for the existing execution error path.

- [ ] **Step 6: Add the selected-Capsule reuse assertion**

For a two-revision successful batch, assert `adapter.load_calls == 2`, not four, and `extractor.extract_calls == 2`. Assert `report.attempted_count <= max_items` and external calls never exceed attempted non-empty selected Capsules.

- [ ] **Step 7: Run focused runner tests and verify GREEN**

```powershell
$env:TEMP='D:\tmp_test'; $env:TMP='D:\tmp_test'
python -m pytest tests/test_capture_manual_runner.py tests/test_capture_backfill.py tests/test_capture_token_budget.py -q --basetemp D:\tmp_test\agc-ranking-task4-green
```

Expected: all selected tests pass with deterministic cross-task order and no duplicate Capsule loads for selected items.

- [ ] **Step 8: Commit task-aware selection**

```powershell
git add agc_runtime/capture_runner.py tests/test_capture_manual_runner.py
git commit -m "feat: prioritize high-signal capture tasks"
```

### Task 5: Regression, Release, Installation, and Production-Scale Acceptance

**Files:**
- Modify: `pyproject.toml`
- Modify: `agc_runtime/__init__.py`
- Modify: `docs/capture-operations.md`
- Modify: `.llm-wiki/bugs/2026-08-23-census-catalog-task-aware-backfill.md`
- Modify: `.llm-wiki/working-context/2026-08-23-census-catalog-task-aware-backfill.md`
- Create: `.llm-wiki/verification/2026-08-23-census-catalog-task-aware-backfill.md`
- Create: `.llm-wiki/handoff/2026-08-23-census-catalog-task-aware-backfill-handoff.md`
- Modify: `.llm-wiki/artifacts/index.md`
- Modify: `.llm-wiki/log.md`

**Interfaces:**
- Produces: patch release `0.4.1`
- Produces: installed immutable Runtime route with unchanged model boundary
- Produces: cold/hot benchmark and no-egress/formal-memory evidence

- [ ] **Step 1: Run the complete focused Capture regression**

```powershell
$env:TEMP='D:\tmp_test'; $env:TMP='D:\tmp_test'
python -m pytest tests/test_capture_*.py tests/test_codex_source_adapter.py -q --basetemp D:\tmp_test\agc-catalog-capture-regression
```

Expected: zero failures. Record exact pass count and elapsed time from fresh output.

- [ ] **Step 2: Run the full repository suite and integrity checks**

```powershell
$env:TEMP='D:\tmp_test'; $env:TMP='D:\tmp_test'
python -m pytest -q --basetemp D:\tmp_test\agc-catalog-full
python -m compileall -q agc_runtime tests
git diff --check
```

Expected: zero new failures, compile exit 0, and diff check exit 0. Any pre-existing failure must be reproduced on unmodified `main` before it can be classified as baseline.

- [ ] **Step 3: Update version and operations documentation**

Set both runtime version declarations to `0.4.1`. Document that first catalog creation is a one-time full cold audit; normal reads use run manifests plus unique revisions; Hard Forget invalidates the catalog; backups exclude it; and runner selection is task-aware with a per-invocation cap of three.

- [ ] **Step 4: Build and inspect release artifacts**

```powershell
$env:TEMP='D:\tmp_test'; $env:TMP='D:\tmp_test'
python -m build --wheel --sdist --outdir D:\tmp_test\agc-catalog-dist
python -m zipfile -l D:\tmp_test\agc-catalog-dist\agent_global_context_runtime-0.4.1-py3-none-any.whl
```

Expected: wheel and sdist build successfully; wheel contains the changed runtime modules and no test, production-memory, Session, or catalog data.

- [ ] **Step 5: Install into a new immutable runtime and smoke-test**

Use the repository's existing install script with the new wheel and a new content-addressed venv under `C:\Users\admin\.agent-global-context-runtime\venvs`. Verify `agc --version`, `pip check`, MCP tool enumeration, and installed module hashes against the committed source. Installation may write outside the workspace only with explicit sandbox approval.

- [ ] **Step 6: Run production-scale read-only acceptance**

Record before-state formal-memory hashes, receipt token totals, and observation count. Run one explicit catalog rebuild against the production Capture root without constructing a `CaptureRunner` or Extractor, then time two hot `read_snapshot()` calls. Assert:

```text
unique_catalog_revisions = frozen_unique_revisions
hot_member_json_reads = 0
extractor_calls_delta = 0
charged_tokens_delta = 0
formal_memory_hash_delta = 0
```

Store only content-free counts, timings, hashes, and pass/fail facts under `D:\tmp_test`; do not copy Session text or memory statements.

- [x] **Step 7: Restart/reload the Codex App route if required and verify live status**

Verify runtime version `0.4.1`, production memory-root fingerprint, `scanner_only` mode, paused state, and model boundary `gpt-5.6-sol`. Do not run a backfill without a fresh authorization digest.

- [ ] **Step 8: Complete lifecycle evidence and final verification**

Update the Bug Brief Flow Record, working context, verification report, handoff, artifact index, and log with exact commands, outputs, test-integrity notes, installed hashes, benchmark results, and residual risk. Re-read the approved spec and mark every acceptance item proved, contradicted, or missing.

- [ ] **Step 9: Commit the verified release**

```powershell
git add pyproject.toml agc_runtime/__init__.py docs/capture-operations.md .llm-wiki
git commit -m "release: verify task-aware census catalog 0.4.1"
```

- [ ] **Step 10: Compare branch state and prepare integration**

```powershell
git status --short
git log --oneline main..HEAD
git diff --check main...HEAD
```

Expected: clean worktree, only planned commits, and no whitespace errors. Integration or GitHub push remains a separate external-state action unless already authorized by the user.
