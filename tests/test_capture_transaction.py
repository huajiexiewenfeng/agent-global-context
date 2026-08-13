from __future__ import annotations

from pathlib import Path

import pytest

from agc_runtime.capture_store import CaptureStore
from agc_runtime.capture_transaction import atomic_write_json
from tests.test_capture_store import _complete_receipt, _key, _observation, _receipt
from agc_runtime.capture_contracts import CaptureKey, CaptureReceipt, CollectedObservation, observation_id_for, receipt_id_for
from agc_runtime.paths import MemoryPaths


@pytest.mark.parametrize(
    "crash_point",
    [
        f"{side}:{point}"
        for point in ("journal", "stage", "observation:0", "observation:1", "ledger", "receipt", "cleanup")
        for side in ("before", "after")
    ],
)
def test_ac_09_crash_recovery_never_exposes_partial_or_duplicate_batches(
    tmp_path: Path, crash_point: str
):
    store = CaptureStore(
        MemoryPaths.from_root(tmp_path / "memory"), crash_at=crash_point,
        clock=lambda: "2026-08-13T12:00:00Z",
    )
    receipt = _receipt()
    store.register_extraction(receipt)
    lease = store.acquire_lease(_key(), owner_id="worker", now="2026-08-13T12:00:00Z", ttl_seconds=60)
    assert lease is not None
    observations = (_observation("User prefers crash-safe commits.", 0), _observation("User values retryable transactions.", 1))
    with pytest.raises(RuntimeError, match="injected crash"):
        store.commit_extraction(lease, observations, _complete_receipt(receipt, 2))

    recovered = CaptureStore(MemoryPaths.from_root(tmp_path / "memory"))
    report = recovered.recover_transactions(now="2026-08-13T12:01:30Z")
    visible = recovered.visible_observations(receipt.receipt_id)
    current = recovered.read_receipt(receipt.receipt_id)
    assert len(visible) in {0, 2}
    assert (current.status == "complete") == (len(visible) == 2)
    if not visible:
        assert current.status == "retryable"
    assert report.orphan_count == report.duplicate_count == 0
    assert report.partial_count in {0, 1}


def test_recovery_fails_closed_for_unsafe_journal_name_and_never_deletes_outside_capture(tmp_path: Path):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    store = CaptureStore(paths, clock=lambda: "2026-08-13T12:00:00Z")
    store.ensure_layout()
    outside = tmp_path / "outside.json"
    atomic_write_json(outside, {"safe": "synthetic"})
    atomic_write_json(paths.capture.journals / "not-a-receipt.json", {"observation_ids": ["../outside"]})
    report = store.recover_transactions(now="2026-08-13T12:01:00Z")
    assert outside.is_file()
    assert report.corrupt_count >= 1
    assert not (paths.capture.journals / "not-a-receipt.json").exists()
    assert list(paths.capture.quarantines.glob("corrupt-*.json"))


def test_recovery_audits_orphans_and_is_idempotent(tmp_path: Path):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    store = CaptureStore(paths, clock=lambda: "2026-08-13T12:00:00Z")
    store.ensure_layout()
    orphan = _observation("User has an orphaned synthetic signal.", 0)
    atomic_write_json(paths.capture.observations / f"{orphan.observation_id}.json", orphan.to_mapping())
    first = store.recover_transactions(now="2026-08-13T12:01:00Z")
    assert first.orphan_count == 1
    assert not (paths.capture.observations / f"{orphan.observation_id}.json").exists()
    second = store.recover_transactions(now="2026-08-13T12:02:00Z")
    assert second.recovered_count == second.orphan_count == second.partial_count == second.duplicate_count == second.corrupt_count == 0


def _foreign_pair():
    key = CaptureKey("synthetic_adapter", "2" * 64, "task-b", "revision-b")
    receipt = _receipt()
    receipt = CaptureReceipt.from_mapping({
        **receipt.to_mapping(), **key.to_mapping(), "receipt_id": receipt_id_for(key),
    })
    observation = _observation("User owns a separate synthetic receipt.", 0)
    mapping = observation.to_mapping()
    mapping.update({"receipt_id": receipt.receipt_id, "source": {**key.to_mapping(), "locator": "sessions/foreign"}})
    mapping["observation_id"] = observation_id_for(receipt.receipt_id, mapping["observation_fingerprint"])
    return receipt, CollectedObservation.from_mapping(mapping)


def test_recovery_never_deletes_foreign_observation_named_by_another_journal_or_stage(tmp_path: Path):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    store = CaptureStore(paths, clock=lambda: "2026-08-13T12:00:00Z")
    owner_receipt = _receipt()
    store.register_extraction(owner_receipt)
    owner_lease = store.acquire_lease(_key(), owner_id="owner", now="2026-08-13T12:00:00Z", ttl_seconds=60)
    assert owner_lease is not None
    owner_observation = _observation("User owns the complete batch.", 0)
    store.commit_extraction(owner_lease, (owner_observation,), _complete_receipt(owner_receipt, 1))
    foreign_receipt, foreign_observation = _foreign_pair()
    store.register_extraction(foreign_receipt)
    payload = {"schema_version": 1, "receipt_id": foreign_receipt.receipt_id, "observation_ids": [owner_observation.observation_id]}
    atomic_write_json(paths.capture.journals / f"{foreign_receipt.receipt_id}.json", payload)
    atomic_write_json(paths.capture.staging / f"{owner_observation.observation_id}.json", owner_observation.to_mapping())

    report = store.recover_transactions(now="2026-08-13T12:01:00Z")

    assert report.corrupt_count >= 1
    assert store.read_receipt(owner_receipt.receipt_id).status == "complete"
    assert store.visible_observations(owner_receipt.receipt_id) == (owner_observation,)
    assert (paths.capture.observations / f"{owner_observation.observation_id}.json").is_file()
    assert not (paths.capture.staging / f"{owner_observation.observation_id}.json").exists()
    assert store.read_receipt(foreign_receipt.receipt_id).status in {"extracting", "retryable"}
    assert store.recover_transactions(now="2026-08-13T12:02:00Z").orphan_count == 0


def test_recovery_counts_conflicting_journal_binding_as_duplicate_without_harming_complete_batch(tmp_path: Path):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    store = CaptureStore(paths, clock=lambda: "2026-08-13T12:00:00Z")
    receipt = _receipt()
    store.register_extraction(receipt)
    lease = store.acquire_lease(_key(), owner_id="worker", now="2026-08-13T12:00:00Z", ttl_seconds=60)
    assert lease is not None
    observation = _observation("User has a canonical batch.", 0)
    store.commit_extraction(lease, (observation,), _complete_receipt(receipt, 1))
    different = _observation("User has a conflicting synthetic artifact.", 1)
    atomic_write_json(paths.capture.journals / f"{receipt.receipt_id}.json", {"schema_version": 1, "receipt_id": receipt.receipt_id, "observation_ids": [different.observation_id]})

    report = store.recover_transactions(now="2026-08-13T12:01:00Z")

    assert report.duplicate_count == 1
    assert store.visible_observations(receipt.receipt_id) == (observation,)
    assert store.recover_transactions(now="2026-08-13T12:02:00Z").duplicate_count == 0


def test_recovery_audits_unreferenced_staging_without_touching_installed_owner(tmp_path: Path):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    store = CaptureStore(paths, clock=lambda: "2026-08-13T12:00:00Z")
    store.ensure_layout()
    staged = _observation("User has orphaned staged content.", 0)
    atomic_write_json(paths.capture.staging / f"{staged.observation_id}.json", staged.to_mapping())
    report = store.recover_transactions(now="2026-08-13T12:01:00Z")
    assert report.orphan_count == 1
    assert not (paths.capture.staging / f"{staged.observation_id}.json").exists()
    assert store.recover_transactions(now="2026-08-13T12:02:00Z").orphan_count == 0


def test_journal_without_receipt_cleans_only_its_bound_local_artifacts(tmp_path: Path):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    store = CaptureStore(paths, clock=lambda: "2026-08-13T12:00:00Z")
    store.ensure_layout()
    missing_receipt, missing_observation = _foreign_pair()
    payload = {"schema_version": 1, "receipt_id": missing_receipt.receipt_id, "observation_ids": [missing_observation.observation_id]}
    atomic_write_json(paths.capture.journals / f"{missing_receipt.receipt_id}.json", payload)
    atomic_write_json(paths.capture.staging / f"{missing_observation.observation_id}.json", missing_observation.to_mapping())
    atomic_write_json(paths.capture.observations / f"{missing_observation.observation_id}.json", missing_observation.to_mapping())
    report = store.recover_transactions(now="2026-08-13T12:01:00Z")
    assert report.partial_count >= 1
    assert not (paths.capture.journals / f"{missing_receipt.receipt_id}.json").exists()
    assert not (paths.capture.staging / f"{missing_observation.observation_id}.json").exists()
    assert not (paths.capture.observations / f"{missing_observation.observation_id}.json").exists()


def test_recovery_rejects_over_limit_extraction_journal_binding(tmp_path: Path):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    store = CaptureStore(paths, clock=lambda: "2026-08-13T12:00:00Z")
    store.ensure_layout()
    receipt = _receipt()
    observations = [_observation(f"User synthetic journal item {index}.", index) for index in range(9)]
    atomic_write_json(
        paths.capture.journals / f"{receipt.receipt_id}.json",
        {"schema_version": 1, "receipt_id": receipt.receipt_id, "observation_ids": [item.observation_id for item in observations]},
    )
    report = store.recover_transactions(now="2026-08-13T12:01:00Z")
    assert report.corrupt_count == 1
    assert list(paths.capture.quarantines.glob("corrupt-*.json"))


def test_recovery_rejects_transition_journal_with_invalid_filename_binding_or_status(tmp_path: Path):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    store = CaptureStore(paths, clock=lambda: "2026-08-13T12:00:00Z")
    receipt = _receipt(status="queued")
    store.register_extraction(receipt)
    atomic_write_json(
        paths.capture.journals / f"tr_{receipt.receipt_id}.json",
        {"schema_version": 1, "operation": "transition", "receipt_id": receipt.receipt_id, "expected_status": "queued", "target_status": "not-a-status"},
    )
    report = store.recover_transactions(now="2026-08-13T12:01:00Z")
    assert report.corrupt_count == 1
    assert store.read_receipt(receipt.receipt_id).status == "queued"


@pytest.mark.parametrize(
    "crash_point",
    [
        f"{side}:transition:{step}"
        for step in ("journal", "receipt", "ledger", "cleanup")
        for side in ("before", "after")
    ],
)
def test_transition_crash_recovery_converges_receipt_and_ledger(tmp_path: Path, crash_point: str):
    from agc_runtime.capture_contracts import SanitizedError
    from agc_runtime.capture_store import ReceiptTransitionPatch

    paths = MemoryPaths.from_root(tmp_path / "memory")
    store = CaptureStore(paths, crash_at=crash_point, clock=lambda: "2026-08-13T12:00:00Z")
    receipt = _receipt()
    store.register_extraction(receipt)
    lease = store.acquire_lease(_key(), owner_id="worker", now="2026-08-13T12:00:00Z", ttl_seconds=60)
    assert lease is not None
    with pytest.raises(RuntimeError, match="injected crash"):
        store.transition(
            lease, expected=frozenset({"extracting"}), target="retryable",
            patch=ReceiptTransitionPatch(
                next_retry_at="2026-08-13T12:01:00Z",
                sanitized_error=SanitizedError("transaction", "interrupted", True),
            ),
        )
    recovered = CaptureStore(paths, clock=lambda: "2026-08-13T12:00:00Z")
    recovered.recover_transactions(now="2026-08-13T12:02:00Z")
    current = recovered.read_receipt(receipt.receipt_id)
    ledger = __import__("agc_runtime.capture_contracts", fromlist=["LedgerEntry"]).LedgerEntry.from_mapping(
        __import__("json").loads((paths.capture.ledger / f"{receipt.receipt_id}.json").read_text(encoding="utf-8"))
    )
    assert current.status in {"extracting", "retryable"}
    assert ledger.status == current.status
    assert recovered.recover_transactions(now="2026-08-13T12:03:00Z").recovered_count == 0
