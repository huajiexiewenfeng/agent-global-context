"""Contract tests for isolated Capture read views."""

import base64
from dataclasses import replace
import hashlib
import os

import pytest

from agc_runtime.capture_contracts import (
    CAPTURE_SCHEMA_VERSION, CaptureKey, CaptureReceipt, CaptureSuppressionTombstone, CollectedObservation, RevisionRef,
    TokenUsage, observation_fingerprint_for, observation_id_for, receipt_id_for, tombstone_id_for,
)
from agc_runtime.capture_read_service import capture_get, capture_overview, capture_search
from agc_runtime.capture_store import CaptureStore
from agc_runtime.paths import MemoryPaths
from agc_runtime.capture_transaction import atomic_write_json
from agc_runtime.admin_service import dispatch_admin
from agc_runtime.locking import capture_write_lock
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
    assert not MemoryPaths.from_root(tmp_path).capture.root.exists()


@pytest.mark.parametrize(
    "read_request",
    [
        {"action": "capture_overview"},
        {"action": "capture_search"},
        {"action": "capture_get", "observation_id": "co_" + "f" * 64},
    ],
)
def test_capture_reads_return_fixed_busy_error_while_writer_holds_root_lock(tmp_path, read_request):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    CaptureStore(paths).ensure_layout()

    with capture_write_lock(paths):
        response = dispatch_read(paths, read_request)

    assert response.status == "failed"
    assert response.error == {
        "code": "capture_read_busy",
        "message": "Capture read is temporarily unavailable",
    }
    rendered = str(response.to_dict())
    assert str(paths.root) not in rendered
    assert ".writer.lock" not in rendered


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
    for name, key in (("known", known), ("suppressed", suppressed)):
        atomic_write_json(
            paths.capture.census / f"{name}.json",
            RevisionRef(
                key=key,
                rollout_anchor_id=f"anchor-{name}",
                completed_at=UTC,
                locator=f"sessions/{name}",
                identity_quality="session_id",
                adapter_version="1",
                source_schema_version="1",
            ).to_mapping(),
        )
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


def test_capture_cursor_is_hmac_bound_to_root_filters_and_limit(tmp_path):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    store = CaptureStore(paths, clock=lambda: UTC)
    first = _receipt(_key("task-1", "r1"))
    second = _receipt(_key("task-2", "r2"))
    _complete(
        store,
        first.key,
        (_observation(first, "Synthetic first page.", 0, captured_at="2026-08-13T12:02:00Z"),),
    )
    _complete(
        store,
        second.key,
        (_observation(second, "Synthetic second page.", 0, captured_at="2026-08-13T12:01:00Z"),),
    )

    filters = {"category": ["work"]}
    first_page = capture_search(paths, {"filters": filters, "limit": 1})
    cursor = first_page["next_cursor"]
    assert cursor is not None

    # A fresh service/store instance for the same root can verify the durable key.
    second_page = capture_search(
        MemoryPaths.from_root(paths.root),
        {"filters": filters, "limit": 1, "cursor": cursor},
    )
    assert second_page["returned_count"] == 1

    for request in (
        {"filters": {"category": ["learning"]}, "limit": 1, "cursor": cursor},
        {"filters": filters, "limit": 2, "cursor": cursor},
    ):
        with pytest.raises(ValueError, match="invalid capture cursor"):
            capture_search(paths, request)

    other_root = MemoryPaths.from_root(tmp_path / "other-memory")
    with pytest.raises(ValueError, match="invalid capture cursor"):
        capture_search(other_root, {"filters": filters, "limit": 1, "cursor": cursor})


def test_capture_cursor_rejects_plain_sha_tamper_and_key_rotation(tmp_path):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    store = CaptureStore(paths, clock=lambda: UTC)
    first = _receipt(_key("task-1", "r1"))
    second = _receipt(_key("task-2", "r2"))
    _complete(store, first.key, (_observation(first, "Synthetic newest.", 0, captured_at="2026-08-13T12:02:00Z"),))
    _complete(store, second.key, (_observation(second, "Synthetic oldest.", 0, captured_at="2026-08-13T12:01:00Z"),))
    cursor = capture_search(paths, {"limit": 1})["next_cursor"]
    assert cursor is not None

    raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
    payload = raw[:-32]
    plain_sha_forgery = base64.urlsafe_b64encode(
        payload + hashlib.sha256(payload).digest()
    ).decode("ascii").rstrip("=")
    tampered = base64.urlsafe_b64encode(
        bytes([raw[0] ^ 1]) + raw[1:]
    ).decode("ascii").rstrip("=")
    for invalid in (plain_sha_forgery, tampered):
        with pytest.raises(ValueError, match="invalid capture cursor"):
            capture_search(paths, {"limit": 1, "cursor": invalid})

    assert paths.capture.cursor_hmac_key.read_bytes() != b""
    paths.capture.cursor_hmac_key.write_bytes(os.urandom(32))
    with pytest.raises(ValueError, match="invalid capture cursor"):
        capture_search(paths, {"limit": 1, "cursor": cursor})


def test_capture_search_only_lazily_recreates_missing_key_when_a_cursor_is_needed(tmp_path):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    store = CaptureStore(paths, clock=lambda: UTC)
    for index in range(2):
        receipt = _receipt(_key(f"task-{index}", f"r{index}"))
        _complete(
            store,
            receipt.key,
            (_observation(receipt, f"Synthetic lazy-key {index}.", 0, captured_at=UTC),),
        )
    paths.capture.cursor_hmac_key.unlink()

    complete_page = capture_search(paths, {"limit": 20})
    assert complete_page["next_cursor"] is None
    assert not paths.capture.cursor_hmac_key.exists()

    partial_page = capture_search(paths, {"limit": 1})
    assert partial_page["next_cursor"] is not None
    assert len(paths.capture.cursor_hmac_key.read_bytes()) == 32


def test_fresh_restore_reports_missing_cursor_key_until_paginated_search_needs_it(tmp_path):
    source_paths = MemoryPaths.from_root(tmp_path / "source-memory")
    assert dispatch_admin(source_paths, {"action": "init"}).status == "accepted"
    backup = dispatch_admin(source_paths, {"action": "backup"})
    assert backup.status == "accepted"

    paths = MemoryPaths.from_root(tmp_path / "restored-memory")
    restored = dispatch_admin(
        paths,
        {"action": "restore", "backup_path": backup.data["backup_path"]},
    )

    assert restored.status == "accepted"
    assert not paths.capture.cursor_hmac_key.exists()
    status = dispatch_admin(paths, {"action": "capture_status"})
    assert status.data["cursor_key"] == {"state": "missing", "key_id": None}

    store = CaptureStore(paths, clock=lambda: UTC)
    for index in range(2):
        receipt = _receipt(_key(f"restored-task-{index}", f"r{index}"))
        _complete(
            store,
            receipt.key,
            (_observation(receipt, f"Synthetic restored {index}.", 0, captured_at=UTC),),
        )
    paths.capture.cursor_hmac_key.unlink()

    assert capture_search(paths, {"limit": 20})["next_cursor"] is None
    assert not paths.capture.cursor_hmac_key.exists()
    assert capture_search(paths, {"limit": 1})["next_cursor"] is not None
    assert len(paths.capture.cursor_hmac_key.read_bytes()) == 32


@pytest.mark.parametrize(
    "search_request",
    [
        {"filters": {"task": "task-1"}},
        {"filters": {"task": []}},
        {"filters": {"category": ["invalid"]}},
        {"filters": {"kind": ["invalid"]}},
        {"filters": {"state": ["invalid"]}},
        {"filters": {"sensitivity": ["secret"]}},
        {"filters": {"time": {}}},
        {"filters": {"time": {"from": "2026-08-13T12:00:00+00:00"}}},
        {"filters": {"time": {"from": "2026-08-14T00:00:00Z", "to": "2026-08-13T00:00:00Z"}}},
        {"limit": True},
        {"limit": 0},
        {"limit": 101},
    ],
)
def test_capture_search_validates_filters_time_and_limit_before_empty_scan(tmp_path, search_request):
    with pytest.raises(ValueError):
        capture_search(tmp_path, search_request)


def test_capture_search_orders_fractional_timestamps_and_ties_across_three_pages(tmp_path):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    store = CaptureStore(paths, clock=lambda: UTC)
    observations = []
    for index, captured_at in enumerate(
        (
            "2026-08-13T12:00:00.900Z",
            "2026-08-13T12:00:00.10Z",
            "2026-08-13T12:00:00.010Z",
            "2026-08-13T12:00:00.010Z",
            "2026-08-13T12:00:00Z",
        )
    ):
        receipt = _receipt(_key(f"task-{index}", f"r{index}"))
        observation = _observation(
            receipt,
            f"Synthetic ordered observation {index}.",
            0,
            captured_at=captured_at,
        )
        _complete(store, receipt.key, (observation,))
        observations.append(observation)

    expected = sorted(
        observations,
        key=lambda item: (-__import__("datetime").datetime.fromisoformat(item.captured_at.replace("Z", "+00:00")).timestamp(), item.observation_id),
    )
    pages = []
    cursor = None
    for _ in range(3):
        request = {"limit": 2}
        if cursor is not None:
            request["cursor"] = cursor
        page = capture_search(paths, request)
        pages.extend(page["results"])
        cursor = page["next_cursor"]

    assert [item["observation_id"] for item in pages] == [item.observation_id for item in expected]
    assert cursor is None


def test_locked_snapshot_reports_corrupt_objects_and_duplicate_census_keys(tmp_path):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    store = CaptureStore(paths, clock=lambda: UTC)
    key = _key()
    receipt = _receipt(key)
    observation = _observation(receipt, "Snapshot content must stay private.", 0, captured_at=UTC)
    complete = _complete(store, key, (observation,))
    revision = RevisionRef(
        key=key,
        rollout_anchor_id="anchor-1",
        completed_at=UTC,
        locator="opaque-locator",
        identity_quality="session_id",
        adapter_version="1",
        source_schema_version="1",
    )
    atomic_write_json(paths.capture.census / "one.json", revision.to_mapping())
    atomic_write_json(paths.capture.census / "duplicate.json", revision.to_mapping())
    atomic_write_json(
        paths.capture.receipts / f"{complete.receipt_id}.json",
        {"schema_version": 1, "secret_marker": "must-not-leak"},
    )

    overview = capture_overview(paths)

    assert overview["census_key_count"] == 1
    assert overview["status_counts"]["complete"] == 0
    assert overview["integrity"]["state"] == "degraded"
    assert {item["code"] for item in overview["integrity"]["diagnostics"]} >= {
        "invalid_receipt",
        "duplicate_capture_key",
    }
    assert overview["source_coverage_complete"] is False
    assert "must-not-leak" not in str(overview)
    assert str(paths.root) not in str(overview)


def test_capture_get_returns_fixed_safe_errors_for_missing_and_corrupt_objects(tmp_path):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    store = CaptureStore(paths, clock=lambda: UTC)
    receipt = _receipt(_key())
    observation = _observation(receipt, "Never reveal this statement in an error.", 0, captured_at=UTC)
    complete = _complete(store, receipt.key, (observation,))
    (paths.capture.indexes / f"{complete.receipt_id}.json").write_text(
        '{"secret_marker":"must-not-leak"}', encoding="utf-8"
    )

    corrupt = dispatch_read(paths, {"action": "capture_get", "receipt_id": complete.receipt_id})
    missing = dispatch_read(paths, {"action": "capture_get", "observation_id": "co_" + "f" * 64})

    assert corrupt.status == "failed" and corrupt.error["code"] == "capture_integrity_degraded"
    assert missing.status == "failed" and missing.error["code"] == "capture_not_found"
    for response in (corrupt, missing):
        rendered = str(response.to_dict())
        assert str(paths.root) not in rendered
        assert "must-not-leak" not in rendered
        assert "Never reveal" not in rendered


def test_capture_search_hides_terminal_reviews_by_default_and_audits_explicitly(
    tmp_path, visible_capture_observations
):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    store, (first, second) = visible_capture_observations(
        paths, ["First review fact.", "Second review fact."]
    )
    store.record_reviews(
        (first.observation_id,), outcome="discard", target_memory_id=None
    )

    assert [
        item["observation_id"] for item in capture_search(paths, {"limit": 20})["results"]
    ] == [second.observation_id]
    audited = capture_search(paths, {"limit": 20, "include_reviewed": True})
    assert {item["observation_id"] for item in audited["results"]} == {
        first.observation_id,
        second.observation_id,
    }
    exact = capture_get(paths, {"observation_id": first.observation_id})
    assert exact["review"]["outcome"] == "discard"
    assert set(exact["review"]) == {
        "schema_version",
        "observation_id",
        "outcome",
        "target_memory_id",
        "reviewed_at",
    }


def test_capture_search_cursor_binds_include_reviewed(
    tmp_path, visible_capture_observations
):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    visible_capture_observations(paths, ["First review fact.", "Second review fact."])
    cursor = capture_search(paths, {"limit": 1})["next_cursor"]
    with pytest.raises(ValueError, match="invalid capture cursor"):
        capture_search(
            paths,
            {"limit": 1, "cursor": cursor, "include_reviewed": True},
        )
    with pytest.raises(ValueError, match="include_reviewed"):
        capture_search(paths, {"include_reviewed": "yes"})
