# Agent Global Context Codex Source and Census Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove that every in-scope completed Codex main-task revision can be discovered and truthfully accounted for without invoking a model or persisting task content.

**Architecture:** A versioned Codex Source Adapter treats local transcript JSONL as a private, drifting format. An optional metadata-only Stop Hook writes immutable dirty markers, while a reconciliation Scanner remains the coverage authority by comparing active/archive sources with a durable Census and Ledger. The plan ends at census-only operation: Receipts may be discovered, excluded, coalesced, retryable, or quarantined, but no Task Capsule or Observation is produced.

**Tech Stack:** Python 3.10+, JSONL streaming, pathlib, SHA-256 root identity, Windows-safe immutable spool files, pytest synthetic fixtures, existing Capture Store from plan 1.

## Global Constraints

- Requires the exit gate of `docs/superpowers/plans/2026-08-13-agent-global-context-capture-core.md`.
- This is plan 2 of 4. It performs no semantic extraction and no model/network call.
- The configured active Codex profile is the only source scope. `source_root_id` is derived from the canonical resolved `CODEX_HOME`; backup, recovery, temp, and other profile roots are excluded.
- Main completed turn is the unit: `(adapter_id, source_root_id, task_id, turn_id)`. A file is not a Task or Revision identity.
- Scanner recognizes a completed Revision only from a version-supported `task_complete` record with a stable `turn_id`. `task_started`, aborted turns, half-written tails, mtime, file size, and session index updates do not prove completion.
- Subagent sources are excluded. Unknown identity/completion shapes fail closed; keyed anomalies get a quarantined Receipt, unkeyed anomalies get a content-free Source Quarantine.
- Hook delivery is optional and never a correctness dependency. Hook failure must not affect the Codex task result.
- No test fixture may contain a real user prompt, answer, path, token, credential, or copied transcript.
- Every task follows red-green TDD and ends in a focused commit.

## Stable Source Interfaces

```python
class SourceAdapter(Protocol):
    def describe(self) -> AdapterDescriptor: ...
    def accept_stop(self, envelope: StopHookEnvelope) -> DirtyMarker: ...
    def discover(
        self, hint: ScanHint | None, window: TimeWindow
    ) -> DiscoveryBatch: ...
    def probe(self, ref: RevisionRef) -> SourceProbe: ...
    def load_capsule(
        self, ref: RevisionRef, policy: CapturePolicy
    ) -> CapsuleResult: ...
```

This plan implements `describe`, `accept_stop`, `discover`, and `probe`. `load_capsule` must explicitly raise `CapabilityUnavailable("semantic_capture_not_installed")` until plan 3 implements the in-memory content boundary.

---

### Task 1: Define Versioned Source, Scan, Census, and Project-Identity Contracts

**Files:**
- Create: `agc_runtime/capture_source.py`
- Create: `agc_runtime/project_identity.py`
- Create: `tests/test_capture_source_contracts.py`
- Create: `tests/test_project_identity.py`
- Modify: `agc_runtime/capture_contracts.py`
- Modify: `agc_runtime/capture_schema.py`
- Modify: `agc_runtime/runtime_config.py`
- Modify: `agc_runtime/default_config.yaml`
- Modify: `templates/memory/config.yaml`

**Interfaces:**
- Produces: `AdapterDescriptor`, `SourceBindingKey`, `StopHookEnvelope`, `DirtyMarker`, `ScanHint`, `TimeWindow`, `DiscoveryBatch`, `SourceProbe`, `SourceQuarantine`, `CensusRun`, `ScanState`, and `ProjectIdentity`.
- Produces: `canonical_source_root(path: Path) -> Path` and `source_root_id_for(path: Path) -> str`.
- Uses the core `capture.mode: off|scanner_only|runner` contract and adds source-dependent readiness rules; installed default remains `off` while `capture.enabled=false`.

- [ ] **Step 1: Add failing strict-contract tests**

Require four-part Capture identity, versioned opaque hints, UTC half-open windows, content-free Source Quarantine, and project identity resolution order: explicit registry → Git common-dir identity → generated registry identity → `None`. Assert no persisted DTO exposes a workstation absolute path.

Test Windows path normalization for case, non-ASCII names, long paths, and junction aliases. Two physical roots must not collide; aliases to one physical root must share an ID.

- [ ] **Step 2: Verify RED**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest `
  tests/test_capture_source_contracts.py tests/test_project_identity.py -q `
  --basetemp 'C:\tmp\agc-capture-source-red-1'
```

- [ ] **Step 3: Implement strict source contracts and configuration**

`source_root_id_for()` hashes canonical normalized resolved path bytes but returns only the opaque digest. Config may contain a local absolute source root because it is an operator binding; Receipt, Observation, status, logs, and backups may contain only `source_root_id` and opaque relative locator.

Add `capture.mode` validation:

```text
enabled=false  -> mode must be off
enabled=true   -> mode may be scanner_only or runner
mode=runner    -> plan 3 activation gates must pass
```

Keep `include_subagents=false` fixed in schema version 1.

- [ ] **Step 4: Verify GREEN and commit**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest `
  tests/test_capture_source_contracts.py tests/test_project_identity.py tests/test_runtime_config.py -q `
  --basetemp 'C:\tmp\agc-capture-source-green-1'
git add agc_runtime/capture_source.py agc_runtime/project_identity.py `
  agc_runtime/capture_contracts.py agc_runtime/capture_schema.py agc_runtime/runtime_config.py `
  agc_runtime/default_config.yaml templates/memory/config.yaml `
  tests/test_capture_source_contracts.py tests/test_project_identity.py
git commit -m "feat: define capture source contracts"
```

---

### Task 2: Implement the Versioned Codex Main-Task Source Adapter

**Files:**
- Create: `agc_runtime/codex_source_adapter.py`
- Create: `tests/test_codex_source_adapter.py`
- Create: `tests/fixtures/codex_source/v1/sessions/main-multiple-turns.jsonl`
- Create: `tests/fixtures/codex_source/v1/sessions/main-partial-tail.jsonl`
- Create: `tests/fixtures/codex_source/v1/sessions/subagent.jsonl`
- Create: `tests/fixtures/codex_source/v1/archived_sessions/main-archived-copy.jsonl`
- Create: `tests/fixtures/codex_source/v1/sessions/unknown-source.jsonl`
- Create: `tests/fixtures/codex_source/v1/sessions/legacy-main.jsonl`

**Interfaces:**
- Produces: `CodexSourceAdapter(SourceAdapter)` with `adapter_id="codex"` and explicit adapter/source schema versions.
- Enumerates only configured-root `sessions/**/*.jsonl` and `archived_sessions/**/*.jsonl`.
- Uses `session_meta.payload.session_id`, with a version-labelled legacy fallback to `session_meta.payload.id` and `identity_quality="legacy_rollout_id"`.

- [ ] **Step 1: Add failing AC-04 and AC-19 tests**

Create exact nodes:

```text
tests/test_codex_source_adapter.py::test_ac_04_only_completed_main_turns_are_revisions
tests/test_codex_source_adapter.py::test_ac_19_unknown_formats_fail_closed_without_false_conflicts
```

The fixture must cover multiple complete turns in one file, same Task continued with a new turn ID, started-only, aborted, trailing half-line, active/archive move, duplicate index hint, explicit subagent, legacy ID quality, unknown source shape, and a simulated Windows sharing violation.

- [ ] **Step 2: Verify RED**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_codex_source_adapter.py -q `
  --basetemp 'C:\tmp\agc-capture-source-red-2'
```

- [ ] **Step 3: Implement tolerant streaming and strict identity/completion output**

Ignore unknown non-critical records. Treat the first anchored `session_meta.payload.source` string as main only for supported source-schema versions; treat a source object with `subagent` or `thread_source=subagent` as excluded. A complete Revision requires `event_msg.payload.type="task_complete"` plus non-empty `turn_id`.

Do not trust path, mtime, size, last message, or session index as identity. Validate every locator resolves inside the configured source root and persist a relative opaque locator. On locks, half-lines, or incomplete tails return retryable diagnostics; do not guess.

- [ ] **Step 4: Prepare source-fingerprint version semantics without loading task content in census-only mode**

Provide an internal target-turn record iterator for plan 3's in-memory pre-Capsule gate, but do not call it from census-only discovery and leave Receipt `source_fingerprint` fields null. Define comparison results now: a different fingerprint is a conflict only when key and hash-schema version are equal; cross-version comparison is `not_comparable`, not quarantine. Plan 3 is the first stage allowed to compute and persist a fingerprint after privacy filtering.

- [ ] **Step 5: Verify GREEN and commit**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_codex_source_adapter.py -q `
  --basetemp 'C:\tmp\agc-capture-source-green-2'
git add agc_runtime/codex_source_adapter.py tests/test_codex_source_adapter.py `
  tests/fixtures/codex_source/v1
git commit -m "feat: discover completed Codex revisions"
```

---

### Task 3: Add the Metadata-Only Stop Hook and Immutable Dirty Spool

**Files:**
- Create: `agc_runtime/capture_dirty.py`
- Create: `agc_runtime/capture_hook.py`
- Create: `tests/test_capture_hook.py`
- Modify: `pyproject.toml`
- Modify: `tests/test_cli_contract.py`

**Interfaces:**
- Adds package entry point `agc-capture-hook = "agc_runtime.capture_hook:main"`; its operation form is `agc-capture-hook --root <memory-root>` and the host-installed launcher binds that exact root.
- Hook consumes stdin JSON and always exits without stdout/stderr content that could affect the foreground task.
- Dirty spool uses one event per temporary file followed by atomic `os.replace`; it never uses a shared append-only JSONL.

- [ ] **Step 1: Add failing metadata and failure-open tests**

Pass `session_id`, `turn_id`, `transcript_path`, `cwd`, `hook_event_name=Stop`, `model`, `stop_hook_active`, and a sentinel-filled `last_assistant_message`. Assert the marker contains only schema/adapter/root versions, task/revision IDs, validated relative locator or null, observed time, and Hook event. Scan the entire memory root for the sentinel and require zero hits.

Inject malformed stdin, path escape, reparse-point escape, spool collision, permission failure, and disk-write failure. The Hook must remain foreground failure-open; Scanner correctness does not depend on the marker.

- [ ] **Step 2: Verify RED**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_capture_hook.py tests/test_cli_contract.py -q `
  --basetemp 'C:\tmp\agc-capture-source-red-3'
```

- [ ] **Step 3: Implement minimal immutable spool behavior**

Never open the transcript in Hook code. Never import the Scanner, Store, extractor, MCP, or formal-memory write service. Generate the marker filename from the stable key plus a nonce, write strict UTF-8 JSON to the dirty temp directory, fsync where supported, and atomically install it. A duplicate marker is harmless and is deduplicated later by key.

- [ ] **Step 4: Verify GREEN and commit**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_capture_hook.py tests/test_cli_contract.py -q `
  --basetemp 'C:\tmp\agc-capture-source-green-3'
git add agc_runtime/capture_dirty.py agc_runtime/capture_hook.py pyproject.toml `
  tests/test_capture_hook.py tests/test_cli_contract.py
git commit -m "feat: add metadata-only capture hook"
```

---

### Task 4: Implement Frozen Census, Durable Ledger, Scan State, and Reconciliation

**Files:**
- Create: `agc_runtime/capture_ledger.py`
- Create: `agc_runtime/capture_scanner.py`
- Create: `tests/test_capture_ledger.py`
- Create: `tests/test_capture_scanner.py`
- Modify: `agc_runtime/capture_store.py`
- Modify: `agc_runtime/capture_transaction.py`

**Interfaces:**
- Adds `freeze_census`, `load_scan_state`, `advance_scan_state`, and `ready_revisions` to `CaptureStore`.
- Scanner order: recover journals → drain dirty markers → enumerate active/archive → reconcile overlap → create/confirm truthful Receipts → advance only safe scan hints → acknowledge markers.
- The durable Revision identity set is correctness truth; cursor/file offsets are only optimizations.

- [ ] **Step 1: Add failing Ledger and scan-state tests**

Prove a frozen run persists the exact half-open window `[run_started_at-7d, run_started_at]` before any semantic processing. Test optimistic scan-state versioning, file shrink/rebuild, anchor change, late completion, out-of-order write, archive move, duplicate roots, dirty-marker replay, process restart, and marker acknowledgment only after Ledger/Receipt durability.

- [ ] **Step 2: Add failing AC-03 and AC-06 tests**

Create exact nodes:

```text
tests/test_capture_scanner.py::test_ac_03_synthetic_seven_day_census_has_full_accounting
tests/test_capture_scanner.py::test_ac_06_reconciliation_recovers_missed_duplicate_and_moved_sources
```

The synthetic Census contains normal, zero-future-observation, 8, over-8, continued, excluded, corrupt, late, active/archive duplicate, and unkeyed unknown shapes. At this plan boundary require known-key accounting 100%, silent loss 0, truthful non-success states, and degraded Source Health for unkeyed anomalies.

- [ ] **Step 3: Verify RED**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest `
  tests/test_capture_ledger.py tests/test_capture_scanner.py -q `
  --basetemp 'C:\tmp\agc-capture-source-red-4'
```

- [ ] **Step 4: Implement reconciliation and coalescing**

One active-to-archive move with the same key is exact replay. Across distinct explicitly configured roots, the Store may coalesce only when a later safe-load stage supplies identity plus a same-version source fingerprint proving equality; write `coalesced_to` and validate its canonical Receipt. Census-only mode has no fingerprint, so it retains separate discovered state rather than guessing. Otherwise retain separate state or quarantine—never silently swallow.

Advance the opaque hint only when every discovered Census key has a Receipt or authorized suppression tombstone. Cursor failure cannot remove queued/retryable/deferred entries. Source Quarantine remains outside the denominator but degrades health.

- [ ] **Step 5: Verify GREEN and commit**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest `
  tests/test_capture_ledger.py tests/test_capture_scanner.py tests/test_capture_transaction.py -q `
  --basetemp 'C:\tmp\agc-capture-source-green-4'
git add agc_runtime/capture_ledger.py agc_runtime/capture_scanner.py `
  agc_runtime/capture_store.py agc_runtime/capture_transaction.py `
  tests/test_capture_ledger.py tests/test_capture_scanner.py
git commit -m "feat: reconcile capture census and ledger"
```

---

### Task 5: Add Census-Only Operations Without Enabling Semantic Capture

**Files:**
- Create: `agc_runtime/capture_cli.py`
- Create: `tests/test_capture_cli.py`
- Modify: `agc_runtime/capture_status_service.py`
- Modify: `agc_runtime/admin_service.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Adds `agc-capture = "agc_runtime.capture_cli:main"`.
- Provides:

```text
agc-capture probe --root <memory-root>
agc-capture scan --root <memory-root> --mode census|incremental --once
agc-capture cycle --root <memory-root> --once
```

- `cycle` performs scan only while `capture.mode=scanner_only`; it must refuse a Runner path until plan 3 exists.

- [ ] **Step 1: Add failing CLI and safe-default tests**

Require machine-readable envelopes, host-bound root, explicit config activation, no scan while disabled, no scan of unspecified roots, no semantic import/call, and content-free diagnostics. `capture_status` reports Scanner health and latest Census counts without exposing paths.

- [ ] **Step 2: Verify RED**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest `
  tests/test_capture_cli.py tests/test_capture_status.py tests/test_cli_contract.py -q `
  --basetemp 'C:\tmp\agc-capture-source-red-5'
```

- [ ] **Step 3: Implement the one-shot CLI**

`probe` is read-only. `scan` requires `enabled=true` and `mode=scanner_only`, then freezes or reconciles only the configured window/root. `cycle --once` is intentionally one-shot so the Host plan can supervise it without embedding a daemon in MCP. Every error remains content-free and exits nonzero only for the background invocation, never the original Codex task.

- [ ] **Step 4: Verify GREEN and commit**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest `
  tests/test_capture_cli.py tests/test_capture_status.py tests/test_cli_contract.py -q `
  --basetemp 'C:\tmp\agc-capture-source-green-5'
git add agc_runtime/capture_cli.py agc_runtime/capture_status_service.py `
  agc_runtime/admin_service.py pyproject.toml tests/test_capture_cli.py
git commit -m "feat: add census-only capture operations"
```

---

### Task 6: Prove Scanner-Only Coverage and No Foreground or Semantic Work

**Files:**
- Create: `tests/test_capture_census_end_to_end.py`
- Modify: `.llm-wiki/requirements/agc-capture-coverage-mvp.md`
- Modify: `.llm-wiki/working-context/agc-capture-coverage-mvp.md`

- [ ] **Step 1: Add the synthetic scanner-only end-to-end test**

Build a synthetic profile with active/archive moves, continued tasks, subagents, bad shapes, lock/retry, and missed Hook delivery. Run two complete reconciliation cycles. Require exact-replay delta zero, accounting 100%, silent loss zero, Source Health truth, and zero Observation/model/subprocess calls.

- [ ] **Step 2: Run focused and complete gates**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_capture_census_end_to_end.py -q `
  --basetemp 'C:\tmp\agc-capture-census-e2e'
& '.\.venv\Scripts\python.exe' -m pytest -q `
  --basetemp 'C:\tmp\agc-capture-census-full'
& '.\.venv\Scripts\python.exe' -m build
git diff --check
```

- [ ] **Step 3: Record evidence and commit**

Record exact synthetic counts, replay delta, Source Quarantine count, file/byte scan diagnostics, and proof of zero semantic calls. Do not enable a real profile or claim continuous hosting.

```powershell
git add tests/test_capture_census_end_to_end.py `
  .llm-wiki/requirements/agc-capture-coverage-mvp.md `
  .llm-wiki/working-context/agc-capture-coverage-mvp.md
git commit -m "test: verify scanner-only capture coverage"
```

## Acceptance Mapping

| Gate | Task/Test |
|---|---|
| AC-03 | Task 4 synthetic Census; Task 6 end-to-end |
| AC-04 | Task 2 completed-main-turn test |
| AC-05 metadata boundary | Task 3 Hook content test; latency gate is plan 4 |
| AC-06 | Task 4 reconciliation recovery test |
| AC-08 source replay | Tasks 2 and 4; Observation replay remains plan 1/3 |
| AC-12 foreground separation | Task 3 failure-open Hook and Task 6 zero semantic calls |
| AC-14 scanner-only | Tasks 1 and 5 |
| AC-19 | Tasks 2 and 4 format-drift/Source Health tests |

## Exit Gate

Proceed to `2026-08-13-agent-global-context-capture-extractor-runner.md` only when the synthetic Census is complete and replay-safe, Scanner-only is diagnosable, all real-profile behavior is still off, and the test suite proves no model or Task Capsule persistence path exists.
