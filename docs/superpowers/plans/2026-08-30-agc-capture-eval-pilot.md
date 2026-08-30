# AGC Capture Eval Pilot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one manual, explicitly authorized AGC Capture-quality Pilot that records one content-free Trace event per completed Capture item, resolves the referenced safe Capsule and CollectedObservations inside AGC, and evaluates them through Eval Runtime without changing any memory.

**Architecture:** Capture remains the domain authority. The Runner creates an AGC-owned evidence digest while the safe Capsule and terminal observations are in memory, the existing failure-open bridge writes only the opaque EvidenceRef and aggregate decision metadata to Trace, and a separate manual `agc-eval` command combines the public TraceSnapshot with AGC-resolved evidence and the AGC-owned `agc.capture-quality` profile.

**Tech Stack:** Python 3.10+ base Runtime, Python 3.12+ optional Eval profile, pytest 9.1.1, JSON Schema contracts from `agent-runtime-modules`, optional `agent-trace-runtime` 0.1.x, `agent-eval-runtime` 0.1.x, and `agent-eval-codex` 0.1.x.

## Global Constraints

- Implement the confirmed mixed mode: TraceSnapshot plus AGC-controlled evidence.
- Capture Runner evaluates CollectedObservation extraction and justified zero results; it does not claim to evaluate formal-memory create/merge decisions that occur later.
- Keep automatic Capture behavior, scheduling interval, source discovery, budgets, extraction, persistence, review, Recall, and formal Memory unchanged.
- Emit `agc.capture.item.completed` only after an immutable `complete` receipt is committed; deferred, retryable, failed, quarantined, and repeated revisions do not create Eval cases in this Pilot.
- At most one item event and one EvalCase may exist for one completed receipt/evidence digest.
- Trace payloads may contain counts, reason codes, versions, Token usage, and EvidenceRef; they may not contain source/Capsule/Observation/Memory text or raw Session/task/revision identifiers outside the opaque EvidenceRef.
- AGC owns the `agc.capture.item-trace.v1`, `agc.capture-evidence.v1`, and `agc.capture-quality:1` semantics.
- Eval and Trace imports remain lazy and optional; missing packages or unavailable stores never change Capture success, failure, exit code, receipt, observation, or budget settlement.
- EvalResult cannot write, delete, merge, promote, or otherwise mutate AGC state.
- The first Pilot is manual and requires a fresh digest over the exact selected cases, profile, and model before any evidence is sent to a Judge.
- Require the exact configured selector `codex-app` for this Pilot and use its resolved bundled executable plus configured model boundary; do not fall back silently to npm, PATH, a literal standalone CLI, another model, or another provider.
- Put every test database, fake source, build, wheel, install, and live Pilot artifact below `D:\tmp_test`.
- Stop before production installation, scheduled-task mutation, live evidence transmission, GitHub push, publication, or release tag unless the user separately authorizes that action.

---

### Task 1: Define stable Capture evidence and item reports

**Files:**
- Create: `agc_runtime/capture_eval_evidence.py`
- Create: `tests/test_capture_eval_evidence.py`
- Modify: `agc_runtime/capture_runner.py`
- Modify: `tests/test_capture_manual_runner.py`

**Interfaces:**
- Produces: `capture_eval_evidence_content(capsule, receipt, observations) -> dict[str, Any]`.
- Produces: `capture_item_trace_report(capsule, receipt, observations, occurred_at) -> CaptureItemTraceReport`.
- Extends: `RunnerReport.trace_items: tuple[CaptureItemTraceReport, ...]`, excluded from `RunnerReport.to_mapping()`.

- [ ] **Step 1: Write failing evidence-contract tests**

Create tests using the existing `TaskCapsule`, `CaptureReceipt`, and `CollectedObservation` factories. The main assertions are:

```python
def test_capture_evidence_ref_binds_capsule_decision_and_observations() -> None:
    capsule, receipt, observations = completed_capture_fixture()
    report = capture_item_trace_report(
        capsule=capsule,
        receipt=receipt,
        observations=observations,
        occurred_at="2026-08-30T08:00:00Z",
    )
    content = capture_eval_evidence_content(capsule, receipt, observations)

    assert report.payload == {
        "schema_version": "agc.capture.item-trace.v1",
        "outcome": "collected",
        "reason_code": "observations_collected",
        "observation_count": 1,
        "filtered_counts": {"safety": 0, "policy": 0, "over_limit": 0},
        "duplicate_suppression_count": 0,
        "token_usage": {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
        "extractor_version": receipt.extractor_version,
        "taxonomy_version": receipt.taxonomy_version,
        "evidence_ref": {
            "schema_version": "eval.evidence-ref.v0.1",
            "provider": "agc",
            "kind": "capture-item",
            "ref": receipt.receipt_id,
            "digest": canonical_sha256(content),
            "version": "1",
        },
    }
```

Add a zero-result test proving outcome `zero`, reason `no_durable_signal`, and an empty observation list in resolved evidence. Add strict rejection tests for non-complete receipts, observation-count mismatch, observation bound to a different receipt, missing extractor/taxonomy/capsule hash, non-UTC occurrence time, and more than eight observations.

Add this privacy assertion:

```python
def test_trace_report_contains_no_capsule_or_observation_text() -> None:
    capsule, receipt, observations = completed_capture_fixture(
        sentinel="private-capture-evidence-must-not-enter-trace"
    )
    report = capture_item_trace_report(
        capsule=capsule,
        receipt=receipt,
        observations=observations,
        occurred_at="2026-08-30T08:00:00Z",
    )
    assert "private-capture-evidence-must-not-enter-trace" not in repr(report)
    assert "task_id" not in repr(report)
    assert "revision_id" not in repr(report)
```

- [ ] **Step 2: Run focused tests and verify RED**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest -q -p no:cacheprovider `
  tests\test_capture_eval_evidence.py `
  --basetemp 'D:\tmp_test\agc-capture-eval\evidence-red'
```

Expected: import failure because `capture_eval_evidence` does not exist.

- [ ] **Step 3: Implement canonical evidence content and opaque references**

Create `capture_eval_evidence.py` with these public shapes:

```python
from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from agc_runtime.capture_capsule import TaskCapsule
from agc_runtime.capture_contracts import CaptureReceipt, CollectedObservation


@dataclass(frozen=True)
class CaptureItemTraceReport:
    occurred_at: str
    payload: dict[str, Any] = field(repr=False)


def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _observation_value(item: CollectedObservation) -> dict[str, Any]:
    return {
        "statement": item.statement,
        "assertion": dict(item.assertion),
        "primary_category": item.primary_category,
        "kind": item.kind,
        "scopes": list(item.scopes),
        "project_scope": item.project_scope,
        "confidence": item.confidence,
        "sensitivity": item.sensitivity,
        "signal_type": item.signal_type,
    }


def capture_eval_evidence_content(
    capsule: TaskCapsule,
    receipt: CaptureReceipt,
    observations: Sequence[CollectedObservation],
) -> dict[str, Any]:
    if not isinstance(capsule, TaskCapsule) or not isinstance(receipt, CaptureReceipt):
        raise ValueError("capture_eval_evidence_invalid")
    items = tuple(observations)
    if (
        receipt.status != "complete"
        or receipt.observation_count != len(items)
        or len(items) > 8
        or any(item.receipt_id != receipt.receipt_id for item in items)
        or receipt.capsule_hash is None
        or receipt.capsule_schema_version is None
        or receipt.extractor_version is None
        or receipt.taxonomy_version is None
        or receipt.filtered_counts is None
        or receipt.duplicate_suppression_count is None
    ):
        raise ValueError("capture_eval_evidence_invalid")
    outcome = "collected" if items else "zero"
    reason = "observations_collected" if items else receipt.zero_reason
    if not isinstance(reason, str) or not reason:
        raise ValueError("capture_eval_evidence_invalid")
    return {
        "schema_version": "agc.capture-evidence.v1",
        "capsule": capsule.to_mapping(),
        "decision": {
            "outcome": outcome,
            "reason_code": reason,
            "observations": [_observation_value(item) for item in items],
            "filtered_counts": dict(receipt.filtered_counts),
            "duplicate_suppression_count": receipt.duplicate_suppression_count,
        },
        "runtime": {
            "capsule_hash": receipt.capsule_hash,
            "capsule_schema_version": receipt.capsule_schema_version,
            "extractor_version": receipt.extractor_version,
            "taxonomy_version": receipt.taxonomy_version,
            "token_usage": receipt.token_usage.to_mapping(),
        },
    }
```

Implement `capture_item_trace_report` by validating `datetime.fromisoformat(occurred_at.replace("Z", "+00:00"))`, building the content above, and returning the exact content-free payload asserted in Step 1. The EvidenceRef `ref` is the already content-derived `cr_<sha256>` receipt ID; Trace and Eval treat it as opaque.

- [ ] **Step 4: Add item reports to the Runner without changing public reports**

Extend `RunnerReport` with a final defaulted field:

```python
    trace_items: tuple[CaptureItemTraceReport, ...] = ()
```

Change `to_mapping()` to exclude that field:

```python
    def to_mapping(self) -> dict[str, Any]:
        result = {
            name: getattr(self, name)
            for name in self.__dataclass_fields__
            if name != "trace_items"
        }
        result["status_deltas"] = dict(self.status_deltas)
        return result
```

Inside `_run_manual_backfill_locked`, initialize `trace_items: list[CaptureItemTraceReport] = []`. Immediately after each of the two successful `store.commit_extraction(...)` calls, append one report using the exact Capsule used for extraction, the terminal receipt, the committed observations, and `now`. Pass `trace_items=tuple(trace_items)` in the final RunnerReport. Do not append on lease contention, budget defer, retryable, failed, quarantined, or exception branches.

- [ ] **Step 5: Add Runner regression coverage**

Extend `tests/test_capture_manual_runner.py`:

```python
def test_runner_returns_one_trace_item_for_one_completed_receipt(tmp_path: Path) -> None:
    paths, adapter, extractor, preparation = _prepared(tmp_path)
    runner = CaptureRunner(paths, (adapter,), extractor, preparation)
    first = runner.run_manual_backfill(
        authorization_digest=preparation.authorization_digest,
        max_items=20,
        now=RUN_AT,
    )
    second = runner.run_manual_backfill(
        authorization_digest=preparation.authorization_digest,
        max_items=20,
        now=RUN_AT,
    )
    assert len(first.trace_items) == 1
    assert first.trace_items[0].payload["outcome"] == "collected"
    assert second.trace_items == ()
    assert "trace_items" not in first.to_mapping()
```

Add these matching boundaries:

```python
def test_zero_result_has_one_zero_trace_item(tmp_path: Path) -> None:
    paths, adapter, extractor, preparation = _prepared(tmp_path)
    adapter.user_signals = ()
    report = CaptureRunner(paths, (adapter,), extractor, preparation).run_manual_backfill(
        authorization_digest=preparation.authorization_digest,
        max_items=20,
        now=RUN_AT,
    )
    assert len(report.trace_items) == 1
    assert report.trace_items[0].payload["outcome"] == "zero"
    assert report.trace_items[0].payload["reason_code"] == "no_durable_signal"


def test_extractor_failure_has_no_completed_trace_item(tmp_path: Path) -> None:
    paths, adapter, extractor, preparation = _prepared(tmp_path)
    extractor.always_fail = True
    report = CaptureRunner(paths, (adapter,), extractor, preparation).run_manual_backfill(
        authorization_digest=preparation.authorization_digest,
        max_items=20,
        now=RUN_AT,
    )
    assert report.failed_count == 1
    assert report.trace_items == ()


def test_budget_defer_has_no_completed_trace_item(tmp_path: Path) -> None:
    paths, adapter, extractor, preparation = _prepared(tmp_path, total=1)
    report = CaptureRunner(paths, (adapter,), extractor, preparation).run_manual_backfill(
        authorization_digest=preparation.authorization_digest,
        max_items=20,
        now=RUN_AT,
    )
    assert report.deferred_budget_count == 1
    assert report.trace_items == ()
```

- [ ] **Step 6: Verify GREEN and commit**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest -q -p no:cacheprovider `
  tests\test_capture_eval_evidence.py tests\test_capture_manual_runner.py `
  --basetemp 'D:\tmp_test\agc-capture-eval\evidence-green'

git add -- agc_runtime/capture_eval_evidence.py agc_runtime/capture_runner.py `
  tests/test_capture_eval_evidence.py tests/test_capture_manual_runner.py
git commit -m "feat(capture): bind item evaluation evidence"
```

### Task 2: Emit item-level domain events through the existing failure-open bridge

**Files:**
- Modify: `agc_runtime/capture_trace.py`
- Modify: `agc_runtime/capture_cli.py`
- Modify: `tests/test_capture_trace.py`
- Modify: `tests/test_capture_cli.py`

**Interfaces:**
- Extends: `record_capture_success(..., items: Sequence[CaptureItemTraceReport] = ()) -> TraceStatus`.
- Produces: zero or more `agc.capture.item.completed` events between the existing root started/completed events.
- Preserves: absent opt-in, empty-cycle suppression, exact cycle summary allowlist, and failure-open behavior.

- [ ] **Step 1: Write failing bridge tests for one item event**

Extend the existing fake Trace Runtime test:

```python
def test_significant_success_records_content_free_item_event(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_TRACE_DB", r"D:\tmp_test\trace.sqlite3")
    events, _resolved = _install_fake_runtime(monkeypatch)
    item = safe_item_report()

    status = record_capture_success(
        action="cycle",
        started_at=STARTED_AT,
        finished_at=FINISHED_AT,
        report=_report(completed_count=1, observation_count=1),
        items=(item,),
    )

    assert status == "recorded"
    assert [event["event_type"] for event in events] == [
        "trace.root.started",
        "agc.capture.item.completed",
        "trace.root.completed",
    ]
    assert events[1]["source"] == "principal"
    assert events[1]["trace_id"] == events[0]["trace_id"] == events[2]["trace_id"]
    assert events[1]["span_id"] == events[0]["span_id"] == events[2]["span_id"]
    assert events[1]["timestamp"] == datetime.fromisoformat(
        item.occurred_at.replace("Z", "+00:00")
    )
    assert events[1]["payload"] == item.payload
    assert SENTINEL not in repr(events)
```

The fake `create_event` already records the datetime returned by its clock. Import `replace` from `dataclasses` and add these exact boundaries:

```python
def test_item_batch_is_bounded_and_malformed_payload_fails_closed(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_TRACE_DB", r"D:\tmp_test\trace.sqlite3")
    _install_fake_runtime(monkeypatch)
    item = safe_item_report()
    assert record_capture_success(
        action="cycle",
        started_at=STARTED_AT,
        finished_at=FINISHED_AT,
        report=_report(completed_count=1),
        items=(item,) * 101,
    ) == "unavailable"
    malformed = replace(item, payload={"raw": SENTINEL})
    assert record_capture_success(
        action="cycle",
        started_at=STARTED_AT,
        finished_at=FINISHED_AT,
        report=_report(completed_count=1),
        items=(malformed,),
    ) == "unavailable"


def test_item_emit_failure_never_raises_into_capture(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_TRACE_DB", r"D:\tmp_test\trace.sqlite3")
    _install_fake_runtime(monkeypatch, fail_emit_at=2)
    assert record_capture_success(
        action="cycle",
        started_at=STARTED_AT,
        finished_at=FINISHED_AT,
        report=_report(completed_count=1),
        items=(safe_item_report(),),
    ) == "unavailable"
```

- [ ] **Step 2: Run bridge tests and verify RED**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest -q -p no:cacheprovider `
  tests\test_capture_trace.py tests\test_capture_cli.py -k 'trace or runner' `
  --basetemp 'D:\tmp_test\agc-capture-eval\trace-item-red'
```

- [ ] **Step 3: Extend the bridge with a strict item allowlist**

Add `items` to `record_capture_success`, reject non-sequences, strings, more than 100 entries, wrong dataclass values, timestamps that are not timezone-aware UTC, or payloads whose exact keys differ from:

```python
_ITEM_FIELDS = frozenset(
    {
        "schema_version",
        "outcome",
        "reason_code",
        "observation_count",
        "filtered_counts",
        "duplicate_suppression_count",
        "token_usage",
        "extractor_version",
        "taxonomy_version",
        "evidence_ref",
    }
)
```

Reuse `CaptureItemTraceReport` validation rather than reading any AGC store. Extend `_emit_root` to emit each accepted item with:

```python
service.emit(
    create_event(
        trace_id=trace_id,
        span_id=span_id,
        parent_span_id=None,
        event_type="agc.capture.item.completed",
        source="principal",
        principal_ref=principal,
        payload=item.payload,
        clock=lambda observed=item_datetime: observed,
    )
)
```

Keep root lifecycle events `source="runtime"`. Do not create child spans or new Trace contracts.

- [ ] **Step 4: Pass Runner items only at the CLI integration boundary**

Change the existing call to:

```python
trace_status = record_capture_success(
    action=action,
    started_at=trace_started_at,
    report=report_mapping,
    items=report.trace_items,
)
```

Extend the CLI test to assert the exact `items` tuple was forwarded while the JSON ToolResponse still contains no `trace_items` or EvidenceRef.

- [ ] **Step 5: Verify GREEN and commit**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest -q -p no:cacheprovider `
  tests\test_capture_trace.py tests\test_capture_cli.py `
  --basetemp 'D:\tmp_test\agc-capture-eval\trace-item-green'

git add -- agc_runtime/capture_trace.py agc_runtime/capture_cli.py `
  tests/test_capture_trace.py tests/test_capture_cli.py
git commit -m "feat(capture): trace completed item evidence"
```

### Task 3: Build the AGC EvidenceResolver and Trace-to-EvalCase adapter

**Files:**
- Create: `agc_runtime/capture_eval_adapter.py`
- Create: `tests/test_capture_eval_adapter.py`

**Interfaces:**
- Produces: `AGCCaptureEvidenceResolver.resolve(reference) -> Mapping[str, Any]`.
- Produces: `capture_eval_cases(trace_reader, profile_ref, implementation_version, max_items) -> tuple[dict[str, Any], ...]`.
- Consumes only: one read-only `CaptureStore.read_snapshot()`, configured SourceAdapters, current CapsulePolicy, and Trace Runtime public `list_traces`, `events`, and `snapshot` methods.

- [ ] **Step 1: Write failing resolver tests**

Use the existing synthetic Adapter/Runner fixture to create one complete receipt, then assert:

```python
def test_resolver_rebuilds_exact_capture_evidence(tmp_path: Path) -> None:
    paths, adapter, reference, expected_content = completed_reference_fixture(tmp_path)
    resolver = AGCCaptureEvidenceResolver(paths=paths, adapters=(adapter,))
    resolved = resolver.resolve(reference)
    assert resolved == expected_content
    assert canonical_sha256(resolved) == reference["digest"]
```

Add content-free failures for wrong provider, wrong kind, invalid ref, non-complete/missing receipt, missing/mismatched frozen revision, missing Adapter, source unavailable, changed Capsule hash, corrupt observation manifest, and digest mismatch. These raise fixed `ValueError` codes only; no source path, locator, task ID, Session text, or exception text may appear.

- [ ] **Step 2: Write failing case-builder tests**

Create a fake Trace reader with two cycle traces containing three item events, including a duplicate EvidenceRef. Assert newest-first stable sampling, duplicate removal, and exact Case shape:

```python
assert cases[0] == {
    "schema_version": "eval.case.v0.1",
    "case_id": expected_case_id,
    "subject": {
        "principal_ref": {"id": "agent-global-context.capture", "kind": "runtime"},
        "capability": "capture",
        "operation": "observation-quality",
        "implementation_version": "0.4.4",
    },
    "profile_ref": {"id": "agc.capture-quality", "version": "1"},
    "evidence_refs": [item_reference],
    "trace_snapshot": newest_snapshot,
    "reference": None,
    "metadata": {"sample_reason": "latest-completed-capture-item"},
}
```

Reject malformed event payloads rather than guessing. Ignore unrelated Trace events and return at most `max_items` in the inclusive range 1–100.

- [ ] **Step 3: Run adapter tests and verify RED**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest -q -p no:cacheprovider `
  tests\test_capture_eval_adapter.py `
  --basetemp 'D:\tmp_test\agc-capture-eval\adapter-red'
```

- [ ] **Step 4: Implement the EvidenceResolver**

At construction, map each Adapter by `(adapter_id, source_root_id)` and build the same CapsulePolicy currently used by Capture from `load_runtime_config(paths).capture.capsule`.

For `resolve`:

1. Require an exact Eval EvidenceRef v0.1 mapping with provider `agc`, kind `capture-item`, version `1`, and `ref` matching `^cr_[0-9a-f]{64}$`.
2. Call `CaptureStore(paths).read_snapshot()` once, require `integrity_state == "healthy"`, find exactly one receipt matching `ref`, and require `status == "complete"`.
3. Find exactly one RevisionRef in `snapshot.census` whose key equals `receipt.key`, and collect the observations in `snapshot.observations` bound to that receipt in ordinal order.
4. Find the bound SourceAdapter and call `load_capsule(revision, policy)`.
5. Require rebuilt `capsule_hash` and `capsule_schema_version` to equal the receipt values.
6. Rebuild `capture_eval_evidence_content(...)` with the observations from the same snapshot and require `canonical_sha256(content) == reference["digest"]`.
7. Return the content mapping only in memory.

Map every failure to one of `capture_eval_reference_invalid`, `capture_eval_evidence_unavailable`, or `capture_eval_evidence_changed` without including exception text.

- [ ] **Step 5: Implement deterministic EvalCase construction**

Define a local Protocol for the three public Trace methods. For each Trace summary newest-first, inspect `events(trace_id)`, select only exact `agc.capture.item.completed` principal events attributed to `agent-global-context.capture`, and validate the item payload with the same allowlist as Task 2.

Derive `case_id` as:

```python
case_id = "evc_" + canonical_sha256(
    {
        "subject": subject,
        "profile_ref": profile_ref,
        "evidence_ref": evidence_ref,
    }
).removeprefix("sha256:")
```

Attach only `trace_reader.snapshot(trace_id)`, not Trace database paths or internal rows. Deduplicate by Case ID before applying `max_items`.

- [ ] **Step 6: Verify GREEN and commit**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest -q -p no:cacheprovider `
  tests\test_capture_eval_adapter.py `
  --basetemp 'D:\tmp_test\agc-capture-eval\adapter-green'

git add -- agc_runtime/capture_eval_adapter.py tests/test_capture_eval_adapter.py
git commit -m "feat(eval): adapt AGC capture evidence"
```

### Task 4: Add the AGC quality profile and explicitly authorized manual CLI

**Files:**
- Create: `agc_runtime/eval_profiles/agc-capture-quality.v1.json`
- Create: `agc_runtime/codex_command.py`
- Create: `agc_runtime/eval_cli.py`
- Create: `tests/test_eval_cli.py`
- Modify: `agc_runtime/capture_cli.py`
- Modify: `tests/test_capture_cli.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Produces: `agc-eval prepare-capture --root ROOT --trace-db DB --max-items N`.
- Produces: `agc-eval capture --root ROOT --trace-db DB --eval-db DB --max-items N --authorization-digest SHA256`.
- Uses: configured Capture executable/model, `AGCCaptureEvidenceResolver`, `EvalService`, `EvalStore`, and `CodexJsonJudge`.

- [ ] **Step 1: Create the exact AGC Capture-quality profile**

Create `agc_runtime/eval_profiles/agc-capture-quality.v1.json`:

```json
{
  "schema_version": "eval.profile.v0.1",
  "profile_id": "agc.capture-quality",
  "profile_version": "1",
  "judge_mode": "llm",
  "dimensions": [
    {
      "id": "faithfulness",
      "description": "The collected observation or zero decision is supported by the safe source Capsule.",
      "rubric": "Score 4 when every retained claim is directly supported, or when a zero decision correctly rejects a Capsule with no durable signal. Score 0 when a retained claim is contradicted or a clear durable signal is incorrectly discarded.",
      "weight": 0.35,
      "minimum_score": 3
    },
    {
      "id": "durability",
      "description": "The result captures stable user context rather than a one-off instruction or transient task state.",
      "rubric": "Score 4 for a stable preference, principle, capability, interest, or long-term goal. Score 0 for a one-time command, temporary status, routine implementation step, or unsupported projection.",
      "weight": 0.25,
      "minimum_score": 3
    },
    {
      "id": "noise_control",
      "description": "The decision avoids irrelevant, redundant, or low-value observations without dropping durable signal.",
      "rubric": "Score 4 when retained observations are useful and nonredundant, or when a zero result removes only noise. Score 0 for noise retention, repeated paraphrases, or a false zero that loses durable context.",
      "weight": 0.20,
      "minimum_score": 3
    },
    {
      "id": "atomicity",
      "description": "Each observation expresses one reusable proposition at an appropriate level of detail.",
      "rubric": "Score 4 for one self-contained proposition per observation. Score 0 for compound, vague, fragmentary, or excessively compressed statements.",
      "weight": 0.10,
      "minimum_score": 2
    },
    {
      "id": "classification",
      "description": "Category, kind, scope, confidence, sensitivity, and signal type agree with the evidence.",
      "rubric": "Score 4 when all labels are supported and useful. Score 0 when labels materially misrepresent the evidence or scope.",
      "weight": 0.10,
      "minimum_score": 2
    }
  ],
  "pass_threshold": 0.75,
  "evidence_requirements": [
    {"provider": "agc", "kind": "capture-item", "min_count": 1}
  ],
  "max_attempts": 2
}
```

- [ ] **Step 2: Extract the existing shared Codex command resolver**

Move the current exact-selector behavior from `capture_cli._extractor_command` into:

```python
def resolve_codex_command(value: str) -> tuple[str, ...]:
    if value == "codex-app":
        from agc_runtime.codex_app_runtime import resolve_codex_app_command

        return resolve_codex_app_command()
    try:
        command = tuple(shlex.split(value, posix=True))
    except ValueError as error:
        raise ValueError("codex_command_invalid") from error
    if not 1 <= len(command) <= 4:
        raise ValueError("codex_command_invalid")
    return command
```

Keep `_extractor_command` as a backward-compatible one-line delegate until all existing tests pass. Add:

```python
def test_capture_and_eval_share_exact_codex_app_resolution(monkeypatch) -> None:
    expected = (r"C:\OpenAI\Codex\bin\version\codex.exe",)
    monkeypatch.setattr(
        "agc_runtime.codex_app_runtime.resolve_codex_app_command",
        lambda: expected,
    )
    assert resolve_codex_command("codex-app") == expected
    assert _extractor_command("codex-app") == expected


def test_codex_app_resolution_failure_has_no_literal_fallback(monkeypatch) -> None:
    def fail() -> tuple[str, ...]:
        raise RuntimeError("capture_extractor_unavailable")

    monkeypatch.setattr(
        "agc_runtime.codex_app_runtime.resolve_codex_app_command",
        fail,
    )
    with pytest.raises(RuntimeError, match="^capture_extractor_unavailable$"):
        resolve_codex_command("codex-app")
```

- [ ] **Step 3: Write failing CLI authorization tests**

Tests must prove:

- `prepare-capture` performs no EvidenceResolver, Judge, network, or model call and returns exact case count, profile ref, provider, configured model, executable identity, and authorization digest.
- Digest input is canonical ordered `{profile_ref, profile_digest, provider, model, executable_identity, case_digests, evidence_digests, max_items}`; each Case digest covers its complete public EvalCase including TraceSnapshot, and executable identity is SHA-256 of the resolved command tuple, never the executable path itself.
- `capture` with a missing or stale digest stops before evidence resolution and Judge invocation.
- A valid digest evaluates at most `max_items`, stores results, and returns only counts, status counts, result IDs, Profile, Judge identity, and Token totals.
- Repeating the same command reuses EvalStore results.
- Missing optional packages return `eval_runtime_unavailable` without affecting Capture.
- No ToolResponse contains resolved Capsule/Observation text, TraceSnapshot bodies, credentials, paths other than the user-supplied root/database bindings, or Judge error text.
- The command never calls AGC write, review, merge, formalization, forget, or promotion services.

Use these exact orchestration tests around private pure helpers `_capture_cases`, `_judge_binding`, `_authorization_digest`, and `_evaluate_cases`:

```python
def test_prepare_never_resolves_evidence_or_imports_judge(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root, trace_db, _eval_db = eval_cli_fixture(tmp_path)
    monkeypatch.setattr("agc_runtime.eval_cli._capture_cases", lambda **_values: CASES)
    monkeypatch.setattr(
        "agc_runtime.eval_cli._judge_binding",
        lambda _capture: {
            "provider": "openai",
            "model": "gpt-5.6-sol",
            "executable_identity": "a" * 64,
            "command": (r"C:\trusted\codex.exe",),
        },
    )
    real_import = builtins.__import__

    def guarded_import(name: str, *args: object, **kwargs: object):
        if name in {"agent_eval_runtime", "agent_eval_codex"}:
            raise AssertionError("prepare must not import Eval or Judge packages")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    assert main(
        [
            "prepare-capture",
            "--root",
            str(root),
            "--trace-db",
            str(trace_db),
            "--max-items",
            "2",
        ]
    ) == 0
    data = json.loads(capsys.readouterr().out)["data"]
    assert data["case_count"] == 2
    assert data["provider"] == "openai"
    assert data["model"] == "gpt-5.6-sol"
    assert data["executable_identity"] == "a" * 64
    assert data["profile_digest"] == canonical_sha256(PROFILE)
    assert data["case_digests"] == [canonical_sha256(item) for item in CASES]
    assert "command" not in data


def test_stale_digest_stops_before_evaluation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root, trace_db, eval_db = eval_cli_fixture(tmp_path)
    monkeypatch.setattr("agc_runtime.eval_cli._capture_cases", lambda **_values: CASES)
    monkeypatch.setattr("agc_runtime.eval_cli._judge_binding", fixed_judge_binding)

    def forbidden(**_values: object):
        raise AssertionError("stale authorization must stop before evidence or Judge")

    monkeypatch.setattr("agc_runtime.eval_cli._evaluate_cases", forbidden)
    assert main(
        [
            "capture",
            "--root",
            str(root),
            "--trace-db",
            str(trace_db),
            "--eval-db",
            str(eval_db),
            "--max-items",
            "2",
            "--authorization-digest",
            "0" * 64,
        ]
    ) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"]["code"] == "capture_eval_authorization_stale"


def test_authorized_run_returns_only_result_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root, trace_db, eval_db = eval_cli_fixture(tmp_path)
    monkeypatch.setattr("agc_runtime.eval_cli._capture_cases", lambda **_values: CASES)
    monkeypatch.setattr("agc_runtime.eval_cli._judge_binding", fixed_judge_binding)
    digest = _authorization_digest(CASES, PROFILE, fixed_judge_binding(None), 2)
    monkeypatch.setattr(
        "agc_runtime.eval_cli._evaluate_cases",
        lambda **_values: (PASS_RESULT, INSUFFICIENT_RESULT),
    )
    assert main(
        [
            "capture",
            "--root",
            str(root),
            "--trace-db",
            str(trace_db),
            "--eval-db",
            str(eval_db),
            "--max-items",
            "2",
            "--authorization-digest",
            digest,
        ]
    ) == 0
    data = json.loads(capsys.readouterr().out)["data"]
    assert data["status_counts"] == {"insufficient_evidence": 1, "pass": 1}
    assert data["result_ids"] == [PASS_RESULT["result_id"], INSUFFICIENT_RESULT["result_id"]]
    assert "trace_snapshot" not in json.dumps(data)
    assert "capsule" not in json.dumps(data)
```

Define `CASES`, `PROFILE`, `PROFILE_REF`, `PASS_RESULT`, `INSUFFICIENT_RESULT`, `fixed_judge_binding`, and `eval_cli_fixture` as fixed content-safe fixtures in the same test module; their mappings must validate against the Eval v0.1 contracts rather than using `SimpleNamespace` shortcuts.

- [ ] **Step 4: Run CLI tests and verify RED**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest -q -p no:cacheprovider `
  tests\test_eval_cli.py tests\test_capture_cli.py `
  --basetemp 'D:\tmp_test\agc-capture-eval\cli-red'
```

- [ ] **Step 5: Implement strict parsing and preparation**

Accept only these forms and ranges:

```text
agc-eval prepare-capture --root ROOT --trace-db DB --max-items 1..100
agc-eval capture --root ROOT --trace-db DB --eval-db DB --max-items 1..100 --authorization-digest 64-lowercase-hex
```

Preparation must lazily import only Trace public APIs, require the exact `codex-app` selector, load the packaged Profile, build cases, resolve the trusted bundled Codex App command without executing it, derive its content-free identity, and compute the digest without resolving EvidenceRefs or importing the Codex Judge. The provider boundary for this Codex App Pilot is exactly `openai`. Return Profile, Case, and evidence digests but not opaque refs, executable paths, Case bodies, or TraceSnapshots.

- [ ] **Step 6: Implement authorized evaluation**

On `capture`:

1. Rebuild the exact selected cases and digest; reject mismatch with `capture_eval_authorization_stale`.
2. Lazily import Eval Runtime and Codex Eval Adapter.
3. Build SourceAdapters and `AGCCaptureEvidenceResolver` from the configured Capture sources.
4. Require `capture.extractor.executable == "codex-app"`, resolve it with `resolve_codex_command`, require a non-null configured model, recompute the executable identity, and require provider `openai`; any other selector is `capture_eval_runtime_unsupported`.
5. Construct `CodexJsonJudge(executable=command, model=model, provider="openai")`, `EvalService`, and `EvalStore(Path(eval_db))`.
6. Evaluate cases sequentially; the EvalStore handles idempotent reuse.
7. Sum only structured usage returned in EvalResult.
8. Emit a content-free `agc.eval` ToolResponse.

Catch optional-import, Trace-store, Eval-store, evidence, Judge, and contract failures into fixed codes. Never catch `KeyboardInterrupt` or alter AGC Capture state.

- [ ] **Step 7: Declare optional packaging without changing base installs**

Within the existing `[project.optional-dependencies]` table, add:

```toml
eval = [
  "agent-eval-runtime>=0.1,<0.2",
  "agent-eval-codex>=0.1,<0.2",
]
```

Within the existing `[project.scripts]` table, add:

```toml
agc-eval = "agc_runtime.eval_cli:main"
```

Replace the existing package-data block with:

```toml
[tool.setuptools.package-data]
agc_runtime = ["default_config.yaml", "UNICODE-LICENSE.txt", "eval_profiles/*.json"]
"*" = ["schemas/capture-extractor-v1.schema.json"]
```

Preserve the existing `mcp`, `trace`, and `test` extras exactly.

- [ ] **Step 8: Verify GREEN and commit**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest -q -p no:cacheprovider `
  tests\test_eval_cli.py tests\test_capture_cli.py tests\test_capture_trace.py `
  --basetemp 'D:\tmp_test\agc-capture-eval\cli-green'

git add -- agc_runtime/eval_profiles agc_runtime/codex_command.py `
  agc_runtime/eval_cli.py agc_runtime/capture_cli.py `
  tests/test_eval_cli.py tests/test_capture_cli.py pyproject.toml
git commit -m "feat(eval): run authorized capture quality pilot"
```

### Task 5: Verify the cross-runtime Pilot, document it, and prepare a release candidate

**Files:**
- Create: `tests/test_capture_eval_end_to_end.py`
- Modify: `README.md`
- Modify: `README.en.md`
- Modify: `README.zh.md`
- Modify: `docs/capture-operations.md`
- Modify: `docs/superpowers/specs/2026-08-29-agc-capture-trace-bridge-design.md`
- Modify: `pyproject.toml`
- Modify: `agc_runtime/__init__.py`
- Modify: `tests/test_cli_contract.py`
- Modify: `tests/test_mcp_server.py`
- Modify: `tests/test_local_install.py`

**Interfaces:**
- Produces: AGC 0.4.4 source release candidate with optional manual Eval profile.
- Does not produce: a production install, automatic Eval schedule, formal-memory mutation, live content transmission, GitHub push, or release tag.

- [ ] **Step 1: Add a synthetic cross-runtime end-to-end test**

Under one `tmp_path`, create a synthetic safe Capture source, complete exactly one receipt, write one production-shaped Trace database with cycle plus item event, prepare the Eval digest, and run the authorized CLI against a fake Codex Judge executable. Assert:

1. one EvalResult exists and validates against EvalResult v0.1;
2. one repeat call returns the same result ID without a second Judge call;
3. the Trace database contains EvidenceRef and aggregates but no sentinel content;
4. the Eval database contains Result, scores, codes, and opaque refs but no resolved evidence or sentinel content;
5. Capture receipt, observation, budget, review state, and formal-memory count are byte-for-byte unchanged by both Eval calls;
6. disabling/uninstalling Eval packages leaves normal Capture tests green;
7. Trace or Eval store failure does not change a subsequent Capture result.

- [ ] **Step 2: Update documentation and the earlier bridge boundary**

Document:

- cycle-level versus item-level Trace coverage;
- the exact item payload allowlist;
- why the first Profile evaluates CollectedObservations and zero decisions rather than formal-memory merges;
- EvidenceRef resolution and digest mismatch behavior;
- preparation/authorization/run commands;
- configured Codex App model/provider boundary;
- no automatic Eval schedule and no automatic memory mutation;
- Result interpretation and `insufficient_evidence`/`evaluation_error` semantics.

Amend the 2026-08-29 bridge design only with a dated extension note pointing to the approved cross-runtime specification; do not rewrite the original 0.4.3 decision history.

- [ ] **Step 3: Bump the source version to 0.4.4**

Update package metadata, `agc_runtime.__version__`, and exact CLI/MCP/installer assertions from `0.4.3` to `0.4.4`. The version bump describes source capability only and does not authorize installation.

- [ ] **Step 4: Run focused and full verification**

Install the locally built `agent-runtime-contracts`, Trace Runtime, Eval Runtime, Codex Eval Adapter, and AGC editable source into an isolated environment below `D:\tmp_test\agc-capture-eval\venv`; do not mutate the production AGC install.

```powershell
& '.\.venv\Scripts\python.exe' -m pytest -q -p no:cacheprovider `
  tests\test_capture_eval_evidence.py tests\test_capture_trace.py `
  tests\test_capture_eval_adapter.py tests\test_eval_cli.py `
  tests\test_capture_eval_end_to_end.py `
  --basetemp 'D:\tmp_test\agc-capture-eval\focused'

& '.\.venv\Scripts\python.exe' -m pytest -q -p no:cacheprovider `
  --basetemp 'D:\tmp_test\agc-capture-eval\full'

& '.\.venv\Scripts\python.exe' -m build `
  --outdir 'D:\tmp_test\agc-capture-eval\dist'

git diff --check
```

Expected: focused and full suites pass; wheel contains the Profile once; base install still works without Eval; source version is 0.4.4; no test artifact appears outside `D:\tmp_test`.

- [ ] **Step 5: Prepare—but do not execute—the live production sample**

Using the installed production Trace database read-only, run only `agc-eval prepare-capture` for at most five latest unique item events. Record the returned Profile, provider, model, executable identity, case count, evidence digests, and authorization digest in a content-free Pilot receipt below `D:\tmp_test\agc-capture-eval\live-preview`.

Stop before `agc-eval capture`. Present the exact digest, maximum item count, provider, model, executable identity, and evidence boundary to the user. Continue only after explicit authorization to send those safe AGC evidence bundles to the configured model.

- [ ] **Step 6: Commit the verified release candidate**

```powershell
git add -- README.md README.en.md README.zh.md docs/capture-operations.md `
  docs/superpowers/specs/2026-08-29-agc-capture-trace-bridge-design.md `
  pyproject.toml agc_runtime/__init__.py tests/test_cli_contract.py `
  tests/test_mcp_server.py tests/test_local_install.py `
  tests/test_capture_eval_end_to_end.py
git commit -m "docs(eval): verify AGC capture pilot"
```

Stop with production installation, live Judge calls, automatic scheduling, GitHub push, package publication, and release tag still pending explicit authorization.

## Self-Review

- Spec coverage: item-level Trace, two-layer evidence, AGC-owned Profile, mixed TraceSnapshot/evidence input, failure-open Capture, immutable EvalResult, manual authorization, and no auto-mutation each map to a concrete task and test.
- Placeholder scan: every code-changing step identifies exact files, interfaces, commands, expected outcomes, and concrete contract values; no deferred subsystem is disguised as an implementation step.
- Type consistency: `CaptureItemTraceReport`, EvidenceRef mapping, `AGCCaptureEvidenceResolver.resolve`, EvalCase fields, Profile identity, and Eval Runtime protocols match the preceding Eval Runtime v0.1 plan.
- Scope: Recall Eval, formalization merge Eval, automatic scheduling, Dataset management, regression dashboards, and automatic strategy changes remain outside this Pilot.
