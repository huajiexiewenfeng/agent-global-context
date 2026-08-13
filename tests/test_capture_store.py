from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from agc_runtime.capture_contracts import (
    CAPTURE_SCHEMA_VERSION,
    CaptureKey,
    CaptureReceipt,
    CollectedObservation,
    TokenUsage,
    observation_fingerprint_for,
    observation_id_for,
    receipt_id_for,
)
from agc_runtime.capture_store import CaptureStore
from agc_runtime.paths import MemoryPaths


UTC = "2026-08-13T12:00:00Z"
SOURCE_ROOT = "1" * 64


def _key() -> CaptureKey:
    return CaptureKey("synthetic_adapter", SOURCE_ROOT, "task-1", "revision-1")


def _receipt(*, fingerprint: str = "b" * 64, status: str = "extracting") -> CaptureReceipt:
    key = _key()
    extracting = status == "extracting"
    complete = status == "complete"
    return CaptureReceipt.from_mapping(
        {
            "schema_version": CAPTURE_SCHEMA_VERSION,
            "receipt_id": receipt_id_for(key),
            **key.to_mapping(),
            "adapter_version": "1",
            "source_schema_version": "1",
            "identity_quality": "session_id",
            "source_fingerprint": fingerprint if (extracting or complete) else None,
            "source_hash_schema_version": "source-v1" if (extracting or complete) else None,
            "capsule_hash": "c" * 64 if (extracting or complete) else None,
            "capsule_schema_version": "capsule-v1" if (extracting or complete) else None,
            "settled_at": UTC,
            "discovered_at": UTC,
            "updated_at": UTC,
            "status": status,
            "attempt_count": 1,
            "next_retry_at": None,
            "extractor_id": "synthetic_extractor" if (extracting or complete) else None,
            "extractor_version": "1" if (extracting or complete) else None,
            "extractor_schema_version": "1" if (extracting or complete) else None,
            "taxonomy_version": "taxonomy-v1" if (extracting or complete) else None,
            "observation_count": 0 if complete else None,
            "filtered_counts": {"safety": 0, "policy": 0, "over_limit": 0} if complete else None,
            "duplicate_suppression_count": 0 if complete else None,
            "token_usage": TokenUsage(1, 2, 3).to_mapping(),
            "usage_quality": "actual",
            "redacted_by_forget": False,
            "forgotten_observation_count": 0,
            "zero_reason": "extractor_empty" if complete else None,
            "sanitized_error": None,
            "coalesced_to": None,
            "exclusion_reason": None,
        }
    )


def _observation(statement: str, ordinal: int) -> CollectedObservation:
    key = _key()
    mapping = {
        "schema_version": CAPTURE_SCHEMA_VERSION,
        "observation_id": "co_" + "0" * 64,
        "receipt_id": receipt_id_for(key),
        "source": {**key.to_mapping(), "locator": "sessions/synthetic"},
        "ordinal": ordinal,
        "observation_fingerprint": "0" * 64,
        "statement": statement,
        "assertion": {"subject": "user", "mode": "direct", "modality": "asserted"},
        "primary_category": "work",
        "taxonomy_version": "taxonomy-v1",
        "kind": "preference",
        "scopes": ["testing"],
        "project_scope": None,
        "confidence": "observed",
        "sensitivity": "normal",
        "signal_type": "decision_or_constraint",
        "observed_at": UTC,
        "captured_at": UTC,
        "extractor_version": "1",
        "processing_state": "collected",
    }
    mapping["observation_fingerprint"] = observation_fingerprint_for(mapping)
    mapping["observation_id"] = observation_id_for(
        mapping["receipt_id"], mapping["observation_fingerprint"]
    )
    return CollectedObservation.from_mapping(mapping)


def _store(tmp_path: Path) -> CaptureStore:
    return CaptureStore(MemoryPaths.from_root(tmp_path / "memory"), clock=lambda: UTC)


def _complete_receipt(receipt: CaptureReceipt, count: int) -> CaptureReceipt:
    return CaptureReceipt.from_mapping(
        {
            **receipt.to_mapping(),
            "status": "complete",
            "observation_count": count,
            "filtered_counts": {"safety": 0, "policy": 0, "over_limit": 0},
            "duplicate_suppression_count": 0,
            "zero_reason": None if count else "extractor_empty",
        }
    )


def test_ac_08_two_level_idempotency_and_source_conflict(tmp_path: Path):
    store = _store(tmp_path)
    receipt = _receipt()
    store.register_extraction(receipt)
    lease = store.acquire_lease(_key(), owner_id="worker-a", now=UTC, ttl_seconds=60)
    assert lease is not None
    observations = (_observation("User prefers synthetic unit tests.", 0), _observation("User values strict test isolation.", 1))
    result = store.commit_extraction(lease, observations, _complete_receipt(receipt, 2))
    assert result.created_observation_count == 2
    assert [item.observation_id for item in store.visible_observations(receipt.receipt_id)] == [item.observation_id for item in observations]

    replay = store.register_extraction(_receipt())
    assert replay.status == "complete"
    assert replay.created is False
    assert store.object_counts()["observations"] == 2

    pre_complete = _store(tmp_path / "pre")
    pre_complete.register_extraction(_receipt())
    quarantined = pre_complete.register_extraction(_receipt(fingerprint="d" * 64))
    assert quarantined.status == "quarantined"
    assert pre_complete.visible_observations(receipt.receipt_id) == ()

    conflict = store.register_extraction(_receipt(fingerprint="d" * 64))
    assert conflict.status == "complete"
    assert conflict.created is False
    assert store.object_counts()["observations"] == 2
    assert store.source_health(_key().adapter_id, _key().source_root_id) == "degraded"


def test_stale_or_concurrent_lease_cannot_commit(tmp_path: Path):
    store = _store(tmp_path)
    receipt = _receipt()
    store.register_extraction(receipt)
    first = store.acquire_lease(_key(), owner_id="worker-a", now=UTC, ttl_seconds=1)
    assert first is not None
    assert store.acquire_lease(_key(), owner_id="worker-b", now=UTC, ttl_seconds=1) is None
    second = store.acquire_lease(_key(), owner_id="worker-b", now="2026-08-13T12:00:02Z", ttl_seconds=60)
    assert second is not None and second.fencing_token > first.fencing_token
    with pytest.raises(ValueError, match="lease"):
        store.commit_extraction(first, (), _complete_receipt(receipt, 0))
    store.commit_extraction(second, (), _complete_receipt(receipt, 0))


def test_commit_rejects_terminal_receipt_that_changes_bound_hashes_or_attempt(tmp_path: Path):
    store = _store(tmp_path)
    receipt = _receipt()
    store.register_extraction(receipt)
    lease = store.acquire_lease(_key(), owner_id="worker", now=UTC, ttl_seconds=60)
    assert lease is not None
    terminal = _complete_receipt(receipt, 0)
    altered = CaptureReceipt.from_mapping(
        {
            **terminal.to_mapping(),
            "source_fingerprint": "d" * 64,
        }
    )
    with pytest.raises(ValueError, match="bound receipt"):
        store.commit_extraction(lease, (), altered)


def test_commit_validates_observation_binding_before_creating_transaction_files(tmp_path: Path):
    store = _store(tmp_path)
    receipt = _receipt()
    store.register_extraction(receipt)
    lease = store.acquire_lease(_key(), owner_id="worker", now=UTC, ttl_seconds=60)
    assert lease is not None
    invalid = replace(_observation("User needs binding validation.", 0), observation_fingerprint="0" * 64)
    with pytest.raises(ValueError, match="Capture contract"):
        store.commit_extraction(lease, (invalid,), _complete_receipt(receipt, 1))
    assert not list(store.capture.journals.glob("*.json"))
    assert not list(store.capture.staging.glob("*.json"))
