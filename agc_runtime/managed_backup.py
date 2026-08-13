"""Deterministic, Capture-aware managed backup helpers.

The archive is deliberately an allowlist.  Capture's worker scratch space and
secrets are local runtime state, not durable AGC facts.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from agc_runtime.capture_contracts import (
    CAPTURE_SCHEMA_VERSION, CaptureReceipt, CaptureSuppressionTombstone,
    CollectedObservation, LedgerEntry, RevisionRef, SourceQuarantine,
)
from agc_runtime.capture_transaction import read_json
from agc_runtime.paths import MemoryPaths


ARCHIVE_SCHEMA_VERSION = 2
CAPTURE_BACKUP_CAPABILITY = "capture-backup-v1"
_CAPTURE_PREFIX = ".runtime/capture/"
_CAPTURE_ALLOWLIST = frozenset({
    "schema-version", "receipts", "observations", "ledger", "census",
    "tombstones", "quarantines", "conflicts", "indexes",
})


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o600 << 16
    return info


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def _capture_name_allowed(relative: str) -> bool:
    if not relative.startswith(_CAPTURE_PREFIX):
        return True
    tail = relative[len(_CAPTURE_PREFIX):]
    return bool(tail) and tail.split("/", 1)[0] in _CAPTURE_ALLOWLIST


def backup_files(paths: MemoryPaths) -> list[tuple[str, bytes]]:
    if not paths.root.exists():
        return []
    files: list[tuple[str, bytes]] = []
    for path in paths.root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(paths.root).as_posix()
        if (relative.startswith(".runtime/locks/") or relative.startswith(".runtime/backups/")
                or relative.endswith(".tmp") or relative == ".runtime/capture/cursor-hmac-key"):
            continue
        if not _capture_name_allowed(relative):
            continue
        files.append((relative, path.read_bytes()))
    return sorted(files, key=lambda item: item[0].encode("utf-8"))


def manifest(files: list[tuple[str, bytes]]) -> dict[str, Any]:
    capture_present = any(name.startswith(_CAPTURE_PREFIX) for name, _ in files)
    value: dict[str, Any] = {
        "schema_version": ARCHIVE_SCHEMA_VERSION,
        "files": [{"path": name, "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)} for name, data in files],
    }
    if capture_present:
        value.update({
            "capture_schema_version": CAPTURE_SCHEMA_VERSION,
            "capabilities": [CAPTURE_BACKUP_CAPABILITY],
        })
    return value


def archive_bytes(files: list[tuple[str, bytes]], value: dict[str, Any]) -> bytes:
    output = io.BytesIO()
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8") + b"\n"
    with zipfile.ZipFile(output, "w") as archive:
        for name, data in files:
            archive.writestr(_zip_info(name), data)
        archive.writestr(_zip_info("manifest.json"), encoded)
    return output.getvalue()


def _safe_archive_name(name: str) -> None:
    pure = PurePosixPath(name.replace("\\", "/"))
    if pure.is_absolute() or ".." in pure.parts or not pure.parts:
        raise ValueError("unsafe archive path")


def _json(entries: dict[str, bytes], name: str) -> dict[str, Any]:
    try:
        value = json.loads(entries[name].decode("utf-8"))
    except (KeyError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("invalid Capture archive object") from error
    if not isinstance(value, dict):
        raise ValueError("invalid Capture archive object")
    return value


def _validate_capture_entries(entries: dict[str, bytes], value: dict[str, Any]) -> None:
    names = [name for name in entries if name.startswith(_CAPTURE_PREFIX)]
    if not names:
        return
    if value.get("capture_schema_version") != CAPTURE_SCHEMA_VERSION:
        raise ValueError("unsupported Capture archive schema")
    capabilities = value.get("capabilities")
    if not isinstance(capabilities, list) or capabilities != [CAPTURE_BACKUP_CAPABILITY]:
        raise ValueError("unsupported Capture archive capabilities")
    schema_name = ".runtime/capture/schema-version"
    if entries.get(schema_name) != f"{CAPTURE_SCHEMA_VERSION}\n".encode("utf-8"):
        raise ValueError("unsupported Capture schema")
    if any(not _capture_name_allowed(name) for name in names):
        raise ValueError("Capture archive contains runtime noise")

    receipts: dict[str, CaptureReceipt] = {}
    observations: dict[str, CollectedObservation] = {}
    ledgers: dict[str, LedgerEntry] = {}
    manifests: dict[str, tuple[str, ...]] = {}
    for name in names:
        parts = PurePosixPath(name).parts
        if len(parts) < 4 or parts[:3] != (".runtime", "capture", parts[2]):
            continue
        namespace = parts[2]
        if namespace == "schema-version":
            continue
        if len(parts) != 4 or not name.endswith(".json"):
            raise ValueError("invalid Capture archive path")
        object_id = parts[3][:-5]
        payload = _json(entries, name)
        if namespace == "receipts":
            item = CaptureReceipt.from_mapping(payload)
            if item.receipt_id != object_id:
                raise ValueError("Capture receipt filename binding is invalid")
            receipts[item.receipt_id] = item
        elif namespace == "observations":
            item = CollectedObservation.from_mapping(payload)
            if item.observation_id != object_id:
                raise ValueError("Capture observation filename binding is invalid")
            observations[item.observation_id] = item
        elif namespace == "ledger":
            item = LedgerEntry.from_mapping(payload)
            if item.receipt_id != object_id:
                raise ValueError("Capture ledger filename binding is invalid")
            ledgers[item.receipt_id] = item
        elif namespace == "census":
            RevisionRef.from_mapping(payload)
        elif namespace == "tombstones":
            item = CaptureSuppressionTombstone.from_mapping(payload)
            if item.tombstone_id != object_id:
                raise ValueError("Capture tombstone filename binding is invalid")
        elif namespace == "quarantines":
            SourceQuarantine.from_mapping(payload)
        elif namespace == "conflicts":
            if set(payload) != {"schema_version", "code", "created_at"} or payload.get("schema_version") != CAPTURE_SCHEMA_VERSION or payload.get("code") != "source_conflict" or not isinstance(payload.get("created_at"), str):
                raise ValueError("invalid Capture conflict diagnostic")
        elif namespace == "indexes":
            if set(payload) != {"schema_version", "receipt_id", "observation_ids"} or payload.get("schema_version") != CAPTURE_SCHEMA_VERSION or payload.get("receipt_id") != object_id or not isinstance(payload.get("observation_ids"), list):
                raise ValueError("invalid Capture immutable manifest")
            ids = payload["observation_ids"]
            if len(ids) > 8 or any(not isinstance(item, str) for item in ids) or len(ids) != len(set(ids)):
                raise ValueError("invalid Capture immutable manifest")
            manifests[object_id] = tuple(ids)
        else:
            raise ValueError("unsupported Capture archive path")
    for receipt_id, receipt in receipts.items():
        ledger = ledgers.get(receipt_id)
        if ledger is None or ledger.capture_key != receipt.key or ledger.status != receipt.status:
            raise ValueError("Capture ledger does not match receipt")
        if receipt.status == "complete":
            ids = manifests.get(receipt_id)
            if ids is None or receipt.observation_count != len(ids):
                raise ValueError("Capture receipt manifest does not match")
            if any(item not in observations or observations[item].receipt_id != receipt_id for item in ids):
                raise ValueError("Capture receipt observation reference is invalid")
    if any(item.receipt_id not in receipts for item in observations.values()):
        raise ValueError("orphan Capture observation")


def read_verified_archive(backup_path: Path) -> tuple[dict[str, bytes], dict[str, Any]]:
    archive_data = backup_path.read_bytes()
    with zipfile.ZipFile(io.BytesIO(archive_data), "r") as archive:
        names = [info.filename for info in archive.infolist() if not info.is_dir()]
        if len(names) != len(set(names)):
            raise ValueError("backup contains duplicate paths")
        for name in names:
            _safe_archive_name(name)
        if "manifest.json" not in names:
            raise ValueError("backup manifest is missing")
        value = json.loads(archive.read("manifest.json").decode("utf-8"))
        if not isinstance(value, dict) or value.get("schema_version") != ARCHIVE_SCHEMA_VERSION:
            raise ValueError("unsupported backup schema")
        entries = {name: archive.read(name) for name in names if name != "manifest.json"}
    expected = value.get("files")
    if not isinstance(expected, list):
        raise ValueError("backup manifest files are invalid")
    expected_names = [item.get("path") if isinstance(item, dict) else None for item in expected]
    if set(expected_names) != set(entries) or len(expected_names) != len(entries):
        raise ValueError("backup manifest file set does not match archive")
    for item in expected:
        if not isinstance(item, dict) or item.get("size") != len(entries[item["path"]]) or item.get("sha256") != hashlib.sha256(entries[item["path"]]).hexdigest():
            raise ValueError("backup checksum mismatch")
    _validate_capture_entries(entries, value)
    return entries, value
