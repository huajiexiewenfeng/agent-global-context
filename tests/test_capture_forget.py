from __future__ import annotations

import json
import shutil
import zipfile
from dataclasses import replace
from pathlib import Path

import pytest

from agc_runtime import capture_forget_service, capture_forget_transaction, managed_backup
from agc_runtime.admin_service import dispatch_admin
from agc_runtime.capture_contracts import CaptureKey, CaptureReceipt, CollectedObservation, SourceQuarantine, TokenUsage, observation_fingerprint_for, observation_id_for, receipt_id_for, tombstone_id_for
from agc_runtime.capture_store import CaptureStore
from agc_runtime.capture_forget_transaction import CaptureForgetTransaction
from agc_runtime.locking import capture_write_lock
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


@pytest.mark.parametrize(
    "payload",
    [
        {
            "action": "capture_forget",
            "authorization": "explicit_user_request",
            "target": {"type": "observation", "observation_id": "co_" + "g" * 64},
        },
        {
            "action": "capture_forget",
            "authorization": "explicit_user_request",
            "target": {"type": "revision", **_key().to_mapping()},
            "unexpected": True,
        },
    ],
)
def test_capture_forget_rejects_nonhex_ids_and_unknown_top_level_fields_before_mutation(
    tmp_path: Path, payload: dict
):
    paths, _store, _receipt_value, observations = _populated(tmp_path)
    observation_path = paths.capture.observations / f"{observations[0].observation_id}.json"
    before = observation_path.read_bytes()

    response = dispatch_write(paths, payload)

    assert response.status == "failed"
    assert response.error["code"] == "invalid_request"
    assert observation_path.read_bytes() == before


def test_observation_capture_forget_rewrites_backups_and_clears_receipt_hashes(tmp_path: Path):
    paths, store, receipt, observations = _populated(tmp_path)
    backup = dispatch_admin(paths, {"action": "backup"}).data["backup_path"]
    response = dispatch_write(paths, _request({"type": "observation", "observation_id": observations[0].observation_id}))
    assert response.status == "accepted", response
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


def test_observation_forget_scrubs_every_strictly_bound_runtime_copy(tmp_path: Path):
    paths, _store, receipt, observations = _populated(tmp_path)
    target = observations[0]
    copies = {
        paths.capture.staging / f"{target.observation_id}.json": target.to_mapping(),
        paths.capture.journals / f"{receipt.receipt_id}.json": {
            "schema_version": 1,
            "receipt_id": receipt.receipt_id,
            "observation_ids": [target.observation_id],
        },
        paths.capture.dirty / "observation-copy.json": {
            "schema_version": 1,
            "observation_id": target.observation_id,
        },
        paths.capture.scan_state / "scan-copy.json": {
            "schema_version": 1,
            "staged_observation_id": target.observation_id,
        },
        paths.capture.budgets / "budget-copy.json": {
            "schema_version": 1,
            "observation_ids": [target.observation_id],
        },
    }
    for path, value in copies.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")

    response = dispatch_write(
        paths,
        _request({"type": "observation", "observation_id": target.observation_id}),
    )

    assert response.status == "accepted"
    assert all(not path.exists() for path in copies)


def test_observation_forget_removes_only_exact_unparseable_staging_filename(tmp_path: Path):
    paths, _store, _receipt_value, observations = _populated(tmp_path)
    target = observations[0]
    exact = paths.capture.staging / f"{target.observation_id}.json"
    exact.write_bytes(b"\xff malformed staging without embedded id")
    unrelated = paths.capture.dirty / f"{target.observation_id}.json"
    unrelated.write_bytes(b"\xff unrelated dirty artifact")

    response = dispatch_write(
        paths,
        _request({"type": "observation", "observation_id": target.observation_id}),
    )

    assert response.status == "accepted", response
    assert not exact.exists()
    assert unrelated.read_bytes() == b"\xff unrelated dirty artifact"


def test_observation_forget_uses_backups_when_primary_observation_is_missing(tmp_path: Path):
    paths, store, receipt, observations = _populated(tmp_path)
    target = observations[0]
    backup = Path(dispatch_admin(paths, {"action": "backup"}).data["backup_path"])
    (paths.capture.observations / f"{target.observation_id}.json").unlink()

    response = dispatch_write(
        paths,
        _request({"type": "observation", "observation_id": target.observation_id}),
    )

    assert response.status == "accepted", response
    updated = store.read_receipt(receipt.receipt_id)
    assert updated.observation_count == 1
    manifest = json.loads(
        (paths.capture.indexes / f"{receipt.receipt_id}.json").read_text(encoding="utf-8")
    )
    assert target.observation_id not in manifest["observation_ids"]
    assert target.observation_id not in _archive_text(backup)


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


def test_revision_forget_fails_closed_on_foreign_observation_in_target_manifest(tmp_path: Path):
    paths, _store, receipt, observations = _populated(tmp_path)
    foreign_key = CaptureKey("synthetic_adapter", "3" * 64, "foreign-task", "foreign-revision")
    value = observations[0].to_mapping()
    value["source"] = {**foreign_key.to_mapping(), "locator": "sessions/foreign"}
    value["receipt_id"] = receipt_id_for(foreign_key)
    value["ordinal"] = 7
    value["observation_fingerprint"] = observation_fingerprint_for(value)
    value["observation_id"] = observation_id_for(
        value["receipt_id"], value["observation_fingerprint"]
    )
    foreign = CollectedObservation.from_mapping(value)
    foreign_path = paths.capture.observations / f"{foreign.observation_id}.json"
    foreign_path.write_text(json.dumps(foreign.to_mapping()), encoding="utf-8")
    manifest_path = paths.capture.indexes / f"{receipt.receipt_id}.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["observation_ids"].append(foreign.observation_id)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    receipt_path = paths.capture.receipts / f"{receipt.receipt_id}.json"
    receipt_value = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt_value["observation_count"] = 3
    receipt_path.write_text(json.dumps(receipt_value), encoding="utf-8")
    before = {
        foreign_path: foreign_path.read_bytes(),
        manifest_path: manifest_path.read_bytes(),
        receipt_path: receipt_path.read_bytes(),
    }

    response = dispatch_write(paths, _request({"type": "revision", **_key().to_mapping()}))

    assert response.status == "failed"
    assert {path: path.read_bytes() for path in before} == before


def test_revision_suppression_tombstone_blocks_future_capture_registration(tmp_path: Path):
    paths, store, receipt, _observations = _populated(tmp_path)
    assert dispatch_write(paths, _request({"type": "revision", **_key().to_mapping()})).status == "accepted"
    result = store.register_extraction(_receipt())
    assert result.status == "suppressed"
    assert result.created is False
    assert not (paths.capture.receipts / f"{receipt.receipt_id}.json").exists()


def test_capture_forget_fails_content_safely_while_capture_writer_is_active(tmp_path: Path):
    paths, _store, _receipt_value, observations = _populated(tmp_path)
    target = paths.capture.observations / f"{observations[0].observation_id}.json"
    before = target.read_bytes()

    with capture_write_lock(paths):
        response = dispatch_write(
            paths,
            _request({"type": "observation", "observation_id": observations[0].observation_id}),
        )

    assert response.status == "failed"
    assert response.error == {"code": "capture_forget_busy", "message": "Capture hard forget is busy"}
    assert target.read_bytes() == before


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


def _archive_text(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        return b"".join(archive.read(name) for name in archive.namelist()).decode("utf-8")


def test_revision_forget_scans_full_capture_tree_without_manifest_and_nested_backups(tmp_path: Path):
    paths, store, receipt, observations = _populated(tmp_path)
    backup = Path(dispatch_admin(paths, {"action": "backup"}).data["backup_path"])
    nested = paths.backups / "year" / "month" / "copy.zip"
    nested.parent.mkdir(parents=True)
    shutil.copy2(backup, nested)

    # The primary graph is intentionally incomplete. Hard forget must identify
    # the target from every strict Observation.source rather than an index.
    (paths.capture.indexes / f"{receipt.receipt_id}.json").unlink()
    orphan = _observation("Orphan target statement must also vanish.", 7)
    (paths.capture.observations / f"{orphan.observation_id}.json").write_text(
        json.dumps(orphan.to_mapping()), encoding="utf-8"
    )
    for directory, name in (
        (paths.capture.leases, f"{receipt.receipt_id}.json"),
        (paths.capture.dirty, "target.json"),
        (paths.capture.staging, "target.json"),
        (paths.capture.scan_state, "target.json"),
        (paths.capture.budgets, "target.json"),
    ):
        directory.mkdir(parents=True, exist_ok=True)
        (directory / name).write_text(
            json.dumps({"schema_version": 1, "capture_key": _key().to_mapping(), "receipt_id": receipt.receipt_id}),
            encoding="utf-8",
        )
    source_task = tmp_path / "source-task.json"
    source_task.write_text(json.dumps({"task_id": _key().task_id, "text": observations[0].statement}), encoding="utf-8")

    response = dispatch_write(paths, _request({"type": "revision", **_key().to_mapping()}))

    assert response.status == "accepted", response
    tombstone = paths.capture.tombstones / f"{tombstone_id_for(_key())}.json"
    assert tombstone.is_file()
    needles = (receipt.receipt_id, observations[0].observation_id, orphan.observation_id,
               observations[0].statement, orphan.statement, "a" * 64, "b" * 64)
    for path in paths.capture.root.rglob("*"):
        if path.is_file() and path != tombstone:
            text = path.read_bytes().decode("utf-8", errors="ignore")
            assert all(needle not in text for needle in needles), path
    for archive in paths.backups.rglob("*.zip"):
        text = _archive_text(archive)
        assert all(needle not in text for needle in needles), archive
    assert source_task.read_text(encoding="utf-8") == json.dumps(
        {"task_id": _key().task_id, "text": observations[0].statement}
    )
    assert store.register_extraction(_receipt()).status == "suppressed"


def test_observation_forget_reaches_zero_across_all_nested_backups_and_repeat_is_stable(tmp_path: Path):
    paths, store, receipt, observations = _populated(tmp_path)
    first_backup = Path(dispatch_admin(paths, {"action": "backup"}).data["backup_path"])
    nested = paths.backups / "nested" / "deeper" / "second.zip"
    nested.parent.mkdir(parents=True)
    shutil.copy2(first_backup, nested)

    first = dispatch_write(paths, _request({"type": "observation", "observation_id": observations[0].observation_id}))
    second = dispatch_write(paths, _request({"type": "observation", "observation_id": observations[1].observation_id}))

    assert first.status == second.status == "accepted"
    updated = store.read_receipt(receipt.receipt_id)
    assert updated.observation_count == 0
    assert updated.forgotten_observation_count == 2
    assert updated.zero_reason == "user_forget"
    assert updated.redacted_by_forget is True
    assert updated.source_fingerprint is updated.source_hash_schema_version is None
    assert updated.capsule_hash is updated.capsule_schema_version is None
    assert list(store.iter_visible_observations()) == []
    manifest = json.loads((paths.capture.indexes / f"{receipt.receipt_id}.json").read_text(encoding="utf-8"))
    assert manifest["observation_ids"] == []
    for archive in paths.backups.rglob("*.zip"):
        text = _archive_text(archive)
        for observation in observations:
            assert observation.observation_id not in text
            assert observation.statement not in text
        managed_backup_entries, managed_backup_manifest = managed_backup.read_verified_archive(archive)
        assert managed_backup_manifest["schema_version"] == 2
        assert managed_backup_entries
    before = {path: path.read_bytes() for path in paths.capture.root.rglob("*") if path.is_file()}
    repeat = dispatch_write(paths, _request({"type": "observation", "observation_id": observations[1].observation_id}))
    after = {path: path.read_bytes() for path in paths.capture.root.rglob("*") if path.is_file()}
    assert repeat.status == "accepted"
    assert before == after


def test_foreign_forget_journal_target_is_quarantined_without_mutating_config(tmp_path: Path):
    paths, _store, _receipt_value, observations = _populated(tmp_path)
    token = "f" * 32
    images = paths.capture.root / "forget-staging" / f"capture-forget-{token}"
    images.mkdir(parents=True)
    (images / "0001.before").write_bytes(b"attacker replacement")
    journal = paths.capture.journals / f"capture-forget-{token}.json"
    journal.write_text(
        json.dumps({
            "schema_version": 1,
            "operation": "capture_forget",
            "state": "active",
            "operation_count": 1,
            "before_images": [
                {"target": "config.yaml", "image": "0001.before", "existed": True}
            ],
        }),
        encoding="utf-8",
    )
    before = (paths.root / "config.yaml").read_bytes()

    response = dispatch_write(
        paths,
        _request({"type": "observation", "observation_id": observations[0].observation_id}),
    )

    assert response.error["code"] == "invalid_capture_forget_journal"
    assert (paths.root / "config.yaml").read_bytes() == before
    assert not journal.exists()
    records = list(paths.capture.quarantines.glob("invalid-forget-journal-*.json"))
    assert len(records) == 1
    quarantine = SourceQuarantine.from_mapping(
        json.loads(records[0].read_text(encoding="utf-8"))
    )
    assert quarantine.code == "corrupt_capture_artifact"
    backup = dispatch_admin(paths, {"action": "backup"})
    assert backup.status == "accepted"
    managed_backup.read_verified_archive(Path(backup.data["backup_path"]))


def test_recovery_validates_all_entries_and_images_before_first_mutation(tmp_path: Path):
    paths, _store, receipt, _observations = _populated(tmp_path)
    first = paths.capture.dirty / "first.json"
    second = paths.capture.dirty / "second.json"
    first.write_bytes(b"first-before")
    second.write_bytes(b"second-before")
    transaction = CaptureForgetTransaction(paths)
    transaction.begin(2)
    transaction.write(first, b"first-interrupted", boundary="primary")
    transaction.write(second, b"second-interrupted", boundary="primary")
    journal = json.loads(transaction._journal.read_text(encoding="utf-8"))
    journal["before_images"][0]["image"] = "missing.before"
    transaction._journal.write_text(json.dumps(journal), encoding="utf-8")

    with pytest.raises(ValueError, match="invalid Capture forget journal"):
        CaptureForgetTransaction.recover(paths)

    assert first.read_bytes() == b"first-interrupted"
    assert second.read_bytes() == b"second-interrupted"


@pytest.mark.parametrize("recorded_count", [0, 1])
def test_recovery_rolls_back_canonical_recorded_crash_prefix(
    tmp_path: Path, recorded_count: int
):
    paths, _store, _receipt_value, _observations = _populated(tmp_path)
    target = paths.capture.dirty / "prefix.json"
    target.write_bytes(b"prefix-before")
    transaction = CaptureForgetTransaction(paths)
    transaction.begin(3)
    if recorded_count:
        transaction.write(target, b"prefix-interrupted", boundary="primary")

    recovered = CaptureForgetTransaction.recover(paths)

    assert recovered == 1
    assert target.read_bytes() == b"prefix-before"
    assert not transaction._journal.exists()
    assert not transaction._images.exists()


def test_recovery_rejects_before_image_overflow_without_mutating_target(tmp_path: Path):
    paths, _store, _receipt_value, _observations = _populated(tmp_path)
    target = paths.capture.dirty / "overflow.json"
    target.write_bytes(b"overflow-before")
    transaction = CaptureForgetTransaction(paths)
    transaction.begin(0)
    transaction.write(target, b"overflow-interrupted", boundary="primary")

    with pytest.raises(ValueError, match="invalid Capture forget journal"):
        CaptureForgetTransaction.recover(paths)

    assert target.read_bytes() == b"overflow-interrupted"


def test_corrupt_recovery_keeps_marker_when_dedicated_staging_cleanup_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    paths, _store, _receipt_value, _observations = _populated(tmp_path)
    token = "e" * 32
    images = paths.capture.root / "forget-staging" / f"capture-forget-{token}"
    images.mkdir(parents=True)
    (images / "0001.before").write_bytes(b"before")
    journal = paths.capture.journals / f"capture-forget-{token}.json"
    journal.write_text(
        json.dumps({
            "schema_version": 1,
            "operation": "capture_forget",
            "state": "active",
            "operation_count": 1,
            "before_images": [
                {"target": "config.yaml", "image": "0001.before", "existed": True}
            ],
        }),
        encoding="utf-8",
    )
    original_rmtree = shutil.rmtree

    def fail_without_removing(path, *args, **kwargs):
        if Path(path) == images:
            if kwargs.get("ignore_errors"):
                return None
            raise OSError("injected corrupt staging cleanup failure")
        return original_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(
        "agc_runtime.capture_forget_transaction.shutil.rmtree",
        fail_without_removing,
    )

    with pytest.raises(OSError, match="injected corrupt staging cleanup failure"):
        CaptureForgetTransaction.recover(paths)

    assert journal.is_file()
    assert images.is_dir()
    assert not list(paths.capture.quarantines.glob("invalid-forget-journal-*.json"))


def test_capture_transaction_deletes_use_durable_unlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    paths, _store, _receipt_value, _observations = _populated(tmp_path)
    target = paths.capture.dirty / "durable-delete.json"
    target.write_bytes(b"before")
    calls: list[Path] = []
    original = capture_forget_transaction.safe_unlink

    def record(path: Path) -> None:
        calls.append(path)
        original(path)

    monkeypatch.setattr(capture_forget_transaction, "safe_unlink", record)
    transaction = CaptureForgetTransaction(paths)
    transaction.begin(1)
    transaction.delete(target, boundary="primary")

    assert target in calls
    transaction.rollback()


def test_forget_commit_keeps_journal_when_staging_cleanup_fails(tmp_path: Path, monkeypatch):
    paths, _store, _receipt_value, _observations = _populated(tmp_path)
    transaction = CaptureForgetTransaction(paths)
    transaction.begin(0)
    journal = transaction._journal
    images = transaction._images

    def fail_cleanup(path, *args, **kwargs):
        if Path(path) == images:
            raise OSError("injected cleanup failure")
        return shutil.rmtree(path, *args, **kwargs)

    monkeypatch.setattr("agc_runtime.capture_forget_transaction.shutil.rmtree", fail_cleanup)

    with pytest.raises(OSError, match="injected cleanup failure"):
        transaction.commit()

    assert journal.is_file()
    assert images.is_dir()


@pytest.mark.parametrize(
    ("boundary", "occurrence"),
    [
        ("before:primary", 1),
        ("after:primary", 1),
        ("before:backup", 1),
        ("after:backup", 1),
        ("before:backup", 2),
        ("after:backup", 2),
        ("before:commit", 1),
    ],
)
def test_forget_transaction_failure_boundaries_rollback_byte_exact(
    tmp_path: Path, boundary: str, occurrence: int
):
    paths, _store, receipt, observations = _populated(tmp_path)
    backup = Path(dispatch_admin(paths, {"action": "backup"}).data["backup_path"])
    nested = paths.backups / "nested" / "second.zip"
    nested.parent.mkdir(parents=True)
    shutil.copy2(backup, nested)
    primary = paths.capture.observations / f"{observations[0].observation_id}.json"
    before = {path: path.read_bytes() for path in (primary, backup, nested)}
    counts: dict[str, int] = {}

    def inject(name: str) -> None:
        counts[name] = counts.get(name, 0) + 1
        if name == boundary and counts[name] == occurrence:
            raise RuntimeError("injected transaction failure")

    transaction = CaptureForgetTransaction(paths, point=inject)
    with pytest.raises(RuntimeError, match="injected transaction failure"):
        try:
            transaction.begin(3)
            transaction.write(primary, b"changed primary", boundary="primary")
            transaction.write(backup, b"changed backup one", boundary="backup")
            transaction.write(nested, b"changed backup two", boundary="backup")
            transaction.commit()
        except Exception:
            transaction.rollback()
            raise

    assert {path: path.read_bytes() for path in before} == before
    assert not list(paths.capture.journals.glob("capture-forget-*.json"))


def test_after_cleanup_is_a_committed_observation_point(tmp_path: Path):
    paths, _store, _receipt_value, observations = _populated(tmp_path)
    primary = paths.capture.observations / f"{observations[0].observation_id}.json"

    def inject(name: str) -> None:
        if name == "after:cleanup":
            raise RuntimeError("post-commit observer failure")

    transaction = CaptureForgetTransaction(paths, point=inject)
    transaction.begin(1)
    transaction.write(primary, b"committed bytes", boundary="primary")
    transaction.commit()

    assert primary.read_bytes() == b"committed bytes"
    assert not transaction._journal.exists()
    assert not transaction._images.exists()


def test_repeated_revision_forget_does_not_churn_tombstone_or_backups(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    paths, _store, _receipt_value, _observations = _populated(tmp_path)
    dispatch_admin(paths, {"action": "backup"})
    times = iter(
        (
            "2026-08-13T12:00:00Z",
            "2026-08-13T12:00:01Z",
            "2026-08-13T12:00:02Z",
            "2026-08-13T12:00:03Z",
        )
    )
    monkeypatch.setattr(capture_forget_service, "_now", lambda: next(times))
    first = dispatch_write(paths, _request({"type": "revision", **_key().to_mapping()}))
    assert first.status == "accepted"
    before = {
        path: path.read_bytes()
        for path in (*paths.capture.root.rglob("*"), *paths.backups.rglob("*.zip"))
        if path.is_file()
    }

    second = dispatch_write(paths, _request({"type": "revision", **_key().to_mapping()}))

    assert second.status == "accepted"
    assert {path: path.read_bytes() for path in before} == before
