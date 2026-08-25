"""Transactional Windows Host configuration contracts."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPOSITORY_ROOT / "scripts" / "configure-capture-host.ps1"
FIXTURES = REPOSITORY_ROOT / "tests" / "fixtures" / "codex-hooks"


def test_windows_scheduler_registration_errors_are_terminating():
    script = SCRIPT.read_text(encoding="utf-8")

    assert (
        "Register-ScheduledTask -TaskName $taskName -Xml $xml -Force "
        "-ErrorAction Stop | Out-Null"
    ) in script


def _tree(root: Path) -> dict[str, bytes]:
    if not root.exists():
        return {}
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _root_id(path: Path) -> str:
    canonical = str(path.resolve()).lower()
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _host(tmp_path: Path) -> tuple[Path, Path, Path]:
    codex_home = tmp_path / "codex-home"
    memory_root = tmp_path / "memory-root"
    install_root = tmp_path / "install-root"
    (install_root / "bin").mkdir(parents=True)
    codex_home.mkdir()
    shutil.copyfile(FIXTURES / "existing-hooks.json", codex_home / "hooks.json")
    shutil.copyfile(
        FIXTURES / "existing-inline-config.toml", codex_home / "config.toml"
    )
    (install_root / "bin" / "agc-capture.cmd").write_text(
        f'@echo off\r\n"{sys.executable}" -m agc_runtime.capture_cli %*\r\n',
        encoding="utf-8",
    )
    (install_root / "bin" / "agc-capture-hook.cmd").write_text(
        "@echo off\r\nexit /b 0\r\n", encoding="utf-8"
    )
    _write_activation_evidence(install_root)
    return codex_home, memory_root, install_root


def _write_activation_evidence(
    install_root: Path, *, extractor_capability: str = "ready"
) -> Path:
    path = install_root / "activation-evidence.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "effective_v2_skill_count": 1,
                "legacy_v1_skill_count": 0,
                "mcp_block_count": 1,
                "memory_root_count": 1,
                "runtime_hash_matches": True,
                "config_hash_matches": True,
                "recall_gate_passed": True,
                "extractor_capability": extractor_capability,
                "hook_enabled": False,
                "hook_trusted": False,
                "hook_latency_passed": False,
                "scheduler_enabled": True,
                "frozen_census": True,
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return path


def _invoke(
    action: str,
    codex_home: Path,
    memory_root: Path,
    install_root: Path,
    *extra: str,
    inject_failure: str | None = None,
    extractor_capability: str = "ready",
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["AGC_CAPTURE_SCHEDULER_STATE"] = str(install_root / "scheduler-state.json")
    if inject_failure is not None:
        env["AGC_CAPTURE_INJECT_FAILURE"] = inject_failure
    evidence = _write_activation_evidence(
        install_root, extractor_capability=extractor_capability
    )
    return subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT),
            "-Action",
            action,
            "-CodexHome",
            str(codex_home),
            "-MemoryRoot",
            str(memory_root),
            "-InstallRoot",
            str(install_root),
            "-ActivationEvidencePath",
            str(evidence),
            *extra,
        ],
        cwd=REPOSITORY_ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
        env=env,
    )


def test_status_is_content_safe_byte_inert_and_deterministic(tmp_path):
    codex_home, memory_root, install_root = _host(tmp_path)
    before_codex = _tree(codex_home)
    before_install = _tree(install_root)

    first = _invoke("Status", codex_home, memory_root, install_root)
    second = _invoke("Status", codex_home, memory_root, install_root)

    assert first.returncode == 0, first.stdout + first.stderr
    assert second.returncode == 0, second.stdout + second.stderr
    first_json = json.loads(first.stdout)
    second_json = json.loads(second.stdout)
    assert first_json == second_json
    assert first_json["status"] == "accepted"
    assert first_json["data"]["mutation_performed"] is False
    assert first_json["data"]["task_name"] == (
        "AgentGlobalContext-Capture-" + _root_id(memory_root)[:12]
    )
    assert len(first_json["data"]["activation_digest"]) == 64
    rendered = json.dumps(first_json, ensure_ascii=False)
    assert str(codex_home) not in rendered
    assert str(memory_root) not in rendered
    assert str(install_root) not in rendered
    assert _tree(codex_home) == before_codex
    assert _tree(install_root) == before_install
    assert not memory_root.exists()


def test_status_uses_runtime_activation_digest_and_runner_requires_extractor(tmp_path):
    codex_home, memory_root, install_root = _host(tmp_path)
    status = _invoke("Status", codex_home, memory_root, install_root)
    payload = json.loads(status.stdout)
    evidence = install_root / "activation-evidence.json"
    direct = subprocess.run(
        [
            str(install_root / "bin" / "agc-capture.cmd"),
            "activation",
            "--root",
            str(memory_root),
            "--evidence",
            str(evidence),
        ],
        cwd=REPOSITORY_ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )

    assert direct.returncode == 0, direct.stdout + direct.stderr
    assert payload["data"]["activation_digest"] == json.loads(direct.stdout)["data"]["activation_digest"]

    enabled = _invoke(
        "EnableScanner",
        codex_home,
        memory_root,
        install_root,
        "-ExpectedActivationDigest",
        payload["data"]["activation_digest"],
    )
    assert enabled.returncode == 0, enabled.stdout + enabled.stderr
    unavailable_digest = _digest(
        codex_home,
        memory_root,
        install_root,
        extractor_capability="unavailable",
    )
    before = _tree(memory_root)
    runner = _invoke(
        "EnableRunner",
        codex_home,
        memory_root,
        install_root,
        "-ExpectedActivationDigest",
        unavailable_digest,
        "-IncrementalTokenBudget",
        "1000",
        extractor_capability="unavailable",
    )
    assert runner.returncode == 2
    assert json.loads(runner.stdout)["error"]["code"] == "extractor_capability_required"
    assert _tree(memory_root) == before


def test_mutation_without_exact_digest_is_rejected_before_any_write(tmp_path):
    codex_home, memory_root, install_root = _host(tmp_path)
    before = (_tree(codex_home), _tree(install_root), _tree(memory_root))

    missing = _invoke("EnableScanner", codex_home, memory_root, install_root)
    stale = _invoke(
        "EnableScanner",
        codex_home,
        memory_root,
        install_root,
        "-ExpectedActivationDigest",
        "0" * 64,
    )

    assert missing.returncode == 2
    assert json.loads(missing.stdout)["error"]["code"] == "activation_digest_required"
    assert stale.returncode == 2
    assert json.loads(stale.stdout)["error"]["code"] == "activation_digest_mismatch"
    assert (_tree(codex_home), _tree(install_root), _tree(memory_root)) == before


def test_status_rejects_overlapping_or_missing_host_paths(tmp_path):
    codex_home, memory_root, install_root = _host(tmp_path)

    overlap = _invoke("Status", codex_home, codex_home / "memory", install_root)
    missing_launcher = install_root / "bin" / "agc-capture.cmd"
    missing_launcher.unlink()
    missing = _invoke("Status", codex_home, memory_root, install_root)

    assert overlap.returncode == 2
    assert json.loads(overlap.stdout)["error"]["code"] == "host_path_overlap"
    assert missing.returncode == 2
    assert json.loads(missing.stdout)["error"]["code"] == "capture_launcher_missing"


def _digest(
    codex_home: Path,
    memory_root: Path,
    install_root: Path,
    *,
    extractor_capability: str = "ready",
) -> str:
    result = _invoke(
        "Status",
        codex_home,
        memory_root,
        install_root,
        extractor_capability=extractor_capability,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout)["data"]["activation_digest"]


def _latency_args(install_root: Path, *, passed: bool = True, p95_ms: float = 50.0) -> tuple[str, ...]:
    launcher = install_root / "bin" / "agc-capture-hook.cmd"
    report = install_root / "latency-report.json"
    payload = {
        "schema_version": 1,
        "sample_count": 1000,
        "p95_ms": p95_ms,
        "passed": passed,
        "launcher_sha256": hashlib.sha256(launcher.read_bytes()).hexdigest(),
    }
    report.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    digest = hashlib.sha256(report.read_bytes()).hexdigest()
    return "-LatencyReportPath", str(report), "-ExpectedLatencyReportHash", digest


def test_enable_scanner_is_digest_gated_transactional_and_idempotent(tmp_path):
    codex_home, memory_root, install_root = _host(tmp_path)
    hooks_before = (codex_home / "hooks.json").read_bytes()
    inline_before = (codex_home / "config.toml").read_bytes()

    first = _invoke(
        "EnableScanner",
        codex_home,
        memory_root,
        install_root,
        "-ExpectedActivationDigest",
        _digest(codex_home, memory_root, install_root),
    )

    assert first.returncode == 0, first.stdout + first.stderr
    config = (memory_root / "config.yaml").read_text(encoding="utf-8")
    assert "enabled: true" in config
    assert "mode: scanner_only" in config
    assert "paused: false" in config
    assert json.dumps(str(codex_home.resolve())) in config
    scheduler = json.loads((install_root / "scheduler-state.json").read_text(encoding="utf-8"))
    assert scheduler["task_name"].startswith("AgentGlobalContext-Capture-")
    assert scheduler["command"].endswith("agc-capture.cmd")
    assert scheduler["arguments"] == f'cycle --root "{memory_root.resolve()}" --once'
    assert scheduler["multiple_instances"] == "IgnoreNew"
    assert scheduler["start_when_available"] is True
    assert scheduler["triggers"] == ["logon", "repetition:15m"]
    assert (codex_home / "hooks.json").read_bytes() == hooks_before
    assert (codex_home / "config.toml").read_bytes() == inline_before

    config_before = (memory_root / "config.yaml").read_bytes()
    scheduler_before = (install_root / "scheduler-state.json").read_bytes()
    second = _invoke(
        "EnableScanner",
        codex_home,
        memory_root,
        install_root,
        "-ExpectedActivationDigest",
        _digest(codex_home, memory_root, install_root),
    )
    assert second.returncode == 0
    assert (memory_root / "config.yaml").read_bytes() == config_before
    assert (install_root / "scheduler-state.json").read_bytes() == scheduler_before


def test_enable_hook_merges_one_owned_stop_hook_and_preserves_unrelated_config(tmp_path):
    codex_home, memory_root, install_root = _host(tmp_path)
    inline_before = (codex_home / "config.toml").read_bytes()
    scanner = _invoke(
        "EnableScanner",
        codex_home,
        memory_root,
        install_root,
        "-ExpectedActivationDigest",
        _digest(codex_home, memory_root, install_root),
    )
    assert scanner.returncode == 0

    enabled = _invoke(
        "EnableHook",
        codex_home,
        memory_root,
        install_root,
        "-ExpectedActivationDigest",
        _digest(codex_home, memory_root, install_root),
        *_latency_args(install_root),
    )

    assert enabled.returncode == 0, enabled.stdout + enabled.stderr
    hooks = json.loads((codex_home / "hooks.json").read_text(encoding="utf-8"))
    owned = [
        item
        for item in hooks["Stop"]
        if "agc-capture-hook.cmd" in item.get("commandWindows", "")
    ]
    assert len(owned) == 1
    assert owned[0] == {
        "type": "command",
        "command": f'"{install_root.resolve() / "bin" / "agc-capture-hook.cmd"}" --root "{memory_root.resolve()}"',
        "commandWindows": f'"{install_root.resolve() / "bin" / "agc-capture-hook.cmd"}" --root "{memory_root.resolve()}"',
        "async": True,
        "timeout": 5,
    }
    assert hooks["Stop"][0]["command"] == "existing-stop.cmd"
    assert hooks["SessionStart"][0]["command"] == "existing-session.cmd"
    assert (codex_home / "config.toml").read_bytes() == inline_before
    assert "enabled: true" in (memory_root / "config.yaml").read_text(encoding="utf-8")


def test_runner_pause_disable_preserve_capture_data_and_unrelated_host_values(tmp_path):
    codex_home, memory_root, install_root = _host(tmp_path)
    inline_before = (codex_home / "config.toml").read_bytes()
    scanner = _invoke(
        "EnableScanner", codex_home, memory_root, install_root,
        "-ExpectedActivationDigest", _digest(codex_home, memory_root, install_root),
    )
    assert scanner.returncode == 0
    no_budget = _invoke(
        "EnableRunner", codex_home, memory_root, install_root,
        "-ExpectedActivationDigest", _digest(codex_home, memory_root, install_root),
    )
    assert no_budget.returncode == 2
    assert json.loads(no_budget.stdout)["error"]["code"] == "incremental_budget_required"

    runner = _invoke(
        "EnableRunner", codex_home, memory_root, install_root,
        "-ExpectedActivationDigest", _digest(codex_home, memory_root, install_root),
        "-IncrementalTokenBudget", "25000",
    )
    assert runner.returncode == 0, runner.stdout + runner.stderr
    config_path = memory_root / "config.yaml"
    config = config_path.read_text(encoding="utf-8")
    assert "mode: runner" in config
    assert "incremental_total_tokens: 25000" in config
    scheduler = json.loads((install_root / "scheduler-state.json").read_text(encoding="utf-8"))
    assert scheduler["arguments"] == f'cycle --root "{memory_root.resolve()}" --once --max-items 10'

    capture_data = memory_root / ".runtime" / "capture" / "observations" / "keep.json"
    capture_data.parent.mkdir(parents=True)
    capture_data.write_bytes(b'{"sentinel":"preserve"}\n')
    paused = _invoke(
        "Pause", codex_home, memory_root, install_root,
        "-ExpectedActivationDigest", _digest(codex_home, memory_root, install_root),
    )
    assert paused.returncode == 0
    assert "paused: true" in config_path.read_text(encoding="utf-8")
    assert (install_root / "scheduler-state.json").is_file()

    disabled = _invoke(
        "Disable", codex_home, memory_root, install_root,
        "-ExpectedActivationDigest", _digest(codex_home, memory_root, install_root),
    )
    assert disabled.returncode == 0
    disabled_config = config_path.read_text(encoding="utf-8")
    assert "enabled: false" in disabled_config
    assert "mode: off" in disabled_config
    assert "paused: false" in disabled_config
    assert not (install_root / "scheduler-state.json").exists()
    assert capture_data.read_bytes() == b'{"sentinel":"preserve"}\n'
    assert (codex_home / "config.toml").read_bytes() == inline_before


def test_injected_failure_restores_config_hooks_and_scheduler_byte_exact(tmp_path):
    codex_home, memory_root, install_root = _host(tmp_path)
    scanner = _invoke(
        "EnableScanner", codex_home, memory_root, install_root,
        "-ExpectedActivationDigest", _digest(codex_home, memory_root, install_root),
    )
    assert scanner.returncode == 0
    before = (_tree(codex_home), _tree(memory_root), (install_root / "scheduler-state.json").read_bytes())

    failed = _invoke(
        "EnableHook", codex_home, memory_root, install_root,
        "-ExpectedActivationDigest", _digest(codex_home, memory_root, install_root),
        *_latency_args(install_root),
        inject_failure="after_hooks",
    )

    assert failed.returncode == 1
    assert json.loads(failed.stdout)["error"]["code"] == "host_mutation_failed"
    assert (_tree(codex_home), _tree(memory_root), (install_root / "scheduler-state.json").read_bytes()) == before


def test_explicit_rollback_restores_the_latest_successful_action(tmp_path):
    codex_home, memory_root, install_root = _host(tmp_path)
    before = (_tree(codex_home), _tree(memory_root), _tree(install_root))
    enabled = _invoke(
        "EnableScanner", codex_home, memory_root, install_root,
        "-ExpectedActivationDigest", _digest(codex_home, memory_root, install_root),
    )
    assert enabled.returncode == 0
    assert (memory_root / "config.yaml").exists()

    rollback = _invoke(
        "Rollback", codex_home, memory_root, install_root,
        "-ExpectedActivationDigest", _digest(codex_home, memory_root, install_root),
    )

    assert rollback.returncode == 0, rollback.stdout + rollback.stderr
    assert _tree(codex_home) == before[0]
    assert _tree(memory_root) == before[1]
    assert not (install_root / "scheduler-state.json").exists()


def test_hook_preflight_rejects_invalid_policy_and_unknown_conflict(tmp_path):
    codex_home, memory_root, install_root = _host(tmp_path)
    scanner = _invoke(
        "EnableScanner", codex_home, memory_root, install_root,
        "-ExpectedActivationDigest", _digest(codex_home, memory_root, install_root),
    )
    assert scanner.returncode == 0

    hooks_path = codex_home / "hooks.json"
    hooks_path.write_text("{invalid", encoding="utf-8")
    invalid_before = hooks_path.read_bytes()
    invalid = _invoke(
        "EnableHook", codex_home, memory_root, install_root,
        "-ExpectedActivationDigest", _digest(codex_home, memory_root, install_root),
        *_latency_args(install_root),
    )
    assert invalid.returncode == 2
    assert json.loads(invalid.stdout)["error"]["code"] == "invalid_hooks_json"
    assert hooks_path.read_bytes() == invalid_before

    shutil.copyfile(FIXTURES / "existing-hooks.json", hooks_path)
    with (codex_home / "config.toml").open("a", encoding="utf-8") as handle:
        handle.write("\nhooks_enabled = false\n")
    policy = _invoke(
        "EnableHook", codex_home, memory_root, install_root,
        "-ExpectedActivationDigest", _digest(codex_home, memory_root, install_root),
        *_latency_args(install_root),
    )
    assert policy.returncode == 2
    assert json.loads(policy.stdout)["error"]["code"] == "hooks_disabled_by_policy"

    (codex_home / "config.toml").write_bytes(
        (FIXTURES / "existing-inline-config.toml").read_bytes()
    )
    conflict = json.loads((FIXTURES / "existing-hooks.json").read_text(encoding="utf-8"))
    conflict["Stop"].append(
        {
            "type": "command",
            "command": "unknown agc-capture-hook.cmd",
            "commandWindows": "unknown agc-capture-hook.cmd",
            "async": False,
            "timeout": 99,
        }
    )
    hooks_path.write_text(json.dumps(conflict), encoding="utf-8")
    conflict_before = hooks_path.read_bytes()
    blocked = _invoke(
        "EnableHook", codex_home, memory_root, install_root,
        "-ExpectedActivationDigest", _digest(codex_home, memory_root, install_root),
        *_latency_args(install_root),
    )
    assert blocked.returncode == 2
    assert json.loads(blocked.stdout)["error"]["code"] == "conflicting_capture_hook"
    assert hooks_path.read_bytes() == conflict_before


def test_hook_rerun_normalizes_to_exactly_one_owned_definition(tmp_path):
    codex_home, memory_root, install_root = _host(tmp_path)
    scanner = _invoke(
        "EnableScanner", codex_home, memory_root, install_root,
        "-ExpectedActivationDigest", _digest(codex_home, memory_root, install_root),
    )
    assert scanner.returncode == 0
    for _ in range(2):
        result = _invoke(
            "EnableHook", codex_home, memory_root, install_root,
            "-ExpectedActivationDigest", _digest(codex_home, memory_root, install_root),
            *_latency_args(install_root),
        )
        assert result.returncode == 0
    hooks = json.loads((codex_home / "hooks.json").read_text(encoding="utf-8"))
    assert sum("agc-capture-hook.cmd" in item.get("commandWindows", "") for item in hooks["Stop"]) == 1


def test_hook_requires_exact_passing_latency_report_before_backup_or_write(tmp_path):
    codex_home, memory_root, install_root = _host(tmp_path)
    scanner = _invoke(
        "EnableScanner", codex_home, memory_root, install_root,
        "-ExpectedActivationDigest", _digest(codex_home, memory_root, install_root),
    )
    assert scanner.returncode == 0
    before = (_tree(codex_home), _tree(memory_root))
    missing = _invoke(
        "EnableHook", codex_home, memory_root, install_root,
        "-ExpectedActivationDigest", _digest(codex_home, memory_root, install_root),
    )
    assert missing.returncode == 2
    assert json.loads(missing.stdout)["error"]["code"] == "latency_report_required"
    failing = _invoke(
        "EnableHook", codex_home, memory_root, install_root,
        "-ExpectedActivationDigest", _digest(codex_home, memory_root, install_root),
        *_latency_args(install_root, passed=False, p95_ms=100.0),
    )
    assert failing.returncode == 2
    assert json.loads(failing.stdout)["error"]["code"] == "latency_gate_failed"
    assert (_tree(codex_home), _tree(memory_root)) == before
