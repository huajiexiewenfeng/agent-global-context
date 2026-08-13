"""Contract tests for Capture status diagnostics."""

from agc_runtime.capture_status_service import capture_status
from agc_runtime.admin_service import dispatch_admin
from agc_runtime.paths import MemoryPaths


def test_capture_status_is_diagnosable_while_disabled(tmp_path):
    status = capture_status(tmp_path)

    assert status["activation_ready"] is False


def test_capture_status_is_explicit_admin_route_without_path_or_user_content(tmp_path):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    response = dispatch_admin(paths, {"action": "capture_status"})

    assert response.status == "accepted"
    assert response.data["state"] == {"enabled": False, "paused": False, "mode": "off", "scanner_only": False}
    assert set(response.data) == {"config_source", "runtime", "memory_root", "configured_source_root_ids", "extractor_boundary", "budgets", "state", "route_conflicts", "activation_ready"}
    assert response.data["configured_source_root_ids"] == []
    assert response.data["extractor_boundary"]["host_binding_present"] is False
    assert str(paths.root) not in str(response.data)
    assert response.data["route_conflicts"] == []
