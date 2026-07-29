import json
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
    assert "mcp==2.0.0" in project["dependencies"]
    assert project["scripts"]["agc-mcp"] == "agc_runtime.mcp_server:main"
