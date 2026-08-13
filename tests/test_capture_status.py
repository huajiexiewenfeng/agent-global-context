"""Contract tests for Capture status diagnostics."""

from agc_runtime.capture_status_service import capture_status
from agc_runtime.capture_store import root_fingerprint
from agc_runtime.admin_service import dispatch_admin
from agc_runtime.paths import MemoryPaths
from agc_runtime.utf8_io import atomic_write_text


def test_capture_status_is_diagnosable_while_disabled(tmp_path):
    status = capture_status(tmp_path)

    assert status["activation_ready"] is False


def test_capture_status_is_explicit_admin_route_without_path_or_user_content(tmp_path):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    response = dispatch_admin(paths, {"action": "capture_status"})

    assert response.status == "accepted"
    assert response.data["state"] == {"enabled": False, "paused": False, "mode": "off", "scanner_only": False}
    assert response.data["memory_root"] == {
        "fingerprint": root_fingerprint(paths),
        "assessment": "not_assessed",
        "matches_host_binding": None,
        "evidence": None,
    }
    assert response.data["source_roots"] == {
        "configured_count": 0,
        "assessment": "unavailable",
        "ids": [],
    }
    assert response.data["extractor_boundary"]["capability_assessment"] == "not_assessed"
    assert str(paths.root) not in str(response.data)
    assert response.data["route"]["assessment"] == "not_assessed"
    assert response.data["activation_ready"] is False
    assert response.data["activation_reasons"]


def test_capture_status_invalid_config_has_fixed_content_safe_machine_error(tmp_path):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    paths.root.mkdir(parents=True)
    atomic_write_text(paths.root / "config.yaml", "invalid: secret-marker-must-not-leak\n")

    response = dispatch_admin(paths, {"action": "capture_status"})

    assert response.status == "failed"
    assert response.error == {
        "code": "invalid_runtime_config",
        "message": "runtime configuration is invalid",
    }
    assert "secret-marker" not in str(response.to_dict())
    assert str(paths.root) not in str(response.to_dict())
