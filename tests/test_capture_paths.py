import json
from pathlib import Path

import pytest

import agc_runtime.admin_service as admin_service
from agc_runtime.admin_service import _managed_directories, dispatch_admin
from agc_runtime.capture_contracts import CAPTURE_SCHEMA_VERSION, CaptureKey
from agc_runtime.paths import MemoryPaths


SOURCE_ROOT = "1" * 64


def test_capture_paths_are_nested_below_an_isolated_runtime_namespace(tmp_path: Path):
    paths = MemoryPaths.from_root(tmp_path / "memory")

    assert paths.capture.root == paths.root / ".runtime" / "capture"
    assert paths.capture.receipts == paths.capture.root / "receipts"
    assert paths.capture.observations == paths.capture.root / "observations"
    assert paths.capture.ledger == paths.capture.root / "ledger"
    assert paths.capture.tombstones == paths.capture.root / "tombstones"
    assert paths.capture.schema_version == paths.capture.root / "schema-version"
    assert paths.capture.root != paths.receipts.parent


def test_admin_init_creates_only_empty_capture_layout(tmp_path: Path):
    paths = MemoryPaths.from_root(tmp_path / "memory")

    response = dispatch_admin(paths, {"action": "init"})

    assert response.status == "accepted"
    assert paths.capture.schema_version.read_text(encoding="utf-8") == "1\n"
    for directory in (
        paths.capture.receipts, paths.capture.observations, paths.capture.ledger,
        paths.capture.census, paths.capture.tombstones, paths.capture.quarantines,
        paths.capture.conflicts, paths.capture.dirty, paths.capture.journals,
        paths.capture.staging, paths.capture.leases, paths.capture.indexes,
        paths.capture.scan_state, paths.capture.budgets,
    ):
        assert directory.is_dir()
        assert not list(directory.iterdir())


def test_capture_layout_is_not_part_of_the_legacy_managed_directory_helper(tmp_path: Path):
    paths = MemoryPaths.from_root(tmp_path / "memory")

    assert paths.capture.receipts not in _managed_directories(paths)


def test_admin_validate_strictly_decodes_present_capture_receipts(tmp_path: Path):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    dispatch_admin(paths, {"action": "init"})
    (paths.capture.receipts / "cr_bad.json").write_text(
        json.dumps({"schema_version": 1}), encoding="utf-8"
    )

    response = dispatch_admin(paths, {"action": "validate"})

    assert response.status == "failed"
    assert any("CaptureReceipt" in issue["message"] for issue in response.data["issues"])
    assert all(not Path(issue["path"]).is_absolute() for issue in response.data["issues"])


def test_admin_validate_contains_contract_type_errors_as_validation_issues(tmp_path: Path):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    dispatch_admin(paths, {"action": "init"})
    (paths.capture.receipts / "cr_bad.json").write_text(
        json.dumps({"schema_version": 1, "status": []}), encoding="utf-8"
    )

    response = dispatch_admin(paths, {"action": "validate"})

    assert response.status == "failed"
    assert response.error["code"] == "validation_failed"
    assert any("CaptureReceipt" in issue["message"] for issue in response.data["issues"])


def test_admin_validate_sanitizes_arbitrary_capture_filenames(tmp_path: Path):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    dispatch_admin(paths, {"action": "init"})
    unsafe_name = "private_sentence_traceback.json"
    (paths.capture.receipts / unsafe_name).write_text(
        json.dumps({"schema_version": 1}), encoding="utf-8"
    )

    response = dispatch_admin(paths, {"action": "validate"})

    assert response.status == "failed"
    rendered = json.dumps(response.data)
    assert unsafe_name not in rendered
    assert "<invalid-name>" in rendered


def test_admin_validate_reports_invalid_capture_schema_marker_utf8_safely(tmp_path: Path):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    dispatch_admin(paths, {"action": "init"})
    paths.capture.schema_version.write_bytes(b"\xff")

    response = dispatch_admin(paths, {"action": "validate"})

    assert response.status == "failed"
    assert response.error["code"] == "validation_failed"
    assert any(
        issue["path"] == ".runtime/capture/schema-version"
        for issue in response.data["issues"]
    )


def test_admin_validate_sanitizes_capture_object_read_oserrors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    dispatch_admin(paths, {"action": "init"})
    receipt_path = paths.capture.receipts / ("cr_" + "a" * 64 + ".json")
    receipt_path.write_text("{}", encoding="utf-8")
    private_path = r"C:\private\user-task\secret-transcript.jsonl"
    private_text = "private-user-content"
    real_read = admin_service.strict_read_text

    def permission_denied(path: Path) -> str:
        if path == receipt_path:
            raise PermissionError(f"{private_text}: {private_path}")
        return real_read(path)

    monkeypatch.setattr(admin_service, "strict_read_text", permission_denied)

    response = dispatch_admin(paths, {"action": "validate"})
    rendered = json.dumps(response.to_dict(), ensure_ascii=False)

    assert response.status == "failed"
    assert response.error["code"] == "validation_failed"
    assert private_path not in rendered
    assert private_text not in rendered
    assert any(
        issue["message"] == "Capture object could not be read"
        for issue in response.data["issues"]
    )


def test_admin_validate_strictly_decodes_census_revision_refs(tmp_path: Path):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    dispatch_admin(paths, {"action": "init"})
    revision = {
        "schema_version": CAPTURE_SCHEMA_VERSION,
        "capture_key": CaptureKey("adapter", SOURCE_ROOT, "task", "revision").to_mapping(),
        "rollout_anchor_id": "turn-anchor",
        "completed_at": "2026-08-13T12:00:00Z",
        "locator": "sessions/opaque-turn-token",
        "identity_quality": "session_id",
        "adapter_version": "1",
        "source_schema_version": "1",
    }
    (paths.capture.census / "revision.json").write_text(
        json.dumps(revision), encoding="utf-8"
    )

    assert dispatch_admin(paths, {"action": "validate"}).status == "accepted"

    revision["unknown"] = "rejected"
    (paths.capture.census / "revision.json").write_text(
        json.dumps(revision), encoding="utf-8"
    )
    response = dispatch_admin(paths, {"action": "validate"})
    assert response.status == "failed"
    assert any("RevisionRef" in issue["message"] for issue in response.data["issues"])


@pytest.mark.parametrize(
    "attribute",
    [
        "conflicts",
        "dirty",
        "journals",
        "staging",
        "indexes",
        "scan_state",
        "budgets",
    ],
)
def test_admin_validate_rejects_payloads_in_future_capture_directories(
    tmp_path: Path, attribute: str
):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    dispatch_admin(paths, {"action": "init"})
    directory = getattr(paths.capture, attribute)
    (directory / "payload.json").write_text(
        '{"private_text":"must never appear in validation"}', encoding="utf-8"
    )

    response = dispatch_admin(paths, {"action": "validate"})

    assert response.status == "failed"
    assert any("unsupported Capture payload" in issue["message"] for issue in response.data["issues"])
    assert "must never appear" not in json.dumps(response.data)
