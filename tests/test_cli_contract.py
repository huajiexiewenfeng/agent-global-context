import json
import subprocess
import sys
import tomllib
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_version_is_a_stable_json_envelope(run_cli):
    result = run_cli("version")

    assert result.returncode == 0
    assert json.loads(result.stdout) == {
        "schema_version": 2,
        "tool": "agc.admin",
        "action": "version",
        "status": "accepted",
        "data": {"runtime_version": "0.2.0"},
        "warnings": [],
        "error": None,
    }


def test_dash_dash_version_is_a_compatible_json_envelope(run_cli):
    result = run_cli("--version")

    assert result.returncode == 0
    assert json.loads(result.stdout) == {
        "schema_version": 2,
        "tool": "agc.admin",
        "action": "version",
        "status": "accepted",
        "data": {"runtime_version": "0.2.0"},
        "warnings": [],
        "error": None,
    }


def test_unknown_tool_is_machine_readable(run_cli):
    result = run_cli("unknown")

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["status"] == "failed"
    assert payload["error"]["code"] == "invalid_tool"


def test_package_exposes_the_pinned_mcp_stdio_entry_point():
    with (REPOSITORY_ROOT / "pyproject.toml").open("rb") as stream:
        project = tomllib.load(stream)["project"]

    assert project["version"] == "0.2.0"
    assert project["dependencies"] == ["PyYAML>=6.0.2,<7"]
    assert project["optional-dependencies"]["mcp"] == ["mcp==2.0.0"]
    assert "mcp==2.0.0" in project["optional-dependencies"]["test"]
    assert project["scripts"]["agc-mcp"] == "agc_runtime.mcp_server:main"


def test_core_cli_import_does_not_require_mcp():
    script = """
import builtins
real_import = builtins.__import__
def reject_mcp(name, *args, **kwargs):
    if name == "mcp" or name.startswith("mcp."):
        raise AssertionError("core CLI imported optional MCP SDK")
    return real_import(name, *args, **kwargs)
builtins.__import__ = reject_mcp
import agc_runtime.cli
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=REPOSITORY_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
