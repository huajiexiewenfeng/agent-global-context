# Agent Global Context Capture Extractor and Runner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn discovered revisions into zero to eight safe, isolated Collected Observations through a bounded background Runner without changing any foreground Codex result or formal memory.

**Architecture:** The Codex Source Adapter constructs a deterministic, privacy-filtered Task Capsule only in memory. A versioned Semantic Extractor runs in an isolated non-interactive Codex subprocess and returns strict JSON. A second persistence gate validates personal relevance and removes prohibited content before a durable token reservation and the crash-safe Capture transaction are settled. The single-concurrency Runner owns retries, leases, backpressure, and truthful Receipt state.

**Tech Stack:** Python 3.10+, subprocess JSONL, static JSON Schema, tempfile empty working directories, strict stdin/stdout boundaries, SHA-256 Capsule hash, pytest fake executables and process integration.

## Global Constraints

- Requires both prior exit gates: Capture Core and Codex Source/Census.
- This is plan 3 of 4. It implements background semantics but does not install a Hook, scheduled task, or activate a real profile.
- Phase 1 stops at Receipt plus Collected Observation. Never call `agc.write observe/propose/confirm/update`, never create Candidate/Formal Memory/Event, and never modify the Catalog.
- Each Revision gets at most one semantic extraction call per attempt; no evidence-expansion call and no whole-session summarization.
- Task Capsule exists only in Python memory and extractor stdin. No Capsule, prompt, raw model output, transcript excerpt, code, diff, log, or stack trace may be written to disk or logs.
- Known secrets are scrubbed before the model call. All output passes strict schema, sensitivity, prohibited-content, personal-relevance, and atomicity gates before persistence.
- The reference extractor must use ephemeral, ignore-user-config, ignore-rules, read-only, schema-constrained non-interactive execution. If any capability is unavailable, fail closed; do not silently weaken isolation.
- Backfill input plus output, including invalid attempts and retries, must never exceed 100,000 actual-or-reserved model tokens.
- Runner concurrency defaults to one; paused, budget-deferred, retryable, failed, and quarantined work remains visible and is never dropped.
- Every task follows red-green TDD and ends in a focused commit.

## Stable Extractor Interface

```python
class SemanticExtractor(Protocol):
    def describe(self) -> ExtractorDescriptor: ...
    def probe_capabilities(self) -> CapabilityProbe: ...
    def extract(
        self, capsule: TaskCapsule, reservation: TokenReservation
    ) -> ExtractionResult: ...
```

The Runner may depend only on this Protocol, not on Codex-specific process details.

---

### Task 1: Build an In-Memory Task Capsule and Two Deterministic Safety Gates

**Files:**
- Create: `agc_runtime/capture_capsule.py`
- Create: `agc_runtime/capture_safety.py`
- Create: `tests/test_capture_capsule_safety.py`
- Modify: `agc_runtime/capture_source.py`
- Modify: `agc_runtime/codex_source_adapter.py`

**Interfaces:**
- Produces: `TaskCapsule` with content fields marked `repr=False`.
- Produces: `build_capsule(records, ref, policy) -> CapsuleResult`.
- Produces: `pre_capsule_gate(...) -> PreCapsuleResult` and `persistence_gate(...) -> PersistenceResult`.
- Completes `CodexSourceAdapter.load_capsule()`.

- [ ] **Step 1: Add failing Capsule allowlist and truncation tests**

Use synthetic records containing high-signal user text and final decisions mixed with system/developer instructions, reasoning, encrypted content, subagent records, complete tool I/O, terminal logs, long code, diffs, attachments, and other turns. Require only the target completed turn's allowed high-level content.

Assert deterministic priority truncation toward about 1,200 model tokens and a hard 3,000-token estimator ceiling. The estimator is a local bound, not a claim of provider-token exactness. Assert `repr(capsule)` and all exceptions contain no content.

- [ ] **Step 2: Add failing pre- and post-safety tests**

Build a sentinel corpus for credentials, API keys, private keys, sensitive labels, long code/diff/log patterns, quotes, questions, hypotheticals, third-party facts, and unsupported psychological/personality inference. Known secrets must be absent before extractor invocation. `sensitive|secret`, policy-irrelevant, non-atomic, or unsupported output must never become a Collected Observation.

- [ ] **Step 3: Verify RED**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_capture_capsule_safety.py -q `
  --basetemp 'C:\tmp\agc-capture-runner-red-1'
```

- [ ] **Step 4: Implement deterministic content selection and gates**

Allow task title, completion time, stable project scope, current-turn high-signal user expressions, final-answer decisions/results/constraints/reusable methods/next steps, and high-level file locators without file bodies. Normalize line endings and Unicode before hashing. Compute `source_fingerprint` after pre-cleaning and `capsule_hash` over the exact privacy-filtered Capsule with separate schema versions.

The persistence gate returns stable accepted drafts plus content-free counts: filtered safety, filtered policy, duplicate within revision, and over limit. It stores no rejected draft. Use the specification's priority order and locator as the stable tie breaker to retain at most eight.

- [ ] **Step 5: Verify GREEN and commit**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest `
  tests/test_capture_capsule_safety.py tests/test_codex_source_adapter.py -q `
  --basetemp 'C:\tmp\agc-capture-runner-green-1'
git add agc_runtime/capture_capsule.py agc_runtime/capture_safety.py `
  agc_runtime/capture_source.py agc_runtime/codex_source_adapter.py `
  tests/test_capture_capsule_safety.py
git commit -m "feat: build safe in-memory task capsules"
```

---

### Task 2: Define the Extractor Schema and Isolated Codex Reference Adapter

**Files:**
- Create: `agc_runtime/capture_extractor.py`
- Create: `agc_runtime/codex_extractor.py`
- Create: `agc_runtime/schemas/capture-extractor-v1.schema.json`
- Create: `tests/fixtures/fake_codex_exec.py`
- Create: `tests/test_capture_extractor.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Produces: `ExtractorDescriptor`, `CapabilityProbe`, `CollectedObservationDraft`, and `ExtractionResult`.
- Packages the static schema via setuptools package data.
- Executes an argv list, never a shell command string.

- [ ] **Step 1: Add failing strict output-schema tests**

Test valid 0, 1, 8, and over-8 drafts; unknown/missing fields; malformed JSONL; multiple final outputs; nonzero exit; timeout; huge stdout/stderr; absent usage; invalid enums; and content sent only through stdin. Assert raw output and process errors never enter Receipt or logs.

- [ ] **Step 2: Add a real fake-process integration test**

Launch `tests/fixtures/fake_codex_exec.py` as a real child process. The fake must inspect argv/cwd/env/stdin and emit representative Codex JSONL events plus usage. Assert:

```text
--ephemeral
--ignore-user-config
--ignore-rules
--sandbox read-only
--output-schema <installed-static-schema>
--json
-
```

The working directory is a newly created empty directory; Capsule is stdin; no content file is created. If configured, append `--model <explicit-model>` without hard-coding one.

- [ ] **Step 3: Verify RED**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_capture_extractor.py -q `
  --basetemp 'C:\tmp\agc-capture-runner-red-2'
```

- [ ] **Step 4: Implement capability probe and bounded process parsing**

The probe checks the installed Codex version/help for all required flags and performs a content-free ephemeral smoke invocation. It reports executable identity, resolved model/provider boundary, auth availability, sandbox capability, and usage availability. Missing capability returns a content-free failure and prevents Runner activation.

Keep stdout/stderr bounded in memory, parse only supported event types, sanitize all failures to `stage/code/retryable`, and discard raw buffers immediately after parsing. Do not inherit AGC Hook variables into the child; ignore user config/rules so Skills/MCP/Hooks cannot recursively activate AGC.

- [ ] **Step 5: Verify GREEN and commit**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_capture_extractor.py -q `
  --basetemp 'C:\tmp\agc-capture-runner-green-2'
git add agc_runtime/capture_extractor.py agc_runtime/codex_extractor.py `
  agc_runtime/schemas/capture-extractor-v1.schema.json tests/fixtures/fake_codex_exec.py `
  tests/test_capture_extractor.py pyproject.toml
git commit -m "feat: add isolated semantic extractor"
```

---

### Task 3: Implement Durable Actual-or-Reserved Token Accounting

**Files:**
- Create: `agc_runtime/capture_budget.py`
- Create: `tests/test_capture_token_budget.py`
- Modify: `agc_runtime/capture_contracts.py`
- Modify: `agc_runtime/capture_store.py`
- Modify: `agc_runtime/capture_transaction.py`

**Interfaces:**
- Produces: `reserve(key, attempt, maximum) -> TokenReservation`.
- Produces: `settle(reservation, usage: TokenUsage | None) -> BudgetSettlement`.
- Backfill pool is fixed by frozen Census run and capped at 100,000; incremental pool is separate and cannot run while its configured total is null.

- [ ] **Step 1: Add failing AC-15 tests**

Create `test_ac_15_backfill_never_exceeds_actual_or_reserved_ceiling`. Test concurrent requests, exact boundary, one-token-over refusal, provider actual usage, absent usage, invalid/partial output, retry, process crash after reservation, restart, and attempted double settlement. Every invocation's input plus output or conservative reservation counts; no refund may make a crashed call disappear.

- [ ] **Step 2: Verify RED**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_capture_token_budget.py -q `
  --basetemp 'C:\tmp\agc-capture-runner-red-3'
```

- [ ] **Step 3: Implement reservation before subprocess start**

Persist the reservation under the root Capture lock before starting a model. If remaining budget cannot cover conservative maximum input plus output, do not invoke the extractor and transition to `deferred_budget`. Settle provider usage in the same semantic commit as Receipt token delta; when usage is absent or the process outcome is unknown, consume the reserved amount with `usage_quality=reserved`.

Token totals are monotonic and include wrapper prompt, invalid structured output, and every retry. Deterministic scan/hash/schema work is reported separately and never mixed into model-token totals.

- [ ] **Step 4: Verify GREEN and commit**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest `
  tests/test_capture_token_budget.py tests/test_capture_transaction.py -q `
  --basetemp 'C:\tmp\agc-capture-runner-green-3'
git add agc_runtime/capture_budget.py agc_runtime/capture_contracts.py `
  agc_runtime/capture_store.py agc_runtime/capture_transaction.py `
  tests/test_capture_token_budget.py
git commit -m "feat: enforce capture token budgets"
```

---

### Task 4: Implement the Single-Concurrency Failure-Open Runner

**Files:**
- Create: `agc_runtime/capture_runner.py`
- Create: `tests/test_capture_runner.py`
- Modify: `agc_runtime/capture_cli.py`
- Modify: `agc_runtime/capture_status_service.py`

**Interfaces:**
- Produces: `CaptureRunner.run_once(*, max_items: int) -> RunnerReport`.
- Extends CLI:

```text
agc-capture run --root <memory-root> --max-items <n>
agc-capture cycle --root <memory-root> --once --max-items <n>
agc-capture retry --root <memory-root> --revision-key <opaque-key>
```

- [ ] **Step 1: Add failing state-machine and failure-open tests**

Create exact nodes:

```text
tests/test_capture_runner.py::test_ac_07_complete_receipt_has_zero_to_eight_strict_observations
tests/test_capture_runner.py::test_ac_12_pipeline_failures_never_change_foreground_result
tests/test_capture_runner.py::test_ac_13_single_concurrency_lease_and_backpressure_never_drop_revisions
```

Cover paused, scanner-only, disabled, no incremental budget, source locked, source changed, capability unavailable, timeout, malformed output, all filtered, zero signal, over limit, duplicate drafts, commit crash, max five attempts, explicit retry, adapter/schema upgrade retry, stale lease, two workers, and queue backlog.

- [ ] **Step 2: Verify RED**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_capture_runner.py -q `
  --basetemp 'C:\tmp\agc-capture-runner-red-4'
```

- [ ] **Step 3: Implement one-item processing in the contractual order**

For each ready Revision:

```text
acquire fenced lease
transition queued -> extracting
probe/load target completed turn
pre-Capsule safety and in-memory Capsule/hash
reserve model budget
invoke exactly one extractor call
strict output + persistence gate + stable 0..8 selection
commit Observations + complete Receipt + Ledger processed + budget settlement
release lease and discard all content buffers
```

Map transient source/process/schema availability to retryable with configured backoff; fifth automatic failure becomes failed. Unknown identity or same-version source conflict becomes quarantined. Only explicit retry or compatible adapter/schema upgrade may requeue parked work. Sanitized errors contain only stage, stable code, and retryable boolean.

- [ ] **Step 4: Keep pause/backpressure truthful**

Runner reads `enabled`, `mode`, `paused`, concurrency, attempts, and budgets at cycle start. Paused stops new model calls but preserves queue/Ledger. Enforce concurrency one in Phase 1 even if config is tampered upward. Report backlog, oldest unresolved time, attempts, status deltas, token deltas, run time, bytes read, and peak-process diagnostics without content.

- [ ] **Step 5: Verify GREEN and commit**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest `
  tests/test_capture_runner.py tests/test_capture_cli.py tests/test_capture_status.py -q `
  --basetemp 'C:\tmp\agc-capture-runner-green-4'
git add agc_runtime/capture_runner.py agc_runtime/capture_cli.py `
  agc_runtime/capture_status_service.py tests/test_capture_runner.py
git commit -m "feat: run bounded background capture"
```

---

### Task 5: Prove Safety, Replay, Failure, and Coverage End to End

**Files:**
- Create: `tests/test_capture_end_to_end.py`
- Modify: `tests/test_capture_read_service.py`
- Modify: `tests/test_capture_backup_restore.py`
- Modify: `tests/test_capture_forget.py`

- [ ] **Step 1: Build the full synthetic pipeline test**

Use the Codex source fixtures and fake executable to run frozen Census → Scanner → Runner → explicit views. Include 0, 1, 8, over-8, short “continue”, duplicate, secret, sensitive, code/diff/log, provider failure, budget defer, retry, crash, continued Revision, format drift, and exclusion cases.

Require accounting 100%, silent loss zero, correct inspection completion, exact-replay delta zero, truthful unresolved/parked counts, valid zero reasons, one model call per attempt, and ordinary Recall/Catalog delta zero.

- [ ] **Step 2: Add the AC-10 persistence sentinel sweep**

Create `test_ac_10_forbidden_sentinels_never_reach_managed_persistence`. Search queue, cache, Receipt, Observation, Event, journal, archive, migration staging, and backup bytes. Forbidden sentinel hits and Capsule files must both be zero. Then run both forget targets and repeat the sweep for content/hash derivatives.

- [ ] **Step 3: Verify focused E2E**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_capture_end_to_end.py -q `
  --basetemp 'C:\tmp\agc-capture-runner-e2e'
```

- [ ] **Step 4: Verify the complete suite and package**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest -q `
  --basetemp 'C:\tmp\agc-capture-runner-full'
& '.\.venv\Scripts\python.exe' -m build
git diff --check
```

Install the built wheel in a temporary venv. Run `agc-capture probe` against synthetic roots only and the fake extractor; verify all package data and entry points work from the installed artifact.

- [ ] **Step 5: Record evidence and commit**

Update Flow evidence with exact tests, process boundaries, fake-vs-real integration coverage, assertion behavior, safety-sweep counts, token totals, and residual Provider retention boundary. Do not run a real seven-day backfill.

```powershell
git add tests/test_capture_end_to_end.py tests/test_capture_read_service.py `
  tests/test_capture_backup_restore.py tests/test_capture_forget.py `
  .llm-wiki/requirements/agc-capture-coverage-mvp.md `
  .llm-wiki/working-context/agc-capture-coverage-mvp.md
git commit -m "test: verify capture runner end to end"
```

## Acceptance Mapping

| Gate | Task/Test |
|---|---|
| AC-07 | Task 4 exact 0–8 schema test |
| AC-08 | Task 5 replay plus plan 1 Store test |
| AC-09 | Task 4/5 integration plus plan 1 crash matrix |
| AC-10 | Tasks 1 and 5 sentinel sweep |
| AC-12 | Task 4 failure-open state test |
| AC-13 | Task 4 lease/concurrency/backpressure test |
| AC-15 | Task 3 actual-or-reserved ceiling test |
| AC-17/18 | Task 5 regression through backup/forget |

## Exit Gate

Proceed to `2026-08-13-agent-global-context-capture-host-rollout.md` only when the synthetic full pipeline passes, installed package entry points work, no forbidden content or Capsule file is persisted, budget accounting is crash-safe, and the real active profile remains untouched and disabled.
