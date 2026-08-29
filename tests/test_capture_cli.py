"""Contract tests for the explicit one-shot Capture census command."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import socket
import subprocess
import sys

import pytest

from agc_runtime.capture_contracts import CaptureReceipt
from agc_runtime.capture_cli import _extractor_command, _run_runner
from agc_runtime.capture_runner import RunnerReport
from agc_runtime.capture_transaction import read_json
from agc_runtime.paths import MemoryPaths


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SENTINEL = "private-source-text-must-not-cross-census-boundary"


def test_extractor_command_delegates_exact_codex_app_selector(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        "agc_runtime.codex_app_runtime.resolve_codex_app_command",
        lambda: (r"C:\app\codex.exe",),
    )

    assert _extractor_command("codex-app") == (r"C:\app\codex.exe",)


def test_extractor_command_does_not_treat_arguments_as_app_selector():
    assert _extractor_command("codex-app --version") == (
        "codex-app",
        "--version",
    )


def _invoke(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "agc_runtime.capture_cli", *arguments],
        cwd=REPOSITORY_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def _payload(result: subprocess.CompletedProcess[str]) -> dict[str, object]:
    assert result.stderr == ""
    assert len(result.stdout.splitlines()) == 1
    return json.loads(result.stdout)


def _runner_report(**changes: object) -> RunnerReport:
    values: dict[str, object] = {
        "attempted_count": 0,
        "completed_count": 0,
        "failed_count": 0,
        "deferred_budget_count": 0,
        "lease_contention_count": 0,
        "reserved_attempt_count": 0,
        "extractor_call_count": 0,
        "observation_count": 0,
        "charged_tokens": 0,
        "silent_loss_count": 0,
        "backlog_count": 0,
        "oldest_unresolved_at": None,
        "attempt_count_delta": 0,
        "status_deltas": (),
        "run_time_ms": 1,
        "source_bytes_read": 0,
        "peak_process_count": 0,
    }
    values.update(changes)
    return RunnerReport(**values)


def _write_config(
    memory_root: Path,
    source_root: Path,
    *,
    enabled: bool = True,
    mode: str = "scanner_only",
    paused: bool = False,
    excluded_task_ids: tuple[str, ...] = (),
    excluded_project_ids: tuple[str, ...] = (),
) -> None:
    memory_root.mkdir(parents=True, exist_ok=True)
    default = (REPOSITORY_ROOT / "agc_runtime" / "default_config.yaml").read_text(
        encoding="utf-8"
    )
    configured = (
        default.replace("enabled: false", f"enabled: {str(enabled).lower()}", 1)
        .replace("mode: off", f"mode: {mode}", 1)
        .replace("paused: false", f"paused: {str(paused).lower()}", 1)
        .replace("sources: []", f"sources:\n    - {source_root.as_posix()}", 1)
        .replace(
            "task_ids: []",
            "task_ids: " + json.dumps(list(excluded_task_ids)),
            1,
        )
        .replace(
            "project_ids: []",
            "project_ids: " + json.dumps(list(excluded_project_ids)),
            1,
        )
    )
    (memory_root / "config.yaml").write_text(configured, encoding="utf-8")


def _write_completed_task(
    source_root: Path,
    *,
    task_id: str = "task-alpha",
    revision_id: str = "turn-alpha",
) -> None:
    sessions = source_root / "sessions"
    sessions.mkdir(parents=True, exist_ok=True)
    completed_at = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(
        minutes=1
    )
    started_at = completed_at - timedelta(minutes=1)
    records = (
        {
            "timestamp": started_at.isoformat().replace("+00:00", "Z"),
            "type": "session_meta",
            "payload": {
                "id": "rollout-alpha",
                "session_id": task_id,
                "source": "cli",
            },
        },
        {
            "timestamp": started_at.isoformat().replace("+00:00", "Z"),
            "type": "response_item",
            "payload": {"message": SENTINEL},
        },
        {
            "timestamp": completed_at.isoformat().replace("+00:00", "Z"),
            "type": "event_msg",
            "payload": {"type": "task_complete", "turn_id": revision_id},
        },
    )
    (sessions / "synthetic.jsonl").write_text(
        "".join(json.dumps(item) + "\n" for item in records), encoding="utf-8"
    )


def _assert_content_did_not_persist(memory_root: Path) -> None:
    for path in memory_root.rglob("*"):
        if path.is_file():
            assert SENTINEL.encode("utf-8") not in path.read_bytes()


def test_probe_is_read_only_while_disabled_and_imports_no_source_or_scanner(
    tmp_path: Path,
):
    memory_root = tmp_path / "absent-memory"
    blocked = (
        "agc_runtime.capture_source",
        "agc_runtime.capture_scanner",
        "agc_runtime.codex_source_adapter",
    )
    script = f"""
import builtins
import json
real_import = builtins.__import__
blocked = {blocked!r}
def guarded(name, *args, **kwargs):
    if any(name == item or name.startswith(item + '.') for item in blocked):
        raise AssertionError('deferred Capture import')
    return real_import(name, *args, **kwargs)
builtins.__import__ = guarded
from agc_runtime.capture_cli import main
raise SystemExit(main(['probe', '--root', {str(memory_root)!r}]))
"""

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=REPOSITORY_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    payload = _payload(result)
    assert result.returncode == 0
    assert payload["tool"] == "agc.capture"
    assert payload["action"] == "probe"
    assert payload["status"] == "accepted"
    assert payload["data"]["state"]["enabled"] is False
    assert payload["data"]["scanner"]["assessment"] == "not_assessed"
    assert payload["data"]["memory_root"]["assessment"] == "verified"
    assert str(memory_root) not in result.stdout
    assert not memory_root.exists()


@pytest.mark.parametrize("entrypoint", ["status", "probe"])
def test_disabled_configured_status_and_probe_do_not_import_or_touch_sources(
    tmp_path: Path, entrypoint: str
):
    memory_root = tmp_path / "memory"
    source_root = tmp_path / "configured-source"
    source_root.mkdir()
    _write_config(memory_root, source_root, enabled=False, mode="off")
    before = {
        item.relative_to(tmp_path): item.read_bytes()
        for item in tmp_path.rglob("*")
        if item.is_file()
    }
    invocation = (
        f"from agc_runtime.capture_status_service import capture_status\n"
        f"sys.stdout.write(json.dumps(capture_status(Path({str(memory_root)!r}))) + '\\n')"
        if entrypoint == "status"
        else (
            f"from agc_runtime.capture_cli import main\n"
            f"raise SystemExit(main(['probe', '--root', {str(memory_root)!r}]))"
        )
    )
    script = f"""
import builtins
import json
import os
from pathlib import Path
import sys
blocked = ('agc_runtime.capture_source', 'agc_runtime.capture_scanner', 'agc_runtime.codex_source_adapter')
real_import = builtins.__import__
def guarded_import(name, *args, **kwargs):
    if any(name == item or name.startswith(item + '.') for item in blocked):
        raise AssertionError('deferred Capture import')
    return real_import(name, *args, **kwargs)
builtins.__import__ = guarded_import
source = str(Path({str(source_root)!r}))
def guarded(name, original):
    def check(self, *args, **kwargs):
        if str(self) == source or str(self).startswith(source + os.sep):
            raise AssertionError('disabled source filesystem access: ' + name)
        return original(self, *args, **kwargs)
    return check
for name in ('resolve', 'is_dir', 'iterdir', 'glob', 'rglob'):
    setattr(Path, name, guarded(name, getattr(Path, name)))
{invocation}
"""

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=REPOSITORY_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    payload = _payload(result)
    assert result.returncode == 0
    data = payload["data"] if entrypoint == "probe" else payload
    assert data["state"]["enabled"] is False
    assert data["source_roots"]["configured_count"] == 1
    assert data["source_roots"]["assessment"] == "unavailable"
    after = {
        item.relative_to(tmp_path): item.read_bytes()
        for item in tmp_path.rglob("*")
        if item.is_file()
    }
    assert after == before


@pytest.mark.skipif(os.name != "nt", reason="Windows junction identity")
def test_disabled_junction_aliases_remain_inert_but_enabled_activation_deduplicates(
    tmp_path: Path,
):
    memory_root = tmp_path / "memory"
    physical = tmp_path / "physical"
    alias = tmp_path / "alias"
    physical.mkdir()
    created = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(alias), str(physical)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert created.returncode == 0, created.stdout + created.stderr
    default = (REPOSITORY_ROOT / "agc_runtime" / "default_config.yaml").read_text(
        encoding="utf-8"
    )
    configured = default.replace(
        "sources: []",
        f"sources:\n    - {physical.as_posix()}\n    - {alias.as_posix()}",
    )
    memory_root.mkdir()
    (memory_root / "config.yaml").write_text(configured, encoding="utf-8")
    script = f"""
import builtins
import json
from pathlib import Path
blocked = ('agc_runtime.capture_source', 'agc_runtime.capture_scanner', 'agc_runtime.codex_source_adapter')
real_import = builtins.__import__
def guarded(name, *args, **kwargs):
    if any(name == item or name.startswith(item + '.') for item in blocked):
        raise AssertionError('deferred Capture import')
    return real_import(name, *args, **kwargs)
builtins.__import__ = guarded
from agc_runtime.capture_status_service import capture_status
print(json.dumps(capture_status(Path({str(memory_root)!r}))))
"""

    disabled = subprocess.run(
        [sys.executable, "-c", script], cwd=REPOSITORY_ROOT,
        text=True, capture_output=True, check=False,
    )
    assert disabled.returncode == 0, disabled.stdout + disabled.stderr
    assert json.loads(disabled.stdout)["source_roots"]["configured_count"] == 2

    (memory_root / "config.yaml").write_text(
        configured.replace("enabled: false", "enabled: true", 1).replace(
            "mode: off", "mode: scanner_only", 1
        ),
        encoding="utf-8",
    )
    enabled = _invoke("probe", "--root", str(memory_root))
    assert enabled.returncode != 0
    assert _payload(enabled)["error"]["code"] == "invalid_runtime_config"


@pytest.mark.parametrize(
    ("arguments", "code"),
    [
        (("scan", "--root", "ROOT", "--mode", "census"), "invalid_invocation"),
        (("cycle", "--root", "ROOT"), "invalid_invocation"),
        (("scan", "--root", "ROOT", "--mode", "runner", "--once"), "invalid_invocation"),
        (("scan", "--root", "ROOT", "--mode", "census", "--once", "--source-root", SENTINEL), "invalid_invocation"),
    ],
)
def test_invalid_or_expansive_forms_emit_one_content_safe_failure(
    tmp_path: Path, arguments: tuple[str, ...], code: str
):
    memory_root = tmp_path / "memory"
    concrete = tuple(str(memory_root) if item == "ROOT" else item for item in arguments)

    result = _invoke(*concrete)

    payload = _payload(result)
    assert result.returncode != 0
    assert payload["status"] == "failed"
    assert payload["error"]["code"] == code
    assert SENTINEL not in result.stdout
    assert str(memory_root) not in result.stdout
    assert not memory_root.exists()


def test_scan_refuses_disabled_capture_without_mutation(tmp_path: Path):
    memory_root = tmp_path / "memory"

    result = _invoke("scan", "--root", str(memory_root), "--mode", "census", "--once")

    payload = _payload(result)
    assert result.returncode != 0
    assert payload["error"]["code"] == "capture_disabled"
    assert not memory_root.exists()


@pytest.mark.parametrize(
    ("mode", "paused", "expected_code"),
    [
        ("runner", False, "capture_runner_unsupported"),
        ("scanner_only", True, "capture_paused"),
    ],
)
def test_scan_refuses_runner_and_paused_configuration(
    tmp_path: Path, mode: str, paused: bool, expected_code: str
):
    memory_root = tmp_path / "memory"
    source_root = tmp_path / "source"
    source_root.mkdir()
    _write_config(memory_root, source_root, mode=mode, paused=paused)
    before = {item.relative_to(tmp_path): item.read_bytes() for item in tmp_path.rglob("*") if item.is_file()}

    result = _invoke("cycle", "--root", str(memory_root), "--once")

    payload = _payload(result)
    assert result.returncode != 0
    assert payload["error"]["code"] == expected_code
    after = {item.relative_to(tmp_path): item.read_bytes() for item in tmp_path.rglob("*") if item.is_file()}
    assert after == before


def test_census_incremental_and_cycle_are_one_shot_scanner_only_flows(tmp_path: Path):
    memory_root = tmp_path / "memory"
    source_root = tmp_path / "source"
    _write_completed_task(source_root)
    _write_config(memory_root, source_root)

    census = _invoke("scan", "--root", str(memory_root), "--mode", "census", "--once")
    incremental = _invoke(
        "scan", "--root", str(memory_root), "--mode", "incremental", "--once"
    )
    cycle = _invoke("cycle", "--root", str(memory_root), "--once")

    census_payload = _payload(census)
    incremental_payload = _payload(incremental)
    cycle_payload = _payload(cycle)
    assert (census.returncode, incremental.returncode, cycle.returncode) == (0, 0, 0)
    assert census_payload["data"]["scan"]["known_key_count"] == 1
    assert census_payload["data"]["scan"]["accounted_key_count"] == 1
    assert census_payload["data"]["scan"]["silent_loss_count"] == 0
    assert incremental_payload["data"]["scan"]["replay_count"] == 1
    assert cycle_payload["data"]["scan"]["replay_count"] == 1
    assert cycle_payload["data"]["mode"] == "incremental"
    assert all(SENTINEL not in item.stdout for item in (census, incremental, cycle))
    assert all(str(source_root) not in item.stdout for item in (census, incremental, cycle))
    _assert_content_did_not_persist(memory_root)


def test_validated_task_exclusion_applies_on_first_discovery_without_project_guess(
    tmp_path: Path,
):
    memory_root = tmp_path / "memory"
    source_root = tmp_path / "source"
    _write_completed_task(source_root, task_id="task-excluded")
    _write_config(
        memory_root,
        source_root,
        excluded_task_ids=("task-excluded",),
        excluded_project_ids=("project-unavailable",),
    )

    result = _invoke("scan", "--root", str(memory_root), "--mode", "census", "--once")

    payload = _payload(result)
    assert result.returncode == 0
    assert payload["data"]["exclusions"] == {
        "task_id_count": 1,
        "project_id_count": 1,
        "project_id_assessment": "not_assessed",
    }
    receipt_files = tuple(MemoryPaths.from_root(memory_root).capture.receipts.glob("*.json"))
    assert len(receipt_files) == 1
    receipt = CaptureReceipt.from_mapping(read_json(receipt_files[0]))
    assert receipt.status == "excluded"
    assert receipt.exclusion_reason == "configured_task_exclusion"


def test_scan_busy_and_invalid_config_fail_with_fixed_content_safe_codes(tmp_path: Path):
    from agc_runtime.locking import capture_write_lock

    memory_root = tmp_path / "memory"
    source_root = tmp_path / "source"
    _write_completed_task(source_root)
    _write_config(memory_root, source_root)
    paths = MemoryPaths.from_root(memory_root)
    with capture_write_lock(paths):
        busy = _invoke("cycle", "--root", str(memory_root), "--once")
        busy_probe = _invoke("probe", "--root", str(memory_root))
    busy_payload = _payload(busy)
    assert busy.returncode != 0
    assert busy_payload["error"]["code"] == "capture_busy"
    busy_probe_payload = _payload(busy_probe)
    assert busy_probe.returncode != 0
    assert busy_probe_payload["error"]["code"] == "capture_busy"

    scanned = _invoke("cycle", "--root", str(memory_root), "--once")
    assert scanned.returncode == 0, scanned.stdout
    run_file = next((paths.capture.root / "census-runs").glob("*/run.json"))
    run_file.write_text('{"private":"must-not-leak"}\n', encoding="utf-8")
    corrupt_probe = _invoke("probe", "--root", str(memory_root))
    corrupt_probe_payload = _payload(corrupt_probe)
    assert corrupt_probe.returncode != 0
    assert corrupt_probe_payload["error"]["code"] == "scanner_corrupt"
    assert "private" not in corrupt_probe.stdout

    (memory_root / "config.yaml").write_text(
        f"invalid: {SENTINEL}\n", encoding="utf-8"
    )
    invalid = _invoke("cycle", "--root", str(memory_root), "--once")
    invalid_payload = _payload(invalid)
    assert invalid.returncode != 0
    assert invalid_payload["error"]["code"] == "invalid_runtime_config"
    assert SENTINEL not in invalid.stdout
    assert str(memory_root) not in invalid.stdout


def test_scan_does_not_expose_model_daemon_or_semantic_request_surface(tmp_path: Path):
    memory_root = tmp_path / "memory"
    for option in ("--model", "--daemon", "--capsule", "--source-root"):
        result = _invoke(
            "scan",
            "--root",
            str(memory_root),
            "--mode",
            "census",
            "--once",
            option,
            SENTINEL,
        )
        payload = _payload(result)
        assert result.returncode != 0
        assert payload["error"]["code"] == "invalid_invocation"
        assert SENTINEL not in result.stdout


def test_activation_cli_uses_exact_runtime_digest_and_rejects_invalid_evidence(
    tmp_path: Path,
):
    from agc_runtime.capture_activation import (
        ActivationEvidence,
        activation_digest_for,
        diagnose_activation,
    )
    from agc_runtime.capture_status_service import bind_capture_status, capture_status

    memory_root = tmp_path / "memory"
    evidence_mapping = {
        "schema_version": 1,
        "effective_v2_skill_count": 1,
        "legacy_v1_skill_count": 0,
        "mcp_block_count": 1,
        "memory_root_count": 1,
        "runtime_hash_matches": True,
        "config_hash_matches": True,
        "recall_gate_passed": True,
        "extractor_capability": "ready",
        "hook_enabled": False,
        "hook_trusted": False,
        "hook_latency_passed": False,
        "scheduler_enabled": False,
        "frozen_census": False,
    }
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(json.dumps(evidence_mapping), encoding="utf-8")

    result = _invoke(
        "activation",
        "--root",
        str(memory_root),
        "--evidence",
        str(evidence_path),
    )
    payload = _payload(result)
    status = bind_capture_status(
        capture_status(memory_root), evidence_kind="capture_cli_root"
    )
    expected = activation_digest_for(
        diagnose_activation(status, ActivationEvidence.from_mapping(evidence_mapping))
    )
    assert result.returncode == 0
    assert payload["data"]["activation_digest"] == expected

    evidence_path.write_text('{"private":"must-not-leak"}', encoding="utf-8")
    invalid = _invoke(
        "activation",
        "--root",
        str(memory_root),
        "--evidence",
        str(evidence_path),
    )
    assert invalid.returncode != 0
    assert _payload(invalid)["error"]["code"] == "invalid_activation_evidence"
    assert "private" not in invalid.stdout


@pytest.mark.parametrize("action", ["run", "cycle"])
def test_runner_success_exposes_disabled_trace_status_without_changing_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    action: str,
) -> None:
    memory_root = tmp_path / "memory"
    source_root = tmp_path / "source"
    source_root.mkdir()
    _write_config(memory_root, source_root, mode="runner")
    report = _runner_report(completed_count=1)
    monkeypatch.delenv("AGENT_TRACE_DB", raising=False)
    monkeypatch.setattr(
        "agc_runtime.capture_runner.CaptureRunner.run_once",
        lambda self, **kwargs: report,
    )

    exit_code = _run_runner(
        MemoryPaths.from_root(memory_root),
        action=action,
        maximum=1,
        scan_first=False,
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["status"] == "accepted"
    assert payload["data"]["completed_count"] == 1
    assert payload["data"]["trace_status"] == "disabled"


def test_runner_failure_exposes_trace_status_without_changing_sanitized_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    memory_root = tmp_path / "memory"
    source_root = tmp_path / "source"
    source_root.mkdir()
    _write_config(memory_root, source_root, mode="runner")
    monkeypatch.delenv("AGENT_TRACE_DB", raising=False)

    def fail_runner(*args: object, **kwargs: object) -> RunnerReport:
        raise RuntimeError("capture_extractor_unavailable")

    monkeypatch.setattr(
        "agc_runtime.capture_runner.CaptureRunner.run_once",
        fail_runner,
    )

    exit_code = _run_runner(
        MemoryPaths.from_root(memory_root),
        action="cycle",
        maximum=1,
        scan_first=False,
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["status"] == "failed"
    assert payload["error"] == {
        "code": "capture_extractor_unavailable",
        "message": "Capture Runner did not start",
    }
    assert payload["data"] == {"trace_status": "disabled"}


def test_runner_passes_timezone_aware_datetime_to_trace_bridge(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    memory_root = tmp_path / "memory"
    source_root = tmp_path / "source"
    source_root.mkdir()
    _write_config(memory_root, source_root, mode="runner")
    report = _runner_report(completed_count=1)
    observed: dict[str, object] = {}
    monkeypatch.setattr(
        "agc_runtime.capture_runner.CaptureRunner.run_once",
        lambda self, **kwargs: report,
    )

    def record(**values: object) -> str:
        observed.update(values)
        return "recorded"

    monkeypatch.setattr("agc_runtime.capture_cli.record_capture_success", record)

    exit_code = _run_runner(
        MemoryPaths.from_root(memory_root),
        action="cycle",
        maximum=1,
        scan_first=False,
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["data"]["trace_status"] == "recorded"
    assert isinstance(observed["started_at"], datetime)
    assert observed["started_at"].tzinfo is not None
    assert observed["started_at"].utcoffset() is not None
