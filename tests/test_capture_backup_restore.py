from __future__ import annotations

import json
import io
import zipfile
from dataclasses import replace
from pathlib import Path

from agc_runtime.admin_service import dispatch_admin
from agc_runtime.capture_contracts import CaptureKey, CaptureReceipt, CollectedObservation, TokenUsage, observation_fingerprint_for, observation_id_for, receipt_id_for
from agc_runtime.capture_store import CaptureStore
from agc_runtime.paths import MemoryPaths


UTC = "2026-08-13T12:00:00Z"
ROOT_ID = "1" * 64


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


def _observation(statement: str) -> CollectedObservation:
    key = _key()
    value = {
        "schema_version": 1, "observation_id": "co_" + "0" * 64,
        "receipt_id": receipt_id_for(key), "source": {**key.to_mapping(), "locator": "sessions/synthetic"},
        "ordinal": 0, "observation_fingerprint": "0" * 64, "statement": statement,
        "assertion": {"subject": "user", "mode": "direct", "modality": "asserted"},
        "primary_category": "work", "taxonomy_version": "taxonomy-v1", "kind": "preference",
        "scopes": ["testing"], "project_scope": None, "confidence": "observed", "sensitivity": "normal",
        "signal_type": "decision_or_constraint", "observed_at": UTC, "captured_at": UTC,
        "extractor_version": "1", "processing_state": "collected",
    }
    value["observation_fingerprint"] = observation_fingerprint_for(value)
    value["observation_id"] = observation_id_for(value["receipt_id"], value["observation_fingerprint"])
    return CollectedObservation.from_mapping(value)


def _complete(receipt: CaptureReceipt) -> CaptureReceipt:
    return CaptureReceipt.from_mapping({**receipt.to_mapping(), "status": "complete", "observation_count": 1,
        "filtered_counts": {"safety": 0, "policy": 0, "over_limit": 0}, "duplicate_suppression_count": 0,
        "zero_reason": None})


def _populated(tmp_path: Path) -> tuple[MemoryPaths, CaptureStore, CollectedObservation]:
    paths = MemoryPaths.from_root(tmp_path / "memory")
    assert dispatch_admin(paths, {"action": "init"}).status == "accepted"
    store = CaptureStore(paths, clock=lambda: UTC)
    receipt = _receipt()
    observation = _observation("Task 5 must preserve only safe Capture facts.")
    store.register_extraction(receipt)
    lease = store.acquire_lease(_key(), owner_id="worker", now=UTC, ttl_seconds=60)
    assert lease is not None
    store.commit_extraction(lease, (observation,), _complete(receipt))
    return paths, store, observation


def test_capture_backup_round_trip_is_allowlisted_and_keeps_recall_isolated(tmp_path: Path):
    paths, store, observation = _populated(tmp_path)
    (paths.capture.dirty / "raw-task.json").write_text("secret transcript", encoding="utf-8")
    (paths.capture.journals / "active.json").write_text("{}", encoding="utf-8")
    (paths.capture.leases / "lease.json").write_text("{}", encoding="utf-8")
    backup = dispatch_admin(paths, {"action": "backup"})

    assert backup.status == "accepted"
    assert backup.data["manifest"]["capture_schema_version"] == 1
    with zipfile.ZipFile(backup.data["backup_path"]) as archive:
        names = set(archive.namelist())
    assert f".runtime/capture/observations/{observation.observation_id}.json" in names
    assert ".runtime/capture/dirty/raw-task.json" not in names
    assert ".runtime/capture/journals/active.json" not in names
    assert ".runtime/capture/leases/lease.json" not in names
    assert ".runtime/capture/cursor-hmac-key" not in names

    paths.capture.observations.joinpath(f"{observation.observation_id}.json").unlink()
    restored = dispatch_admin(paths, {"action": "restore", "backup_path": backup.data["backup_path"]})
    assert restored.status == "accepted"
    assert [item.observation_id for item in store.iter_visible_observations()] == [observation.observation_id]
    assert not list(paths.memories.rglob("*.md"))


def test_restore_rejects_unknown_capture_versions_before_mutation(tmp_path: Path):
    paths, _store, _observation_value = _populated(tmp_path)
    backup = dispatch_admin(paths, {"action": "backup"}).data["backup_path"]
    before = paths.capture.schema_version.read_bytes()
    with zipfile.ZipFile(backup) as archive:
        entries = {name: archive.read(name) for name in archive.namelist() if name != "manifest.json"}
        manifest = json.loads(archive.read("manifest.json"))
    manifest["capture_schema_version"] = 999
    with zipfile.ZipFile(backup, "w") as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
        archive.writestr("manifest.json", json.dumps(manifest))
    response = dispatch_admin(paths, {"action": "restore", "backup_path": backup})
    assert response.error["code"] == "backup_verification_failed"
    assert paths.capture.schema_version.read_bytes() == before
