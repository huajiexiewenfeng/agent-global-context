"""Release-verifier integrity and content-free evidence contracts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "verify-capture-release.ps1"
VERIFICATION = (
    ROOT
    / ".llm-wiki"
    / "verification"
    / "2026-08-13-agc-capture-coverage-mvp.md"
)


def _powershell(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT),
            *arguments,
        ],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )


def test_release_verifier_lists_ac_01_through_ac_20_exactly_once():
    result = _powershell("-List")
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    expected = [f"AC-{number:02d}" for number in range(1, 21)]
    assert list(payload) == expected
    assert all(isinstance(payload[gate], list) and payload[gate] for gate in expected)
    rendered = json.dumps(payload)
    assert "verify-capture-release.ps1" not in rendered


def test_single_gate_writes_hashed_content_free_raw_evidence(tmp_path: Path):
    evidence = tmp_path / "release evidence"
    result = _powershell(
        "-Gate",
        "AC-01",
        "-PythonPath",
        str(Path(__import__("sys").executable)),
        "-EvidenceRoot",
        str(evidence),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    manifest = json.loads((evidence / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 1
    assert manifest["requested_gate"] == "AC-01"
    assert manifest["live_profile_gate"] == "pending_explicit_authorization"
    assert [item["gate"] for item in manifest["commands"]] == ["AC-01"]
    for item in manifest["commands"]:
        for stream in ("stdout", "stderr"):
            path = evidence / item[f"{stream}_file"]
            assert hashlib.sha256(path.read_bytes()).hexdigest() == item[f"{stream}_sha256"]
    combined = "".join(
        path.read_text(encoding="utf-8")
        for path in evidence.iterdir()
        if path.suffix in {".txt", ".json"}
    )
    assert "PRIVATE_SENTINEL" not in combined
    assert "transcript" not in combined.casefold()


def test_release_verifier_stops_after_first_nonzero_gate(tmp_path: Path):
    fake = tmp_path / "fake-python.cmd"
    fake.write_text("@echo off\r\necho fixed failure 1>&2\r\nexit /b 7\r\n", encoding="utf-8")
    evidence = tmp_path / "failure"
    result = _powershell(
        "-Gate",
        "All",
        "-PythonPath",
        str(fake),
        "-EvidenceRoot",
        str(evidence),
    )
    assert result.returncode != 0
    manifest = json.loads((evidence / "manifest.json").read_text(encoding="utf-8"))
    assert len(manifest["commands"]) == 1
    assert manifest["commands"][0]["gate"] == "AC-01"
    assert manifest["commands"][0]["exit_code"] == 7


def test_verification_record_has_required_evidence_sections():
    text = VERIFICATION.read_text(encoding="utf-8")
    for heading in (
        "## Production evidence",
        "## Test evidence",
        "## Mock and synthetic boundaries",
        "## Assertions and behavior",
        "## Residual risk",
    ):
        assert heading in text


def test_ac_20_implements_isolated_install_and_all_entrypoint_provenance():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "'package-install'" in text
    assert "'installed-surface'" in text
    assert "--target" in text
    for entrypoint in ("agc", "agc-mcp", "agc-capture", "agc-capture-hook"):
        assert entrypoint in text
    assert "distribution located outside isolated target" in text
    assert '"agent-global-context-runtime"' in text
    assert "[switch]$Resume" in text


def test_ac_20_runs_from_commit_bound_lf_export_with_short_test_root():
    text = SCRIPT.read_text(encoding="utf-8")

    assert "core.autocrlf=false" in text
    assert "RepositoryUnderTest" in text
    assert "VerificationTempRoot" in text
    assert "Split-Path -Parent $ResolvedEvidence" in text
    assert (
        "$VerificationTempRoot = Join-Path (\n"
        "    [System.IO.Path]::GetTempPath()"
    ) not in text
    assert "LF export contains CR bytes" in text
    assert "--basetemp',$fullTemp" in text
    assert "Invoke-RecordedProcess 'AC-20' 'full-suite'" in text
    assert "-WorkingDirectory $RepositoryUnderTest" in text
