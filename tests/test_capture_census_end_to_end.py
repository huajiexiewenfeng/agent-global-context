"""End-to-end proof for the explicit Scanner-only Capture boundary."""

from __future__ import annotations

import builtins
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
import hashlib
import importlib
from importlib.abc import MetaPathFinder
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import urllib.request

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SENTINEL = "private-task-content-must-not-cross-census-boundary"
PRIVATE_PROMPT = "private-synthetic-prompt-must-stay-in-source"
LAST_ASSISTANT = "private-last-assistant-message-must-stay-in-source"
RAW_EXCEPTION = "private-sharing-exception-must-not-be-persisted"
DEFERRED_CAPTURE_MODULES = frozenset(
    {
        "agc_runtime.capture_dirty",
        "agc_runtime.capture_hook",
        "agc_runtime.capture_ledger",
        "agc_runtime.capture_scanner",
        "agc_runtime.capture_source",
        "agc_runtime.capture_capsule",
        "agc_runtime.capture_safety",
        "agc_runtime.capture_extractor",
        "agc_runtime.codex_extractor",
        "agc_runtime.capture_budget",
        "agc_runtime.capture_runner",
        "agc_runtime.capture_activation",
        "agc_runtime.capture_cli",
        "agc_runtime.codex_source_adapter",
        "agc_runtime.project_identity",
    }
)
SOURCE_SCANNER_MODULES = frozenset(
    {
        "agc_runtime.capture_ledger",
        "agc_runtime.capture_scanner",
        "agc_runtime.capture_source",
        "agc_runtime.codex_source_adapter",
    }
)
PLANNED_CAPABILITY_IMPORTS = {
    "agc_runtime.capture_capsule": "task_capsule",
    "agc_runtime.capture_safety": "safety_gate",
    "agc_runtime.capture_extractor": "extractor",
    "agc_runtime.codex_extractor": "extractor",
    "agc_runtime.capture_budget": "token_budget",
    "agc_runtime.capture_runner": "runner",
    "agc_runtime.capture_activation": "host_activation",
}
FORBIDDEN_IMPORTS = {
    **PLANNED_CAPABILITY_IMPORTS,
    "agc_runtime.write_service": "formal_write",
}


@pytest.fixture(autouse=True)
def _remove_deferred_modules_introduced_by_this_test():
    starting_modules = set(sys.modules)
    yield
    for name in DEFERRED_CAPTURE_MODULES:
        if name not in starting_modules:
            sys.modules.pop(name, None)


def _utc(minutes: int) -> str:
    return datetime(2026, 8, 18, 12, minutes, tzinfo=timezone.utc).isoformat().replace(
        "+00:00", "Z"
    )


def _records(
    task_id: str,
    rollout_id: str,
    revisions: tuple[tuple[str, str], ...],
    *,
    source: object = "synthetic-cli",
    include_content: bool = False,
    lifecycle_tail: tuple[dict[str, object], ...] = (),
) -> tuple[dict[str, object], ...]:
    items: list[dict[str, object]] = [
        {
            "timestamp": _utc(0),
            "type": "session_meta",
            "payload": {
                "id": rollout_id,
                "session_id": task_id,
                "source": source,
            },
        }
    ]
    if include_content:
        items.append(
            {
                "timestamp": _utc(1),
                "type": "response_item",
                "payload": {
                    "prompt": PRIVATE_PROMPT,
                    "last_assistant_message": LAST_ASSISTANT,
                    "message": SENTINEL,
                },
            }
        )
    items.extend(lifecycle_tail)
    items.extend(
        {
            "timestamp": completed_at,
            "type": "event_msg",
            "payload": {"type": "task_complete", "turn_id": revision_id},
        }
        for revision_id, completed_at in revisions
    )
    return tuple(items)


def _write_rollout(path: Path, records: tuple[dict[str, object], ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(item, sort_keys=True) + "\n" for item in records),
        encoding="utf-8",
    )


def _write_config(
    memory_root: Path,
    source_root: Path,
    *,
    enabled: bool,
    hook_enabled: bool,
) -> None:
    memory_root.mkdir(parents=True, exist_ok=True)
    default = (REPOSITORY_ROOT / "agc_runtime" / "default_config.yaml").read_text(
        encoding="utf-8"
    )
    configured = (
        default.replace("enabled: false", f"enabled: {str(enabled).lower()}", 1)
        .replace("mode: off", "mode: scanner_only" if enabled else "mode: off", 1)
        .replace("sources: []", f"sources:\n    - {source_root.as_posix()}", 1)
        .replace(
            "hook:\n    enabled: false",
            f"hook:\n    enabled: {str(hook_enabled).lower()}",
            1,
        )
        .replace("task_ids: []", 'task_ids: ["task-excluded"]', 1)
    )
    (memory_root / "config.yaml").write_text(configured, encoding="utf-8")


def _tree_state(root: Path) -> tuple[tuple[str, ...], tuple[tuple[str, bytes], ...]]:
    if not root.exists():
        return (), ()
    directories = tuple(
        sorted(path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_dir())
    )
    files = tuple(
        sorted(
            (path.relative_to(root).as_posix(), path.read_bytes())
            for path in root.rglob("*")
            if path.is_file()
        )
    )
    return directories, files


def _catalog_state(paths) -> tuple[str, int]:
    payload = paths.catalog_json.read_bytes() + b"\0" + paths.catalog_md.read_bytes()
    count = json.loads(paths.catalog_json.read_text(encoding="utf-8"))["memory_count"]
    return hashlib.sha256(payload).hexdigest(), count


def _file_count(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        return 1
    return sum(item.is_file() for item in path.rglob("*"))


def _formal_counts(paths) -> dict[str, int]:
    return {
        "formal_memory": _file_count(paths.memories),
        "candidate": _file_count(paths.candidates),
        "event": _file_count(paths.events),
    }


def _invoke(main, *arguments: str) -> tuple[int, dict[str, object], str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        exit_code = main(arguments)
    assert stderr.getvalue() == ""
    lines = stdout.getvalue().splitlines()
    assert len(lines) == 1
    return exit_code, json.loads(lines[0]), stdout.getvalue()


def _is_within(value: object, root: Path) -> bool:
    try:
        Path(os.fspath(value)).resolve().relative_to(root.resolve())
    except (OSError, TypeError, ValueError):
        return False
    return True


def _install_boundary_guards(
    monkeypatch,
    *,
    source_root: Path,
    unconfigured_root: Path,
    transient_lock_file: Path | None = None,
) -> tuple[dict[str, int], list[str]]:
    counters = {
        "network": 0,
        "subprocess": 0,
        "extractor": 0,
        "runner": 0,
        "task_capsule": 0,
        "safety_gate": 0,
        "token_budget": 0,
        "target_turn_load": 0,
        "observation_write": 0,
        "formal_write": 0,
        "host_activation": 0,
        "unconfigured_source_enumeration": 0,
    }
    source_reads: list[str] = []

    def reject(counter: str):
        def rejected(*_args, **_kwargs):
            counters[counter] += 1
            raise AssertionError(f"census-only boundary invoked {counter}")

        return rejected

    for name in ("Popen", "run", "call", "check_call", "check_output"):
        monkeypatch.setattr(subprocess, name, reject("subprocess"))
    monkeypatch.setattr(socket, "socket", reject("network"))
    monkeypatch.setattr(socket, "create_connection", reject("network"))
    monkeypatch.setattr(urllib.request, "urlopen", reject("network"))

    patched_adapter = False
    original_import = builtins.__import__

    class CapabilityImportBlocker(MetaPathFinder):
        def find_spec(self, fullname, path=None, target=None):
            del path, target
            for blocked, counter in FORBIDDEN_IMPORTS.items():
                if fullname == blocked or fullname.startswith(blocked + "."):
                    counters[counter] += 1
                    raise AssertionError(f"census-only boundary imported {fullname}")
            return None

    monkeypatch.setattr(sys, "meta_path", [CapabilityImportBlocker(), *sys.meta_path])

    def patch_adapter_boundary() -> None:
        nonlocal patched_adapter
        if (
            patched_adapter
            or "agc_runtime.codex_source_adapter" not in sys.modules
            or not hasattr(
                sys.modules["agc_runtime.codex_source_adapter"],
                "CodexSourceAdapter",
            )
        ):
            return
        adapter = sys.modules["agc_runtime.codex_source_adapter"].CodexSourceAdapter
        patched_adapter = True
        monkeypatch.setattr(adapter, "load_capsule", reject("task_capsule"))
        monkeypatch.setattr(adapter, "_iter_target_turn_records", reject("target_turn_load"))

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        for blocked, counter in FORBIDDEN_IMPORTS.items():
            if name == blocked or name.startswith(blocked + "."):
                counters[counter] += 1
                raise AssertionError(f"census-only boundary imported {name}")
        module = original_import(name, globals, locals, fromlist, level)
        patch_adapter_boundary()
        return module

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    original_import_module = importlib.import_module

    def guarded_import_module(name, package=None):
        for blocked, counter in FORBIDDEN_IMPORTS.items():
            if name == blocked or name.startswith(blocked + "."):
                counters[counter] += 1
                raise AssertionError(f"census-only boundary imported {name}")
        module = original_import_module(name, package)
        patch_adapter_boundary()
        return module

    monkeypatch.setattr(importlib, "import_module", guarded_import_module)

    for name in ("scandir", "listdir"):
        original = getattr(os, name)

        def guarded_os(path, *args, _name=name, _original=original, **kwargs):
            if _is_within(path, unconfigured_root):
                counters["unconfigured_source_enumeration"] += 1
                raise AssertionError(f"enumerated unconfigured root through os.{_name}")
            return _original(path, *args, **kwargs)

        monkeypatch.setattr(os, name, guarded_os)

    for name in ("iterdir", "glob", "rglob"):
        original = getattr(Path, name)

        def guarded_path(self, *args, _name=name, _original=original, **kwargs):
            if _is_within(self, unconfigured_root):
                counters["unconfigured_source_enumeration"] += 1
                raise AssertionError(f"enumerated unconfigured root through Path.{_name}")
            return _original(self, *args, **kwargs)

        monkeypatch.setattr(Path, name, guarded_path)

    original_open = Path.open
    lock_pending = transient_lock_file is not None

    def guarded_open(self, mode="r", *args, **kwargs):
        nonlocal lock_pending
        if _is_within(self, unconfigured_root):
            counters["unconfigured_source_enumeration"] += 1
            raise AssertionError("opened an unconfigured source")
        if "r" in mode and _is_within(self, source_root):
            source_reads.append(self.resolve().relative_to(source_root.resolve()).as_posix())
            if lock_pending and self.resolve() == transient_lock_file.resolve():
                lock_pending = False
                raise PermissionError(RAW_EXCEPTION)
        return original_open(self, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded_open)
    return counters, source_reads


def _semantic_capture_state(paths, store_type) -> dict[str, object]:
    snapshot = store_type(paths).read_snapshot()
    census_membership = []
    for item in snapshot.census:
        value = item.to_mapping()
        value.pop("locator", None)
        census_membership.append(json.dumps(value, sort_keys=True))
    scan_states = []
    for item in snapshot.scan_states:
        value = item.to_mapping()
        for timestamp_or_version in ("state_version", "last_scan_at", "lookback_started_at"):
            value.pop(timestamp_or_version, None)
        scan_states.append(value)
    return {
        "census_membership": sorted(census_membership),
        "receipts": sorted(json.dumps(item.to_mapping(), sort_keys=True) for item in snapshot.receipts),
        "ledger": tuple(sorted((item.name, item.read_bytes()) for item in paths.capture.ledger.glob("*.json"))),
        "tombstones": sorted(json.dumps(item.to_mapping(), sort_keys=True) for item in snapshot.tombstones),
        "quarantines": sorted(json.dumps(item.to_mapping(), sort_keys=True) for item in snapshot.source_quarantines),
        "conflicts": snapshot.source_conflict_count,
        "scan_state_correctness": sorted(json.dumps(item, sort_keys=True) for item in scan_states),
    }


def test_planned_semantic_and_host_imports_have_real_meta_path_tripwires(
    tmp_path: Path,
    monkeypatch,
):
    source_root = tmp_path / "configured-source"
    unconfigured_root = tmp_path / "unconfigured-source"
    source_root.mkdir()
    unconfigured_root.mkdir()
    original_builtin_import = builtins.__import__
    original_import_module = importlib.import_module
    counters, _source_reads = _install_boundary_guards(
        monkeypatch,
        source_root=source_root,
        unconfigured_root=unconfigured_root,
    )
    monkeypatch.setattr(builtins, "__import__", original_builtin_import)
    monkeypatch.setattr(importlib, "import_module", original_import_module)

    for module_name, counter_name in PLANNED_CAPABILITY_IMPORTS.items():
        already_loaded = sys.modules.pop(module_name, None)
        before = counters[counter_name]
        try:
            with pytest.raises(
                AssertionError,
                match=f"census-only boundary imported {module_name}",
            ):
                importlib.import_module(module_name)
        finally:
            if already_loaded is not None:
                sys.modules[module_name] = already_loaded
        assert counters[counter_name] == before + 1


def test_source_quarantine_exact_replay_is_byte_stable_and_corruption_fails_closed(
    tmp_path: Path,
):
    from agc_runtime.capture_source import SourceBindingKey
    from agc_runtime.capture_store import CaptureStore
    from agc_runtime.paths import MemoryPaths

    paths = MemoryPaths.from_root(tmp_path / "memory")
    store = CaptureStore(paths)
    binding = SourceBindingKey.from_mapping(
        {
            "schema_version": 1,
            "adapter_id": "codex",
            "source_root_id": "7" * 64,
        }
    )
    first = store.record_source_quarantine(
        binding,
        created_at="2026-08-19T12:00:00Z",
        code="unknown_source_shape",
    )
    quarantine_path = next(paths.capture.quarantines.glob("source-*.json"))
    first_bytes = quarantine_path.read_bytes()

    replay = store.record_source_quarantine(
        binding,
        created_at="2026-08-19T12:00:01Z",
        code="unknown_source_shape",
    )
    assert replay == first
    assert quarantine_path.read_bytes() == first_bytes

    replacement = store.record_source_quarantine(
        binding,
        created_at="2026-08-19T12:00:02Z",
        code="partial_tail",
    )
    assert replacement.code == "partial_tail"
    assert replacement.created_at == "2026-08-19T12:00:02Z"
    assert quarantine_path.read_bytes() != first_bytes

    quarantine_path.write_bytes(b'{"broken":')
    corrupt_bytes = quarantine_path.read_bytes()
    with pytest.raises(ValueError, match="invalid_source_quarantine"):
        store.record_source_quarantine(
            binding,
            created_at="2026-08-19T12:00:03Z",
            code="partial_tail",
        )
    assert quarantine_path.read_bytes() == corrupt_bytes


def test_disabled_probe_and_status_are_byte_inert_and_import_no_source_modules(tmp_path: Path, monkeypatch):
    memory_root = tmp_path / "disabled-memory"
    configured_but_disabled = tmp_path / "disabled-source"
    unconfigured = tmp_path / "unconfigured-source"
    configured_but_disabled.mkdir()
    unconfigured.mkdir()
    source_file = configured_but_disabled / "private-source.jsonl"
    source_file.write_text(SENTINEL + "\n", encoding="utf-8")
    _write_config(memory_root, configured_but_disabled, enabled=False, hook_enabled=False)
    before = _tree_state(memory_root)
    source_before = source_file.read_bytes()
    deferred_before = SOURCE_SCANNER_MODULES.intersection(sys.modules)
    counters, _source_reads = _install_boundary_guards(
        monkeypatch, source_root=configured_but_disabled, unconfigured_root=unconfigured
    )

    from agc_runtime.admin_service import dispatch_admin
    from agc_runtime.capture_cli import main
    from agc_runtime.paths import MemoryPaths

    status = dispatch_admin(MemoryPaths.from_root(memory_root), {"action": "capture_status"})
    exit_code, probe, probe_text = _invoke(main, "probe", "--root", str(memory_root))

    assert status.status == "accepted"
    assert status.data["state"] == {"enabled": False, "paused": False, "mode": "off", "scanner_only": False}
    assert exit_code == 0
    assert probe["status"] == "accepted"
    assert _tree_state(memory_root) == before
    assert source_file.read_bytes() == source_before
    assert SOURCE_SCANNER_MODULES.intersection(sys.modules) == deferred_before
    assert SENTINEL not in probe_text
    assert str(configured_but_disabled) not in probe_text
    assert SENTINEL not in json.dumps(status.to_dict(), sort_keys=True)
    assert str(configured_but_disabled) not in json.dumps(status.to_dict(), sort_keys=True)
    assert all(value == 0 for value in counters.values())


def test_scanner_only_capture_coverage_end_to_end(tmp_path: Path, monkeypatch):
    memory_root = tmp_path / "memory"
    source_root = tmp_path / "configured-codex-source"
    unconfigured_root = tmp_path / "unconfigured-codex-source"
    sessions = source_root / "sessions"
    archived = source_root / "archived_sessions"
    unconfigured_root.mkdir()
    _write_rollout(unconfigured_root / "sessions" / "must-not-be-seen.jsonl", _records("task-unconfigured", "rollout-unconfigured", (("turn-u", _utc(2)),)))
    ordinary_path = sessions / "ordinary.jsonl"
    _write_rollout(ordinary_path, _records("task-ordinary", "rollout-ordinary", (("turn-ordinary", _utc(2)),), include_content=True))
    _write_rollout(sessions / "continued.jsonl", _records("task-continued", "rollout-continued", (("turn-continued-a", _utc(3)), ("turn-continued-b", _utc(4)))))
    replay_records = _records("task-replay", "rollout-replay", (("turn-replay", _utc(5)),))
    active_replay = sessions / "replay.jsonl"
    archived_replay = archived / "replay.jsonl"
    _write_rollout(active_replay, replay_records)
    _write_rollout(archived_replay, replay_records)
    _write_rollout(sessions / "subagent.jsonl", _records("task-subagent", "rollout-subagent", (("turn-subagent", _utc(6)),), source={"subagent": "synthetic"}))
    lifecycle_tail = (
        {"timestamp": _utc(6), "type": "event_msg", "payload": {"type": "task_started", "turn_id": "turn-incomplete"}},
        {"timestamp": _utc(7), "type": "event_msg", "payload": {"type": "task_aborted", "turn_id": "turn-incomplete"}},
    )
    _write_rollout(sessions / "incomplete-aborted.jsonl", _records("task-incomplete", "rollout-incomplete", (), lifecycle_tail=lifecycle_tail))
    _write_rollout(sessions / "unknown-shape.jsonl", _records("task-unknown", "rollout-unknown", (("turn-unknown", _utc(8)),), source={"unknown": "shape"}))
    partial_tail = sessions / "partial-tail.jsonl"
    _write_rollout(partial_tail, _records("task-partial", "rollout-partial", ()))
    with partial_tail.open("a", encoding="utf-8", newline="") as handle:
        handle.write('{"type":"event_msg","payload":')
    _write_rollout(sessions / "excluded.jsonl", _records("task-excluded", "rollout-excluded", (("turn-excluded", _utc(9)),)))
    locked_path = sessions / "locked.jsonl"
    _write_rollout(locked_path, _records("task-locked", "rollout-locked", (("turn-locked", _utc(10)),)))

    # Collection of later-phase contract tests may preload these modules. Remove
    # them for this test so the import finder still proves the scanner-only path
    # does not cross the deferred semantic/host boundary; monkeypatch restores
    # any preloaded modules after the test.
    for module_name in PLANNED_CAPABILITY_IMPORTS:
        monkeypatch.delitem(sys.modules, module_name, raising=False)
    assert not set(PLANNED_CAPABILITY_IMPORTS).intersection(sys.modules)
    counters, source_reads = _install_boundary_guards(
        monkeypatch,
        source_root=source_root,
        unconfigured_root=unconfigured_root,
        transient_lock_file=locked_path,
    )

    from agc_runtime.admin_service import dispatch_admin
    from agc_runtime.capture_contracts import CaptureKey
    from agc_runtime.capture_store import CaptureStore
    from agc_runtime.capture_transaction import safe_unlink as real_safe_unlink
    from agc_runtime.paths import MemoryPaths
    from agc_runtime.store import MemoryStore

    paths = MemoryPaths.from_root(memory_root)
    assert dispatch_admin(paths, {"action": "init"}).status == "accepted"
    _write_config(memory_root, source_root, enabled=True, hook_enabled=True)
    catalog_before = _catalog_state(paths)
    formal_before = _formal_counts(paths)

    def reject_observation_write(*_args, **_kwargs):
        counters["observation_write"] += 1
        raise AssertionError("census-only operation attempted an Observation write")

    monkeypatch.setattr(CaptureStore, "register_extraction", reject_observation_write)
    monkeypatch.setattr(CaptureStore, "commit_extraction", reject_observation_write)

    def reject_formal_write(*_args, **_kwargs):
        counters["formal_write"] += 1
        raise AssertionError("census-only operation attempted a formal-memory write")

    for name in ("create_memory", "add_evidence", "replace_memory", "transition_memory"):
        monkeypatch.setattr(MemoryStore, name, reject_formal_write)

    acknowledged: list[tuple[str, str]] = []

    def durable_safe_unlink(path: Path) -> None:
        if path.parent == paths.capture.dirty and path.suffix == ".json":
            marker = json.loads(path.read_text(encoding="utf-8"))
            key = CaptureKey.from_mapping({"adapter_id": marker["adapter_id"], "source_root_id": marker["source_root_id"], "task_id": marker["task_id"], "revision_id": marker["revision_id"]})
            assert key in CaptureStore(paths).read_snapshot().accounted_keys
            acknowledged.append((key.task_id, key.revision_id))
        real_safe_unlink(path)

    import agc_runtime.capture_transaction as capture_transaction

    monkeypatch.setattr(capture_transaction, "safe_unlink", durable_safe_unlink)

    # A real Stop Hook invocation loses its marker and remains silent/failure-open.
    from agc_runtime import capture_hook

    real_hook_writer = capture_hook.write_dirty_marker
    hook_failures: list[str] = []

    def fail_hook_delivery(*_args, **_kwargs):
        hook_failures.append("failed_open")
        raise OSError(RAW_EXCEPTION)

    monkeypatch.setattr(capture_hook, "write_dirty_marker", fail_hook_delivery)
    hook_input = {
        "session_id": "task-ordinary", "turn_id": "turn-ordinary",
        "transcript_path": str(ordinary_path.resolve()), "cwd": str(tmp_path / "private-cwd"),
        "hook_event_name": "Stop", "model": "private-model-name",
        "stop_hook_active": True, "last_assistant_message": LAST_ASSISTANT,
    }
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(hook_input)))
    hook_stdout = io.StringIO()
    hook_stderr = io.StringIO()
    with redirect_stdout(hook_stdout), redirect_stderr(hook_stderr):
        assert capture_hook.main(("--root", str(memory_root))) == 0
    assert hook_stdout.getvalue() == hook_stderr.getvalue() == ""
    assert hook_failures == ["failed_open"]
    monkeypatch.setattr(capture_hook, "write_dirty_marker", real_hook_writer)

    from agc_runtime.capture_dirty import write_dirty_marker
    from agc_runtime.capture_source import DirtyMarker, source_root_id_for

    canonical_source_root = source_root.resolve(strict=True)
    expected_source_root_id = source_root_id_for(canonical_source_root)

    locked_marker = DirtyMarker.from_mapping(
        {
            "schema_version": 1, "adapter_id": "codex", "adapter_version": "1.0",
            "source_schema_version": "codex-v1", "source_root_id": expected_source_root_id,
            "task_id": "task-locked", "revision_id": "turn-locked",
            "locator": "sessions/locked.jsonl", "observed_at": "2026-08-19T11:59:59Z", "hook_event": "Stop",
        }
    )
    marker_path = write_dirty_marker(memory_root, locked_marker)

    from agc_runtime.capture_cli import main

    run_times = iter(("2026-08-19T12:00:00Z", "2026-08-19T12:00:01Z", "2026-08-19T12:00:02Z"))
    monkeypatch.setattr("agc_runtime.capture_cli._utc_now", lambda: next(run_times))

    first_code, first, first_text = _invoke(main, "scan", "--root", str(memory_root), "--mode", "census", "--once")
    assert first_code == 0
    assert first["data"]["scan"] == {
        "window": {"start_at": "2026-08-12T12:00:00Z", "end_at": "2026-08-19T12:00:00Z"},
        "known_key_count": 5, "accounted_key_count": 5, "silent_loss_count": 0,
        "pending_key_count": 0, "created_receipt_count": 5, "replay_count": 0,
        "source_quarantine_count": 1, "source_health": "degraded",
        "acknowledged_marker_count": 0, "advanced_hint_count": 0,
    }
    assert marker_path.exists()

    active_replay.unlink()
    late_path = archived / "late-out-of-order.jsonl"
    _write_rollout(late_path, _records("task-late", "rollout-late", (("turn-late", "2026-08-13T00:00:00Z"),)))
    second_code, second, second_text = _invoke(main, "cycle", "--root", str(memory_root), "--once")
    assert second_code == 0
    assert second["data"]["scan"]["known_key_count"] == 7
    assert second["data"]["scan"]["accounted_key_count"] == 7
    assert second["data"]["scan"]["silent_loss_count"] == 0
    assert second["data"]["scan"]["created_receipt_count"] == 2
    assert second["data"]["scan"]["replay_count"] == 5
    assert second["data"]["scan"]["acknowledged_marker_count"] == 1
    assert not marker_path.exists()
    assert acknowledged == [("task-locked", "turn-locked")]

    snapshot = CaptureStore(paths).read_snapshot()
    assert snapshot.integrity_state == "healthy"
    assert len(snapshot.census) == len(snapshot.receipts) == len(snapshot.accounted_keys) == 7
    assert len(snapshot.observations) == 0
    assert len(snapshot.tombstones) == 0
    assert len(snapshot.source_quarantines) == 1
    assert len(snapshot.dirty_markers) == 0
    assert {item.status for item in snapshot.receipts} == {"discovered", "excluded"}
    excluded = [item for item in snapshot.receipts if item.status == "excluded"]
    assert [(item.task_id, item.exclusion_reason) for item in excluded] == [("task-excluded", "configured_task_exclusion")]
    continued = [item for item in snapshot.census if item.key.task_id == "task-continued"]
    assert {item.key.revision_id for item in continued} == {"turn-continued-a", "turn-continued-b"}
    assert len([item for item in snapshot.census if item.key.task_id == "task-replay"]) == 1
    assert not any(item.key.task_id == "task-subagent" for item in snapshot.census)
    assert not any(item.key.task_id == "task-incomplete" for item in snapshot.census)
    state_before_replay = _semantic_capture_state(paths, CaptureStore)

    third_code, third, third_text = _invoke(main, "cycle", "--root", str(memory_root), "--once")
    state_after_replay = _semantic_capture_state(paths, CaptureStore)
    assert third_code == 0
    assert third["data"]["scan"]["created_receipt_count"] == 0
    assert third["data"]["scan"]["replay_count"] == 7
    assert third["data"]["scan"]["known_key_count"] == 7
    assert third["data"]["scan"]["accounted_key_count"] == 7
    assert third["data"]["scan"]["silent_loss_count"] == 0
    before_membership = set(state_before_replay["census_membership"])
    after_membership = set(state_after_replay["census_membership"])
    assert after_membership == before_membership, {
        "added": sorted(after_membership - before_membership),
        "removed": sorted(before_membership - after_membership),
    }
    assert state_after_replay == state_before_replay

    probe_code, probe, probe_text = _invoke(main, "probe", "--root", str(memory_root))
    scanner_status = probe["data"]["scanner"]
    strict = CaptureStore(paths).read_snapshot()
    assert probe_code == 0
    assert scanner_status["assessment"] == "degraded"
    assert scanner_status["source_health"] == "degraded"
    assert scanner_status["accounting"] == {"known_key_count": len(strict.census), "accounted_key_count": len(strict.accounted_keys), "pending_key_count": 0, "silent_loss_count": 0}
    assert scanner_status["latest_census"] == {"assessment": "available", "run_count": 3, "key_count": 7}
    assert scanner_status["dirty_marker_count"] == len(strict.dirty_markers) == 0
    assert probe["data"]["source_roots"]["configured_count"] == 1
    assert probe["data"]["source_roots"]["ids"] == [expected_source_root_id]
    assert all(
        item.binding.source_root_id == expected_source_root_id
        for item in strict.scan_states
    )
    assert {item.key.source_root_id for item in strict.census} == {
        expected_source_root_id
    }

    from agc_runtime.read_service import dispatch_read

    ordinary_recall = (dispatch_read(paths, {"action": "overview"}), dispatch_read(paths, {"action": "search"}))
    assert all(item.status == "accepted" for item in ordinary_recall)
    assert ordinary_recall[0].data["memory_count"] == 0
    assert ordinary_recall[1].data["results"] == []
    assert "capture_key" not in json.dumps([item.to_dict() for item in ordinary_recall], sort_keys=True)
    assert _catalog_state(paths) == catalog_before
    assert catalog_before[1] == 0
    assert _formal_counts(paths) == formal_before

    response_text = "".join(
        (
            first_text,
            second_text,
            third_text,
            probe_text,
            hook_stdout.getvalue(),
            hook_stderr.getvalue(),
            json.dumps([item.to_dict() for item in ordinary_recall], sort_keys=True),
        )
    )
    content_sentinels = (SENTINEL, PRIVATE_PROMPT, LAST_ASSISTANT, RAW_EXCEPTION)
    absolute_path_sentinels = {
        str(source_root),
        source_root.as_posix(),
        str(ordinary_path),
        ordinary_path.as_posix(),
    }
    assert not any(value in response_text for value in content_sentinels)
    assert not any(value in response_text for value in absolute_path_sentinels)

    managed_files = tuple(
        sorted(path for path in memory_root.rglob("*") if path.is_file())
    )
    assert managed_files
    config_path = memory_root / "config.yaml"
    assert config_path in managed_files
    for path in managed_files:
        payload = path.read_bytes()
        assert not any(value.encode("utf-8") in payload for value in content_sentinels), path
        if path == config_path:
            assert payload.count(source_root.as_posix().encode("utf-8")) == 1
            assert str(ordinary_path).encode("utf-8") not in payload
            assert ordinary_path.as_posix().encode("utf-8") not in payload
        else:
            assert not any(
                value.encode("utf-8") in payload for value in absolute_path_sentinels
            ), path

    source_files = tuple(sorted(source_root.rglob("*.jsonl")))
    source_file_count = len(source_files)
    source_byte_count = sum(path.stat().st_size for path in source_files)
    assert source_file_count == 10
    assert source_byte_count == 3297
    assert "sessions/ordinary.jsonl" in source_reads
    assert "archived_sessions/replay.jsonl" in source_reads
    assert "archived_sessions/late-out-of-order.jsonl" in source_reads
    assert all(value == 0 for value in counters.values())
