"""End-to-end release proof for the disabled Capture core."""

from __future__ import annotations

import builtins
import hashlib
import importlib
import json
import os
import socket
import sys
import urllib.request
from pathlib import Path
from typing import Any

UTC = "2026-08-13T12:00:00Z"
SOURCE_ROOT_ID = "1" * 64
DEFERRED_RUNTIME_MODULES = (
    "agc_runtime.capture_source",
    "agc_runtime.project_identity",
    "agc_runtime.codex_source_adapter",
    "agc_runtime.capture_scanner",
    "agc_runtime.capture_capsule",
    "agc_runtime.capture_safety",
    "agc_runtime.capture_extractor",
    "agc_runtime.codex_extractor",
    "agc_runtime.capture_budget",
    "agc_runtime.capture_runner",
    "agc_runtime.capture_cli",
    "agc_runtime.capture_hook",
)


def _key(
    task_id: str = "synthetic-task", revision_id: str = "revision-1"
) -> CaptureKey:
    from agc_runtime.capture_contracts import CaptureKey

    return CaptureKey(
        "synthetic_adapter", SOURCE_ROOT_ID, task_id, revision_id
    )


def _receipt(key: CaptureKey) -> CaptureReceipt:
    from agc_runtime.capture_contracts import (
        CAPTURE_SCHEMA_VERSION,
        CaptureReceipt,
        TokenUsage,
        receipt_id_for,
    )

    return CaptureReceipt.from_mapping(
        {
            "schema_version": CAPTURE_SCHEMA_VERSION,
            "receipt_id": receipt_id_for(key),
            **key.to_mapping(),
            "adapter_version": "1",
            "source_schema_version": "1",
            "identity_quality": "session_id",
            "source_fingerprint": "a" * 64,
            "source_hash_schema_version": "source-v1",
            "capsule_hash": "b" * 64,
            "capsule_schema_version": "capsule-v1",
            "settled_at": UTC,
            "discovered_at": UTC,
            "updated_at": UTC,
            "status": "extracting",
            "attempt_count": 1,
            "next_retry_at": None,
            "extractor_id": "synthetic_only",
            "extractor_version": "1",
            "extractor_schema_version": "1",
            "taxonomy_version": "taxonomy-v1",
            "observation_count": None,
            "filtered_counts": None,
            "duplicate_suppression_count": None,
            "token_usage": TokenUsage(0, 0, 0).to_mapping(),
            "usage_quality": "actual",
            "redacted_by_forget": False,
            "forgotten_observation_count": 0,
            "zero_reason": None,
            "sanitized_error": None,
            "coalesced_to": None,
            "exclusion_reason": None,
        }
    )


def _observation(
    receipt: CaptureReceipt, *, ordinal: int, statement: str
) -> CollectedObservation:
    from agc_runtime.capture_contracts import (
        CAPTURE_SCHEMA_VERSION,
        CollectedObservation,
        observation_fingerprint_for,
        observation_id_for,
    )

    value: dict[str, Any] = {
        "schema_version": CAPTURE_SCHEMA_VERSION,
        "observation_id": "co_" + "0" * 64,
        "receipt_id": receipt.receipt_id,
        "source": {**receipt.key.to_mapping(), "locator": "synthetic/only"},
        "ordinal": ordinal,
        "observation_fingerprint": "0" * 64,
        "statement": statement,
        "assertion": {
            "subject": "user",
            "mode": "direct",
            "modality": "asserted",
        },
        "primary_category": "work",
        "taxonomy_version": "taxonomy-v1",
        "kind": "preference",
        "scopes": ["testing"],
        "project_scope": "synthetic-project",
        "confidence": "observed",
        "sensitivity": "normal",
        "signal_type": "decision_or_constraint",
        "observed_at": UTC,
        "captured_at": UTC,
        "extractor_version": "1",
        "processing_state": "collected",
    }
    value["observation_fingerprint"] = observation_fingerprint_for(value)
    value["observation_id"] = observation_id_for(
        receipt.receipt_id, value["observation_fingerprint"]
    )
    return CollectedObservation.from_mapping(value)


def _complete(
    receipt: CaptureReceipt, observations: tuple[CollectedObservation, ...]
) -> CaptureReceipt:
    from agc_runtime.capture_contracts import CaptureReceipt

    return CaptureReceipt.from_mapping(
        {
            **receipt.to_mapping(),
            "status": "complete",
            "observation_count": len(observations),
            "filtered_counts": {"safety": 0, "policy": 0, "over_limit": 0},
            "duplicate_suppression_count": 0,
            "zero_reason": None,
        }
    )


def _catalog_state(paths: MemoryPaths) -> tuple[str, int]:
    catalog_json = paths.catalog_json.read_bytes()
    catalog_markdown = paths.catalog_md.read_bytes()
    digest = hashlib.sha256(catalog_json + b"\0" + catalog_markdown).hexdigest()
    memory_count = json.loads(catalog_json.decode("utf-8"))["memory_count"]
    return digest, memory_count


def _assert_catalog_unchanged(
    paths: MemoryPaths, baseline: tuple[str, int]
) -> None:
    from agc_runtime.admin_service import dispatch_admin
    from agc_runtime.read_service import dispatch_read

    assert dispatch_admin(paths, {"action": "validate"}).status == "accepted"
    assert _catalog_state(paths) == baseline
    overview = dispatch_read(paths, {"action": "overview"})
    assert overview.status == "accepted"
    assert overview.data["memory_count"] == baseline[1]


def _guard_disabled_boundary(
    monkeypatch, source_root: Path
) -> tuple[list[str], list[str], list[str], list[str]]:
    process_calls: list[str] = []
    source_imports: list[str] = []
    source_enumerations: list[str] = []
    external_calls: list[str] = []
    assert set(DEFERRED_RUNTIME_MODULES).isdisjoint(sys.modules)

    def reject_process(name: str):
        def rejected(*_args, **_kwargs):
            process_calls.append(name)
            raise AssertionError(f"disabled Capture invoked subprocess.{name}")

        return rejected

    subprocess_module = sys.modules["subprocess"]
    for name in ("Popen", "run", "call", "check_call", "check_output"):
        monkeypatch.setattr(subprocess_module, name, reject_process(name))

    original_import = builtins.__import__

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        if any(
            name == blocked or name.startswith(blocked + ".")
            for blocked in DEFERRED_RUNTIME_MODULES
        ):
            source_imports.append(name)
            raise AssertionError(f"disabled Capture imported deferred module {name}")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    original_import_module = importlib.import_module

    def guarded_import_module(name, package=None):
        if any(
            name == blocked or name.startswith(blocked + ".")
            for blocked in DEFERRED_RUNTIME_MODULES
        ):
            source_imports.append(name)
            raise AssertionError(f"disabled Capture imported deferred module {name}")
        return original_import_module(name, package)

    monkeypatch.setattr(importlib, "import_module", guarded_import_module)

    def is_source_path(value: object) -> bool:
        try:
            candidate = Path(os.fspath(value)).resolve()
            candidate.relative_to(source_root.resolve())
        except (TypeError, ValueError, OSError):
            return False
        return True

    def reject_source_enumeration(name: str, original):
        def guarded(path, *args, **kwargs):
            if is_source_path(path):
                source_enumerations.append(name)
                raise AssertionError(f"disabled Capture invoked source enumeration {name}")
            return original(path, *args, **kwargs)

        return guarded

    monkeypatch.setattr(
        os, "scandir", reject_source_enumeration("os.scandir", os.scandir)
    )
    monkeypatch.setattr(
        os, "listdir", reject_source_enumeration("os.listdir", os.listdir)
    )
    for name in ("iterdir", "glob", "rglob"):
        original = getattr(Path, name)
        monkeypatch.setattr(
            Path,
            name,
            reject_source_enumeration(f"Path.{name}", original),
        )

    def reject_external(name: str):
        def rejected(*_args, **_kwargs):
            external_calls.append(name)
            raise AssertionError(f"disabled Capture invoked external boundary {name}")

        return rejected

    monkeypatch.setattr(socket, "socket", reject_external("socket.socket"))
    monkeypatch.setattr(
        socket, "create_connection", reject_external("socket.create_connection")
    )
    monkeypatch.setattr(urllib.request, "urlopen", reject_external("urllib.urlopen"))
    return process_calls, source_imports, source_enumerations, external_calls


def test_disabled_capture_core_is_independently_releasable(
    tmp_path: Path, monkeypatch
):
    source_root = tmp_path / "synthetic-codex-source"
    source_root.mkdir()
    source_task = source_root / "synthetic-task.jsonl"
    source_task_bytes = b'{"synthetic":"source-task-sentinel"}\n'
    source_task.write_bytes(source_task_bytes)
    (
        process_calls,
        source_imports,
        source_enumerations,
        external_calls,
    ) = _guard_disabled_boundary(monkeypatch, source_root)

    from agc_runtime.admin_service import dispatch_admin
    from agc_runtime.capture_store import CaptureStore
    from agc_runtime.paths import MemoryPaths
    from agc_runtime.read_service import dispatch_read
    from agc_runtime.write_service import dispatch_write

    paths = MemoryPaths.from_root(tmp_path / "synthetic-memory")
    assert dispatch_admin(paths, {"action": "init"}).status == "accepted"
    baseline = _catalog_state(paths)
    assert baseline[1] == 0

    status = dispatch_admin(paths, {"action": "capture_status"})
    assert status.status == "accepted"
    assert status.data["state"] == {
        "enabled": False,
        "paused": False,
        "mode": "off",
        "scanner_only": False,
    }
    assert status.data["source_roots"]["configured_count"] == 0
    assert status.data["source_roots"]["ids"] == []
    assert status.data["extractor_boundary"]["model_configured"] is False
    _assert_catalog_unchanged(paths, baseline)

    key = _key()
    receipt = _receipt(key)
    observations = (
        _observation(
            receipt,
            ordinal=0,
            statement="Synthetic exact observation target.",
        ),
        _observation(
            receipt,
            ordinal=1,
            statement="Synthetic revision target remains after exact observation forget.",
        ),
    )
    store = CaptureStore(paths, clock=lambda: UTC)
    registered = store.register_extraction(receipt)
    assert registered.created is True
    lease = store.acquire_lease(
        key, owner_id="synthetic-worker", now=UTC, ttl_seconds=60
    )
    assert lease is not None
    complete = _complete(receipt, observations)
    committed = store.commit_extraction(lease, observations, complete)
    assert committed.created_observation_count == 2
    replayed = store.commit_extraction(lease, observations, complete)
    assert replayed.created_observation_count == 0
    _assert_catalog_unchanged(paths, baseline)

    capture_overview = dispatch_read(paths, {"action": "capture_overview"})
    capture_search = dispatch_read(paths, {"action": "capture_search"})
    capture_observation = dispatch_read(
        paths,
        {
            "action": "capture_get",
            "observation_id": observations[0].observation_id,
        },
    )
    capture_receipt = dispatch_read(
        paths, {"action": "capture_get", "receipt_id": receipt.receipt_id}
    )
    assert capture_overview.status == "accepted"
    assert capture_overview.data["receipt_key_count"] == 1
    assert capture_search.status == "accepted"
    assert capture_search.data["returned_count"] == 2
    assert (
        capture_observation.data["observation"]["statement"]
        == observations[0].statement
    )
    assert capture_receipt.data["receipt"]["status"] == "complete"

    ordinary = (
        dispatch_read(paths, {"action": "overview"}),
        dispatch_read(paths, {"action": "search"}),
        dispatch_read(paths, {"action": "get", "id": observations[0].observation_id}),
    )
    assert observations[0].statement not in str([item.to_dict() for item in ordinary])
    assert ordinary[0].data["memory_count"] == 0
    assert ordinary[1].data["results"] == []
    assert ordinary[2].status == "failed"
    _assert_catalog_unchanged(paths, baseline)

    backup = dispatch_admin(paths, {"action": "backup"})
    assert backup.status == "accepted"
    post_backup_receipt = _receipt(_key("post-backup-task", "revision-2"))
    post_backup_observation = _observation(
        post_backup_receipt,
        ordinal=0,
        statement="Synthetic state created only after backup.",
    )
    assert store.register_extraction(post_backup_receipt).created is True
    post_backup_lease = store.acquire_lease(
        post_backup_receipt.key,
        owner_id="synthetic-post-backup-worker",
        now=UTC,
        ttl_seconds=60,
    )
    assert post_backup_lease is not None
    store.commit_extraction(
        post_backup_lease,
        (post_backup_observation,),
        _complete(post_backup_receipt, (post_backup_observation,)),
    )
    assert dispatch_read(paths, {"action": "capture_search"}).data[
        "returned_count"
    ] == 3
    assert source_task.read_bytes() == source_task_bytes
    restored = dispatch_admin(
        paths,
        {"action": "restore", "backup_path": backup.data["backup_path"]},
    )
    assert restored.status == "accepted"
    assert restored.data["memory_count"] == 0
    restored_search = dispatch_read(paths, {"action": "capture_search"})
    assert restored_search.status == "accepted"
    assert restored_search.data["returned_count"] == 2
    _assert_catalog_unchanged(paths, baseline)

    observation_forget = dispatch_write(
        paths,
        {
            "action": "capture_forget",
            "authorization": "explicit_user_request",
            "target": {
                "type": "observation",
                "observation_id": observations[0].observation_id,
            },
        },
    )
    assert observation_forget.status == "accepted"
    assert source_task.read_bytes() == source_task_bytes
    after_observation_forget = dispatch_read(paths, {"action": "capture_search"})
    assert [
        item["observation_id"] for item in after_observation_forget.data["results"]
    ] == [observations[1].observation_id]
    _assert_catalog_unchanged(paths, baseline)

    revision_forget = dispatch_write(
        paths,
        {
            "action": "capture_forget",
            "authorization": "explicit_user_request",
            "target": {"type": "revision", **key.to_mapping()},
        },
    )
    assert revision_forget.status == "accepted"
    assert revision_forget.data["source_task_deleted"] is False
    assert source_task.read_bytes() == source_task_bytes
    after_revision_forget = dispatch_read(paths, {"action": "capture_search"})
    after_revision_overview = dispatch_read(
        paths, {"action": "capture_overview"}
    )
    assert after_revision_forget.data["results"] == []
    assert after_revision_overview.data["receipt_key_count"] == 0
    assert after_revision_overview.data["suppression_tombstone_key_count"] == 1
    _assert_catalog_unchanged(paths, baseline)

    assert process_calls == []
    assert source_imports == []
    assert source_enumerations == []
    assert external_calls == []
