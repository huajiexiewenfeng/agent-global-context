from __future__ import annotations

from pathlib import Path
import json

from agc_runtime.capture_store import CaptureStore
from agc_runtime.paths import MemoryPaths
from tests.test_capture_store import _freeze, _revision


NOW = "2026-08-13T12:00:00Z"


def test_audit_baseline_and_age(tmp_path: Path) -> None:
    from agc_runtime.capture_maintenance import run_full_audit

    store = CaptureStore(MemoryPaths.from_root(tmp_path / "memory"))
    store.ensure_layout()
    audit = run_full_audit(store, now=NOW)
    assert audit.status == "healthy"
    assert audit.scope == "full_historical_integrity"
    assert audit.completed_at == NOW
    assert audit.input_generation
    assert store.recover_active_transactions(now="2026-08-14T12:00:01Z").status == "audit_due"


def test_audit_reads_cold_census_members_even_when_catalog_is_warm(tmp_path: Path) -> None:
    from agc_runtime.capture_maintenance import run_full_audit

    paths = MemoryPaths.from_root(tmp_path / "memory")
    store = CaptureStore(paths)
    _freeze(store, (_revision(),), started_at=NOW)
    assert store.read_snapshot().integrity_state == "healthy"
    member = next((paths.capture.root / "census-runs").rglob("members/*.json"))
    member.write_text("{bad-json", encoding="utf-8")
    audit = run_full_audit(store, now=NOW)
    assert audit.status == "integrity_failed"
    assert store.recover_active_transactions(now=NOW).status == "capture_bootstrap_required"


def test_audit_accepts_identical_overlapping_frozen_runs(tmp_path: Path) -> None:
    from agc_runtime.capture_maintenance import run_full_audit

    store = CaptureStore(MemoryPaths.from_root(tmp_path / "memory"))
    revision = _revision()
    _freeze(store, (revision,), started_at="2026-08-13T11:00:00Z")
    _freeze(store, (revision,), started_at=NOW)
    assert run_full_audit(store, now=NOW).status == "healthy"


def test_audit_rejects_conflicting_overlapping_frozen_runs(tmp_path: Path) -> None:
    from agc_runtime.capture_maintenance import run_full_audit

    store = CaptureStore(MemoryPaths.from_root(tmp_path / "memory"))
    _freeze(store, (_revision(),), started_at="2026-08-13T11:00:00Z")
    _freeze(store, (_revision(completed_at="2026-08-12T12:00:01Z"),), started_at=NOW)
    audit = run_full_audit(store, now=NOW)
    assert audit.status == "integrity_failed"
    assert store.recover_active_transactions(now=NOW).status == "capture_bootstrap_required"


def test_audit_cli_is_explicit_one_shot_and_no_model(tmp_path: Path, capsys) -> None:
    from agc_runtime.capture_cli import main

    root = tmp_path / "memory"
    assert main(["audit", "--root", str(root), "--once"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["action"] == "audit"
    assert payload["status"] == "accepted"
    assert payload["data"]["scope"] == "full_historical_integrity"


def test_config_change_invalidates_baseline(tmp_path: Path) -> None:
    from agc_runtime.capture_maintenance import run_full_audit

    paths = MemoryPaths.from_root(tmp_path / "memory")
    store = CaptureStore(paths)
    assert run_full_audit(store, now=NOW).status == "healthy"
    (paths.root / "config.yaml").write_text("capture: changed\n", encoding="utf-8")
    assert store.recover_active_transactions(now=NOW).status == "capture_bootstrap_required"


def test_forget_removes_workset_not_only_its_generation_binding(tmp_path: Path) -> None:
    from agc_runtime.capture_maintenance import run_full_audit
    from agc_runtime.write_service import dispatch_write
    from tests.test_capture_forget import _key, _populated, _request

    paths, store, _receipt, _observations = _populated(tmp_path)
    assert run_full_audit(store, now=NOW).status == "healthy"
    checkpoint = paths.capture.root / "active-workset.json"
    assert checkpoint.exists()
    response = dispatch_write(paths, _request({"type": "revision", **_key().to_mapping()}))
    assert response.status == "accepted"
    assert not checkpoint.exists()


def test_forget_before_images_exclude_flat_workset(tmp_path: Path) -> None:
    from agc_runtime.capture_forget_service import _read_primary
    from agc_runtime.capture_maintenance import run_full_audit
    from tests.test_capture_forget import _populated

    paths, store, _receipt, _observations = _populated(tmp_path)
    assert run_full_audit(store, now=NOW).status == "healthy"
    before = _read_primary(paths)
    assert ".runtime/capture/active-workset.json" not in before
    assert ".runtime/capture/active-workset-seal.json" not in before


def test_restore_removes_workset_and_requires_reaudit(tmp_path: Path) -> None:
    from agc_runtime.admin_service import dispatch_admin
    from agc_runtime.capture_maintenance import run_full_audit
    from tests.test_capture_backup_restore import _populated

    paths, store, _observation = _populated(tmp_path)
    backup = dispatch_admin(paths, {"action": "backup"})
    assert backup.status == "accepted"
    assert run_full_audit(store, now=NOW).status == "healthy"
    checkpoint = paths.capture.root / "active-workset.json"
    assert checkpoint.exists()
    restored = dispatch_admin(paths, {"action": "restore", "backup_path": backup.data["backup_path"]})
    assert restored.status == "accepted"
    assert not checkpoint.exists()
    assert store.recover_active_transactions(now=NOW).status == "capture_bootstrap_required"


def test_audit_reports_orphan_without_deleting_or_signing_healthy(tmp_path: Path) -> None:
    from agc_runtime.capture_maintenance import run_full_audit
    from agc_runtime.capture_transaction import atomic_write_json
    from tests.test_capture_store import _observation

    paths = MemoryPaths.from_root(tmp_path / "memory")
    store = CaptureStore(paths)
    store.ensure_layout()
    orphan = _observation("Synthetic orphan observation.", 0)
    path = paths.capture.observations / f"{orphan.observation_id}.json"
    atomic_write_json(path, orphan.to_mapping())
    audit = run_full_audit(store, now=NOW)
    assert audit.status == "integrity_failed"
    assert "orphan_observation" in audit.diagnostics
    assert path.exists()
    assert store.recover_active_transactions(now=NOW).status == "capture_bootstrap_required"


def test_failed_audit_cannot_leave_previous_healthy_checkpoint(tmp_path: Path, monkeypatch) -> None:
    import pytest
    from agc_runtime.capture_maintenance import run_full_audit

    paths = MemoryPaths.from_root(tmp_path / "memory")
    store = CaptureStore(paths)
    assert run_full_audit(store, now=NOW).status == "healthy"

    def interrupted(*_args, **_kwargs):
        raise RuntimeError("synthetic audit interruption")

    monkeypatch.setattr(store, "_read_snapshot_locked", interrupted)
    with pytest.raises(RuntimeError, match="synthetic audit interruption"):
        run_full_audit(store, now="2026-08-13T13:00:00Z")
    assert store.recover_active_transactions(now=NOW).status == "capture_bootstrap_required"


def test_audit_does_not_ignore_or_delete_unowned_staging(tmp_path: Path) -> None:
    from agc_runtime.capture_maintenance import run_full_audit
    from agc_runtime.capture_transaction import atomic_write_json
    from tests.test_capture_store import _observation

    paths = MemoryPaths.from_root(tmp_path / "memory")
    store = CaptureStore(paths)
    store.ensure_layout()
    staged = _observation("Synthetic unowned stage.", 0)
    path = paths.capture.staging / f"{staged.observation_id}.json"
    atomic_write_json(path, staged.to_mapping())
    audit = run_full_audit(store, now=NOW)
    assert audit.status == "integrity_failed"
    assert path.exists()
