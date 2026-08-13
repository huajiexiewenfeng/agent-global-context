from __future__ import annotations

import json
import zipfile
from dataclasses import replace
from pathlib import Path

from agc_runtime.admin_service import dispatch_admin
from agc_runtime.capture_contracts import CaptureKey, CaptureReceipt, CollectedObservation, TokenUsage, observation_fingerprint_for, observation_id_for, receipt_id_for, tombstone_id_for
from agc_runtime.capture_store import CaptureStore
from agc_runtime.capture_forget_transaction import CaptureForgetTransaction
from agc_runtime.paths import MemoryPaths
from agc_runtime.write_service import dispatch_write


UTC = "2026-08-13T12:00:00Z"
ROOT_ID = "2" * 64


def _key() -> CaptureKey:
    return CaptureKey("synthetic_adapter", ROOT_ID, "task-5", "revision-5")


def _receipt() -> CaptureReceipt:
    key = _key()
    return CaptureReceipt.from_mapping({
        "schema_version": 1, "receipt_id": receipt_id_for(key), **key.to_mapping(),
        "adapter_version": "1", "source_schema_version": "1", "identity_quality": "session_id",
        "source_fingerprint": "a" * 64, "source_hash_schema_version": "source-v1",
        "capsule_hash": "b" * 64, "capsule_schema_version": "capsule-v1",
        "settled_at": UTC, "discovered_at": UTC, "updated_at": UTC, "status": "extracting",
        "attempt_count": 1, "next_retry_at": None, "extractor_id": "synthetic_extractor",
        "extractor_version": "1", "extractor_schema_version": "1", "taxonomy_version": "taxonomy-v1",
        "observation_count": None, "filtered_counts": None, "duplicate_suppression_count": None,
        "token_usage": TokenUsage(1, 2, 3).to_mapping(), "usage_quality": "actual",
        "redacted_by_forget": False, "forgotten_observation_count": 0, "zero_reason": None,
        "sanitized_error": None, "coalesced_to": None, "exclusion_reason": None,
    })


def _observation(statement: str, ordinal: int) -> CollectedObservation:
    key = _key()
    value = {
        "schema_version": 1, "observation_id": "co_" + "0" * 64, "receipt_id": receipt_id_for(key),
        "source": {**key.to_mapping(), "locator": "sessions/synthetic"}, "ordinal": ordinal,
        "observation_fingerprint": "0" * 64, "statement": statement,
        "assertion": {"subject": "user", "mode": "direct", "modality": "asserted"},
        "primary_category": "work", "taxonomy_version": "taxonomy-v1", "kind": "preference", "scopes": ["testing"],
        "project_scope": None, "confidence": "observed", "sensitivity": "normal", "signal_type": "decision_or_constraint",
        "observed_at": UTC, "captured_at": UTC, "extractor_version": "1", "processing_state": "collected",
    }
    value["observation_fingerprint"] = observation_fingerprint_for(value)
    value["observation_id"] = observation_id_for(value["receipt_id"], value["observation_fingerprint"])
    return CollectedObservation.from_mapping(value)


def _populated(tmp_path: Path) -> tuple[MemoryPaths, CaptureStore, CaptureReceipt, tuple[CollectedObservation, ...]]:
    paths = MemoryPaths.from_root(tmp_path / "memory")
    assert dispatch_admin(paths, {"action": "init"}).status == "accepted"
    store = CaptureStore(paths, clock=lambda: UTC)
    receipt = _receipt()
    observations = (_observation("Secret target statement must vanish.", 0), _observation("Remaining observation stays visible.", 1))
    store.register_extraction(receipt)
    lease = store.acquire_lease(_key(), owner_id="worker", now=UTC, ttl_seconds=60)
    assert lease is not None
    complete = CaptureReceipt.from_mapping({**receipt.to_mapping(), "status": "complete", "observation_count": 2,
        "filtered_counts": {"safety": 0, "policy": 0, "over_limit": 0}, "duplicate_suppression_count": 0, "zero_reason": None})
    store.commit_extraction(lease, observations, complete)
    return paths, store, receipt, observations


def _request(target: dict) -> dict:
    return {"action": "capture_forget", "authorization": "explicit_user_request", "target": target}


def test_capture_forget_requires_exact_authorized_union(tmp_path: Path):
    paths, _store, _receipt_value, observations = _populated(tmp_path)
    missing_auth = dispatch_write(paths, {"action": "capture_forget", "target": {"type": "observation", "observation_id": observations[0].observation_id}})
    assert missing_auth.error["code"] == "capture_forget_authorization_required"
    broad = dispatch_write(paths, _request({"type": "observation", "observation_id": observations[0].observation_id, "term": "Secret"}))
    assert broad.error["code"] == "invalid_request"


def test_observation_capture_forget_rewrites_backups_and_clears_receipt_hashes(tmp_path: Path):
    paths, store, receipt, observations = _populated(tmp_path)
    backup = dispatch_admin(paths, {"action": "backup"}).data["backup_path"]
    response = dispatch_write(paths, _request({"type": "observation", "observation_id": observations[0].observation_id}))
    assert response.status == "accepted"
    updated = store.read_receipt(receipt.receipt_id)
    assert updated.observation_count == 1
    assert updated.forgotten_observation_count == 1
    assert updated.redacted_by_forget is True
    assert updated.source_fingerprint is None and updated.source_hash_schema_version is None
    assert updated.capsule_hash is None and updated.capsule_schema_version is None
    assert updated.zero_reason is None
    assert [item.observation_id for item in store.iter_visible_observations()] == [observations[1].observation_id]
    with zipfile.ZipFile(backup) as archive:
        text = b"".join(archive.read(name) for name in archive.namelist()).decode("utf-8")
    assert observations[0].observation_id not in text
    assert observations[0].statement not in text
    assert "a" * 64 not in text and "b" * 64 not in text


def test_revision_capture_forget_leaves_only_content_free_suppression_tombstone(tmp_path: Path):
    paths, _store, receipt, observations = _populated(tmp_path)
    response = dispatch_write(paths, _request({"type": "revision", **_key().to_mapping()}))
    assert response.status == "accepted"
    assert response.data["source_task_deleted"] is False
    tombstone = paths.capture.tombstones / f"{tombstone_id_for(_key())}.json"
    assert tombstone.is_file()
    assert set(json.loads(tombstone.read_text(encoding="utf-8"))) == {"schema_version", "tombstone_id", "capture_key", "created_at", "reason"}
    assert not (paths.capture.receipts / f"{receipt.receipt_id}.json").exists()
    assert not list(paths.capture.observations.glob("*.json"))
    assert not list(paths.capture.indexes.glob("*.json"))


def test_revision_suppression_tombstone_blocks_future_capture_registration(tmp_path: Path):
    paths, store, receipt, _observations = _populated(tmp_path)
    assert dispatch_write(paths, _request({"type": "revision", **_key().to_mapping()})).status == "accepted"
    result = store.register_extraction(_receipt())
    assert result.status == "suppressed"
    assert result.created is False
    assert not (paths.capture.receipts / f"{receipt.receipt_id}.json").exists()


def test_capture_forget_recovers_interrupted_primary_before_exact_retry(tmp_path: Path):
    paths, store, receipt, observations = _populated(tmp_path)
    receipt_path = paths.capture.receipts / f"{receipt.receipt_id}.json"
    original = receipt_path.read_bytes()
    transaction = CaptureForgetTransaction(paths)
    transaction.begin(1)
    transaction.write(receipt_path, b"{}", boundary="primary")
    retry = dispatch_write(paths, _request({"type": "observation", "observation_id": observations[0].observation_id}))
    assert retry.status == "accepted"
    assert not list(paths.capture.journals.glob("capture-forget-*.json"))
    assert receipt_path.read_bytes() != original
    assert not (paths.capture.observations / f"{observations[0].observation_id}.json").exists()
