# AGC Quality-First Memory Formalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Codex App-driven, user-confirmed workflow that consolidates bounded Capture observations into useful formal Memory Items and records only content-free terminal review receipts.

**Architecture:** Keep semantic grouping and deduplication in the active Codex App `gpt-5.6-sol` turn. Add a small deterministic Capture review domain to Runtime, extend the existing `agc.read` and `agc.write` actions, and package the review workflow in the repository's single public `agent-global-context` skill. Formal writes remain authoritative; review-receipt publication is idempotent and warning-bearing when it cannot follow an accepted memory write.

**Tech Stack:** Python 3.13, pytest 9.1.1, Markdown/YAML Memory Items, JSON Capture runtime objects, MCP 2.0.0, PowerShell local installer, Codex App runtime.

## Global Constraints

- Keep exactly three public tools: `agc.read`, `agc.write`, and `agc.admin`.
- Keep exactly one packaged public skill: `skills/agent-global-context/SKILL.md`.
- Do not change `CollectedObservation` or reopen raw Codex Session files.
- Do not add a proposal database, embeddings, vector search, background promotion, or automatic formal-memory writes.
- Review outcomes are exactly `draft`, `needs_context`, and `discard`.
- Preview and deferred confirmation write no Memory Item and no review receipt.
- `draft` becomes terminal only after an accepted formal-memory write.
- Each request contains 1–20 unique canonical `co_<sha256>` observation IDs.
- Review receipts contain only schema version, observation ID, outcome, target memory ID, and UTC review timestamp.
- Draft quality gate is exactly: **Grounded**, **Self-contained**, **Decision-relevant**, **Deduplicated**, **Bounded**, and **Policy-valid**.
- Formalization rejects sensitive/secret proposals and unresolved phrases such as `该 skill`, `该技能`, `这个方案`, `上述方案`, and `上面的设置`.
- Use active Codex App `gpt-5.6-sol`; do not launch Codex CLI or an extractor subprocess for formalization.
- Put every test temporary directory and build artifact under `D:\tmp_test`; use short children such as `D:\tmp_test\q` to avoid Windows path-length failures.
- Preserve LF when running byte-sensitive tests because this host has system `core.autocrlf=true`.
- Release the implemented feature as Runtime `0.4.0` after all verification passes.

---

## File Structure

- Create `agc_runtime/capture_review.py`: strict receipt model, ID/outcome parsing, formalization body checks, and reusable constants.
- Modify `agc_runtime/paths.py`: add the managed `.runtime/capture/reviews` directory.
- Modify `agc_runtime/capture_store.py`: read, validate, and idempotently publish review receipts under the Capture writer lock.
- Modify `agc_runtime/capture_read_service.py`: default unreviewed search, explicit audit search, and exact review metadata.
- Modify `agc_runtime/write_service.py`: add `capture_review`, validate contributing observation IDs before mutation, and attach `draft` receipts after accepted formal writes.
- Modify `agc_runtime/managed_backup.py`: allow, capability-bind, and validate review receipts in managed backups.
- Modify `agc_runtime/admin_service.py`: validate review receipts in a live Memory Root.
- Modify `agc_runtime/capture_forget_service.py`: remove matching review receipts from primary state and every managed backup.
- Create `skills/agent-global-context/references/formalization-workflow.md`: Codex App semantic review and confirmation workflow.
- Modify `skills/agent-global-context/SKILL.md`: route Capture formalization requests to the workflow reference.
- Modify `skills/agent-global-context/references/tool-contract.md`: document the new fields and action without adding a tool.
- Modify `docs/capture-operations.md`, `README.md`, and `README.zh.md`: operator workflow and Runtime `0.4.0`.
- Create `tests/test_capture_review.py`: strict contract and persistence tests.
- Modify `tests/conftest.py`: reusable factory for 1–8 committed visible Capture observations.
- Modify `tests/test_capture_read_service.py`, `tests/test_write_service.py`, `tests/test_capture_backup_restore.py`, `tests/test_capture_forget.py`, `tests/test_admin_service.py`, and `tests/test_skill_adapter.py`: cross-boundary regression coverage.
- Modify `tests/test_cli_contract.py`, `tests/test_local_install.py`, `tests/test_mcp_server.py`, `pyproject.toml`, and `agc_runtime/__init__.py`: Runtime `0.4.0` release contract.

---

### Task 1: Strict Review Receipt Domain and Managed Store

**Files:**
- Create: `agc_runtime/capture_review.py`
- Modify: `agc_runtime/paths.py`
- Modify: `agc_runtime/capture_store.py`
- Create: `tests/test_capture_review.py`
- Modify: `tests/conftest.py`

**Interfaces:**
- Produces: `CaptureReviewReceipt.from_mapping(value) -> CaptureReviewReceipt`
- Produces: `parse_capture_observation_ids(value) -> tuple[str, ...]`
- Produces: `validate_formalization_item(item: MemoryItem) -> None`
- Produces: `CaptureStore.validate_review_batch(observation_ids, *, outcome, target_memory_id) -> None`
- Produces: `CaptureStore.record_reviews(observation_ids, *, outcome, target_memory_id, reviewed_at=None) -> int`
- Produces: `CaptureSnapshot.review_receipts: tuple[CaptureReviewReceipt, ...]`

- [ ] **Step 1: Write failing receipt contract and path tests**

Add this reusable real-Capture factory to `tests/conftest.py` so every later test uses committed observations rather than hand-written orphan files:

```python
@pytest.fixture
def visible_capture_observations():
    def create(paths: MemoryPaths, statements: list[str]):
        if not 1 <= len(statements) <= 8:
            raise ValueError("test factory supports one Capture extraction batch")
        now = "2026-08-23T12:00:00Z"
        key = CaptureKey("synthetic_adapter", "1" * 64, "review-task", "review-revision")
        base = {
            "schema_version": 1, "receipt_id": receipt_id_for(key), **key.to_mapping(),
            "adapter_version": "1", "source_schema_version": "1", "identity_quality": "session_id",
            "source_fingerprint": "a" * 64, "source_hash_schema_version": "source-v1",
            "capsule_hash": "b" * 64, "capsule_schema_version": "capsule-v1",
            "settled_at": now, "discovered_at": now, "updated_at": now, "status": "extracting",
            "attempt_count": 1, "next_retry_at": None, "extractor_id": "synthetic_extractor",
            "extractor_version": "1", "extractor_schema_version": "1", "taxonomy_version": "taxonomy-v1",
            "observation_count": None, "filtered_counts": None, "duplicate_suppression_count": None,
            "token_usage": TokenUsage(1, 1, 2).to_mapping(), "usage_quality": "actual",
            "redacted_by_forget": False, "forgotten_observation_count": 0, "zero_reason": None,
            "sanitized_error": None, "coalesced_to": None, "exclusion_reason": None,
        }
        receipt = CaptureReceipt.from_mapping(base)
        observations = []
        for ordinal, statement in enumerate(statements):
            value = {
                "schema_version": 1, "observation_id": "co_" + "0" * 64,
                "receipt_id": receipt.receipt_id,
                "source": {**key.to_mapping(), "locator": "sessions/review.jsonl"},
                "ordinal": ordinal, "observation_fingerprint": "0" * 64,
                "statement": statement,
                "assertion": {"subject": "user", "mode": "direct", "modality": "asserted"},
                "primary_category": "work", "taxonomy_version": "taxonomy-v1",
                "kind": "preference", "scopes": ["testing"], "project_scope": None,
                "confidence": "observed", "sensitivity": "normal",
                "signal_type": "decision_or_constraint", "observed_at": now,
                "captured_at": now, "extractor_version": "1", "processing_state": "collected",
            }
            value["observation_fingerprint"] = observation_fingerprint_for(value)
            value["observation_id"] = observation_id_for(receipt.receipt_id, value["observation_fingerprint"])
            observations.append(CollectedObservation.from_mapping(value))
        terminal = CaptureReceipt.from_mapping({
            **base,
            "status": "complete",
            "observation_count": len(observations),
            "filtered_counts": {"safety": 0, "policy": 0, "over_limit": 0},
            "duplicate_suppression_count": 0,
        })
        store = CaptureStore(paths, clock=lambda: now)
        store.register_extraction(receipt)
        lease = store.acquire_lease(key, owner_id="review-worker", now=now, ttl_seconds=60)
        assert lease is not None
        store.commit_extraction(lease, tuple(observations), terminal)
        return store, tuple(observations)
    return create
```

Import `CaptureKey`, `CaptureReceipt`, `CollectedObservation`, `TokenUsage`, `observation_fingerprint_for`, `observation_id_for`, `receipt_id_for`, `CaptureStore`, and `MemoryPaths` at the top of `tests/conftest.py`.

Then add tests that assert strict parsing, canonical filename binding, 1–20 unique IDs, outcome/target coupling, and no content fields:

```python
def test_review_receipt_is_strict_content_free_and_target_bound():
    value = {
        "schema_version": 1,
        "observation_id": "co_" + "a" * 64,
        "outcome": "draft",
        "target_memory_id": "publish-with-human-confirmation",
        "reviewed_at": "2026-08-23T12:00:00Z",
    }
    receipt = CaptureReviewReceipt.from_mapping(value)
    assert receipt.to_mapping() == value
    for extra in ("statement", "memory_markdown", "reason", "prompt"):
        with pytest.raises(ValueError):
            CaptureReviewReceipt.from_mapping({**value, extra: "forbidden"})


def test_review_id_batch_is_canonical_unique_and_bounded():
    ids = [f"co_{index:064x}" for index in range(20)]
    assert parse_capture_observation_ids(ids) == tuple(ids)
    for invalid in ([], ids + ["co_" + "f" * 64], ids[:1] * 2, ["not-an-id"]):
        with pytest.raises(ValueError):
            parse_capture_observation_ids(invalid)
```

- [ ] **Step 2: Run the new tests and verify RED**

Run:

```powershell
$env:TEMP='D:\tmp_test\q'; $env:TMP='D:\tmp_test\q'
& 'D:\tmp\github\agent-global-context\.venv\Scripts\python.exe' -m pytest tests/test_capture_review.py -q --basetemp D:\tmp_test\q\t -o cache_dir=D:\tmp_test\q\c
```

Expected: collection fails because `agc_runtime.capture_review` and `CapturePaths.reviews` do not exist.

- [ ] **Step 3: Implement the strict receipt model and deterministic content checks**

Create `agc_runtime/capture_review.py` with these concrete contracts:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
from typing import Any

from agc_runtime.models import MemoryItem

MAX_REVIEW_OBSERVATIONS = 20
REVIEW_OUTCOMES = frozenset({"draft", "needs_context", "discard"})
_OBSERVATION_ID = re.compile(r"^co_[0-9a-f]{64}$")
_MEMORY_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,79}$")
_DANGLING_REFERENCES = (
    "该 skill", "该技能", "这个方案", "上述方案", "上面的设置", "最终目标保持不变"
)


def _utc(value: Any) -> str:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("reviewed_at must be an RFC 3339 UTC timestamp")
    parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise ValueError("reviewed_at must be an RFC 3339 UTC timestamp")
    return value


def parse_capture_observation_ids(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list) or not 1 <= len(value) <= MAX_REVIEW_OBSERVATIONS:
        raise ValueError("capture_observation_ids must contain between 1 and 20 items")
    if any(not isinstance(item, str) or not _OBSERVATION_ID.fullmatch(item) for item in value):
        raise ValueError("capture_observation_ids must contain canonical observation ids")
    if len(value) != len(set(value)):
        raise ValueError("capture_observation_ids must not contain duplicates")
    return tuple(value)


@dataclass(frozen=True)
class CaptureReviewReceipt:
    schema_version: int
    observation_id: str
    outcome: str
    target_memory_id: str | None
    reviewed_at: str

    @classmethod
    def from_mapping(cls, value: Any) -> "CaptureReviewReceipt":
        fields = {"schema_version", "observation_id", "outcome", "target_memory_id", "reviewed_at"}
        if not isinstance(value, dict) or set(value) != fields:
            raise ValueError("CaptureReviewReceipt must contain the exact fields")
        if type(value["schema_version"]) is not int or value["schema_version"] != 1:
            raise ValueError("CaptureReviewReceipt.schema_version must be 1")
        observation_id = parse_capture_observation_ids([value["observation_id"]])[0]
        outcome = value["outcome"]
        if outcome not in REVIEW_OUTCOMES:
            raise ValueError("CaptureReviewReceipt.outcome is unsupported")
        target = value["target_memory_id"]
        if outcome == "draft":
            if not isinstance(target, str) or not _MEMORY_ID.fullmatch(target):
                raise ValueError("draft review receipt requires target_memory_id")
        elif target is not None:
            raise ValueError("non-draft review receipt forbids target_memory_id")
        return cls(1, observation_id, outcome, target, _utc(value["reviewed_at"]))

    def to_mapping(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "observation_id": self.observation_id,
            "outcome": self.outcome,
            "target_memory_id": self.target_memory_id,
            "reviewed_at": self.reviewed_at,
        }


def validate_formalization_item(item: MemoryItem) -> None:
    body = "\n".join((item.memory_card, item.full_meaning, item.application_boundary, item.rationale))
    found = next((phrase for phrase in _DANGLING_REFERENCES if phrase.casefold() in body.casefold()), None)
    if found is not None:
        raise ValueError(f"formalization memory contains dangling reference: {found}")
```

- [ ] **Step 4: Add `reviews` to managed paths and store operations**

Add `reviews: Path` to `CapturePaths`, return `root / "reviews"`, and include it in `directories()`.

Extend `CaptureSnapshot` with `review_receipts`. In `read_snapshot`, decode every `reviews/*.json`, require filename/ID equality, report fixed `invalid_review_receipt` diagnostics, and retain valid receipts only when their observation is visible.

Add store methods with these semantics:

```python
def _validate_review_batch_locked(
    self,
    observation_ids: Sequence[str],
    *,
    outcome: str,
    target_memory_id: str | None,
) -> tuple[str, ...]:
    ids = tuple(observation_ids)
    candidate = CaptureReviewReceipt.from_mapping({
        "schema_version": 1,
        "observation_id": ids[0],
        "outcome": outcome,
        "target_memory_id": target_memory_id,
        "reviewed_at": self._clock(),
    })
    for observation_id in ids:
        observation = CollectedObservation.from_mapping(read_json(self._observation_path(observation_id)))
        receipt = self._read_receipt(observation.receipt_id)
        if receipt.status != "complete" or observation_id not in self._read_manifest(receipt.receipt_id):
            raise ValueError("review observation is not visible")
        path = self.capture.reviews / f"{observation_id}.json"
        if path.exists():
            current = CaptureReviewReceipt.from_mapping(read_json(path))
            if (current.outcome, current.target_memory_id) != (candidate.outcome, candidate.target_memory_id):
                raise ValueError("review receipt conflicts with terminal outcome")
    return ids


def validate_review_batch(
    self,
    observation_ids: Sequence[str],
    *,
    outcome: str,
    target_memory_id: str | None,
) -> None:
    ids = parse_capture_observation_ids(list(observation_ids))
    with capture_write_lock(self.paths):
        self._ensure_layout_locked()
        self._validate_review_batch_locked(
            ids,
            outcome=outcome,
            target_memory_id=target_memory_id,
        )


def record_reviews(
    self,
    observation_ids: Sequence[str],
    *,
    outcome: str,
    target_memory_id: str | None,
    reviewed_at: str | None = None,
) -> int:
    ids = parse_capture_observation_ids(list(observation_ids))
    timestamp = reviewed_at or self._clock()
    created = 0
    with capture_write_lock(self.paths):
        self._ensure_layout_locked()
        self._validate_review_batch_locked(
            ids,
            outcome=outcome,
            target_memory_id=target_memory_id,
        )
        for observation_id in ids:
            path = self.capture.reviews / f"{observation_id}.json"
            receipt = CaptureReviewReceipt.from_mapping({
                "schema_version": 1,
                "observation_id": observation_id,
                "outcome": outcome,
                "target_memory_id": target_memory_id,
                "reviewed_at": timestamp,
            })
            if not path.exists():
                atomic_write_json(path, receipt.to_mapping())
                created += 1
    return created
```

- [ ] **Step 5: Run focused tests and verify GREEN**

Run the Task 1 command again.

Expected: all `tests/test_capture_review.py` tests pass.

- [ ] **Step 6: Commit Task 1**

```powershell
git add agc_runtime/capture_review.py agc_runtime/paths.py agc_runtime/capture_store.py tests/conftest.py tests/test_capture_review.py
git commit -m "feat: add capture review receipts"
```

---

### Task 2: Unreviewed-by-Default Capture Reads

**Files:**
- Modify: `agc_runtime/capture_read_service.py`
- Modify: `tests/test_capture_read_service.py`

**Interfaces:**
- Consumes: `CaptureSnapshot.review_receipts`
- Produces: `capture_search(..., include_reviewed=False)` behavior
- Produces: exact `capture_get` result field `review: mapping | None`

- [ ] **Step 1: Write failing read and cursor tests**

```python
def test_capture_search_hides_terminal_reviews_by_default_and_audits_explicitly(tmp_path, visible_capture_observations):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    store, (first, second) = visible_capture_observations(paths, ["First review fact.", "Second review fact."])
    store.record_reviews((first.observation_id,), outcome="discard", target_memory_id=None)

    assert [item["observation_id"] for item in capture_search(paths, {"limit": 20})["results"]] == [second.observation_id]
    audited = capture_search(paths, {"limit": 20, "include_reviewed": True})
    assert {item["observation_id"] for item in audited["results"]} == {first.observation_id, second.observation_id}
    assert capture_get(paths, {"observation_id": first.observation_id})["review"]["outcome"] == "discard"


def test_capture_search_cursor_binds_include_reviewed(tmp_path, visible_capture_observations):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    visible_capture_observations(paths, ["First review fact.", "Second review fact."])
    cursor = capture_search(paths, {"limit": 1})["next_cursor"]
    with pytest.raises(ValueError, match="invalid capture cursor"):
        capture_search(paths, {"limit": 1, "cursor": cursor, "include_reviewed": True})
    with pytest.raises(ValueError, match="include_reviewed"):
        capture_search(paths, {"include_reviewed": "yes"})
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```powershell
& 'D:\tmp\github\agent-global-context\.venv\Scripts\python.exe' -m pytest tests/test_capture_read_service.py -q --basetemp D:\tmp_test\q\t -o cache_dir=D:\tmp_test\q\c
```

Expected: reviewed observations are still returned and the cursor does not bind the new flag.

- [ ] **Step 3: Implement filtering and audit metadata**

Validate `include_reviewed` as an exact boolean. Add it to the cursor query digest:

```python
def _query_digest(filters: dict[str, Any], limit: int, include_reviewed: bool) -> str:
    payload = json.dumps(
        {"filters": filters, "include_reviewed": include_reviewed, "limit": limit},
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
```

Index receipts by observation ID, exclude reviewed IDs unless the flag is true, and expose only the receipt's five content-free fields. `capture_get` must return the exact observation even when reviewed and add `"review": receipt.to_mapping() if receipt else None`.

- [ ] **Step 4: Run read tests and verify GREEN**

Run the Task 2 command again.

Expected: all Capture read tests pass.

- [ ] **Step 5: Commit Task 2**

```powershell
git add agc_runtime/capture_read_service.py tests/test_capture_read_service.py
git commit -m "feat: hide reviewed capture observations by default"
```

---

### Task 3: Terminal `needs_context` and `discard` Write Action

**Files:**
- Modify: `agc_runtime/write_service.py`
- Modify: `tests/test_write_service.py`

**Interfaces:**
- Consumes: `parse_capture_observation_ids`
- Consumes: `CaptureStore.record_reviews`
- Produces: `agc.write capture_review`

- [ ] **Step 1: Write failing strict action tests**

```python
@pytest.mark.parametrize("outcome", ["needs_context", "discard"])
def test_capture_review_records_only_terminal_non_draft_outcomes(tmp_path, outcome, visible_capture_observations):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    _store, (item,) = visible_capture_observations(paths, ["Reviewable preference."])
    observation_id = item.observation_id
    response = dispatch_write(paths, {
        "action": "capture_review",
        "observation_ids": [observation_id],
        "outcome": outcome,
    })
    assert response.status == "accepted"
    assert response.data == {
        "code": "capture_review_recorded",
        "outcome": outcome,
        "reviewed_count": 1,
    }


@pytest.mark.parametrize("request", [
    {"action": "capture_review", "observation_ids": ["co_" + "a" * 64], "outcome": "draft"},
    {"action": "capture_review", "observation_ids": ["co_" + "a" * 64], "outcome": "discard", "reason": "free text"},
])
def test_capture_review_rejects_draft_and_unknown_fields_before_write(tmp_path, request):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    response = dispatch_write(paths, request)
    assert response.status == "failed"
    assert response.error["code"] == "invalid_request"
    assert not paths.capture.reviews.exists()
```

- [ ] **Step 2: Run the write tests and verify RED**

Run:

```powershell
& 'D:\tmp\github\agent-global-context\.venv\Scripts\python.exe' -m pytest tests/test_write_service.py -q --basetemp D:\tmp_test\q\t -o cache_dir=D:\tmp_test\q\c
```

Expected: `capture_review` returns `invalid_action`.

- [ ] **Step 3: Implement the exact handler**

```python
def _handle_capture_review(paths: MemoryPaths, request: dict[str, Any]) -> ToolResponse:
    if set(request) != {"action", "observation_ids", "outcome"}:
        raise ValueError("capture_review request must contain exact fields")
    outcome = request["outcome"]
    if outcome not in {"needs_context", "discard"}:
        raise ValueError("capture_review supports only needs_context or discard")
    observation_ids = parse_capture_observation_ids(request["observation_ids"])
    created = CaptureStore(paths).record_reviews(
        observation_ids,
        outcome=outcome,
        target_memory_id=None,
    )
    return _response(
        "capture_review",
        "accepted",
        "capture_review_recorded",
        data={"outcome": outcome, "reviewed_count": created},
    )
```

Register the handler. Exclude `capture_review` from formal catalog refresh alongside `forget` and `capture_forget`.

- [ ] **Step 4: Run write and MCP tests and verify GREEN**

```powershell
& 'D:\tmp\github\agent-global-context\.venv\Scripts\python.exe' -m pytest tests/test_write_service.py tests/test_mcp_server.py -q --basetemp D:\tmp_test\q\t -o cache_dir=D:\tmp_test\q\c
```

Expected: both files pass and MCP still exposes exactly three tools.

- [ ] **Step 5: Commit Task 3**

```powershell
git add agc_runtime/write_service.py tests/test_write_service.py tests/test_mcp_server.py
git commit -m "feat: classify capture review outcomes"
```

---

### Task 4: Attach Confirmed Formal Writes to Capture Evidence

**Files:**
- Modify: `agc_runtime/write_service.py`
- Modify: `tests/test_write_service.py`
- Modify: `tests/test_capture_review.py`

**Interfaces:**
- Consumes: optional `capture_observation_ids` on `confirm`, `update`, and `observe` only when the disposition is `reinforce`
- Consumes: `validate_formalization_item`
- Produces: accepted responses with `capture_reviewed_count`
- Produces: stable warning `capture_review_receipt_failed`

- [ ] **Step 1: Write failing ordering, merge, and content-quality tests**

```python
def test_confirm_merges_two_capture_observations_into_one_draft_target(tmp_path, visible_capture_observations):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    _store, observations = visible_capture_observations(paths, ["Automate publishing.", "Human confirms final publication."])
    observation_ids = tuple(item.observation_id for item in observations)
    request = {
        "action": "confirm",
        "observation": observation(),
        "memory_markdown": principle().to_markdown(),
        "capture_observation_ids": list(observation_ids),
    }
    response = dispatch_write(paths, request)
    assert response.status == "accepted"
    assert response.data["memory_id"] == principle().id
    assert response.data["capture_reviewed_count"] == 2
    reviews = CaptureStore(paths).read_snapshot().review_receipts
    assert {(item.observation_id, item.outcome, item.target_memory_id) for item in reviews} == {
        (observation_ids[0], "draft", principle().id),
        (observation_ids[1], "draft", principle().id),
    }


def test_failed_formal_write_never_records_draft_review(tmp_path, monkeypatch, visible_capture_observations):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    _store, (item,) = visible_capture_observations(paths, ["Reviewable preference."])
    observation_id = item.observation_id
    monkeypatch.setattr(MemoryStore, "create_memory", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("disk unavailable")))
    response = dispatch_write(paths, {
        **direct_request(),
        "action": "confirm",
        "capture_observation_ids": [observation_id],
    })
    assert response.status == "failed"
    assert not list(paths.capture.reviews.glob("*.json"))


def test_receipt_failure_warns_without_unsaving_memory(tmp_path, monkeypatch, visible_capture_observations):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    _store, (item,) = visible_capture_observations(paths, ["Reviewable preference."])
    observation_id = item.observation_id
    monkeypatch.setattr(CaptureStore, "record_reviews", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("receipt unavailable")))
    response = dispatch_write(paths, {
        **direct_request(),
        "action": "confirm",
        "capture_observation_ids": [observation_id],
    })
    assert response.status == "accepted"
    assert response.warnings == ("capture_review_receipt_failed",)
    assert MemoryStore(paths).get_memory(principle().id).id == principle().id


def test_formalization_rejects_dangling_reference_before_memory_write(tmp_path, visible_capture_observations):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    _store, (item,) = visible_capture_observations(paths, ["该 skill 调用当前本地 harness。"])
    observation_id = item.observation_id
    invalid = replace(principle(), full_meaning="该 skill 调用当前本地 harness。")
    response = dispatch_write(paths, {
        **direct_request(),
        "action": "confirm",
        "memory_markdown": invalid.to_markdown(),
        "capture_observation_ids": [observation_id],
    })
    assert response.status == "failed"
    assert not list(paths.memories.rglob("*.md"))
```

- [ ] **Step 2: Run focused tests and verify RED**

Run Task 3's focused write command.

Expected: `capture_observation_ids` is ignored, no draft receipts exist, and dangling-reference content is accepted.

- [ ] **Step 3: Prevalidate formalization before mutation**

Add a helper that returns `()` when the field is absent and otherwise parses and validates the batch. Reject `capture_observation_ids` on actions other than `confirm`, `update`, and `observe` with disposition `reinforce`. In `observe_batch`, apply the same rule independently to each nested item.

For `confirm` and `update`, call `validate_formalization_item(item)` after the ordinary Memory Item validator. Before any formal mutation, call:

```python
CaptureStore(paths).validate_review_batch(
    observation_ids,
    outcome="draft",
    target_memory_id=item.id if action == "confirm" else match_memory_id,
)
```

For `reinforce`, use `match_memory_id` as the target and do not require new Markdown. Keep `capture_observation_ids` out of the nested request passed from `confirm`/`update` to `_handle_observe`; those wrappers prevalidate, execute the existing mutation, and call `_attach_draft_reviews` themselves. Add a regression assertion that `observe` with disposition `new` plus `capture_observation_ids` returns `invalid_request` before creating memory.

- [ ] **Step 4: Publish receipts only after an accepted mutation**

Use one helper for all three dispositions:

```python
def _attach_draft_reviews(
    paths: MemoryPaths,
    response: ToolResponse,
    observation_ids: tuple[str, ...],
) -> ToolResponse:
    memory_id = response.data.get("memory_id")
    if response.status != "accepted" or not observation_ids or not isinstance(memory_id, str):
        return response
    try:
        count = CaptureStore(paths).record_reviews(
            observation_ids,
            outcome="draft",
            target_memory_id=memory_id,
        )
    except (OSError, RuntimeError, ValueError):
        return replace(response, warnings=(*response.warnings, "capture_review_receipt_failed"))
    return replace(response, data={**response.data, "capture_reviewed_count": count})
```

Call it after `_mutation_response` for `new`, `update`, and `reinforce`. Do not call it for rejected, deferred, conflict, candidate, supersede, archive, forget, or preview paths.

- [ ] **Step 5: Run focused tests and verify GREEN**

```powershell
& 'D:\tmp\github\agent-global-context\.venv\Scripts\python.exe' -m pytest tests/test_capture_review.py tests/test_write_service.py tests/test_catalog_and_read.py -q --basetemp D:\tmp_test\q\t -o cache_dir=D:\tmp_test\q\c
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit Task 4**

```powershell
git add agc_runtime/write_service.py tests/test_write_service.py tests/test_capture_review.py
git commit -m "feat: bind confirmed memories to capture reviews"
```

---

### Task 5: Backup, Validation, Restore, and Hard Forget

**Files:**
- Modify: `agc_runtime/managed_backup.py`
- Modify: `agc_runtime/admin_service.py`
- Modify: `agc_runtime/capture_forget_service.py`
- Modify: `tests/test_capture_backup_restore.py`
- Modify: `tests/test_capture_forget.py`
- Modify: `tests/test_admin_service.py`

**Interfaces:**
- Consumes: `.runtime/capture/reviews/<observation-id>.json`
- Produces: backup capability `capture-review-receipts-v1`
- Preserves: exact observation and revision Hard Forget semantics

- [ ] **Step 1: Write failing lifecycle tests**

Add tests that:

```python
def test_capture_review_receipt_round_trips_in_managed_backup(tmp_path):
    paths, store, observation = _populated(tmp_path)
    store.record_reviews((observation.observation_id,), outcome="discard", target_memory_id=None)
    backup = dispatch_admin(paths, {"action": "backup"})
    assert "capture-review-receipts-v1" in backup.data["manifest"]["capabilities"]
    paths.capture.reviews.joinpath(f"{observation.observation_id}.json").unlink()
    assert dispatch_admin(paths, {"action": "restore", "backup_path": backup.data["backup_path"]}).status == "accepted"
    assert paths.capture.reviews.joinpath(f"{observation.observation_id}.json").is_file()


def test_observation_forget_removes_review_receipt_from_primary_and_backups(tmp_path):
    paths, store, _receipt_value, observations = _populated(tmp_path)
    observation = observations[0]
    store.record_reviews((observation.observation_id,), outcome="discard", target_memory_id=None)
    backup = dispatch_admin(paths, {"action": "backup"})
    response = dispatch_write(paths, _request({"type": "observation", "observation_id": observation.observation_id}))
    assert response.status == "accepted"
    assert not paths.capture.reviews.joinpath(f"{observation.observation_id}.json").exists()
    for backup_path in paths.backups.glob("*.zip"):
        with zipfile.ZipFile(backup_path) as archive:
            assert f".runtime/capture/reviews/{observation.observation_id}.json" not in archive.namelist()
```

Also test that `agc.admin validate` reports an invalid filename, unknown outcome, dangling target, and orphan review receipt without exposing statements or paths outside the safe relative namespace.

- [ ] **Step 2: Run lifecycle tests and verify RED**

```powershell
& 'D:\tmp\github\agent-global-context\.venv\Scripts\python.exe' -m pytest tests/test_capture_backup_restore.py tests/test_capture_forget.py tests/test_admin_service.py -q --basetemp D:\tmp_test\q\t -o cache_dir=D:\tmp_test\q\c
```

Expected: backups omit reviews, restore rejects the namespace, and Hard Forget leaves the receipt behind.

- [ ] **Step 3: Extend backup capability and graph validation**

Add `reviews` to `_CAPTURE_ALLOWLIST` and define:

```python
CAPTURE_REVIEW_RECEIPTS_CAPABILITY = "capture-review-receipts-v1"
```

Append that capability when any archive entry starts with `.runtime/capture/reviews/`. In `_validate_capture_entries`, parse each review object with `CaptureReviewReceipt.from_mapping`, require filename binding, require its observation to exist in the archive, and require the capability whenever reviews exist.

- [ ] **Step 4: Extend live validation and Hard Forget**

Add `paths.capture.reviews: CaptureReviewReceipt.from_mapping` to the admin parser map, then cross-check every valid review ID against visible observations.

In `_updated_observation`, remove the exact review path before returning:

```python
result.pop(f".runtime/capture/reviews/{observation_id}.json", None)
```

In `_updated_revision`, remove review paths for every member of `target_observations`. Keep review receipts out of `_RUNTIME_PREFIXES`; they are durable managed objects, not scratch files.

- [ ] **Step 5: Run lifecycle tests and verify GREEN**

Run the Task 5 command again.

Expected: all selected lifecycle tests pass.

- [ ] **Step 6: Commit Task 5**

```powershell
git add agc_runtime/managed_backup.py agc_runtime/admin_service.py agc_runtime/capture_forget_service.py tests/test_capture_backup_restore.py tests/test_capture_forget.py tests/test_admin_service.py
git commit -m "feat: manage capture reviews across lifecycle operations"
```

---

### Task 6: Codex App Quality-First Review Workflow and Tool Documentation

**Files:**
- Create: `skills/agent-global-context/references/formalization-workflow.md`
- Modify: `skills/agent-global-context/SKILL.md`
- Modify: `skills/agent-global-context/references/tool-contract.md`
- Modify: `docs/capture-operations.md`
- Modify: `tests/test_skill_adapter.py`

**Interfaces:**
- Consumes: `capture_search(include_reviewed)`, `capture_get`, formal reads, `capture_review`, and `capture_observation_ids`
- Produces: one public Codex App skill workflow using `gpt-5.6-sol`

- [ ] **Step 1: Write failing skill and documentation contract tests**

Extend the action table expectation with:

```python
"capture_review": {"action", "observation_ids", "outcome"},
```

Add assertions:

```python
def test_quality_first_formalization_workflow_is_bounded_and_user_confirmed():
    text = _guidance_text().casefold()
    assert "formalization-workflow.md" in _skill_text()
    assert "gpt-5.6-sol" in text
    assert "include_reviewed" in text
    assert "capture_observation_ids" in text
    assert "needs_context" in text and "discard" in text and "draft" in text
    assert "1–20" in _guidance_text()
    assert "raw codex session" in text
    assert "do not" in text
    assert "explicit user confirmation" in text
    assert "该 skill" in _guidance_text()


def test_golden_six_observations_have_exact_expected_review_results():
    text = _guidance_text()
    assert "Codex 自动完成发布" in text and "人工只确认发布" in text
    assert "使用 1Panel" in text
    assert "最终目标保持不变" in text
    assert "Docker Desktop 数据放在 D 盘" in text
    assert "该 skill 调用当前本地 harness" in text
    assert "24" in text
```

- [ ] **Step 2: Run skill tests and verify RED**

```powershell
& 'D:\tmp\github\agent-global-context\.venv\Scripts\python.exe' -m pytest tests/test_skill_adapter.py -q --basetemp D:\tmp_test\q\t -o cache_dir=D:\tmp_test\q\c
```

Expected: the workflow reference and `capture_review` action are absent.

- [ ] **Step 3: Create the formalization workflow reference**

The new reference must contain this exact operational sequence:

```markdown
# Quality-First Capture Formalization

Use this workflow only when the user asks to review or formalize Capture observations. The active Codex App model boundary for this rollout is `gpt-5.6-sol`; do not launch Codex CLI, an extractor subprocess, or reopen a raw Codex Session.

1. Call `capture_search` with `limit` at most `10` and omit `include_reviewed` so terminal observations stay hidden.
2. Call `capture_get` for each selected observation. Use 1–20 unique observation IDs.
3. Recall only relevant active formal memories with `overview → search → get`.
4. Assign every observation exactly one outcome: `draft`, `needs_context`, or `discard`.
5. A draft must be grounded, self-contained, decision-relevant, deduplicated, bounded, and policy-valid. Never guess a referent for `该 skill`, `该技能`, `这个方案`, `上述方案`, or `上面的设置`.
6. Show the complete Memory Item, the new/update/reinforce disposition, and all contributing observation IDs. Preview writes nothing.
7. After explicit user confirmation, call `confirm`, `update`, or `observe` with `reinforce` and include `capture_observation_ids`.
8. After the user accepts a non-draft classification, call `capture_review` with only `needs_context` or `discard`.
9. If a write fails, state that it was not saved. If `capture_review_receipt_failed` is returned, state that formal memory succeeded but review bookkeeping needs repair.

Golden batch: merge `Codex 自动完成发布` and `人工只确认发布`; draft bounded 1Panel context from `使用 1Panel`; update the matched AGC goal for `最终目标保持不变`; discard `Docker Desktop 数据放在 D 盘`; mark `该 skill 调用当前本地 harness` as `needs_context`. Preview must leave the formal-memory count at 24.
```

- [ ] **Step 4: Link the workflow and update the exact tool contract**

Add one paragraph to `SKILL.md`: when the user asks to review, consolidate, classify, or formalize Capture observations, read `references/formalization-workflow.md` and follow it before any write.

Document:

```json
{"action":"capture_search","filters":{"project":["project-id"]},"limit":10,"include_reviewed":false}
```

```json
{"action":"capture_review","observation_ids":["co_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"],"outcome":"needs_context"}
```

State that `capture_observation_ids` is optional on `confirm`, `update`, and `observe` only for `reinforce`; it contains 1–20 unique canonical IDs and creates `draft` receipts only after an accepted formal mutation.

- [ ] **Step 5: Run skill tests and verify GREEN**

Run the Task 6 command again.

Expected: all skill adapter tests pass, exactly one public skill remains, and the tool set remains exactly three.

- [ ] **Step 6: Commit Task 6**

```powershell
git add skills/agent-global-context/SKILL.md skills/agent-global-context/references/formalization-workflow.md skills/agent-global-context/references/tool-contract.md docs/capture-operations.md tests/test_skill_adapter.py
git commit -m "docs: add quality-first capture formalization workflow"
```

---

### Task 7: Runtime 0.4.0 Release Contract

**Files:**
- Modify: `pyproject.toml`
- Modify: `agc_runtime/__init__.py`
- Modify: `README.md`
- Modify: `README.zh.md`
- Modify: `docs/capture-operations.md`
- Modify: `tests/test_cli_contract.py`
- Modify: `tests/test_local_install.py`
- Modify: `tests/test_mcp_server.py`

**Interfaces:**
- Produces: package and executable version `0.4.0`

- [ ] **Step 1: Update version expectations first and verify RED**

Change test expectations from `0.3.0` to `0.4.0`, then run:

```powershell
& 'D:\tmp\github\agent-global-context\.venv\Scripts\python.exe' -m pytest tests/test_cli_contract.py tests/test_mcp_server.py tests/test_local_install.py -q --basetemp D:\tmp_test\q\t -o cache_dir=D:\tmp_test\q\c
```

Expected: version assertions fail because source metadata remains `0.3.0`.

- [ ] **Step 2: Set source and documentation to 0.4.0**

Use exact values:

```toml
[project]
version = "0.4.0"
```

```python
__version__ = "0.4.0"
```

Update README and Capture operations text to call `0.4.0` the quality-first formalization release while preserving the statement that installation does not enable Capture or automatic promotion.

- [ ] **Step 3: Run version and installer tests and verify GREEN**

Run the Task 7 command again.

Expected: all selected tests pass and both `python -m agc_runtime.mcp_server --version` and built executable probes report `0.4.0`.

- [ ] **Step 4: Commit Task 7**

```powershell
git add pyproject.toml agc_runtime/__init__.py README.md README.zh.md docs/capture-operations.md tests/test_cli_contract.py tests/test_local_install.py tests/test_mcp_server.py
git commit -m "chore: release agc runtime 0.4.0"
```

---

### Task 8: Full Verification, Isolated Acceptance, Installation, and GitHub Sync

**Files:**
- Verify: entire repository
- Build output: `D:\tmp_test\agc-formalization-package`
- Isolated Memory Root: `D:\tmp_test\agc-formalization-pilot`
- Install from verified main checkout: `D:\tmp\github\agent-global-context`
- Active skill root: `C:\Users\admin\.agents\skills`
- Active Codex App config: `C:\Users\admin\.codex-clean-20260710\config.toml`
- Production Memory Root: `<AGC_MEMORY_ROOT>`
- Runtime install root: `C:\Users\admin\.agent-global-context-runtime`

**Interfaces:**
- Consumes: all prior tasks
- Produces: verified wheel, immutable Runtime install, non-mutating golden preview, and pushed Git commit

- [ ] **Step 1: Run whitespace and focused regression checks**

```powershell
git diff --check
$env:TEMP='D:\tmp_test\q'; $env:TMP='D:\tmp_test\q'
& 'D:\tmp\github\agent-global-context\.venv\Scripts\python.exe' -m pytest tests/test_capture_review.py tests/test_capture_read_service.py tests/test_write_service.py tests/test_capture_backup_restore.py tests/test_capture_forget.py tests/test_admin_service.py tests/test_skill_adapter.py tests/test_mcp_server.py -q --basetemp D:\tmp_test\q\t -o cache_dir=D:\tmp_test\q\c
```

Expected: zero diff errors and all focused tests pass.

- [ ] **Step 2: Run the complete suite from an LF-preserving short-path export**

Export the current commit with `core.autocrlf=false` into a commit-bound fresh child of `D:\tmp_test`, verify `agc_runtime/default_config.yaml` contains zero CR bytes, then run:

```powershell
$short=(git rev-parse --short HEAD).Trim()
$zip="D:\tmp_test\lf-full-$short.zip"
$export="D:\tmp_test\lf-full-$short"
if((Test-Path -LiteralPath $zip) -or (Test-Path -LiteralPath $export)){ throw 'LF test export must be fresh' }
git -c core.autocrlf=false archive --format=zip --output=$zip HEAD
Expand-Archive -LiteralPath $zip -DestinationPath $export
$bytes=[System.IO.File]::ReadAllBytes("$export\agc_runtime\default_config.yaml")
if(($bytes | Where-Object { $_ -eq 13 }).Count -ne 0){ throw 'LF export contains CR bytes' }
Set-Location -LiteralPath $export
$env:TEMP='D:\tmp_test\q'; $env:TMP='D:\tmp_test\q'
& 'D:\tmp\github\agent-global-context\.venv\Scripts\python.exe' -m pytest -q --basetemp D:\tmp_test\q\t -o cache_dir=D:\tmp_test\q\c
```

Expected: all tests pass with zero failures.

- [ ] **Step 3: Build and inspect the wheel**

```powershell
$short=(git rev-parse --short HEAD).Trim()
$packageRoot="D:\tmp_test\agc-formalization-package-$short"
if(Test-Path -LiteralPath $packageRoot){ throw 'Package output must be fresh' }
$env:TEMP='D:\tmp_test\q'; $env:TMP='D:\tmp_test\q'
& 'D:\tmp\github\agent-global-context\.venv\Scripts\python.exe' -m build --wheel --outdir $packageRoot
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\verify-capture-release.ps1 `
  -Gate All `
  -PythonPath 'D:\tmp\github\agent-global-context\.venv\Scripts\python.exe' `
  -EvidenceRoot "D:\tmp_test\agc-formalization-release-$short"
```

Expected: wheel version `0.4.0`, four local entry points, exactly three MCP tools, and no repository build artifacts.

- [ ] **Step 4: Create an isolated 24-memory Pilot and run preview only**

Copy the production Memory Root through the managed backup/restore path into `D:\tmp_test\agc-formalization-pilot`; do not copy raw Session files:

```powershell
$python='D:\tmp\github\agent-global-context\.venv\Scripts\python.exe'
$production='<AGC_MEMORY_ROOT>'
$pilot='D:\tmp_test\agc-formalization-pilot'
if(Test-Path -LiteralPath $pilot){ throw 'Pilot Memory Root must be fresh' }
$backupJson='{"action":"backup"}' | & $python -m agc_runtime.cli admin --root $production --input -
$backup=$backupJson | ConvertFrom-Json
if($backup.status -ne 'accepted'){ throw 'Managed production backup failed' }
$restoreRequest=@{action='restore';backup_path=$backup.data.backup_path} | ConvertTo-Json -Compress
$restoreJson=$restoreRequest | & $python -m agc_runtime.cli admin --root $pilot --input -
$restore=$restoreJson | ConvertFrom-Json
if($restore.status -ne 'accepted'){ throw 'Pilot restore failed' }
$overviewJson='{"action":"overview"}' | & $python -m agc_runtime.cli read --root $pilot --input -
$overview=$overviewJson | ConvertFrom-Json
if($overview.status -ne 'accepted' -or $overview.data.memory_count -ne 24){ throw 'Pilot must contain exactly 24 formal memories' }
```

Use the same Runtime CLI `read` adapter against `$pilot` for bounded `capture_search`, `capture_get`, `overview`, `search`, and `get` requests; the active Codex App `gpt-5.6-sol` turn performs the semantic review. Run preview only and verify:

- publishing observations merge into one draft;
- 1Panel produces one bounded environment draft;
- unchanged-goal evidence targets the existing AGC goal;
- Docker D-drive detail is `discard`;
- ambiguous skill/harness evidence is `needs_context`;
- there are no dangling references;
- formal-memory count remains exactly 24;
- no review receipt exists before confirmation.

- [ ] **Step 5: Present the exact Pilot drafts and wait for user confirmation**

Do not write production memory in this step. Show complete Memory Item Markdown, action (`confirm`, `update`, or `reinforce`), matched memory ID when present, and contributing observation IDs. Wait for explicit confirmation.

- [ ] **Step 6: Merge the verified branch into local main**

From `D:\tmp\github\agent-global-context`, fetch local worktree state, verify main has not diverged from the feature base, then fast-forward or create a normal merge commit. Do not reset or overwrite unrelated work.

- [ ] **Step 7: Install Runtime 0.4.0 into Codex App paths**

```powershell
$repository='D:\tmp\github\agent-global-context'
& "$repository\scripts\install-local.ps1" `
  -RepositoryRoot $repository `
  -SkillsRoot 'C:\Users\admin\.agents\skills' `
  -CodexConfig 'C:\Users\admin\.codex-clean-20260710\config.toml' `
  -MemoryRoot '<AGC_MEMORY_ROOT>' `
  -InstallRoot 'C:\Users\admin\.agent-global-context-runtime'
```

Expected: a new immutable Runtime venv reports `0.4.0`, the stable launchers point to it, the single public skill is refreshed, production Capture remains configured as before, and automatic promotion remains disabled. Restart Codex App before live MCP verification.

- [ ] **Step 8: Apply only user-confirmed production writes**

After restart, verify `agc.read overview` still reports 24 formal memories before mutation. Apply only the actions the user confirmed, each with exact `capture_observation_ids`. Then verify target stable IDs, catalog consistency, receipt outcomes, and that default `capture_search` no longer returns terminally reviewed observations.

- [ ] **Step 9: Push the verified commit to GitHub**

```powershell
git status --short
git log -1 --oneline
git push origin main
```

Expected: clean status, local `main` equals `origin/main`, and the pushed history contains Runtime `0.4.0` plus the quality-first formalization commits.

- [ ] **Step 10: Record final evidence**

Report exact test counts, wheel hash, installed Runtime path/version, formal-memory count before and after confirmed writes, target memory IDs, review receipt counts by outcome, and the pushed Git commit. Do not claim any unconfirmed draft was stored.
