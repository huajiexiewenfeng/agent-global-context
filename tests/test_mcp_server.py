import asyncio
import importlib
import json
import sys

import pytest

from agc_runtime.admin_service import dispatch_admin
from agc_runtime.capture_store import root_fingerprint
from agc_runtime.capture_contracts import (
    CAPTURE_SCHEMA_VERSION,
    CaptureKey,
    CaptureReceipt,
    CollectedObservation,
    TokenUsage,
    observation_fingerprint_for,
    observation_id_for,
    receipt_id_for,
)
from agc_runtime.capture_store import CaptureStore
from agc_runtime.paths import MemoryPaths


UTC = "2026-08-13T12:00:00Z"


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


def _seed_visible_capture(paths: MemoryPaths) -> CollectedObservation:
    key = CaptureKey("synthetic_adapter", "1" * 64, "task-1", "revision-1")
    receipt = CaptureReceipt.from_mapping({
        "schema_version": CAPTURE_SCHEMA_VERSION,
        "receipt_id": receipt_id_for(key),
        **key.to_mapping(),
        "adapter_version": "1",
        "source_schema_version": "1",
        "identity_quality": "session_id",
        "source_fingerprint": "b" * 64,
        "source_hash_schema_version": "source-v1",
        "capsule_hash": "c" * 64,
        "capsule_schema_version": "capsule-v1",
        "settled_at": UTC,
        "discovered_at": UTC,
        "updated_at": UTC,
        "status": "extracting",
        "attempt_count": 1,
        "next_retry_at": None,
        "extractor_id": "synthetic",
        "extractor_version": "1",
        "extractor_schema_version": "1",
        "taxonomy_version": "taxonomy-v1",
        "observation_count": None,
        "filtered_counts": None,
        "duplicate_suppression_count": None,
        "token_usage": TokenUsage(1, 2, 3).to_mapping(),
        "usage_quality": "actual",
        "redacted_by_forget": False,
        "forgotten_observation_count": 0,
        "zero_reason": None,
        "sanitized_error": None,
        "coalesced_to": None,
        "exclusion_reason": None,
    })
    observation_value = {
        "schema_version": CAPTURE_SCHEMA_VERSION,
        "observation_id": "co_" + "0" * 64,
        "receipt_id": receipt.receipt_id,
        "source": {**key.to_mapping(), "locator": "sessions/synthetic"},
        "ordinal": 0,
        "observation_fingerprint": "0" * 64,
        "statement": "Synthetic MCP-visible observation.",
        "assertion": {"subject": "user", "mode": "direct", "modality": "asserted"},
        "primary_category": "work",
        "taxonomy_version": "taxonomy-v1",
        "kind": "preference",
        "scopes": ["testing"],
        "project_scope": None,
        "confidence": "observed",
        "sensitivity": "normal",
        "signal_type": "decision_or_constraint",
        "observed_at": UTC,
        "captured_at": UTC,
        "extractor_version": "1",
        "processing_state": "collected",
    }
    observation_value["observation_fingerprint"] = observation_fingerprint_for(observation_value)
    observation_value["observation_id"] = observation_id_for(
        receipt.receipt_id, observation_value["observation_fingerprint"]
    )
    observation = CollectedObservation.from_mapping(observation_value)
    complete = CaptureReceipt.from_mapping({
        **receipt.to_mapping(),
        "status": "complete",
        "observation_count": 1,
        "filtered_counts": {"safety": 0, "policy": 0, "over_limit": 0},
        "duplicate_suppression_count": 0,
    })
    store = CaptureStore(paths, clock=lambda: UTC)
    store.register_extraction(receipt)
    lease = store.acquire_lease(key, owner_id="mcp-test", now=UTC, ttl_seconds=60)
    assert lease is not None
    store.commit_extraction(lease, (observation,), complete)
    return observation


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


def test_main_version_probe_does_not_start_stdio(monkeypatch, capsys):
    mcp_server_module = _mcp_server_module()
    monkeypatch.delenv("AGC_MEMORY_ROOT", raising=False)

    exit_code = mcp_server_module.main(["--version"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out == "0.4.0\n"
    assert captured.err == ""


def test_main_starts_stdio_without_stdout_contamination(
    tmp_path, monkeypatch, capsys
):
    mcp_server_module = _mcp_server_module()
    calls = []

    class Server:
        def run(self, *, transport):
            calls.append(transport)

    memory_root = tmp_path / "memory"
    monkeypatch.setenv("AGC_MEMORY_ROOT", str(memory_root))
    monkeypatch.setattr(
        mcp_server_module,
        "create_server",
        lambda root: calls.append(root) or Server(),
    )

    mcp_server_module.main()

    captured = capsys.readouterr()
    assert calls == [memory_root, "stdio"]
    assert captured.out == ""


def test_request_body_is_not_logged_to_stdout(tmp_path, capsys):
    mcp_server_module = _mcp_server_module()
    server = mcp_server_module.create_server(tmp_path / "memory")
    marker = "request-body-must-remain-private-74f9"

    _call(server, "agc.read", {"action": "unsupported", "marker": marker})

    captured = capsys.readouterr()
    assert marker not in captured.out
    assert captured.out == ""


def test_capture_actions_use_existing_three_tool_envelope(tmp_path):
    mcp_server_module = _mcp_server_module()
    server = mcp_server_module.create_server(tmp_path / "memory")

    read = _call(server, "agc.read", {"action": "capture_overview"})
    admin = _call(server, "agc.admin", {"action": "capture_status"})

    assert read["status"] == "accepted"
    assert read["action"] == "capture_overview"
    assert admin["status"] == "accepted"
    assert admin["action"] == "capture_status"
    assert {tool.name for tool in _list_tools(server)} == {"agc.read", "agc.write", "agc.admin"}


def test_mcp_capture_status_proves_only_the_bound_memory_root(tmp_path):
    mcp_server_module = _mcp_server_module()
    memory_root = tmp_path / "bound-memory"
    rogue_root = tmp_path / "rogue-memory"
    server = mcp_server_module.create_server(memory_root)
    _call(server, "agc.admin", {"action": "init"})

    response = _call(
        server,
        "agc.admin",
        {"action": "capture_status", "root": str(rogue_root)},
    )
    data = response["data"]
    direct = dispatch_admin(MemoryPaths.from_root(memory_root), {"action": "capture_status"})

    assert data["memory_root"]["fingerprint"] == root_fingerprint(MemoryPaths.from_root(memory_root))
    assert data["memory_root"]["assessment"] == "verified"
    assert data["memory_root"]["matches_host_binding"] is True
    assert data["memory_root"]["evidence"] == {"kind": "mcp_memory_root"}
    assert "memory_root_binding_not_assessed" not in data["activation_reasons"]
    assert "memory_root_binding_not_assessed" not in data["scanner"]["operation_reasons"]
    assert {
        "capture_disabled",
        "capture_mode_off",
        "source_roots_unavailable",
        "extractor_capability_not_assessed",
        "route_not_assessed",
    }.issubset(data["activation_reasons"])
    assert data["activation_ready"] is False
    assert data["route"]["assessment"] == "not_assessed"
    assert data["extractor_boundary"]["capability_assessment"] == "not_assessed"
    assert data["cursor_key"]["state"] == "ready"
    assert len(data["cursor_key"]["key_id"]) == 64
    assert direct.data["memory_root"]["fingerprint"] == data["memory_root"]["fingerprint"]
    assert direct.data["memory_root"]["assessment"] == "not_assessed"
    assert MemoryPaths.from_root(memory_root).capture.cursor_hmac_key.read_bytes().hex() not in str(data)
    assert str(memory_root) not in str(data)
    assert str(rogue_root) not in str(data)
    assert not rogue_root.exists()


def test_mcp_bound_status_recomputes_scanner_eligibility_but_direct_status_does_not(
    tmp_path,
):
    mcp_server_module = _mcp_server_module()
    memory_root = tmp_path / "bound-memory"
    rogue_root = tmp_path / "rogue-memory"
    source_root = tmp_path / "synthetic-source"
    source_root.mkdir()
    server = mcp_server_module.create_server(memory_root)
    _call(server, "agc.admin", {"action": "init"})
    config_path = memory_root / "config.yaml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8")
        .replace("enabled: false", "enabled: true", 1)
        .replace("mode: off", "mode: scanner_only", 1)
        .replace("sources: []", f"sources:\n    - {source_root.as_posix()}", 1),
        encoding="utf-8",
    )

    mcp = _call(
        server,
        "agc.admin",
        {"action": "capture_status", "root": str(rogue_root)},
    )
    direct = dispatch_admin(
        MemoryPaths.from_root(memory_root), {"action": "capture_status"}
    )

    assert mcp["data"]["scanner"]["operation_eligible"] is True
    assert mcp["data"]["scanner"]["operation_reasons"] == []
    assert direct.data["scanner"]["operation_eligible"] is False
    assert direct.data["scanner"]["operation_reasons"] == [
        "memory_root_binding_not_assessed"
    ]
    assert {tool.name for tool in _list_tools(server)} == {
        "agc.read",
        "agc.write",
        "agc.admin",
    }
    assert str(memory_root) not in str(mcp)
    assert str(source_root) not in str(mcp)
    assert str(rogue_root) not in str(mcp)
    assert not rogue_root.exists()


def test_mcp_capture_search_and_get_use_bound_root_and_safe_machine_errors(tmp_path):
    mcp_server_module = _mcp_server_module()
    memory_root = tmp_path / "bound-memory"
    rogue_root = tmp_path / "rogue-memory"
    paths = MemoryPaths.from_root(memory_root)
    observation = _seed_visible_capture(paths)
    server = mcp_server_module.create_server(memory_root)

    search = _call(
        server,
        "agc.read",
        {"action": "capture_search", "limit": 1, "root": str(rogue_root)},
    )
    get = _call(
        server,
        "agc.read",
        {"action": "capture_get", "observation_id": observation.observation_id, "root": str(rogue_root)},
    )
    missing = _call(
        server,
        "agc.read",
        {"action": "capture_get", "observation_id": "co_" + "f" * 64},
    )

    assert search["status"] == "accepted"
    assert search["data"]["results"][0]["observation_id"] == observation.observation_id
    assert get["status"] == "accepted"
    assert get["data"]["observation"]["statement"] == observation.statement
    assert missing["status"] == "failed"
    assert missing["error"] == {
        "code": "capture_not_found",
        "message": "Capture object is not available",
    }
    assert str(memory_root) not in str(missing)
    assert str(rogue_root) not in str(search) + str(get) + str(missing)
    assert not rogue_root.exists()
