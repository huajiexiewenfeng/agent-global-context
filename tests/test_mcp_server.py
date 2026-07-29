import asyncio
import importlib
import json

import pytest


def _mcp_server_module():
    try:
        return importlib.import_module("agc_runtime.mcp_server")
    except ModuleNotFoundError as error:
        if error.name != "agc_runtime.mcp_server":
            raise
        pytest.fail("agc_runtime.mcp_server is not implemented")


def _list_tools(server):
    return asyncio.run(server.list_tools())


def _call(server, name: str, request: dict) -> dict:
    result = asyncio.run(server.call_tool(name, {"request": request}))
    assert result.is_error is False
    assert result.content
    return json.loads(result.content[0].text)


def test_server_exposes_exactly_three_host_bound_tools(tmp_path):
    mcp_server_module = _mcp_server_module()
    server = mcp_server_module.create_server(tmp_path / "memory")
    tools = _list_tools(server)

    assert {tool.name for tool in tools} == {
        "agc.read",
        "agc.write",
        "agc.admin",
    }
    for tool in tools:
        assert set(tool.input_schema["properties"]) == {"request"}
        assert tool.input_schema["required"] == ["request"]
        assert tool.input_schema["properties"]["request"]["type"] == "object"


def test_admin_uses_the_host_bound_root_not_request_data(tmp_path):
    mcp_server_module = _mcp_server_module()
    memory_root = tmp_path / "bound-memory"
    rogue_root = tmp_path / "request-memory"
    server = mcp_server_module.create_server(memory_root)

    response = _call(
        server,
        "agc.admin",
        {"action": "init", "root": str(rogue_root)},
    )

    assert response["schema_version"] == 2
    assert response["tool"] == "agc.admin"
    assert response["action"] == "init"
    assert response["status"] == "accepted"
    assert (memory_root / "schema-version").read_text(encoding="utf-8") == "2\n"
    assert not rogue_root.exists()


def test_read_returns_the_runtime_schema_v2_envelope(tmp_path):
    mcp_server_module = _mcp_server_module()
    server = mcp_server_module.create_server(tmp_path / "memory")
    _call(server, "agc.admin", {"action": "init"})

    response = _call(server, "agc.read", {"action": "overview"})

    assert response["schema_version"] == 2
    assert response["tool"] == "agc.read"
    assert response["action"] == "overview"
    assert response["status"] == "accepted"
    assert set(response) == {
        "schema_version",
        "tool",
        "action",
        "status",
        "data",
        "warnings",
        "error",
    }


def test_main_refuses_to_start_without_memory_root(monkeypatch):
    mcp_server_module = _mcp_server_module()
    monkeypatch.delenv("AGC_MEMORY_ROOT", raising=False)

    with pytest.raises(RuntimeError, match="AGC_MEMORY_ROOT is required"):
        mcp_server_module.main()


def test_request_body_is_not_logged_to_stdout(tmp_path, capsys):
    mcp_server_module = _mcp_server_module()
    server = mcp_server_module.create_server(tmp_path / "memory")
    marker = "request-body-must-remain-private-74f9"

    _call(server, "agc.read", {"action": "unsupported", "marker": marker})

    captured = capsys.readouterr()
    assert marker not in captured.out
    assert captured.out == ""
