# Agent Global Context Manual Backfill Fast Track Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver an installed, explicit, authorized seven-day manual backfill that classifies and persists many Capture Observations before background Host automation is implemented.

**Architecture:** Reuse the reviewed Census, Capsule, isolated Extractor, safety gates, Capture Store, backup, and Hard Forget layers. Add a durable actual-or-reserved Token ledger, a read-only preparation/digest boundary, and a single-concurrency one-shot batch runner. Keep the final Runner and Host plans intact; this plan moves only the minimum usable slice forward.

**Tech Stack:** Python 3.10+, dataclasses, canonical JSON, SHA-256, existing Capture root locks and transactions, strict subprocess Extractor, pytest, setuptools wheel.

## Global Constraints

- The frozen backfill Census is exactly seven days and the model Token ceiling is at most `100000`.
- Every model call is preceded by a durable conservative input-plus-output reservation.
- Known Provider usage settles as actual; missing, partial, invalid, timed-out, or crash-unknown usage settles as reserved.
- A valid authorization digest is required before any model call.
- Each batch is explicit, `--once`, single-concurrency, and bounded by `--max-items`.
- No transcript, Capsule, prompt, raw model output, rejected draft, code, diff, log, or stack trace is persisted or logged.
- Each Revision produces zero through eight strict Observations and at most one Extractor call per attempt.
- Existing Recall, Catalog, backup/restore, and Hard Forget contracts remain unchanged.
- Development and installed-artifact verification use synthetic roots and the fake Extractor only. Real backfill remains a separate user-authorized action.
- Follow RED -> GREEN for every production behavior and commit each independently reviewable task.

---

### Task 1: Define strict durable Token budget contracts

**Files:**
- Create: `agc_runtime/capture_budget.py`
- Create: `tests/test_capture_token_budget.py`
- Modify: `agc_runtime/capture_contracts.py`
- Modify: `agc_runtime/capture_schema.py`

**Interfaces:**
- Consumes: `CaptureKey`, `TokenUsage`, `MemoryPaths`, `CAPTURE_SCHEMA_VERSION`.
- Produces: `TokenReservation`, `BudgetSettlement`, `BudgetSnapshot`, `BudgetUnavailable`, `reservation_id_for(...)`, and `CaptureTokenBudget`.

- [ ] **Step 1: Write strict DTO and AC-15 boundary tests**

Add tests that construct mappings with the exact shapes below and reject missing/unknown fields, booleans-as-integers, invalid UTC, invalid IDs, key mismatches, non-additive usage, attempts below one, ceilings above `100000`, and settlements exceeding reservations.

```python
reservation_value = {
    "schema_version": 1,
    "reservation_id": reservation_id_for("backfill", census_id, key, 1),
    "pool": "backfill",
    "census_id": census_id,
    "capture_key": key.to_mapping(),
    "attempt": 1,
    "maximum_usage": {
        "input_tokens": 700,
        "output_tokens": 300,
        "total_tokens": 1000,
    },
    "reserved_at": "2026-08-20T00:00:00Z",
}
settlement_value = {
    "schema_version": 1,
    "reservation_id": reservation_value["reservation_id"],
    "capture_key": key.to_mapping(),
    "charged_usage": {
        "input_tokens": 600,
        "output_tokens": 200,
        "total_tokens": 800,
    },
    "usage_quality": "actual",
    "settled_at": "2026-08-20T00:01:00Z",
}
```

- [ ] **Step 2: Run the focused tests and verify RED**

```powershell
python -m pytest tests/test_capture_token_budget.py -q -p no:cacheprovider `
  --basetemp D:\t_agc_fast_red_budget
```

Expected: collection/import failures because `capture_budget` and the new DTOs do not exist.

- [ ] **Step 3: Implement strict DTOs and deterministic IDs**

Add frozen dataclasses in `capture_contracts.py` with validated public mappings:

```python
@dataclass(frozen=True)
class TokenReservation:
    schema_version: int
    reservation_id: str
    pool: str
    census_id: str | None
    capture_key: CaptureKey
    attempt: int
    maximum_usage: TokenUsage
    reserved_at: str

@dataclass(frozen=True)
class BudgetSettlement:
    schema_version: int
    reservation_id: str
    capture_key: CaptureKey
    charged_usage: TokenUsage
    usage_quality: str
    settled_at: str
```

Implement strict parsers in `capture_schema.py`. In `capture_budget.py`, derive the reservation ID from canonical JSON containing pool, Census ID, all four `CaptureKey` fields, and attempt:

```python
def reservation_id_for(pool, census_id, key, attempt):
    payload = canonical_json_bytes({
        "pool": pool,
        "census_id": census_id,
        "capture_key": key.to_mapping(),
        "attempt": attempt,
    })
    return "br_" + hashlib.sha256(payload).hexdigest()
```

- [ ] **Step 4: Run DTO tests and verify GREEN**

Run the command from Step 2. Expected: strict DTO/ID nodes pass; persistence nodes may remain RED until Task 2.

- [ ] **Step 5: Commit Task 1**

```powershell
git add agc_runtime/capture_budget.py agc_runtime/capture_contracts.py `
  agc_runtime/capture_schema.py tests/test_capture_token_budget.py
git commit -m "feat: define capture token budget contracts"
```

---

### Task 2: Persist reservations and crash-safe settlements

**Files:**
- Modify: `agc_runtime/capture_budget.py`
- Modify: `agc_runtime/capture_store.py`
- Modify: `agc_runtime/capture_transaction.py`
- Modify: `tests/test_capture_token_budget.py`
- Modify: `tests/test_capture_transaction.py`

**Interfaces:**
- Consumes: Task 1 DTOs and existing frozen Census/Receipt/lease APIs.
- Produces: `CaptureTokenBudget.reserve(key, attempt, maximum)`, `prepare_settlement(reservation, usage)`, `settle(reservation, usage)`, `snapshot()`, and Store settlement recovery hooks.

- [ ] **Step 1: Add failing AC-15 persistence tests**

Add exact coverage for:

```python
def test_ac_15_backfill_never_exceeds_actual_or_reserved_ceiling(): ...
def test_concurrent_exact_boundary_allows_only_one_winner(): ...
def test_one_token_over_is_refused_without_a_reservation_file(): ...
def test_actual_usage_replaces_active_reservation_charge(): ...
def test_absent_invalid_timeout_and_unknown_usage_charge_reserved_maximum(): ...
def test_retry_attempts_have_distinct_charges(): ...
def test_crash_after_reservation_survives_restart(): ...
def test_exact_double_settlement_is_idempotent_and_conflict_is_rejected(): ...
def test_incremental_pool_is_unavailable_when_configured_total_is_null(): ...
def test_foreign_key_cannot_charge_a_frozen_backfill_pool(): ...
```

Use two threads synchronized at a barrier for the exact-boundary race. Assert persisted JSON contains only IDs, keys, counts, quality, and UTC timestamps.

- [ ] **Step 2: Run persistence tests and verify RED**

```powershell
python -m pytest tests/test_capture_token_budget.py -q -p no:cacheprovider `
  --basetemp D:\t_agc_fast_red_budget_store
```

Expected: `CaptureTokenBudget` persistence methods are absent or do not enforce the ceiling.

- [ ] **Step 3: Implement the locked budget ledger**

Store pool metadata, reservations, and settlements beneath `.runtime/capture/budgets/` using canonical JSON and the existing Capture root lock:

```text
pool-backfill-<census-id>.json
reservation-<reservation-id>.json
settlement-<reservation-id>.json
```

`reserve` must:

1. Strictly reload the frozen Census and require membership.
2. Freeze pool kind, Census ID, and ceiling on first use.
3. Sum settled actual/reserved usage plus active maximum reservations.
4. Refuse if `charged + maximum.total_tokens > ceiling`.
5. Atomically publish the reservation before returning it.
6. Return the exact existing reservation for same key/attempt/maximum; reject a conflicting replay.

`prepare_settlement` must charge actual usage only when a complete `TokenUsage` is present and within the reservation maximum; otherwise charge the maximum with `usage_quality="reserved"`.

- [ ] **Step 4: Add Store transaction integration and recovery**

Extend extraction commit and failure transition paths with optional strict budget objects:

```python
def commit_extraction(
    self,
    lease: CaptureLease,
    observations: Sequence[CollectedObservation],
    terminal_receipt: CaptureReceipt,
    *,
    reservation: TokenReservation | None = None,
    settlement: BudgetSettlement | None = None,
) -> CommitResult: ...

def transition_with_settlement(
    self,
    lease: CaptureLease,
    *,
    expected: frozenset[str],
    target: str,
    patch: ReceiptTransitionPatch,
    reservation: TokenReservation,
    settlement: BudgetSettlement,
) -> CaptureReceipt: ...
```

The transaction journal records only receipt ID, reservation ID, target status,
and charged Token counts. Recovery must converge a settlement-without-Receipt or
Receipt-without-cleanup prefix to the same final Token totals. Exact replay is
idempotent; foreign binding is quarantined before mutation.

- [ ] **Step 5: Verify GREEN and adjacent transactions**

```powershell
python -m pytest tests/test_capture_token_budget.py tests/test_capture_transaction.py `
  tests/test_capture_store.py -q -p no:cacheprovider `
  --basetemp D:\t_agc_fast_green_budget
```

Expected: all selected tests pass with zero unexpected warnings.

- [ ] **Step 6: Commit Task 2**

```powershell
git add agc_runtime/capture_budget.py agc_runtime/capture_store.py `
  agc_runtime/capture_transaction.py tests/test_capture_token_budget.py `
  tests/test_capture_transaction.py
git commit -m "feat: enforce durable capture token budgets"
```

---

### Task 3: Prepare a manual backfill and bind authorization

**Files:**
- Create: `agc_runtime/capture_backfill.py`
- Create: `tests/test_capture_backfill.py`
- Modify: `agc_runtime/capture_cli.py`
- Modify: `agc_runtime/capture_status_service.py`

**Interfaces:**
- Consumes: runtime config, Scanner, frozen Census, Store snapshot, Extractor probe, and budget snapshot.
- Produces: `BackfillPreparation`, `prepare_backfill(...)`, `authorization_digest_for(...)`, and CLI `prepare-backfill`.

- [ ] **Step 1: Add failing preparation and digest tests**

Add tests proving preparation invokes Scanner and a content-free Extractor probe but never `extract`, reports frozen/ready/status counts and budget state, and yields a deterministic digest. Require digest changes for Memory Root, Census, Source binding, effective Capture config, Extractor identity/version/schema, model, Provider, or Token ceiling changes.

```python
preparation = prepare_backfill(
    paths=paths,
    adapters=(adapter,),
    extractor=fake_extractor,
    now="2026-08-20T00:00:00Z",
)
assert fake_extractor.extract_calls == 0
assert preparation.backfill_total_tokens == 100000
assert len(preparation.authorization_digest) == 64
```

- [ ] **Step 2: Verify RED**

```powershell
python -m pytest tests/test_capture_backfill.py -q -p no:cacheprovider `
  --basetemp D:\t_agc_fast_red_prepare
```

Expected: `capture_backfill` and CLI action are absent.

- [ ] **Step 3: Implement canonical preparation**

Define a frozen content-free DTO containing only IDs, versions, counts, Token totals, machine states, and digest. Build the digest from canonical JSON; never include absolute Source paths, statements, locators, Capsule data, or raw probe output.

Preparation must require enabled `scanner_only`, not paused, exactly seven-day backfill, configured sources, healthy Scanner integrity, available isolated Extractor capability, and a non-corrupt frozen budget. It may freeze/refresh the Census but must never reserve or spend model Tokens.

- [ ] **Step 4: Extend the one-shot CLI parser**

Add the exact form:

```text
agc-capture prepare-backfill --root <memory-root>
```

Return one schema-v2 `agc.capture` envelope with action `prepare-backfill`. Map invalid config, busy, corrupt, source unavailable, and capability unavailable to fixed content-free codes.

- [ ] **Step 5: Verify GREEN and disabled-boundary regression**

```powershell
python -m pytest tests/test_capture_backfill.py tests/test_capture_cli.py `
  tests/test_capture_status.py tests/test_capture_core_end_to_end.py -q `
  -p no:cacheprovider --basetemp D:\t_agc_fast_green_prepare
```

Expected: selected tests pass; disabled/probe paths still defer Source/Extractor imports.

- [ ] **Step 6: Commit Task 3**

```powershell
git add agc_runtime/capture_backfill.py agc_runtime/capture_cli.py `
  agc_runtime/capture_status_service.py tests/test_capture_backfill.py
git commit -m "feat: prepare authorized capture backfill"
```

---

### Task 4: Run an explicit single-concurrency manual batch

**Files:**
- Create: `agc_runtime/capture_runner.py`
- Create: `tests/test_capture_manual_runner.py`
- Modify: `agc_runtime/capture_backfill.py`
- Modify: `agc_runtime/capture_cli.py`
- Modify: `agc_runtime/capture_store.py`

**Interfaces:**
- Consumes: Task 2 budget APIs, Task 3 authorization, SourceAdapter, SemanticExtractor, CapsulePolicy, persistence gate, and Store lease/commit APIs.
- Produces: `CaptureRunner.run_manual_backfill(...) -> RunnerReport`, `release_lease(...)`, and CLI `backfill`.

- [ ] **Step 1: Add failing manual Runner tests**

Cover 0, 1, 8, and over-8 drafts; classification fields; duplicate drafts; zero-signal; exact replay; stale digest; insufficient budget; one failing item followed by a successful item; source drift; capability unavailable; timeout; malformed output; and active lease contention. Assert one Extractor call per reserved attempt and no call for stale authorization or budget refusal.

```python
report = runner.run_manual_backfill(
    authorization_digest=preparation.authorization_digest,
    max_items=20,
    now="2026-08-20T00:01:00Z",
)
assert report.attempted_count <= 20
assert report.extractor_call_count == report.reserved_attempt_count
assert report.silent_loss_count == 0
```

- [ ] **Step 2: Verify RED**

```powershell
python -m pytest tests/test_capture_manual_runner.py -q -p no:cacheprovider `
  --basetemp D:\t_agc_fast_red_runner
```

Expected: `CaptureRunner` and the manual backfill CLI action are absent.

- [ ] **Step 3: Implement the contractual item order**

For each ready Receipt in stable `(discovered_at, receipt_id)` order:

```text
validate current digest
acquire fenced lease
load matching frozen Revision
build in-memory Capsule
reserve maximum usage
transition queued -> extracting
invoke extractor once
run persistence gate
construct stable 0..8 CollectedObservations
prepare actual/reserved settlement
commit observations + complete Receipt + Ledger + settlement
release lease and discard content buffers
```

On an item failure, settle reserved usage when a process may have started,
transition to truthful retryable/failed/quarantined/deferred status, release the
lease, and continue to the next item. Root integrity, stale digest, or corrupt
budget stops the batch before another model call.

An insufficient budget must use the existing persisted Receipt status
`deferred_budget`; it must not be represented only as a transient report count.

- [ ] **Step 4: Add strict lease release and Observation conversion**

`CaptureStore.release_lease(lease)` must validate the current lease and fencing
epoch, unlink only the bound lease file, and preserve the epoch high-water mark.
Convert accepted drafts to `CollectedObservation` using existing fingerprint/ID
helpers, stable accepted order, Revision completion time as `observed_at`, batch
time as `captured_at`, and processing state `collected`.

- [ ] **Step 5: Add the explicit CLI form**

```text
agc-capture backfill --root <memory-root> --authorization-digest <64hex> --max-items <1..100> --once
```

Reject every other shape. Return counts and Token deltas only; do not return
statements, evidence, locators, Source paths, Capsule hashes, or raw errors.

- [ ] **Step 6: Verify GREEN and adjacent Store/Extractor tests**

```powershell
python -m pytest tests/test_capture_manual_runner.py tests/test_capture_backfill.py `
  tests/test_capture_token_budget.py tests/test_capture_store.py `
  tests/test_capture_transaction.py tests/test_capture_extractor.py `
  tests/test_capture_capsule_safety.py -q -p no:cacheprovider `
  --basetemp D:\t_agc_fast_green_runner
```

Expected: all selected tests pass with only documented adversarial ZIP warnings if those tests are included.

- [ ] **Step 7: Commit Task 4**

```powershell
git add agc_runtime/capture_runner.py agc_runtime/capture_backfill.py `
  agc_runtime/capture_cli.py agc_runtime/capture_store.py `
  tests/test_capture_manual_runner.py
git commit -m "feat: run authorized manual capture backfill"
```

---

### Task 5: Prove, package, install, and expose the early-use workflow

**Files:**
- Create: `tests/test_capture_manual_backfill_end_to_end.py`
- Modify: `tests/test_capture_read_service.py`
- Modify: `tests/test_capture_backup_restore.py`
- Modify: `tests/test_capture_forget.py`
- Modify: `.llm-wiki/requirements/agc-capture-coverage-mvp.md`
- Modify: `.llm-wiki/working-context/agc-capture-coverage-mvp.md`
- Modify: `.superpowers/sdd/progress.md`

**Interfaces:**
- Consumes: installed `agc-capture`, fake Source/Extractor, and synthetic Memory Root.
- Produces: Phase A acceptance evidence and an installable early-use AGC artifact.

- [ ] **Step 1: Add the synthetic installed-workflow E2E**

Run Census preparation, authorized batches, overview/search inspection, exact replay, backup/restore, observation forget, and revision forget. Include 0, 1, 8, over-8, duplicate, secret, sensitive, malformed output, timeout, budget deferral, and crash/restart fixtures.

- [ ] **Step 2: Add the persistence sentinel sweep**

Search every managed Capture directory, journal, staging path, backup, queue,
cache, Receipt, Observation, Ledger, and tombstone for transcript, Capsule,
prompt, raw-output, secret, code, diff, and log sentinels. Require zero hits
before and after both Forget targets. Assert ordinary Recall/Catalog bytes are
unchanged.

- [ ] **Step 3: Run focused Phase A acceptance**

```powershell
python -m pytest tests/test_capture_manual_backfill_end_to_end.py `
  tests/test_capture_read_service.py tests/test_capture_backup_restore.py `
  tests/test_capture_forget.py -q -p no:cacheprovider `
  --basetemp D:\t_agc_fast_e2e
```

Expected: all selected tests pass; forbidden sentinel hits are zero.

- [ ] **Step 4: Run the natural-order full suite once**

```powershell
python -m pytest -q -p no:cacheprovider --basetemp D:\t_agc_fast_full
git diff --check
```

Expected: zero failures and only explicitly documented adversarial warnings.

- [ ] **Step 5: Build and verify a clean installed wheel**

Build from `git archive HEAD` in a disposable directory. Install the wheel plus
the MCP extra into a fresh isolated environment. From outside the repository,
assert:

```text
agc --version                         -> accepted
agc-capture prepare-backfill ...     -> accepted, model calls 0
agc-capture backfill ... --once      -> accepted against fake extractor
capture overview/search              -> classified Observations visible
MCP tools                            -> exactly agc.admin/read/write
```

Verify package provenance, schema resources, strict UTF-8/no BOM, entry points,
and zero changes to the real Memory Root.

- [ ] **Step 6: Update durable evidence and commit**

Record exact RED/GREEN/full/wheel commands and residual deferred work. Do not
mark original Runner/Host phases complete; mark only Manual Backfill Phase A.

```powershell
git add tests/test_capture_manual_backfill_end_to_end.py `
  tests/test_capture_read_service.py tests/test_capture_backup_restore.py `
  tests/test_capture_forget.py .llm-wiki/requirements/agc-capture-coverage-mvp.md `
  .llm-wiki/working-context/agc-capture-coverage-mvp.md
git add -f .superpowers/sdd/progress.md
git commit -m "test: verify manual capture backfill"
```

## Final audit

Before declaring Phase A complete, map every requirement in
`2026-08-20-agent-global-context-manual-backfill-fast-track-design.md` to a
test node, installed command, persisted artifact inspection, or byte comparison.
Unproven requirements remain incomplete. Phase B–D work remains active after
this plan succeeds; the final Capture goal is not redefined around Phase A.
