from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import pytest

import agc_runtime.capture_store as capture_store_module
from agc_runtime.capture_contracts import (
    CAPTURE_SCHEMA_VERSION,
    CaptureKey,
    CaptureLease,
    CaptureReceipt,
    CollectedObservation,
    RevisionRef,
    TokenUsage,
    observation_fingerprint_for,
    observation_id_for,
    receipt_id_for,
)
from agc_runtime.capture_store import CaptureStore, ReceiptTransitionPatch
from agc_runtime.capture_transaction import atomic_write_json
from agc_runtime.locking import capture_write_lock
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


def _revision(
    *,
    task_id: str = "task-1",
    revision_id: str = "revision-1",
    completed_at: str = "2026-08-12T12:00:00Z",
) -> RevisionRef:
    key = CaptureKey("synthetic_adapter", SOURCE_ROOT, task_id, revision_id)
    return RevisionRef.from_mapping(
        {
            "schema_version": CAPTURE_SCHEMA_VERSION,
            "capture_key": key.to_mapping(),
            "rollout_anchor_id": "rollout-1",
            "completed_at": completed_at,
            "locator": "sessions/synthetic.jsonl",
            "identity_quality": "session_id",
            "adapter_version": "1",
            "source_schema_version": "1",
        }
    )


def _freeze(
    store: CaptureStore,
    revisions: tuple[RevisionRef, ...],
    *,
    started_at: str,
) -> None:
    from datetime import datetime, timedelta
    from agc_runtime.capture_source import SourceBindingKey, TimeWindow

    end = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
    start = (end - timedelta(days=7)).isoformat().replace("+00:00", "Z")
    store.freeze_census(
        binding=SourceBindingKey(1, "synthetic_adapter", SOURCE_ROOT),
        window=TimeWindow(1, start, started_at),
        started_at=started_at,
        revisions=revisions,
    )


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


@pytest.mark.parametrize(
    ("damage", "expected_codes"),
    [
        ("bad_json", {"invalid_ledger"}),
        ("bad_filename", {"invalid_ledger", "missing_ledger"}),
        ("missing_ledger", {"missing_ledger"}),
        ("missing_receipt", {"orphan_ledger"}),
        ("wrong_status", {"ledger_receipt_mismatch"}),
        ("foreign_reference", {"orphan_ledger", "missing_ledger"}),
    ],
)
def test_locked_snapshot_validates_ledger_receipt_graph(
    tmp_path: Path, damage: str, expected_codes: set[str]
):
    store = _store(tmp_path)
    receipt = _receipt(status="discovered")
    store.register_extraction(receipt)
    ledger_path = store.capture.ledger / f"{receipt.receipt_id}.json"
    receipt_path = store.capture.receipts / f"{receipt.receipt_id}.json"
    if damage == "bad_json":
        ledger_path.write_text('{"private":"must-not-leak"}\n', encoding="utf-8")
    elif damage == "bad_filename":
        ledger_path.rename(store.capture.ledger / "not-a-ledger.json")
    elif damage == "missing_ledger":
        ledger_path.unlink()
    elif damage == "missing_receipt":
        receipt_path.unlink()
    elif damage == "wrong_status":
        value = json.loads(ledger_path.read_text(encoding="utf-8"))
        value["status"] = "queued"
        atomic_write_json(ledger_path, value)
    elif damage == "foreign_reference":
        value = json.loads(ledger_path.read_text(encoding="utf-8"))
        value["capture_key"]["task_id"] = "foreign-task"
        foreign_key = CaptureKey.from_mapping(value["capture_key"])
        value["receipt_id"] = receipt_id_for(foreign_key)
        foreign_path = store.capture.ledger / f"{value['receipt_id']}.json"
        atomic_write_json(foreign_path, value)
        ledger_path.unlink()

    snapshot = store.read_snapshot()

    codes = {item.code for item in snapshot.diagnostics}
    assert expected_codes <= codes
    assert "private" not in json.dumps(
        [item.to_mapping() for item in snapshot.diagnostics]
    )


def test_locked_snapshot_accepts_matching_discovered_receipt_and_ledger(tmp_path: Path):
    store = _store(tmp_path)
    store.register_extraction(_receipt(status="discovered"))

    snapshot = store.read_snapshot()

    assert snapshot.integrity_state == "healthy"
    assert len(snapshot.receipts) == 1


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


def test_fencing_epoch_rejects_rolled_back_lease_file_and_forged_leases(tmp_path: Path):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    store = CaptureStore(paths, clock=lambda: UTC)
    receipt = _receipt()
    store.register_extraction(receipt)
    first = store.acquire_lease(_key(), owner_id="worker-a", now=UTC, ttl_seconds=1)
    assert first is not None
    second = store.acquire_lease(_key(), owner_id="worker-b", now="2026-08-13T12:00:02Z", ttl_seconds=60)
    assert second is not None and second.fencing_token == 2
    atomic_write_json(paths.capture.leases / f"{receipt.receipt_id}.json", first.to_mapping())
    restarted = CaptureStore(paths, clock=lambda: UTC)
    for forged in (
        first,
        replace(second, owner_id="forged-owner"),
        replace(second, capture_key=CaptureKey("synthetic_adapter", SOURCE_ROOT, "other", "revision-1")),
    ):
        with pytest.raises(ValueError, match="lease|epoch"):
            restarted.commit_extraction(forged, (), _complete_receipt(receipt, 0))
    assert restarted.acquire_lease(_key(), owner_id="worker-c", now="2026-08-13T12:01:03Z", ttl_seconds=60).fencing_token == 3


def test_complete_visibility_requires_immutable_manifest_and_ignores_extra_files(tmp_path: Path):
    store = _store(tmp_path)
    receipt = _receipt()
    store.register_extraction(receipt)
    lease = store.acquire_lease(_key(), owner_id="worker", now=UTC, ttl_seconds=60)
    assert lease is not None
    observation = _observation("User needs a manifest binding.", 0)
    store.commit_extraction(lease, (observation,), _complete_receipt(receipt, 1))
    manifest = store.capture.indexes / f"{receipt.receipt_id}.json"
    assert manifest.is_file()
    assert list(__import__("json").loads(manifest.read_text(encoding="utf-8"))) == ["observation_ids", "receipt_id", "schema_version"]
    extra = _observation("User creates an unrelated synthetic signal.", 1)
    atomic_write_json(store.capture.observations / f"{extra.observation_id}.json", extra.to_mapping())
    assert store.visible_observations(receipt.receipt_id) == (observation,)
    manifest.unlink()
    assert store.visible_observations(receipt.receipt_id) == ()


def test_commit_revalidates_exact_batch_duplicate_count_and_limit(tmp_path: Path):
    store = _store(tmp_path)
    receipt = _receipt()
    store.register_extraction(receipt)
    lease = store.acquire_lease(_key(), owner_id="worker", now=UTC, ttl_seconds=60)
    assert lease is not None
    same = _observation("User deduplicates within one batch.", 0)
    terminal = _complete_receipt(receipt, 1)
    terminal = CaptureReceipt.from_mapping({**terminal.to_mapping(), "duplicate_suppression_count": 0})
    with pytest.raises(ValueError, match="duplicate"):
        store.commit_extraction(lease, (same, same), terminal)
    many = tuple(_observation(f"User synthetic signal number {index}.", index) for index in range(9))
    with pytest.raises(ValueError, match="at most 8"):
        store.commit_extraction(lease, many, _complete_receipt(receipt, 8))


def test_transition_validates_expected_status_reopen_and_immutable_metadata(tmp_path: Path):
    store = _store(tmp_path)
    receipt = _receipt()
    store.register_extraction(receipt)
    lease = store.acquire_lease(_key(), owner_id="worker", now=UTC, ttl_seconds=60)
    assert lease is not None
    with pytest.raises(ValueError, match="expected"):
        store.transition(lease, expected=frozenset({"queued"}), target="retryable", patch=ReceiptTransitionPatch())
    with pytest.raises(ValueError, match="illegal"):
        store.transition(lease, expected=frozenset({"extracting"}), target="queued", patch=ReceiptTransitionPatch())
    with pytest.raises(ValueError, match="immutable"):
        store.transition(lease, expected=frozenset({"extracting"}), target="retryable", patch=ReceiptTransitionPatch(source_fingerprint="d" * 64))


def test_transition_writes_valid_retryable_and_authorized_reopen(tmp_path: Path):
    store = _store(tmp_path)
    receipt = _receipt()
    store.register_extraction(receipt)
    lease = store.acquire_lease(_key(), owner_id="worker", now=UTC, ttl_seconds=60)
    assert lease is not None
    retryable = store.transition(
        lease, expected=frozenset({"extracting"}), target="retryable",
        patch=ReceiptTransitionPatch(
            updated_at="2026-08-13T12:00:01Z", next_retry_at="2026-08-13T12:01:00Z",
            sanitized_error=__import__("agc_runtime.capture_contracts", fromlist=["SanitizedError"]).SanitizedError("transaction", "interrupted", True),
        ),
    )
    failed = store.transition(
        lease, expected=frozenset({"retryable"}), target="failed",
        patch=ReceiptTransitionPatch(
            sanitized_error=__import__("agc_runtime.capture_contracts", fromlist=["SanitizedError"]).SanitizedError("transaction", "interrupted", False),
        ),
    )
    reopened = store.transition(
        lease, expected=frozenset({"failed"}), target="queued",
        patch=ReceiptTransitionPatch(reopen_reason="explicit_retry"),
    )
    assert retryable.status == "retryable" and failed.status == "failed"
    assert reopened.status == "queued" and reopened.sanitized_error is None


def test_store_layout_keeps_task2_schema_marker_text_contract(tmp_path: Path):
    store = _store(tmp_path)
    store.ensure_layout()
    assert store.capture.schema_version.read_bytes() == b"1\n"


def test_corrupt_capture_lock_fails_closed(tmp_path: Path):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    paths.capture.root.mkdir(parents=True)
    (paths.capture.root / ".writer.lock").write_bytes(b"not-json\n")
    with pytest.raises(RuntimeError, match="active Capture"):
        with capture_write_lock(paths):
            pass


def test_rebuild_census_catalog_deduplicates_overlapping_frozen_runs(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    revision = _revision()
    _freeze(store, (revision,), started_at="2026-08-13T11:00:00Z")
    _freeze(store, (revision,), started_at="2026-08-13T12:00:00Z")

    revisions = store.rebuild_census_catalog()

    active = json.loads(
        (store.capture.census_catalog / "active.json").read_text(encoding="utf-8")
    )
    generation = (
        store.capture.census_catalog / "g" / active["catalog_id"]
    )
    assert revisions == (revision,)
    assert sorted(path.name for path in (generation / "r").iterdir()) == [
        f"{receipt_id_for(revision.key)}.json"
    ]
    manifest = json.loads((generation / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["catalog_schema_version"] == "census-catalog-v1"
    assert manifest["revision_count"] == 1


def test_rebuild_census_catalog_rejects_conflicting_revision_without_publish(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    _freeze(store, (_revision(),), started_at="2026-08-13T11:00:00Z")
    _freeze(
        store,
        (_revision(completed_at="2026-08-12T12:00:01Z"),),
        started_at="2026-08-13T12:00:00Z",
    )

    with pytest.raises(ValueError, match="revision_metadata_conflict"):
        store.rebuild_census_catalog()

    assert not (store.capture.census_catalog / "active.json").exists()


def test_hot_catalog_snapshot_does_not_decode_frozen_members(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = _store(tmp_path)
    revision = _revision()
    _freeze(store, (revision,), started_at="2026-08-13T12:00:00Z")
    store.rebuild_census_catalog()
    member_reads: list[Path] = []
    original = capture_store_module.read_json

    def counted(path: Path):
        if path.parent.name == "members":
            member_reads.append(path)
        return original(path)

    monkeypatch.setattr(capture_store_module, "read_json", counted)

    snapshot = store.read_snapshot()

    assert snapshot.census == (revision,)
    assert member_reads == []


def test_hot_catalog_rebuilds_after_new_frozen_run(tmp_path: Path) -> None:
    store = _store(tmp_path)
    first = _revision()
    second = _revision(task_id="task-2", revision_id="revision-2")
    _freeze(store, (first,), started_at="2026-08-13T11:00:00Z")
    store.rebuild_census_catalog()
    before = json.loads(
        (store.capture.census_catalog / "active.json").read_text(encoding="utf-8")
    )["catalog_id"]
    _freeze(store, (first, second), started_at="2026-08-13T12:00:00Z")

    snapshot = store.read_snapshot()

    after = json.loads(
        (store.capture.census_catalog / "active.json").read_text(encoding="utf-8")
    )["catalog_id"]
    assert set(snapshot.census) == {first, second}
    assert after != before


def test_freeze_census_refreshes_valid_catalog_without_old_member_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = _store(tmp_path)
    first = _revision()
    second = _revision(task_id="task-2", revision_id="revision-2")
    _freeze(store, (first,), started_at="2026-08-13T11:00:00Z")
    store.rebuild_census_catalog()
    before = json.loads(
        (store.capture.census_catalog / "active.json").read_text(encoding="utf-8")
    )["catalog_id"]
    member_reads: list[Path] = []
    original = capture_store_module.read_json

    def counted(path: Path):
        if path.parent.name == "members":
            member_reads.append(path)
        return original(path)

    monkeypatch.setattr(capture_store_module, "read_json", counted)

    _freeze(store, (first, second), started_at="2026-08-13T12:00:00Z")

    after = json.loads(
        (store.capture.census_catalog / "active.json").read_text(encoding="utf-8")
    )["catalog_id"]
    assert after != before
    assert member_reads == []
    assert set(store.ensure_census_catalog()) == {first, second}


def test_hot_catalog_ignores_interrupted_generation_stage(tmp_path: Path) -> None:
    store = _store(tmp_path)
    revision = _revision()
    _freeze(store, (revision,), started_at="2026-08-13T12:00:00Z")
    stage = store.capture.census_catalog / "g" / ".interrupted.tmp"
    stage.mkdir(parents=True)
    (stage / "private.bin").write_bytes(b"not-catalog-data")

    snapshot = store.read_snapshot()

    assert snapshot.census == (revision,)
    assert snapshot.integrity_state == "healthy"
