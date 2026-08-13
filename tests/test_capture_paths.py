import json
from pathlib import Path

from agc_runtime.admin_service import _managed_directories, dispatch_admin
from agc_runtime.paths import MemoryPaths


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
