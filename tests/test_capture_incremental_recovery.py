from __future__ import annotations

from pathlib import Path

import pytest

from agc_runtime.capture_store import CaptureStore
from agc_runtime.paths import MemoryPaths
from tests.test_capture_store import _complete_receipt, _key, _receipt


NOW = "2026-08-13T12:00:00Z"


def test_old_root_requires_explicit_bootstrap(tmp_path: Path) -> None:
    store = CaptureStore(MemoryPaths.from_root(tmp_path / "memory"))
    store.ensure_layout()
    result = store.recover_active_transactions(now=NOW)
    assert result.status == "capture_bootstrap_required"


def test_bounded_recovery_handles_extracting_without_commit_journal(tmp_path: Path) -> None:
    from agc_runtime.capture_maintenance import run_full_audit

    paths = MemoryPaths.from_root(tmp_path / "memory")
    store = CaptureStore(paths)
    store.ensure_layout()
    assert run_full_audit(store, now=NOW).status == "healthy"
    receipt = _receipt()
    store.register_extraction(receipt)
    assert not list(paths.capture.journals.glob(f"{receipt.receipt_id}.json"))

    result = CaptureStore(paths).recover_active_transactions(now="2026-08-13T12:02:00Z")
    assert result.status == "ok"
    assert result.report.recovered_count == 1
    assert store.read_receipt(receipt.receipt_id).status == "retryable"


def test_live_lease_is_not_recovered(tmp_path: Path) -> None:
    from agc_runtime.capture_maintenance import run_full_audit
    from tests.test_capture_store import _key

    paths = MemoryPaths.from_root(tmp_path / "memory")
    store = CaptureStore(paths)
    store.ensure_layout()
    assert run_full_audit(store, now=NOW).status == "healthy"
    receipt = _receipt()
    store.register_extraction(receipt)
    lease = store.acquire_lease(_key(), owner_id="worker", now=NOW, ttl_seconds=60)
    assert lease is not None
    result = store.recover_active_transactions(now="2026-08-13T12:00:30Z")
    assert result.status == "ok"
    assert result.report.recovered_count == 0
    assert store.read_receipt(receipt.receipt_id).status == "extracting"


def test_old_root_with_interrupted_extraction_bootstraps_in_two_phases(tmp_path: Path) -> None:
    from agc_runtime.capture_maintenance import run_full_audit

    paths = MemoryPaths.from_root(tmp_path / "memory")
    store = CaptureStore(paths)
    store.register_extraction(_receipt())
    audit = run_full_audit(store, now=NOW)
    assert audit.status == "recovery_needed"
    recovered = store.recover_active_transactions(now="2026-08-13T12:02:00Z")
    assert recovered.report.recovered_count == 1
    assert recovered.status == "capture_bootstrap_required"
    assert run_full_audit(store, now="2026-08-13T12:03:00Z").status == "healthy"


def test_corrupt_active_workset_requires_bootstrap(tmp_path: Path) -> None:
    from agc_runtime.capture_maintenance import run_full_audit

    paths = MemoryPaths.from_root(tmp_path / "memory")
    store = CaptureStore(paths)
    store.ensure_layout()
    assert run_full_audit(store, now=NOW).status == "healthy"
    (paths.capture.root / "active-workset.json").write_text("{}", encoding="utf-8")
    assert store.recover_active_transactions(now=NOW).status == "capture_bootstrap_required"


def test_non_utf8_active_workset_requires_bootstrap(tmp_path: Path) -> None:
    from agc_runtime.capture_maintenance import run_full_audit

    paths = MemoryPaths.from_root(tmp_path / "memory")
    store = CaptureStore(paths)
    assert run_full_audit(store, now=NOW).status == "healthy"
    (paths.capture.root / "active-workset.json").write_bytes(b"\xff")
    assert store.recover_active_transactions(now=NOW).status == "capture_bootstrap_required"


def test_older_valid_workset_cannot_hide_new_active_entry(tmp_path: Path) -> None:
    from agc_runtime.capture_maintenance import run_full_audit

    paths = MemoryPaths.from_root(tmp_path / "memory")
    store = CaptureStore(paths)
    assert run_full_audit(store, now=NOW).status == "healthy"
    workset = paths.capture.root / "active-workset.json"
    stale_bytes = workset.read_bytes()
    store.register_extraction(_receipt())
    workset.write_bytes(stale_bytes)
    assert store.recover_active_transactions(now=NOW).status == "capture_bootstrap_required"


def test_interrupted_workset_seal_fails_closed_before_primary_write(tmp_path: Path, monkeypatch) -> None:
    import agc_runtime.capture_maintenance as maintenance

    paths = MemoryPaths.from_root(tmp_path / "memory")
    store = CaptureStore(paths)
    assert maintenance.run_full_audit(store, now=NOW).status == "healthy"
    original = maintenance.atomic_write_json

    def interrupted(path: Path, value: dict):
        if path.name == "active-workset-seal.json":
            raise RuntimeError("synthetic seal interruption")
        return original(path, value)

    monkeypatch.setattr(maintenance, "atomic_write_json", interrupted)
    receipt = _receipt(status="discovered")
    with pytest.raises(RuntimeError, match="synthetic seal interruption"):
        store.register_extraction(receipt)
    assert not (paths.capture.receipts / f"{receipt.receipt_id}.json").exists()
    assert store.recover_active_transactions(now=NOW).status == "capture_bootstrap_required"


def test_corrupt_transition_journal_requires_audit_on_every_retry(tmp_path: Path) -> None:
    from agc_runtime.capture_maintenance import run_full_audit
    from agc_runtime.capture_transaction import atomic_write_json
    from agc_runtime.capture_store import ReceiptTransitionPatch
    from agc_runtime.capture_contracts import SanitizedError

    paths = MemoryPaths.from_root(tmp_path / "memory")
    store = CaptureStore(paths, crash_at="after:transition:journal", clock=lambda: NOW)
    assert run_full_audit(store, now=NOW).status == "healthy"
    receipt = _receipt(status="queued")
    store.register_extraction(receipt)
    lease = store.acquire_lease(_key(), owner_id="worker", now=NOW, ttl_seconds=60)
    assert lease is not None
    with pytest.raises(RuntimeError, match="injected crash"):
        store.transition(lease, expected=frozenset({"queued"}), target="retryable", patch=ReceiptTransitionPatch(sanitized_error=SanitizedError("extractor", "timeout", True), next_retry_at="2026-08-13T12:03:00Z"))
    journal = paths.capture.journals / f"tr_{receipt.receipt_id}.json"
    atomic_write_json(journal, {"corrupt": True})
    recovered = CaptureStore(paths)
    assert recovered.recover_active_transactions(now="2026-08-13T12:02:00Z").status == "capture_bootstrap_required"
    assert not journal.exists()
    assert recovered.recover_active_transactions(now="2026-08-13T12:03:00Z").status == "capture_bootstrap_required"


def test_missing_receipt_with_ledger_never_retires_as_pure_premark(tmp_path: Path) -> None:
    from agc_runtime.capture_maintenance import run_full_audit
    from agc_runtime.capture_transaction import safe_unlink

    paths = MemoryPaths.from_root(tmp_path / "memory")
    store = CaptureStore(paths)
    assert run_full_audit(store, now=NOW).status == "healthy"
    receipt = _receipt()
    store.register_extraction(receipt)
    safe_unlink(paths.capture.receipts / f"{receipt.receipt_id}.json")
    ledger = paths.capture.ledger / f"{receipt.receipt_id}.json"
    assert ledger.exists()
    assert store.recover_active_transactions(now=NOW).status == "capture_bootstrap_required"
    assert ledger.exists()
    assert store.recover_active_transactions(now=NOW).status == "capture_bootstrap_required"


def test_missing_receipt_with_manifest_never_retires_as_pure_premark(tmp_path: Path) -> None:
    from agc_runtime.capture_maintenance import run_full_audit, mark_active_locked
    from agc_runtime.capture_transaction import atomic_write_json
    from agc_runtime.locking import capture_write_lock

    paths = MemoryPaths.from_root(tmp_path / "memory")
    store = CaptureStore(paths)
    assert run_full_audit(store, now=NOW).status == "healthy"
    receipt = _receipt()
    with capture_write_lock(paths):
        mark_active_locked(store, receipt.receipt_id)
    manifest = paths.capture.indexes / f"{receipt.receipt_id}.json"
    atomic_write_json(manifest, {"schema_version": 1, "receipt_id": receipt.receipt_id, "observation_ids": []})
    assert store.recover_active_transactions(now=NOW).status == "capture_bootstrap_required"
    assert manifest.exists()


def test_missing_receipt_with_bound_observation_is_sticky_corruption(tmp_path: Path) -> None:
    from agc_runtime.capture_maintenance import run_full_audit, mark_active_locked
    from agc_runtime.capture_transaction import atomic_write_json
    from agc_runtime.locking import capture_write_lock
    from tests.test_capture_store import _observation

    paths = MemoryPaths.from_root(tmp_path / "memory")
    store = CaptureStore(paths)
    assert run_full_audit(store, now=NOW).status == "healthy"
    receipt = _receipt()
    with capture_write_lock(paths):
        mark_active_locked(store, receipt.receipt_id)
    observation = _observation("Bound synthetic observation.", 0)
    path = paths.capture.observations / f"{observation.observation_id}.json"
    atomic_write_json(path, observation.to_mapping())
    assert store.recover_active_transactions(now=NOW).status == "capture_bootstrap_required"
    assert path.exists()
    assert store.recover_active_transactions(now=NOW).status == "capture_bootstrap_required"


def test_pure_premark_without_primary_artifacts_can_retire(tmp_path: Path) -> None:
    from agc_runtime.capture_maintenance import run_full_audit, mark_active_locked
    from agc_runtime.locking import capture_write_lock

    paths = MemoryPaths.from_root(tmp_path / "memory")
    store = CaptureStore(paths)
    assert run_full_audit(store, now=NOW).status == "healthy"
    receipt = _receipt()
    with capture_write_lock(paths):
        mark_active_locked(store, receipt.receipt_id)
    assert store.recover_active_transactions(now=NOW).status == "ok"


def test_registration_receipt_before_ledger_is_bounded_recoverable(tmp_path: Path) -> None:
    from agc_runtime.capture_maintenance import run_full_audit

    paths = MemoryPaths.from_root(tmp_path / "memory")
    store = CaptureStore(paths, crash_at="after:discovery:receipt")
    assert run_full_audit(store, now=NOW).status == "healthy"
    receipt = _receipt(status="discovered")
    with pytest.raises(RuntimeError, match="injected crash"):
        store.register_extraction(receipt)
    assert not (paths.capture.ledger / f"{receipt.receipt_id}.json").exists()
    result = CaptureStore(paths).recover_active_transactions(now=NOW)
    assert result.status == "ok"
    assert (paths.capture.ledger / f"{receipt.receipt_id}.json").exists()


def test_old_root_receipt_before_ledger_bootstraps_in_two_phases(tmp_path: Path) -> None:
    from agc_runtime.capture_maintenance import run_full_audit

    paths = MemoryPaths.from_root(tmp_path / "memory")
    store = CaptureStore(paths, crash_at="after:discovery:receipt")
    with pytest.raises(RuntimeError, match="injected crash"):
        store.register_extraction(_receipt(status="discovered"))
    audit = run_full_audit(CaptureStore(paths), now=NOW)
    assert audit.status == "recovery_needed"
    result = CaptureStore(paths).recover_active_transactions(now=NOW)
    assert result.report.recovered_count == 1
    assert result.status == "capture_bootstrap_required"
    assert run_full_audit(CaptureStore(paths), now=NOW).status == "healthy"


@pytest.mark.parametrize("crash_point", ["after:ledger", "after:receipt", "after:cleanup"])
def test_bounded_commit_crash_windows(tmp_path: Path, crash_point: str) -> None:
    from agc_runtime.capture_maintenance import run_full_audit

    paths = MemoryPaths.from_root(tmp_path / "memory")
    store = CaptureStore(paths, crash_at=crash_point, clock=lambda: NOW)
    assert run_full_audit(store, now=NOW).status == "healthy"
    receipt = _receipt()
    store.register_extraction(receipt)
    lease = store.acquire_lease(_key(), owner_id="worker", now=NOW, ttl_seconds=60)
    assert lease is not None
    with pytest.raises(RuntimeError, match="injected crash"):
        store.commit_extraction(lease, (), _complete_receipt(receipt, 0))
    result = CaptureStore(paths).recover_active_transactions(now="2026-08-13T12:02:00Z")
    assert result.status == "ok"
    assert result.report.recovered_count == 1
    assert store.read_receipt(receipt.receipt_id).status == (
        "retryable" if crash_point == "after:ledger" else "complete"
    )


def test_settlement_before_transition_journal_remains_tracked(tmp_path: Path) -> None:
    from agc_runtime.capture_maintenance import run_full_audit
    from agc_runtime.capture_store import ReceiptTransitionPatch
    from agc_runtime.capture_contracts import SanitizedError
    from tests.test_capture_transaction import _transaction_budget

    paths = MemoryPaths.from_root(tmp_path / "memory")
    store = CaptureStore(paths, crash_at="after:budget:settlement", clock=lambda: NOW)
    budget, reservation, settlement = _transaction_budget(store)
    assert run_full_audit(store, now=NOW).status == "healthy"
    receipt = _receipt()
    store.register_extraction(receipt)
    lease = store.acquire_lease(_key(), owner_id="worker", now=NOW, ttl_seconds=60)
    assert lease is not None
    with pytest.raises(RuntimeError, match="injected crash"):
        store.transition_with_settlement(
            lease, expected=frozenset({"extracting"}), target="retryable",
            patch=ReceiptTransitionPatch(sanitized_error=SanitizedError("extractor", "timeout", True)),
            reservation=reservation, settlement=settlement,
        )
    result = CaptureStore(paths).recover_active_transactions(now="2026-08-13T12:02:00Z")
    assert result.status == "ok"
    assert store.read_receipt(receipt.receipt_id).status == "retryable"
    assert budget.snapshot().settlements == 1


@pytest.mark.parametrize("crash_point", [
    "after:transition:journal", "after:transition:receipt",
    "after:transition:ledger", "after:transition:cleanup",
])
def test_bounded_transition_crash_windows(tmp_path: Path, crash_point: str) -> None:
    from agc_runtime.capture_maintenance import run_full_audit
    from agc_runtime.capture_store import ReceiptTransitionPatch
    from agc_runtime.capture_contracts import SanitizedError

    paths = MemoryPaths.from_root(tmp_path / "memory")
    store = CaptureStore(paths, crash_at=crash_point, clock=lambda: NOW)
    assert run_full_audit(store, now=NOW).status == "healthy"
    receipt = _receipt(status="queued")
    store.register_extraction(receipt)
    lease = store.acquire_lease(_key(), owner_id="worker", now=NOW, ttl_seconds=60)
    assert lease is not None
    with pytest.raises(RuntimeError, match="injected crash"):
        store.transition(lease, expected=frozenset({"queued"}), target="retryable", patch=ReceiptTransitionPatch(sanitized_error=SanitizedError("extractor", "timeout", True), next_retry_at="2026-08-13T12:03:00Z"))
    result = CaptureStore(paths).recover_active_transactions(now="2026-08-13T12:02:00Z")
    assert result.status == "ok"
    assert store.read_receipt(receipt.receipt_id).status == (
        "queued" if crash_point == "after:transition:journal" else "retryable"
    )
    assert not (paths.capture.journals / f"tr_{receipt.receipt_id}.json").exists()


def test_explicit_full_recovery_invalidates_changed_workset(tmp_path: Path) -> None:
    from agc_runtime.capture_maintenance import run_full_audit

    paths = MemoryPaths.from_root(tmp_path / "memory")
    store = CaptureStore(paths)
    assert run_full_audit(store, now=NOW).status == "healthy"
    store.register_extraction(_receipt())
    assert store.recover_transactions(now="2026-08-13T12:02:00Z").recovered_count == 1
    assert store.recover_active_transactions(now=NOW).status == "capture_bootstrap_required"


def test_bounded_recovery_skips_healthy_completed_history_content(tmp_path: Path, monkeypatch) -> None:
    import agc_runtime.capture_store as store_module
    from agc_runtime.capture_contracts import CaptureKey, CaptureReceipt, receipt_id_for
    from agc_runtime.capture_maintenance import run_full_audit

    paths = MemoryPaths.from_root(tmp_path / "memory")
    store = CaptureStore(paths)
    for index in range(20):
        key = CaptureKey("synthetic_adapter", "1" * 64, f"task-{index}", "revision-1")
        receipt = CaptureReceipt.from_mapping({
            **_receipt(status="discovered").to_mapping(), **key.to_mapping(),
            "receipt_id": receipt_id_for(key),
        })
        store.register_extraction(receipt)
    assert run_full_audit(store, now=NOW).status == "healthy"
    reads: list[Path] = []
    original = store_module.read_json

    def counted(path: Path):
        reads.append(path)
        return original(path)

    monkeypatch.setattr(store_module, "read_json", counted)
    assert store.recover_active_transactions(now=NOW).status == "ok"
    assert not any(path.parent == paths.capture.receipts for path in reads)


def test_quarantined_registration_retires_marker_after_all_writes(tmp_path: Path) -> None:
    from agc_runtime.capture_maintenance import run_full_audit
    from agc_runtime.capture_transaction import read_json
    from tests.test_capture_store import _revision

    paths = MemoryPaths.from_root(tmp_path / "memory")
    store = CaptureStore(paths)
    assert run_full_audit(store, now=NOW).status == "healthy"
    store.register_quarantined_revision(_revision(), discovered_at=NOW, code="revision_metadata_conflict")
    assert read_json(paths.capture.root / "active-workset.json")["active"] == []


def test_quarantined_registration_crash_before_conflict_is_recovered(tmp_path: Path, monkeypatch) -> None:
    from agc_runtime.capture_maintenance import run_full_audit
    from tests.test_capture_store import _revision

    paths = MemoryPaths.from_root(tmp_path / "memory")
    store = CaptureStore(paths)
    assert run_full_audit(store, now=NOW).status == "healthy"

    def interrupted(*_args, **_kwargs):
        raise RuntimeError("synthetic conflict write interruption")

    monkeypatch.setattr(store, "_write_source_conflict", interrupted)
    with pytest.raises(RuntimeError, match="synthetic conflict write interruption"):
        store.register_quarantined_revision(_revision(), discovered_at=NOW, code="revision_metadata_conflict")
    result = CaptureStore(paths).recover_active_transactions(now=NOW)
    assert result.status == "ok"
    assert result.report.recovered_count == 1
    assert list(paths.capture.conflicts.glob("*.json"))
