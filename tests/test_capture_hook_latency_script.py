"""Installed Capture Hook latency harness contracts."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "measure-capture-hook.ps1"
SENTINEL = "private-hook-payload-must-not-enter-report"


def _launcher(tmp_path: Path, *, exit_code: int = 0) -> Path:
    path = tmp_path / "hook launcher.cmd"
    path.write_text(f"@echo off\r\nexit /b {exit_code}\r\n", encoding="utf-8")
    return path


def _run(
    tmp_path: Path,
    launcher: Path,
    *,
    samples: int,
    timings: list[float] | None = None,
) -> subprocess.CompletedProcess[str]:
    report = tmp_path / "latency report.json"
    runtime = tmp_path / "runtime.bin"
    runtime.write_bytes(b"synthetic-runtime")
    env = os.environ.copy()
    if timings is not None:
        env["AGC_CAPTURE_TEST_SAMPLE_MS"] = ",".join(str(item) for item in timings)
    return subprocess.run(
        [
            "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", str(SCRIPT),
            "-Launcher", str(launcher),
            "-MemoryRoot", str(tmp_path / "synthetic-memory"),
            "-RuntimePath", str(runtime),
            "-OutputPath", str(report),
            "-Samples", str(samples),
        ],
        input=json.dumps({"schema_version": 1, "event": "Stop", "task_id": SENTINEL}),
        text=True,
        encoding="utf-8",
        capture_output=True,
        env=env,
        check=False,
    )


@pytest.mark.parametrize(
    ("timings", "passed"),
    [([99.999] * 1000, True), ([100.0] * 1000, False)],
)
def test_exact_1000_samples_and_strict_p95_boundary(tmp_path, timings, passed):
    launcher = _launcher(tmp_path)
    result = _run(tmp_path, launcher, samples=1000, timings=timings)

    assert result.returncode == (0 if passed else 1), result.stdout + result.stderr
    report_path = tmp_path / "latency report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["sample_count"] == 1000
    assert report["failure_count"] == 0
    assert report["min_ms"] == timings[0]
    assert report["median_ms"] == timings[0]
    assert report["p95_ms"] == timings[0]
    assert report["max_ms"] == timings[-1]
    assert report["passed"] is passed
    assert report["launcher_sha256"] == hashlib.sha256(launcher.read_bytes()).hexdigest()
    assert len(report["runtime_sha256"]) == 64
    assert SENTINEL not in report_path.read_text(encoding="utf-8")


def test_real_launcher_failure_is_reported_content_free(tmp_path):
    launcher = _launcher(tmp_path, exit_code=7)
    result = _run(tmp_path, launcher, samples=3)

    assert result.returncode == 1
    report = json.loads((tmp_path / "latency report.json").read_text(encoding="utf-8"))
    assert report["sample_count"] == 3
    assert report["failure_count"] == 3
    assert report["passed"] is False
    assert SENTINEL not in json.dumps(report)
    assert result.stdout == ""
    assert result.stderr == ""


def test_real_silent_launcher_runs_without_process_failures(tmp_path):
    launcher = _launcher(tmp_path, exit_code=0)
    result = _run(tmp_path, launcher, samples=3)

    assert result.returncode == 1  # Fewer than the required 1,000 samples.
    report = json.loads((tmp_path / "latency report.json").read_text(encoding="utf-8"))
    assert report["failure_count"] == 0
    assert report["sample_count"] == 3


def test_measurement_removes_only_markers_created_by_the_launcher(tmp_path):
    launcher = tmp_path / "marker launcher.cmd"
    launcher.write_text(
        "@echo off\r\n"
        "mkdir \"%~2\\.runtime\\capture\\dirty\" 2>nul\r\n"
        "echo new>\"%~2\\.runtime\\capture\\dirty\\new-marker.json\"\r\n"
        "exit /b 0\r\n",
        encoding="utf-8",
    )
    dirty = tmp_path / "synthetic-memory" / ".runtime" / "capture" / "dirty"
    dirty.mkdir(parents=True)
    existing = dirty / "existing-marker.json"
    existing.write_bytes(b"preserve")

    result = _run(tmp_path, launcher, samples=2)

    assert result.returncode == 1
    assert existing.read_bytes() == b"preserve"
    assert not (dirty / "new-marker.json").exists()


def test_default_sample_contract_and_invalid_paths_fail_before_output(tmp_path):
    script = SCRIPT.read_text(encoding="utf-8")
    assert "[int]$Samples = 1000" in script
    missing = _run(tmp_path, tmp_path / "missing.cmd", samples=1)
    assert missing.returncode == 2
    assert not (tmp_path / "latency report.json").exists()
