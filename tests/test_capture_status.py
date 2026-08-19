"""Contract tests for Capture status diagnostics."""

from datetime import datetime, timedelta, timezone
import json
import inspect
from pathlib import Path
import subprocess
import sys

import pytest

import agc_runtime.admin_service as admin_service
import agc_runtime.capture_status_service as capture_status_service
from agc_runtime.capture_status_service import capture_status
from agc_runtime.capture_store import root_fingerprint
from agc_runtime.admin_service import dispatch_admin
from agc_runtime.paths import MemoryPaths
from agc_runtime.utf8_io import atomic_write_text


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module", autouse=True)
def _unload_deferred_status_modules():
    yield
    for name in (
        "agc_runtime.codex_source_adapter",
        "agc_runtime.capture_scanner",
        "agc_runtime.capture_ledger",
        "agc_runtime.capture_source",
    ):
        sys.modules.pop(name, None)


def _configured_status_root(tmp_path: Path) -> tuple[MemoryPaths, Path]:
    memory_root = tmp_path / "memory"
    source_root = tmp_path / "source"
    sessions = source_root / "sessions"
    sessions.mkdir(parents=True)
    completed = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(minutes=1)
    started = completed - timedelta(minutes=1)
    records = (
        {"timestamp": started.isoformat().replace("+00:00", "Z"), "type": "session_meta", "payload": {"id": "rollout-status", "session_id": "task-status", "source": "cli"}},
        {"timestamp": completed.isoformat().replace("+00:00", "Z"), "type": "event_msg", "payload": {"type": "task_complete", "turn_id": "turn-status"}},
    )
    (sessions / "status.jsonl").write_text(
        "".join(json.dumps(item) + "\n" for item in records), encoding="utf-8"
    )
    default = (REPOSITORY_ROOT / "agc_runtime" / "default_config.yaml").read_text(encoding="utf-8")
    memory_root.mkdir()
    (memory_root / "config.yaml").write_text(
        default.replace("enabled: false", "enabled: true", 1)
        .replace("mode: off", "mode: scanner_only", 1)
        .replace("sources: []", f"sources:\n    - {source_root.as_posix()}", 1),
        encoding="utf-8",
    )
    return MemoryPaths.from_root(memory_root), source_root


def _scan(paths: MemoryPaths, action: str = "scan") -> None:
    arguments = (
        [action, "--root", str(paths.root), "--once"]
        if action == "cycle"
        else [
            action,
            "--root",
            str(paths.root),
            "--mode",
            "census",
            "--once",
        ]
    )
    result = subprocess.run(
        [sys.executable, "-m", "agc_runtime.capture_cli", *arguments],
        cwd=REPOSITORY_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def _probe(paths: MemoryPaths) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "agc_runtime.capture_cli",
            "probe",
            "--root",
            str(paths.root),
        ],
        cwd=REPOSITORY_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_capture_status_is_diagnosable_while_disabled(tmp_path):
    memory_root = tmp_path / "memory"
    status = capture_status(memory_root)

    assert status["activation_ready"] is False
    assert status["scanner"]["assessment"] == "not_assessed"
    assert status["scanner"]["code"] == "capture_disabled"
    assert status["scanner"]["operation_eligible"] is False
    assert not memory_root.exists()


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


def test_direct_admin_api_has_no_host_evidence_injection_surface(tmp_path):
    paths = MemoryPaths.from_root(tmp_path / "memory")

    response = dispatch_admin(
        paths,
        {
            "action": "capture_status",
            "host_binding": "mcp_memory_root",
            "root_fingerprint": root_fingerprint(paths),
        },
    )

    assert response.data["memory_root"]["assessment"] == "not_assessed"
    assert tuple(inspect.signature(dispatch_admin).parameters) == ("paths", "request")
    assert tuple(inspect.signature(capture_status).parameters) == ("value",)
    assert not hasattr(capture_status_service, "HostBindingEvidence")
    assert not hasattr(admin_service, "make_host_bound_admin_dispatch")


def test_capture_status_reports_truthful_durable_scanner_metrics_without_paths(
    tmp_path, monkeypatch
):
    from agc_runtime.capture_store import CaptureStore

    paths, source_root = _configured_status_root(tmp_path)
    result = subprocess.run(
        [sys.executable, "-m", "agc_runtime.capture_cli", "scan", "--root", str(paths.root), "--mode", "census", "--once"],
        cwd=REPOSITORY_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout
    monkeypatch.setattr(
        CaptureStore,
        "is_revision_accounted",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("status escaped its locked snapshot")
        ),
    )

    status = capture_status(paths)

    scanner = status["scanner"]
    assert scanner["assessment"] == "ready"
    assert scanner["code"] == "scanner_ready"
    assert scanner["source_health"] == "healthy"
    assert scanner["latest_census"] == {
        "assessment": "available",
        "run_count": 1,
        "key_count": 1,
    }
    assert scanner["accounting"] == {
        "known_key_count": 1,
        "accounted_key_count": 1,
        "pending_key_count": 0,
        "silent_loss_count": 0,
    }
    assert scanner["dirty_marker_count"] == 0
    assert scanner["scan_state"]["assessment"] == "available"
    assert scanner["scan_state"]["binding_count"] == 1
    assert scanner["scan_state"]["max_state_version"] == 2
    assert scanner["operation_eligible"] is False
    assert "memory_root_binding_not_assessed" in scanner["operation_reasons"]
    rendered = json.dumps(status)
    assert str(paths.root) not in rendered
    assert str(source_root) not in rendered


def test_capture_status_does_not_guess_ready_when_layout_has_no_scanner_state(tmp_path):
    from agc_runtime.capture_store import CaptureStore

    paths, _source_root = _configured_status_root(tmp_path)
    CaptureStore(paths).ensure_layout()

    status = capture_status(paths)

    assert status["scanner"]["assessment"] == "absent"
    assert status["scanner"]["code"] == "scanner_state_absent"
    assert status["scanner"]["source_health"] == "not_assessed"
    assert status["scanner"]["latest_census"]["assessment"] == "absent"
    assert status["scanner"]["scan_state"]["assessment"] == "absent"


def test_capture_status_reports_busy_and_corrupt_with_fixed_codes(tmp_path):
    from agc_runtime.locking import capture_write_lock

    paths, _source_root = _configured_status_root(tmp_path)
    first = subprocess.run(
        [sys.executable, "-m", "agc_runtime.capture_cli", "cycle", "--root", str(paths.root), "--once"],
        cwd=REPOSITORY_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert first.returncode == 0, first.stdout

    with capture_write_lock(paths):
        busy = capture_status(paths)
    assert busy["scanner"]["assessment"] == "busy"
    assert busy["scanner"]["code"] == "scanner_busy"
    assert busy["scanner"]["operation_eligible"] is False

    run_file = next((paths.capture.root / "census-runs").glob("*/run.json"))
    run_file.write_text('{"private":"must-not-leak"}\n', encoding="utf-8")
    corrupt = capture_status(paths)
    assert corrupt["scanner"]["assessment"] == "corrupt"
    assert corrupt["scanner"]["code"] == "scanner_corrupt"
    assert corrupt["scanner"]["operation_eligible"] is False
    assert "private" not in json.dumps(corrupt)


@pytest.mark.parametrize("artifact", ["ledger_json", "receipt_json", "missing_ledger"])
def test_capture_status_and_probe_reject_corrupt_or_partial_receipt_graph(
    tmp_path: Path, artifact: str
):
    paths, source_root = _configured_status_root(tmp_path)
    _scan(paths)
    ledger = next(paths.capture.ledger.glob("*.json"))
    receipt = next(paths.capture.receipts.glob("*.json"))
    if artifact == "ledger_json":
        ledger.write_text('{"private":"ledger-secret"}\n', encoding="utf-8")
    elif artifact == "receipt_json":
        receipt.write_text('{"private":"receipt-secret"}\n', encoding="utf-8")
    else:
        ledger.unlink()

    status = capture_status(paths)
    result = _probe(paths)
    payload = json.loads(result.stdout)

    assert status["scanner"]["assessment"] == "corrupt"
    assert status["scanner"]["code"] == "scanner_corrupt"
    assert result.returncode != 0
    assert result.stderr == ""
    assert len(result.stdout.splitlines()) == 1
    assert payload["status"] == "failed"
    assert payload["error"] == {
        "code": "scanner_corrupt",
        "message": "Capture state failed integrity validation",
    }
    rendered = json.dumps(payload)
    assert "secret" not in rendered
    assert str(paths.root) not in rendered
    assert str(source_root) not in rendered


def test_capture_status_scopes_durable_metrics_to_current_source_binding(tmp_path: Path):
    from agc_runtime.capture_source import DirtyMarker, SourceBindingKey, source_root_id_for
    from agc_runtime.capture_store import CaptureStore

    paths, source_a = _configured_status_root(tmp_path)
    _scan(paths)
    source_a_id = source_root_id_for(source_a)
    binding_a = SourceBindingKey.from_mapping(
        {
            "schema_version": 1,
            "adapter_id": "codex",
            "source_root_id": source_a_id,
        }
    )
    CaptureStore(paths).record_source_quarantine(
        binding_a,
        created_at="2026-08-19T00:00:00Z",
        code="stale_source_diagnostic",
    )
    stale_marker = DirtyMarker.from_mapping(
        {
            "schema_version": 1,
            "adapter_id": "codex",
            "adapter_version": "1.0",
            "source_schema_version": "codex-v1",
            "source_root_id": source_a_id,
            "task_id": "stale-task",
            "revision_id": "stale-revision",
            "locator": None,
            "observed_at": "2026-08-19T00:00:00Z",
            "hook_event": "Stop",
        }
    )
    (paths.capture.dirty / "stale-marker.json").write_text(
        json.dumps(stale_marker.to_mapping()) + "\n", encoding="utf-8"
    )
    source_b = tmp_path / "source-b"
    source_b.mkdir()
    config_path = paths.root / "config.yaml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            source_a.as_posix(), source_b.as_posix()
        ),
        encoding="utf-8",
    )

    status = capture_status(paths)

    assert status["source_roots"]["configured_count"] == 1
    assert status["scanner"]["assessment"] == "absent"
    assert status["scanner"]["source_health"] == "not_assessed"
    assert status["scanner"]["latest_census"] == {
        "assessment": "absent",
        "run_count": 0,
        "key_count": 0,
    }
    assert status["scanner"]["accounting"] == {
        "known_key_count": 0,
        "accounted_key_count": 0,
        "pending_key_count": 0,
        "silent_loss_count": 0,
    }
    assert status["scanner"]["scan_state"]["binding_count"] == 0
    assert status["scanner"]["dirty_marker_count"] == 0


@pytest.mark.skipif(sys.platform != "win32", reason="Windows junction identity")
def test_capture_status_matches_configured_alias_by_canonical_source_id(tmp_path: Path):
    paths, source_root = _configured_status_root(tmp_path)
    _scan(paths)
    alias = tmp_path / "source-alias"
    created = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(alias), str(source_root)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert created.returncode == 0, created.stdout + created.stderr
    config_path = paths.root / "config.yaml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            source_root.as_posix(), alias.as_posix()
        ),
        encoding="utf-8",
    )

    status = capture_status(paths)

    assert status["scanner"]["assessment"] == "ready"
    assert status["scanner"]["latest_census"]["run_count"] == 1
    assert status["scanner"]["accounting"]["known_key_count"] == 1
    assert status["scanner"]["scan_state"]["binding_count"] == 1
