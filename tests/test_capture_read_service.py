"""Contract tests for isolated Capture read views."""

from dataclasses import replace

import pytest

from agc_runtime.capture_contracts import (
    CAPTURE_SCHEMA_VERSION, CaptureKey, CaptureReceipt, CaptureSuppressionTombstone, CollectedObservation,
    TokenUsage, observation_fingerprint_for, observation_id_for, receipt_id_for, tombstone_id_for,
)
from agc_runtime.capture_read_service import capture_get, capture_overview, capture_search
from agc_runtime.capture_store import CaptureStore
from agc_runtime.paths import MemoryPaths
from agc_runtime.capture_transaction import atomic_write_json
from agc_runtime.admin_service import dispatch_admin
from agc_runtime.read_service import dispatch_read


UTC = "2026-08-13T12:00:00Z"


def _key(task: str = "task-1", revision: str = "revision-1") -> CaptureKey:
    return CaptureKey("synthetic_adapter", "1" * 64, task, revision)


def _receipt(key: CaptureKey) -> CaptureReceipt:
    return CaptureReceipt.from_mapping({
        "schema_version": CAPTURE_SCHEMA_VERSION, "receipt_id": receipt_id_for(key),
        **key.to_mapping(), "adapter_version": "1", "source_schema_version": "1",
        "identity_quality": "session_id", "source_fingerprint": "b" * 64,
        "source_hash_schema_version": "source-v1", "capsule_hash": "c" * 64,
        "capsule_schema_version": "capsule-v1", "settled_at": UTC,
        "discovered_at": UTC, "updated_at": UTC, "status": "extracting",
        "attempt_count": 1, "next_retry_at": None, "extractor_id": "synthetic",
        "extractor_version": "1", "extractor_schema_version": "1",
        "taxonomy_version": "taxonomy-v1", "observation_count": None,
        "filtered_counts": None, "duplicate_suppression_count": None,
        "token_usage": TokenUsage(1, 2, 3).to_mapping(), "usage_quality": "actual",
        "redacted_by_forget": False, "forgotten_observation_count": 0,
        "zero_reason": None, "sanitized_error": None, "coalesced_to": None,
        "exclusion_reason": None,
    })


def _observation(receipt: CaptureReceipt, statement: str, ordinal: int, *, captured_at: str, sensitivity: str = "normal") -> CollectedObservation:
    mapping = {
        "schema_version": CAPTURE_SCHEMA_VERSION, "observation_id": "co_" + "0" * 64,
        "receipt_id": receipt.receipt_id, "source": {**receipt.key.to_mapping(), "locator": "synthetic/only"},
        "ordinal": ordinal, "observation_fingerprint": "0" * 64, "statement": statement,
        "assertion": {"subject": "user", "mode": "direct", "modality": "asserted"},
        "primary_category": "work", "taxonomy_version": "taxonomy-v1", "kind": "preference",
        "scopes": ["testing"], "project_scope": "project-1", "confidence": "observed",
        "sensitivity": sensitivity, "signal_type": "decision_or_constraint", "observed_at": captured_at,
        "captured_at": captured_at, "extractor_version": "1", "processing_state": "collected",
    }
    mapping["observation_fingerprint"] = observation_fingerprint_for(mapping)
    mapping["observation_id"] = observation_id_for(receipt.receipt_id, mapping["observation_fingerprint"])
    return CollectedObservation.from_mapping(mapping)


def _complete(store: CaptureStore, key: CaptureKey, observations: tuple[CollectedObservation, ...]) -> CaptureReceipt:
    receipt = _receipt(key)
    store.register_extraction(receipt)
    lease = store.acquire_lease(key, owner_id="synthetic", now=UTC, ttl_seconds=60)
    assert lease is not None
    complete = CaptureReceipt.from_mapping({**receipt.to_mapping(), "status": "complete", "observation_count": len(observations), "filtered_counts": {"safety": 0, "policy": 0, "over_limit": 0}, "duplicate_suppression_count": 0, "zero_reason": None if observations else "extractor_empty"})
    store.commit_extraction(lease, observations, complete)
    return complete


def test_empty_capture_overview_marks_inspection_not_applicable(tmp_path):
    overview = capture_overview(tmp_path)

    assert overview["coverage_unit"] == "ratio_0_to_1"
    assert overview["inspection_completion"] == "not_applicable"


def test_capture_search_filters_orders_pages_and_redacts_source(tmp_path):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    store = CaptureStore(paths, clock=lambda: UTC)
    first = _receipt(_key("task-1", "r1"))
    second = _receipt(_key("task-2", "r2"))
    newer = _observation(first, "Synthetic newer observation.", 0, captured_at="2026-08-13T12:02:00Z")
    older = _observation(second, "Synthetic older observation.", 0, captured_at="2026-08-13T12:01:00Z", sensitivity="personal")
    _complete(store, first.key, (newer,))
    _complete(store, second.key, (older,))

    page_one = capture_search(paths, {"filters": {"task": ["task-1"], "project": ["project-1"], "category": ["work"], "kind": ["preference"], "scope": ["testing"], "state": ["collected"], "sensitivity": ["normal"], "time": ["2026-08-13T12:02:00Z"]}, "limit": 1})
    assert [item["observation_id"] for item in page_one["results"]] == [newer.observation_id]
    assert set(page_one["results"][0]["source"]) == {"adapter_id", "source_root_id", "task_id", "revision_id"}
    assert "observation_fingerprint" not in str(page_one)
    assert "capsule_hash" not in str(page_one)

    all_first = capture_search(paths, {"limit": 1})
    all_second = capture_search(paths, {"limit": 1, "cursor": all_first["next_cursor"]})
    assert [item["observation_id"] for item in all_first["results"] + all_second["results"]] == [newer.observation_id, older.observation_id]
    assert all_second["next_cursor"] is None
    assert capture_search(paths, {"filters": {"task": ["missing"]}})["results"] == []
    with pytest.raises(ValueError, match="invalid capture cursor"):
        capture_search(paths, {"cursor": all_first["next_cursor"][:-1] + "A"})
    with pytest.raises(ValueError, match="unsupported capture search filter"):
        capture_search(paths, {"filters": {"unknown": ["x"]}})
    with pytest.raises(ValueError, match="limit"):
        capture_search(paths, {"limit": 101})


def test_capture_get_never_reveals_incomplete_or_unmanifested_data(tmp_path):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    store = CaptureStore(paths, clock=lambda: UTC)
    receipt = _receipt(_key())
    observation = _observation(receipt, "Synthetic visible observation.", 0, captured_at=UTC)
    complete = _complete(store, receipt.key, (observation,))

    assert capture_get(paths, {"observation_id": observation.observation_id})["observation"]["statement"] == observation.statement
    assert capture_get(paths, {"receipt_id": complete.receipt_id})["receipt"]["status"] == "complete"
    (paths.capture.indexes / f"{complete.receipt_id}.json").unlink()
    with pytest.raises(LookupError):
        capture_get(paths, {"observation_id": observation.observation_id})


def test_capture_overview_uses_capture_keys_and_unkeyed_quarantine_degrades_health(tmp_path):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    store = CaptureStore(paths, clock=lambda: UTC)
    known = _key("task-1", "r1")
    suppressed = _key("task-2", "r2")
    receipt = _receipt(known)
    _complete(store, known, ())
    paths.capture.census.mkdir(parents=True, exist_ok=True)
    atomic_write_json(paths.capture.census / "known.json", {"schema_version": 1, "capture_key": known.to_mapping()})
    atomic_write_json(paths.capture.census / "suppressed.json", {"schema_version": 1, "capture_key": suppressed.to_mapping()})
    paths.capture.tombstones.mkdir(parents=True, exist_ok=True)
    tombstone = CaptureSuppressionTombstone.from_mapping({"schema_version": 1, "tombstone_id": tombstone_id_for(suppressed), "capture_key": suppressed.to_mapping(), "created_at": UTC, "reason": "user_forget"})
    atomic_write_json(paths.capture.tombstones / f"{tombstone.tombstone_id}.json", tombstone.to_mapping())
    paths.capture.quarantines.mkdir(parents=True, exist_ok=True)
    atomic_write_json(paths.capture.quarantines / "source.json", {"schema_version": 1, "adapter_id": "synthetic_adapter", "source_root_id": "2" * 64, "created_at": UTC, "code": "unknown_identity"})

    overview = capture_overview(paths)

    assert overview["census_key_count"] == 2
    assert overview["accounting_coverage"] == 1.0
    assert overview["inspection_denominator"] == 1
    assert overview["inspection_completion"] == 1.0
    assert overview["silent_loss"] == 0
    assert overview["source_health"] == "degraded"
    assert overview["source_coverage_complete"] is False


def test_capture_actions_are_explicit_read_dispatch_routes(tmp_path):
    paths = MemoryPaths.from_root(tmp_path / "memory")

    response = dispatch_read(paths, {"action": "capture_overview"})

    assert response.status == "accepted"
    assert response.data["inspection_completion"] == "not_applicable"


def test_ordinary_recall_actions_do_not_expose_capture_objects(tmp_path):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    store = CaptureStore(paths, clock=lambda: UTC)
    receipt = _receipt(_key())
    observation = _observation(receipt, "Synthetic isolated observation.", 0, captured_at=UTC)
    _complete(store, receipt.key, (observation,))
    dispatch_admin(paths, {"action": "init"})

    overview = dispatch_read(paths, {"action": "overview"})
    search = dispatch_read(paths, {"action": "search"})
    history = dispatch_read(paths, {"action": "history", "id": "not-a-capture-id"})
    evidence = dispatch_read(paths, {"action": "evidence", "id": "not-a-capture-id"})

    get = dispatch_read(paths, {"action": "get", "id": observation.observation_id})
    assert overview.status == "accepted" and "Synthetic isolated observation." not in str(overview.data)
    assert search.status == "accepted" and "Synthetic isolated observation." not in str(search.data)
    assert get.status == "failed"
    assert history.status == "accepted" and history.data["events"] == []
    assert evidence.status == "accepted" and evidence.data["sources"] == []
