from __future__ import annotations

import json
import io
import hashlib
import os
import subprocess
import threading
import zipfile
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from agc_runtime import admin_service, managed_backup
from agc_runtime.admin_service import dispatch_admin
from agc_runtime.capture_contracts import CaptureKey, CaptureReceipt, CollectedObservation, TokenUsage, observation_fingerprint_for, observation_id_for, receipt_id_for
from agc_runtime.capture_store import CaptureStore
from agc_runtime.locking import capture_write_lock
from agc_runtime.paths import MemoryPaths
from agc_runtime.write_service import dispatch_write


UTC = "2026-08-13T12:00:00Z"
ROOT_ID = "1" * 64


def _key() -> CaptureKey:
    return CaptureKey("synthetic_adapter", ROOT_ID, "task-5", "revision-5")


def _receipt() -> CaptureReceipt:
    key = _key()
    return CaptureReceipt.from_mapping({
        "schema_version": 1, "receipt_id": receipt_id_for(key), **key.to_mapping(),
        "adapter_version": "1", "source_schema_version": "1", "identity_quality": "session_id",
        "source_fingerprint": "a" * 64, "source_hash_schema_version": "source-v1",
        "capsule_hash": "b" * 64, "capsule_schema_version": "capsule-v1",
        "settled_at": UTC, "discovered_at": UTC, "updated_at": UTC, "status": "extracting",
        "attempt_count": 1, "next_retry_at": None, "extractor_id": "synthetic_extractor",
        "extractor_version": "1", "extractor_schema_version": "1", "taxonomy_version": "taxonomy-v1",
        "observation_count": None, "filtered_counts": None, "duplicate_suppression_count": None,
        "token_usage": TokenUsage(1, 2, 3).to_mapping(), "usage_quality": "actual",
        "redacted_by_forget": False, "forgotten_observation_count": 0, "zero_reason": None,
        "sanitized_error": None, "coalesced_to": None, "exclusion_reason": None,
    })


def _observation(statement: str) -> CollectedObservation:
    key = _key()
    value = {
        "schema_version": 1, "observation_id": "co_" + "0" * 64,
        "receipt_id": receipt_id_for(key), "source": {**key.to_mapping(), "locator": "sessions/synthetic"},
        "ordinal": 0, "observation_fingerprint": "0" * 64, "statement": statement,
        "assertion": {"subject": "user", "mode": "direct", "modality": "asserted"},
        "primary_category": "work", "taxonomy_version": "taxonomy-v1", "kind": "preference",
        "scopes": ["testing"], "project_scope": None, "confidence": "observed", "sensitivity": "normal",
        "signal_type": "decision_or_constraint", "observed_at": UTC, "captured_at": UTC,
        "extractor_version": "1", "processing_state": "collected",
    }
    value["observation_fingerprint"] = observation_fingerprint_for(value)
    value["observation_id"] = observation_id_for(value["receipt_id"], value["observation_fingerprint"])
    return CollectedObservation.from_mapping(value)


def _complete(receipt: CaptureReceipt) -> CaptureReceipt:
    return CaptureReceipt.from_mapping({**receipt.to_mapping(), "status": "complete", "observation_count": 1,
        "filtered_counts": {"safety": 0, "policy": 0, "over_limit": 0}, "duplicate_suppression_count": 0,
        "zero_reason": None})


def _populated(tmp_path: Path) -> tuple[MemoryPaths, CaptureStore, CollectedObservation]:
    paths = MemoryPaths.from_root(tmp_path / "memory")
    assert dispatch_admin(paths, {"action": "init"}).status == "accepted"
    store = CaptureStore(paths, clock=lambda: UTC)
    receipt = _receipt()
    observation = _observation("Task 5 must preserve only safe Capture facts.")
    store.register_extraction(receipt)
    lease = store.acquire_lease(_key(), owner_id="worker", now=UTC, ttl_seconds=60)
    assert lease is not None
    store.commit_extraction(lease, (observation,), _complete(receipt))
    return paths, store, observation


def test_capture_backup_round_trip_is_allowlisted_and_keeps_recall_isolated(tmp_path: Path):
    paths, store, observation = _populated(tmp_path)
    (paths.capture.dirty / "raw-task.json").write_text("secret transcript", encoding="utf-8")
    (paths.capture.journals / "active.json").write_text("{}", encoding="utf-8")
    (paths.capture.leases / "lease.json").write_text("{}", encoding="utf-8")
    (paths.queue / "queued.json").write_text("runtime queue", encoding="utf-8")
    (paths.cache / "cached.json").write_text("runtime cache", encoding="utf-8")
    backup = dispatch_admin(paths, {"action": "backup"})

    assert backup.status == "accepted"
    assert backup.data["manifest"]["capture_schema_version"] == 1
    with zipfile.ZipFile(backup.data["backup_path"]) as archive:
        names = set(archive.namelist())
    assert f".runtime/capture/observations/{observation.observation_id}.json" in names
    assert ".runtime/capture/dirty/raw-task.json" not in names
    assert ".runtime/capture/journals/active.json" not in names
    assert ".runtime/capture/leases/lease.json" not in names
    assert ".runtime/capture/cursor-hmac-key" not in names
    assert ".runtime/queue/queued.json" not in names
    assert ".runtime/cache/cached.json" not in names

    paths.capture.observations.joinpath(f"{observation.observation_id}.json").unlink()
    restored = dispatch_admin(paths, {"action": "restore", "backup_path": backup.data["backup_path"]})
    assert restored.status == "accepted"
    assert [item.observation_id for item in store.iter_visible_observations()] == [observation.observation_id]
    assert not list(paths.memories.rglob("*.md"))


def test_restore_rejects_unknown_capture_versions_before_mutation(tmp_path: Path):
    paths, _store, _observation_value = _populated(tmp_path)
    backup = dispatch_admin(paths, {"action": "backup"}).data["backup_path"]
    before = paths.capture.schema_version.read_bytes()
    with zipfile.ZipFile(backup) as archive:
        entries = {name: archive.read(name) for name in archive.namelist() if name != "manifest.json"}
        manifest = json.loads(archive.read("manifest.json"))
    manifest["capture_schema_version"] = 999
    with zipfile.ZipFile(backup, "w") as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
        archive.writestr("manifest.json", json.dumps(manifest))
    response = dispatch_admin(paths, {"action": "restore", "backup_path": backup})
    assert response.error["code"] == "backup_verification_failed"
    assert paths.capture.schema_version.read_bytes() == before


def _write_archive(path: Path, entries: list[tuple[str, bytes]], *, manifest_value=None) -> None:
    value = manifest_value or managed_backup.manifest(entries)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries:
            archive.writestr(name, data)
        archive.writestr("manifest.json", json.dumps(value, sort_keys=True))


@pytest.mark.parametrize(
    "attack",
    [
        "backslash_cursor_key", "casefold_duplicate", "schema_child", "zip_bomb", "duplicate_name",
        "manifest_unknown", "manifest_files_type", "manifest_capability", "manifest_hash", "manifest_size_bool",
    ],
)
def test_restore_rejects_noncanonical_or_resource_abusive_zip_before_mutation(tmp_path: Path, attack: str):
    paths, _store, _observation_value = _populated(tmp_path)
    valid = dispatch_admin(paths, {"action": "backup"})
    assert valid.status == "accepted"
    with zipfile.ZipFile(valid.data["backup_path"]) as archive:
        entries = [(name, archive.read(name)) for name in archive.namelist() if name != "manifest.json"]
    malicious = tmp_path / f"{attack}.zip"
    if attack == "backslash_cursor_key":
        entries.append((r".runtime\capture\cursor-hmac-key", b"x" * 32))
        _write_archive(malicious, entries)
    elif attack == "casefold_duplicate":
        entries.extend((("case.txt", b"a"), ("CASE.txt", b"b")))
        _write_archive(malicious, entries)
    elif attack == "schema_child":
        entries.append((".runtime/capture/schema-version/child.json", b"{}"))
        _write_archive(malicious, entries)
    elif attack == "zip_bomb":
        entries.append(("bomb.txt", b"0" * (2 * 1024 * 1024)))
        _write_archive(malicious, entries)
    elif attack == "duplicate_name":
        manifest_value = managed_backup.manifest(entries)
        with zipfile.ZipFile(malicious, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, data in entries:
                archive.writestr(name, data)
            archive.writestr(entries[0][0], entries[0][1])
            archive.writestr("manifest.json", json.dumps(manifest_value, sort_keys=True))
    else:
        manifest_value = managed_backup.manifest(entries)
        if attack == "manifest_unknown":
            manifest_value["unexpected"] = True
        elif attack == "manifest_files_type":
            manifest_value["files"] = {"not": "a list"}
        elif attack == "manifest_capability":
            manifest_value["capabilities"] = ["capture-backup-v1", "unknown"]
        elif attack == "manifest_hash":
            manifest_value["files"][0]["sha256"] = "A" * 64
        else:
            manifest_value["files"][0]["size"] = True
        _write_archive(malicious, entries, manifest_value=manifest_value)
    marker = paths.root / "pre-restore-marker.txt"
    marker.write_bytes(b"unchanged")

    response = dispatch_admin(paths, {"action": "restore", "backup_path": str(malicious)})

    assert response.status == "failed"
    assert response.error["code"] == "backup_verification_failed"
    assert marker.read_bytes() == b"unchanged"


@pytest.mark.parametrize("corruption", ["orphan_observation", "orphan_manifest", "ledger_filename"])
def test_backup_rejects_inconsistent_live_capture_graph(tmp_path: Path, corruption: str):
    paths, _store, observation = _populated(tmp_path)
    receipt_id = receipt_id_for(_key())
    if corruption == "orphan_observation":
        value = _observation("Orphan backup content must fail closed.").to_mapping()
        value["observation_id"] = "co_" + "f" * 64
        (paths.capture.observations / f"{value['observation_id']}.json").write_text(
            json.dumps(value), encoding="utf-8"
        )
    elif corruption == "orphan_manifest":
        source = paths.capture.indexes / f"{receipt_id}.json"
        (paths.capture.indexes / ("cr_" + "f" * 64 + ".json")).write_bytes(source.read_bytes())
    else:
        source = paths.capture.ledger / f"{receipt_id}.json"
        (paths.capture.ledger / ("cr_" + "f" * 64 + ".json")).write_bytes(source.read_bytes())

    response = dispatch_admin(paths, {"action": "backup"})

    assert response.status == "failed"
    assert response.error["code"] in {"validation_failed", "admin_failed"}


def test_restore_uses_capture_lock_and_preserves_existing_cursor_key(tmp_path: Path):
    source_paths, _source_store, _observation_value = _populated(tmp_path / "source")
    backup = dispatch_admin(source_paths, {"action": "backup"})
    assert backup.status == "accepted"
    paths, _store, _target_observation = _populated(tmp_path / "target")
    paths.capture.cursor_hmac_key.write_bytes(b"K" * 32)
    before = {
        path.relative_to(paths.root).as_posix(): path.read_bytes()
        for path in paths.root.rglob("*") if path.is_file()
    }

    with capture_write_lock(paths):
        busy = dispatch_admin(paths, {"action": "restore", "backup_path": backup.data["backup_path"]})

    assert busy.status == "failed"
    assert busy.error == {"code": "admin_busy", "message": "admin operation is temporarily unavailable"}
    assert {
        path.relative_to(paths.root).as_posix(): path.read_bytes()
        for path in paths.root.rglob("*") if path.is_file()
    } == before

    restored = dispatch_admin(paths, {"action": "restore", "backup_path": backup.data["backup_path"]})
    assert restored.status == "accepted"
    assert paths.capture.cursor_hmac_key.read_bytes() == b"K" * 32


def test_restore_archive_read_and_mutation_are_serialized_with_capture_forget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    paths, _store, observation = _populated(tmp_path)
    backup = Path(dispatch_admin(paths, {"action": "backup"}).data["backup_path"])
    original_read = managed_backup.read_verified_archive
    read_ready = threading.Event()
    release_read = threading.Event()

    def blocked_read(path: Path):
        result = original_read(path)
        if threading.current_thread().name == "restore-worker":
            read_ready.set()
            assert release_read.wait(5), "restore read was not released"
        return result

    monkeypatch.setattr(managed_backup, "read_verified_archive", blocked_read)
    results: dict[str, object] = {}

    restore_thread = threading.Thread(
        name="restore-worker",
        target=lambda: results.setdefault(
            "restore",
            dispatch_admin(paths, {"action": "restore", "backup_path": str(backup)}),
        ),
    )
    restore_thread.start()
    assert read_ready.wait(5), "restore never reached archive verification"

    forget_thread = threading.Thread(
        name="forget-worker",
        target=lambda: results.setdefault(
            "forget",
            dispatch_write(
                paths,
                {
                    "action": "capture_forget",
                    "authorization": "explicit_user_request",
                    "target": {
                        "type": "observation",
                        "observation_id": observation.observation_id,
                    },
                },
            ),
        ),
    )
    forget_thread.start()
    forget_thread.join(5)
    assert not forget_thread.is_alive(), "concurrent forget did not resolve at the lock boundary"
    release_read.set()
    restore_thread.join(5)
    assert not restore_thread.is_alive(), "restore did not complete"

    forget = results["forget"]
    if forget.status == "failed" and forget.error["code"] == "capture_forget_busy":
        forget = dispatch_write(
            paths,
            {
                "action": "capture_forget",
                "authorization": "explicit_user_request",
                "target": {
                    "type": "observation",
                    "observation_id": observation.observation_id,
                },
            },
        )
    assert forget.status == "accepted"
    assert not (paths.capture.observations / f"{observation.observation_id}.json").exists()


def test_restore_prevalidates_ordinary_utf8_before_clearing_current_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    paths, _store, _observation_value = _populated(tmp_path)
    valid = Path(dispatch_admin(paths, {"action": "backup"}).data["backup_path"])
    with zipfile.ZipFile(valid) as archive:
        entries = [
            (name, archive.read(name))
            for name in archive.namelist()
            if name != "manifest.json"
        ]
    entries.append(("ordinary-invalid.txt", b"\xff\xfe"))
    malicious = tmp_path / "ordinary-invalid.zip"
    _write_archive(malicious, entries)
    clear_called = False
    original_clear = admin_service._clear_replaceable_files

    def track_clear(current_paths: MemoryPaths) -> None:
        nonlocal clear_called
        clear_called = True
        original_clear(current_paths)

    monkeypatch.setattr(admin_service, "_clear_replaceable_files", track_clear)
    response = dispatch_admin(paths, {"action": "restore", "backup_path": str(malicious)})

    assert response.status == "failed"
    assert response.error["code"] == "backup_verification_failed"
    assert clear_called is False


@pytest.mark.parametrize("namespace", ["queue", "cache"])
def test_restore_rejects_excluded_transient_runtime_namespaces_before_mutation(
    tmp_path: Path, namespace: str
):
    paths, _store, _observation_value = _populated(tmp_path)
    valid = Path(dispatch_admin(paths, {"action": "backup"}).data["backup_path"])
    with zipfile.ZipFile(valid) as archive:
        entries = [
            (name, archive.read(name))
            for name in archive.namelist()
            if name != "manifest.json"
        ]
    crafted_name = f".runtime/{namespace}/crafted.json"
    entries.append((crafted_name, b'{"crafted":true}\n'))
    malicious = tmp_path / f"crafted-{namespace}.zip"
    _write_archive(malicious, entries)
    marker = paths.root / "pre-restore-marker.txt"
    marker.write_bytes(b"unchanged")

    response = dispatch_admin(paths, {"action": "restore", "backup_path": str(malicious)})

    assert response.status == "failed"
    assert response.error["code"] == "backup_verification_failed"
    assert marker.read_bytes() == b"unchanged"
    assert not (paths.root / Path(*crafted_name.split("/"))).exists()


def test_restore_failure_rolls_back_non_utf8_snapshot_byte_exact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    paths, _store, _observation_value = _populated(tmp_path)
    backup = Path(dispatch_admin(paths, {"action": "backup"}).data["backup_path"])
    opaque = paths.root / "opaque.bin"
    opaque.write_bytes(b"\x00\xff\x80current")
    before = admin_service._current_replaceable_files(paths)
    original_write = admin_service.atomic_write_text
    failed = False

    def fail_once(path: Path, text: str) -> None:
        nonlocal failed
        if path == paths.root / "config.yaml" and not failed:
            failed = True
            raise OSError("injected restore failure")
        original_write(path, text)

    monkeypatch.setattr(admin_service, "atomic_write_text", fail_once)
    response = dispatch_admin(paths, {"action": "restore", "backup_path": str(backup)})

    assert response.status == "failed"
    assert admin_service._current_replaceable_files(paths) == before


def test_backup_rejects_symbolic_link_before_reading_target(tmp_path: Path):
    paths, _store, _observation_value = _populated(tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_text("outside secret", encoding="utf-8")
    link = paths.contexts / "escape.txt"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        if os.name != "nt":
            pytest.skip("symbolic links unavailable")
        outside_directory = tmp_path / "outside-directory"
        outside_directory.mkdir()
        (outside_directory / "secret.txt").write_text("outside secret", encoding="utf-8")
        link = paths.contexts / "escape-directory"
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(outside_directory)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            pytest.skip(f"symbolic links and junctions unavailable: {result.stderr}")

    with pytest.raises(ValueError, match="symbolic link|reparse|escape"):
        managed_backup.backup_files(paths)


def test_archive_file_size_limit_is_checked_before_read_bytes():
    class OversizedPath(type(Path())):
        def stat(self, *args, **kwargs):
            return SimpleNamespace(st_size=1024 * 1024 * 1024)

        def read_bytes(self):
            raise AssertionError("oversized archive was read before its size check")

    with pytest.raises(ValueError, match="archive.*limit|archive.*large|size"):
        managed_backup.read_verified_archive(OversizedPath("oversized.zip"))


@pytest.mark.parametrize(
    ("limits", "files"),
    [
        ({"_MAX_ARCHIVE_FILES": 1}, [("one.txt", b"1"), ("two.txt", b"2")]),
        ({"_MAX_FILE_SIZE": 3}, [("large.txt", b"1234")]),
        ({"_MAX_TOTAL_SIZE": 5}, [("one.txt", b"123"), ("two.txt", b"456")]),
    ],
)
def test_backup_manifest_rejects_output_exceeding_reader_limits(
    monkeypatch: pytest.MonkeyPatch,
    limits: dict[str, int],
    files: list[tuple[str, bytes]],
):
    for name, value in limits.items():
        monkeypatch.setattr(managed_backup, name, value)

    with pytest.raises(ValueError, match="file count|file size|total size|safe limit"):
        managed_backup.manifest(files)


def test_backup_creation_fails_before_archive_when_writer_limit_is_exceeded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    paths, _store, _observation_value = _populated(tmp_path)
    monkeypatch.setattr(managed_backup, "_MAX_ARCHIVE_FILES", 0)

    response = dispatch_admin(paths, {"action": "backup"})

    assert response.status == "failed"
    assert response.error["code"] == "validation_failed"
    assert not list(paths.backups.glob("*.zip"))
