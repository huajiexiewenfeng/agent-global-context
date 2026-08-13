# Agent Global Context Capture Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the deterministic Capture data plane and governance boundary while Capture remains disabled and no Codex source or model is invoked.

**Architecture:** First repair the ordinary Recall activation gate, then add a separate JSON-based Capture namespace with its own strict contracts, two-level idempotency, journaled commit, explicit read views, schema-aware backup/restore, and exact hard forget. Capture reuses only strict UTF-8 I/O, atomic replace, the root writer lock, and the existing three-tool response envelope; it never reuses formal-memory source receipts or writes the Catalog.

**Tech Stack:** Python 3.10+, dataclasses, `typing.Protocol`, PyYAML 6, JSON, SHA-256 canonicalization, pytest 9.1.1, Windows-safe atomic `os.replace`.

## Global Constraints

- Parent contract: `.llm-wiki/requirements/agc-capture-coverage-mvp.md` and `docs/superpowers/specs/2026-08-13-agent-global-context-high-coverage-capture-design.md`.
- This is plan 1 of 4. It must pass before Codex discovery, semantic extraction, or host activation begins.
- `capture.enabled=false`, `capture.mode=off`, and `capture.paused=false` are safe defaults. This plan must not scan `CODEX_HOME`, install a Hook, call a model, or create a scheduled task.
- Do not reuse `contracts.ObservationEnvelope`, `contracts.SourceKey`, `store.MemoryStore`, or `.runtime/receipts/source-keys.json` for Capture.
- Capture objects live outside `memories/`, `candidates/`, `events/`, and ordinary Catalog/Recall.
- Receipts contain no user text, model output, statements, absolute paths, stack traces, or source excerpts.
- Task Capsules do not exist in this plan and no placeholder Capsule file may be created.
- Every task follows red-green TDD and ends in one focused commit. Synthetic fixtures only; never copy a real Codex transcript or personal Observation into tests.
- New text files are strict UTF-8 without BOM and use LF line endings.

## Program Boundary

1. **Capture Core — this plan:** Runtime config, Recall gate, Capture contracts, store, transaction, views, backup/restore, and hard forget.
2. **Codex Source and Census:** metadata-only Hook spool, versioned source adapter, frozen census, Ledger reconciliation, and census-only CLI.
3. **Extractor and Runner:** in-memory Capsule, safety gates, isolated semantic extractor, durable token budget, retry/backpressure, and background Runner.
4. **Host Rollout and Release:** installer, Task Scheduler supervision, route diagnostics, latency gate, staged activation, rollback drill, and release evidence.

## Stable Core Interfaces

Implement these public Python boundaries; implementation helpers may remain private:

```python
@dataclass(frozen=True)
class CaptureKey:
    adapter_id: str
    source_root_id: str
    task_id: str
    revision_id: str


class CaptureStore:
    def ensure_layout(self) -> None: ...
    def reconcile_discovery(self, batch: DiscoveryBatch) -> ReconcileResult: ...
    def acquire_lease(
        self, key: CaptureKey, *, owner_id: str, now: str, ttl_seconds: int
    ) -> CaptureLease | None: ...
    def transition(
        self,
        lease: CaptureLease,
        *,
        expected: frozenset[CaptureStatus],
        target: CaptureStatus,
        patch: ReceiptTransitionPatch,
    ) -> CaptureReceipt: ...
    def commit_extraction(
        self,
        lease: CaptureLease,
        observations: Sequence[CollectedObservation],
        terminal_receipt: CaptureReceipt,
    ) -> CommitResult: ...
    def recover_transactions(self, *, now: str) -> RecoveryReport: ...
```

The source plan may add methods for census and scan state, but it must not change the key, Receipt, Observation, lease, or commit semantics defined here.

---

### Task 1: Make Runtime Configuration Real and Close the Recall Activation Gate

**Files:**
- Create: `agc_runtime/runtime_config.py`
- Create: `agc_runtime/response_budget.py`
- Create: `agc_runtime/default_config.yaml`
- Create: `tests/test_recall_activation_gate.py`
- Create: `tests/test_runtime_config.py`
- Modify: `agc_runtime/catalog.py`
- Modify: `agc_runtime/read_service.py`
- Modify: `agc_runtime/admin_service.py`
- Modify: `templates/memory/config.yaml`
- Modify: `tests/test_catalog_and_read.py`
- Modify: `tests/test_admin_service.py`

**Interfaces:**
- Produces: `load_runtime_config(paths: MemoryPaths) -> RuntimeConfig`.
- Produces: `estimate_tool_response_tokens(response: ToolResponse) -> int`.
- Produces: `fit_overview_response(response, *, budget) -> ToolResponse`.
- Changes Catalog Card schema to include `lifecycle`.
- Ordinary `overview` and `search` use only `lifecycle == "active"`; exact `get/history/evidence` remain unchanged.
- Validates `capture.mode` as `off|scanner_only|runner`; only `off` is activation-ready in this plan because source and extractor capabilities do not exist yet.

- [ ] **Step 1: Add failing configuration and Recall tests**

Create AC-02 tests that prove:

```python
def test_ac_02_lifecycle_and_hard_overview_budget(tmp_path: Path):
    paths = initialized_root_with_active_and_historical_memories(tmp_path)
    response = dispatch_read(paths, {"action": "overview"})
    assert response.status == "accepted"
    assert response.data["estimated_tokens"] <= load_runtime_config(paths).recall.overview_token_budget
    assert {card["lifecycle"] for card in response.data["cards"]} <= {"active"}

    search = dispatch_read(paths, {"action": "search", "query": "shared text"})
    assert {item["lifecycle"] for item in search.data["results"]} <= {"active"}
```

Also cover a root whose fixed counts cannot fit: it must return `status="failed"` and `error.code="response_budget_exceeded"`, never an accepted over-budget response. Require unknown config keys, invalid types, unsafe Capture defaults, and a config/template mismatch to fail validation.

- [ ] **Step 2: Verify RED**

Run:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest `
  tests/test_recall_activation_gate.py tests/test_runtime_config.py `
  tests/test_catalog_and_read.py tests/test_admin_service.py -q `
  --basetemp 'C:\tmp\agc-capture-core-red-1'
```

Expected: FAIL because lifecycle is absent from cards, budgets are hard-coded, and `config.yaml` is not a behavioral input.

- [ ] **Step 3: Implement strict typed configuration**

Use frozen dataclasses and strict mappings. The installed default must include:

```yaml
schema_version: 3
sensitive_storage: disabled
recall:
  overview_token_budget: 250
  compact_card_token_budget: 600
  default_lifecycle: active
capture:
  schema_version: 1
  enabled: false
  mode: off
  paused: false
  include_subagents: false
  sources: []
  hook:
    enabled: false
  runner:
    concurrency: 1
    max_attempts: 5
    backoff_seconds: [60, 300, 1800, 7200, 21600]
  capsule:
    target_tokens: 1200
    max_tokens: 3000
  budgets:
    backfill_window_days: 7
    backfill_total_tokens: 100000
    incremental_total_tokens: null
  extractor:
    kind: codex_exec
    executable: codex
    model: null
  exclude:
    task_ids: []
    project_ids: []
```

`default_config.yaml` and `templates/memory/config.yaml` must be byte-identical package assets. `admin init` copies the package default. `admin validate` parses and validates instead of comparing against a hard-coded string.

- [ ] **Step 4: Implement the lifecycle and response-budget gates**

Make `card_from_item()` include lifecycle. Filter eligible cards and search matches before loading bodies. Move the deterministic estimator into `response_budget.py` and evaluate the entire accepted envelope after every compression stage. Compression order is cards → high-impact scopes → by-scope counts → by-kind counts; preserve total memory count. If the minimum accepted envelope is still too large, return the stable error.

- [ ] **Step 5: Verify GREEN and commit**

Run the Step 2 command plus:

```powershell
git diff --check
git add agc_runtime/runtime_config.py agc_runtime/response_budget.py agc_runtime/default_config.yaml `
  agc_runtime/catalog.py agc_runtime/read_service.py agc_runtime/admin_service.py `
  templates/memory/config.yaml tests/test_recall_activation_gate.py tests/test_runtime_config.py `
  tests/test_catalog_and_read.py tests/test_admin_service.py
git commit -m "fix: enforce recall activation gates"
```

---

### Task 2: Define Strict Capture Contracts, State Machine, IDs, and Paths

**Files:**
- Create: `agc_runtime/capture_contracts.py`
- Create: `agc_runtime/capture_schema.py`
- Create: `tests/test_capture_contracts.py`
- Create: `tests/test_capture_paths.py`
- Modify: `agc_runtime/paths.py`
- Modify: `agc_runtime/admin_service.py`

**Interfaces:**
- Produces: `CaptureKey`, `RevisionRef`, `CaptureReceipt`, `CollectedObservation`, `LedgerEntry`, `CaptureLease`, `TokenUsage`, `SanitizedError`, `SourceQuarantine`, and `CaptureSuppressionTombstone`.
- Produces: `receipt_id_for`, `observation_fingerprint_for`, `observation_id_for`, strict mapping parsers, and state-transition validation.
- Produces: nested `CapturePaths` rooted at `.runtime/capture/`.

- [ ] **Step 1: Add failing schema and path tests**

Test every required and conditional Receipt field, every legal and illegal transition, strict rejection of unknown keys, 300-code-point statement limit, exactly 0–8 Observations, controlled enums, UTC timestamps, opaque locators, and absence of absolute paths. Test stable IDs across dict ordering and exact replay, and prove ordinal is not part of the Observation fingerprint.

Use the exact status graph:

```text
discovered -> queued | excluded | coalesced | deferred_budget | quarantined
queued -> extracting | deferred_budget | excluded
extracting -> complete | retryable | failed | quarantined
retryable -> queued | deferred_budget | failed | quarantined
deferred_budget -> queued | excluded
failed | quarantined -> queued  # explicit retry or compatible version upgrade only
```

- [ ] **Step 2: Verify RED**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest `
  tests/test_capture_contracts.py tests/test_capture_paths.py -q `
  --basetemp 'C:\tmp\agc-capture-core-red-2'
```

Expected: collection FAIL because Capture contracts and paths do not exist.

- [ ] **Step 3: Implement canonical contracts and IDs**

Use canonical JSON with sorted keys, UTF-8, compact separators, explicit schema version, and full SHA-256. Prefix IDs with `cr_`, `co_`, and `ct_`. The Observation fingerprint covers normalized statement, assertion, primary category, kind, sorted scopes, project scope, and signal type; it excludes ordinal, timestamps, locator, and source hashes.

Keep the Phase 1 Observation state fixed to `collected`. `sensitivity` permits only `normal|personal`; a `sensitive|secret` value must fail before serialization.

- [ ] **Step 4: Implement the isolated layout**

Add:

```text
.runtime/capture/
  schema-version
  receipts/ observations/ ledger/ census/ tombstones/
  quarantines/ conflicts/ dirty/ journals/ staging/
  leases/ indexes/ scan-state/ budgets/
```

`admin init` creates the layout without a Census, Receipt, Observation, Hook, worker, or scan. `admin validate` strictly decodes managed Capture objects when present.

- [ ] **Step 5: Verify GREEN and commit**

Run focused tests, then:

```powershell
git add agc_runtime/capture_contracts.py agc_runtime/capture_schema.py agc_runtime/paths.py `
  agc_runtime/admin_service.py tests/test_capture_contracts.py tests/test_capture_paths.py
git commit -m "feat: define capture contracts and namespace"
```

---

### Task 3: Implement Capture Store, Two-Level Idempotency, Lease Fencing, and Crash Recovery

**Files:**
- Create: `agc_runtime/capture_store.py`
- Create: `agc_runtime/capture_transaction.py`
- Create: `tests/test_capture_store.py`
- Create: `tests/test_capture_transaction.py`
- Modify: `agc_runtime/locking.py`

**Interfaces:**
- Implements the `CaptureStore` surface in this plan.
- Capture idempotency key: `(adapter_id, source_root_id, task_id, revision_id)`.
- Observation idempotency key: `(receipt_id, observation_fingerprint)`.
- Uses one root Capture writer lock and per-key lease fencing tokens.

- [ ] **Step 1: Add failing AC-08 and lease tests**

Create `test_ac_08_two_level_idempotency_and_source_conflict`. Prove one Revision can commit multiple Observations, exact replay adds zero objects, same key/same hash-schema/different fingerprint quarantines pre-complete work, and a post-complete conflict preserves the committed batch while degrading Source Health. Add stale lease and same-key concurrent owner tests.

- [ ] **Step 2: Add failing AC-09 crash matrix**

Parameterize crash injection immediately before and after: journal creation, staged after-images, each Observation install, Ledger processed install, terminal Receipt install, and cleanup. After `recover_transactions()`, require either a complete valid batch or zero visible Observations with a truthful retryable Receipt. Assert orphan, partial, and duplicate counts are all zero.

- [ ] **Step 3: Verify RED**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest `
  tests/test_capture_store.py tests/test_capture_transaction.py -q `
  --basetemp 'C:\tmp\agc-capture-core-red-3'
```

- [ ] **Step 4: Implement the store and journal transaction**

Persist one canonical JSON file per Receipt, Observation, Ledger entry, and journal. `commit_extraction()` must revalidate lease/key/version, 0–8 limit, stable within-batch deduplication, Receipt counts, monotonic token totals, zero reason, redaction, and hashes.

Publish staged after-images in this order: Observations → Ledger processed marker → terminal Receipt last. Explicit reads expose Observations only when the complete Receipt references the full valid set. A cursor or scan-state failure is outside this semantic transaction and cannot undo it.

- [ ] **Step 5: Verify GREEN and commit**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest `
  tests/test_capture_store.py tests/test_capture_transaction.py -q `
  --basetemp 'C:\tmp\agc-capture-core-green-3'
git add agc_runtime/capture_store.py agc_runtime/capture_transaction.py agc_runtime/locking.py `
  tests/test_capture_store.py tests/test_capture_transaction.py
git commit -m "feat: add crash-safe capture store"
```

---

### Task 4: Add Explicit Capture Views, Coverage Math, Status, and Recall Isolation

**Files:**
- Create: `agc_runtime/capture_read_service.py`
- Create: `agc_runtime/capture_status_service.py`
- Create: `tests/test_capture_read_service.py`
- Create: `tests/test_capture_status.py`
- Modify: `agc_runtime/read_service.py`
- Modify: `agc_runtime/admin_service.py`
- Modify: `agc_runtime/mcp_server.py`
- Modify: `tests/test_mcp_server.py`

**Interfaces:**
- Adds `agc.read` actions `capture_overview`, `capture_search`, and `capture_get`.
- Adds `agc.admin` action `capture_status`.
- Keeps exactly three public MCP tools.
- Search order: `captured_at DESC, observation_id ASC`; default 20, maximum 100.

- [ ] **Step 1: Add failing AC-11 and AC-16 tests**

Test time/task/project/category/kind/scope/state/sensitivity filters, stable opaque cursor pagination, empty results, maximum limit, source redaction, and `inspection_completion="not_applicable"` for an empty denominator. Prove ordinary `overview/search/get/history/evidence` and the Formal Catalog return zero Capture objects.

- [ ] **Step 2: Add failing status tests**

Require status to report config source, Runtime version, Memory Root, configured Source Root IDs, extractor boundary, budgets, enabled/paused/scanner-only state, and route conflicts without revealing absolute source paths or user content. Disabled state must be accepted and diagnosable; activation readiness remains false until later plans provide a valid source/extractor/host binding.

- [ ] **Step 3: Verify RED**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest `
  tests/test_capture_read_service.py tests/test_capture_status.py tests/test_mcp_server.py -q `
  --basetemp 'C:\tmp\agc-capture-core-red-4'
```

- [ ] **Step 4: Implement views and coverage formulas**

Return raw counts with:

```text
accounting_coverage = receipts_or_suppression_tombstones / census_keys
inspection_completion = complete / (eligible - revision_suppression_tombstones)
silent_loss = census_keys - (receipt_keys union suppression_tombstone_keys)
unresolved = discovered + queued + extracting + retryable + deferred_budget
parked = failed + quarantined
```

Unkeyed Source Quarantine makes Source Health `degraded` and prevents a claim of complete source coverage even if known-key accounting is 100%.

- [ ] **Step 5: Verify GREEN and commit**

Run the focused tests and `tests/test_catalog_and_read.py`, then commit:

```powershell
git add agc_runtime/capture_read_service.py agc_runtime/capture_status_service.py `
  agc_runtime/read_service.py agc_runtime/admin_service.py agc_runtime/mcp_server.py `
  tests/test_capture_read_service.py tests/test_capture_status.py tests/test_mcp_server.py
git commit -m "feat: expose isolated capture views"
```

---

### Task 5: Make Backup, Restore, and Hard Forget Capture-Aware

**Files:**
- Create: `agc_runtime/managed_backup.py`
- Create: `agc_runtime/capture_forget_service.py`
- Create: `agc_runtime/capture_forget_transaction.py`
- Create: `tests/test_capture_backup_restore.py`
- Create: `tests/test_capture_forget.py`
- Modify: `agc_runtime/admin_service.py`
- Modify: `agc_runtime/write_service.py`
- Modify: `tests/test_admin_service.py`
- Modify: `tests/test_forget_service.py`

**Interfaces:**
- Adds `agc.write` action `capture_forget` with a strict union target of exact `observation_id` or exact Capture Key.
- Backup allowlists Capture schema, Receipts, Observations, Ledger/Census, required content-free diagnostics, and tombstones.
- Backup excludes dirty spool, queue, journal, staging, lease, cache, rebuildable index, scan hint, and all Capsule/transcript content.

- [ ] **Step 1: Add failing AC-17 tests**

Round-trip a Capture root and assert strict schema, Receipt/Observation references, Ledger, idempotency, tombstones, and Recall isolation survive. Corrupt references and unknown manifest/Capture schema versions must be rejected before mutation. Assert excluded runtime-noise paths are absent from the zip.

- [ ] **Step 2: Add failing AC-18 tests**

Use the exact request union:

```json
{"action":"capture_forget","authorization":"explicit_user_request","target":{"type":"observation","observation_id":"co_..."}}
```

or a `revision` target containing the four Capture Key fields. Observation forget deletes every managed copy, decrements count, clears both hashes and versions, sets `redacted_by_forget`, increments forgotten count, and uses `zero_reason=user_forget` at zero. Revision forget leaves only a content-free suppression tombstone and reports `source_task_deleted=false`. Inject failures across primary files and backup rewrites and require rollback plus exact retry convergence.

- [ ] **Step 3: Verify RED**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest `
  tests/test_capture_backup_restore.py tests/test_capture_forget.py `
  tests/test_admin_service.py tests/test_forget_service.py -q `
  --basetemp 'C:\tmp\agc-capture-core-red-5'
```

- [ ] **Step 4: Implement allowlisted backup compatibility and exact forget**

Extract deterministic archive/manifest and rollback helpers into `managed_backup.py`; keep formal-memory behavior unchanged. A Capture-capable Runtime must reject unknown Capture schema. Record the compatibility limit accurately: released Runtime 0.2.0 cannot be retroactively changed, so Capture data must not be produced until a Capture-capable Runtime is installed, and post-data rollback is feature-disable rather than binary downgrade.

Do not reuse term-based formal-memory forget. Capture forget must address deterministic object IDs, rewrite every managed backup, leave content-free integrity journals only while active, and verify zero managed text/hash matches before commit.

- [ ] **Step 5: Verify GREEN and commit**

Run the focused suite, then:

```powershell
git add agc_runtime/managed_backup.py agc_runtime/capture_forget_service.py `
  agc_runtime/capture_forget_transaction.py agc_runtime/admin_service.py `
  agc_runtime/write_service.py tests/test_capture_backup_restore.py tests/test_capture_forget.py `
  tests/test_admin_service.py tests/test_forget_service.py
git commit -m "feat: govern capture backup and hard forget"
```

---

### Task 6: Prove the Disabled Core Is Independently Releasable

**Files:**
- Create: `tests/test_capture_core_end_to_end.py`
- Modify: `tests/test_runtime_end_to_end.py`
- Modify: `.llm-wiki/requirements/agc-capture-coverage-mvp.md`
- Modify: `.llm-wiki/working-context/agc-capture-coverage-mvp.md`

**Interfaces:**
- Demonstrates AC-02, AC-07/08/09 core, AC-11/16/17/18 while Capture is disabled and source/model count is zero.

- [ ] **Step 1: Add an end-to-end disabled-mode test**

Initialize, validate, create synthetic Capture objects through the internal store, read only through explicit actions, backup/restore, forget both target types, and verify the Formal Catalog hash and memory count never change. Assert no source enumeration or subprocess API is imported or invoked.

- [ ] **Step 2: Run focused and complete tests**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_capture_core_end_to_end.py -q `
  --basetemp 'C:\tmp\agc-capture-core-e2e'
& '.\.venv\Scripts\python.exe' -m pytest -q `
  --basetemp 'C:\tmp\agc-capture-core-full'
```

Expected: PASS. No test may depend on a real profile, network, provider, or real transcript.

- [ ] **Step 3: Run package and text gates**

```powershell
& '.\.venv\Scripts\python.exe' -m build
git diff --check
```

Decode every changed tracked text file using strict UTF-8 and reject BOM. Install the wheel into a temporary venv and run `agc --version`, `agc admin validate`, and the exactly-three-MCP-tools test from the installed artifact.

- [ ] **Step 4: Record evidence and commit**

Update Flow evidence with exact commands, exit codes, test counts, production/test/mocks/assertions/actual-behavior notes, and the 0.2.0 backward-restore residual risk. Do not claim Capture is usable yet.

```powershell
git add tests/test_capture_core_end_to_end.py tests/test_runtime_end_to_end.py `
  .llm-wiki/requirements/agc-capture-coverage-mvp.md `
  .llm-wiki/working-context/agc-capture-coverage-mvp.md
git commit -m "test: verify disabled capture core"
```

## Acceptance Mapping

| Gate | Task/Test |
|---|---|
| AC-02 | Task 1, `test_ac_02_lifecycle_and_hard_overview_budget` |
| AC-07 | Task 2 schema tests; completed pipeline proof arrives in plan 3 |
| AC-08 | Task 3, `test_ac_08_two_level_idempotency_and_source_conflict` |
| AC-09 | Task 3 crash matrix |
| AC-11 | Task 4 explicit-action isolation test |
| AC-16 | Task 4 filters/sort/page/redaction test |
| AC-17 | Task 5 round-trip and unknown-schema tests |
| AC-18 | Task 5 exact Observation/Revision forget tests |

## Exit Gate

Proceed to `2026-08-13-agent-global-context-codex-source-census.md` only when the complete suite and package checks pass, Capture remains disabled by default, ordinary Recall meets AC-02, and no source/model/host behavior has been introduced.
