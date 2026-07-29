import json


def test_version_is_a_stable_json_envelope(run_cli):
    result = run_cli("version")

    assert result.returncode == 0
    assert json.loads(result.stdout) == {
        "schema_version": 2,
        "tool": "agc.admin",
        "action": "version",
        "status": "accepted",
        "data": {"runtime_version": "0.1.0"},
        "warnings": [],
        "error": None,
    }


def test_unknown_tool_is_machine_readable(run_cli):
    result = run_cli("unknown")

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["status"] == "failed"
    assert payload["error"]["code"] == "invalid_tool"
