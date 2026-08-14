"""Deterministic, Capture-aware managed backup helpers.

The archive is deliberately an allowlist.  Capture's worker scratch space and
secrets are local runtime state, not durable AGC facts.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import stat
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
_CAPTURE_ROOT = ".runtime/capture"
_CAPTURE_PREFIX = f"{_CAPTURE_ROOT}/"
_CAPTURE_ALLOWLIST = frozenset({
    "schema-version", "receipts", "observations", "ledger", "census",
    "tombstones", "quarantines", "conflicts", "indexes",
})
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_RECEIPT_ID = re.compile(r"^cr_[0-9a-f]{64}$")
_OBSERVATION_ID = re.compile(r"^co_[0-9a-f]{64}$")
_TOMBSTONE_ID = re.compile(r"^ct_[0-9a-f]{64}$")
_CENSUS_NAME = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_CONFLICT_NAME = re.compile(r"^source-[0-9a-f]{64}$")
_DIAGNOSTIC_NAME = re.compile(r"^[A-Za-z0-9._-]{1,160}$")
_MAX_ARCHIVE_FILES = 4096
_MAX_FILE_SIZE = 16 * 1024 * 1024
_MAX_TOTAL_SIZE = 64 * 1024 * 1024
_MAX_MANIFEST_SIZE = 1024 * 1024
_MAX_COMPRESSION_RATIO = 200
_MAX_ARCHIVE_SIZE = _MAX_TOTAL_SIZE + _MAX_MANIFEST_SIZE + (2 * 1024 * 1024)
_RUNTIME_EXCLUDED_ROOTS = frozenset({
    ".runtime/locks", ".runtime/backups", ".runtime/queue", ".runtime/cache",
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


def is_protected_capture_path(name: str) -> bool:
    normalized = PurePosixPath(name.replace("\\", "/")).as_posix().casefold()
    return normalized == _CAPTURE_ROOT or normalized.startswith(_CAPTURE_PREFIX)


def _capture_name_allowed(relative: str) -> bool:
    if not is_protected_capture_path(relative):
        return True
    if not relative.startswith(_CAPTURE_PREFIX):
        return False
    tail = relative[len(_CAPTURE_PREFIX):]
    return bool(tail) and tail.split("/", 1)[0] in _CAPTURE_ALLOWLIST


def _is_link_or_reparse(path: Path) -> bool:
    if path.is_symlink():
        return True
    attributes = getattr(path.lstat(), "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return bool(attributes & reparse_flag)


def _runtime_name_excluded(name: str) -> bool:
    folded = name.casefold()
    return any(
        folded == root or folded.startswith(f"{root}/")
        for root in _RUNTIME_EXCLUDED_ROOTS
    )


def _validate_backup_files_for_write(files: list[tuple[str, bytes]]) -> None:
    if len(files) > _MAX_ARCHIVE_FILES:
        raise ValueError("backup file count exceeds safe limit")
    total = 0
    for _name, data in files:
        size = len(data)
        if size > _MAX_FILE_SIZE:
            raise ValueError("backup file size exceeds safe limit")
        total += size
        if total > _MAX_TOTAL_SIZE:
            raise ValueError("backup total size exceeds safe limit")


def backup_files(paths: MemoryPaths) -> list[tuple[str, bytes]]:
    if not paths.root.exists():
        return []
    files: list[tuple[str, bytes]] = []
    total = 0
    root = paths.root.resolve()
    for path in paths.root.rglob("*"):
        if _is_link_or_reparse(path):
            raise ValueError("managed backup path is a symbolic link or reparse point")
        if not path.is_file():
            continue
        resolved = path.resolve()
        if resolved == root or not resolved.is_relative_to(root):
            raise ValueError("managed backup path escapes the memory root")
        relative = resolved.relative_to(root).as_posix()
        if _runtime_name_excluded(relative) or relative.casefold().endswith(".tmp"):
            continue
        if not _capture_name_allowed(relative):
            continue
        if len(files) >= _MAX_ARCHIVE_FILES:
            raise ValueError("backup file count exceeds safe limit")
        size = resolved.stat().st_size
        if size > _MAX_FILE_SIZE:
            raise ValueError("backup file size exceeds safe limit")
        if total + size > _MAX_TOTAL_SIZE:
            raise ValueError("backup total size exceeds safe limit")
        data = resolved.read_bytes()
        if len(data) > _MAX_FILE_SIZE:
            raise ValueError("backup file size exceeds safe limit")
        if total + len(data) > _MAX_TOTAL_SIZE:
            raise ValueError("backup total size exceeds safe limit")
        files.append((relative, data))
        total += len(data)
    return sorted(files, key=lambda item: item[0].encode("utf-8"))


def manifest(files: list[tuple[str, bytes]]) -> dict[str, Any]:
    _validate_backup_files_for_write(files)
    capture_present = any(is_protected_capture_path(name) for name, _ in files)
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
    _validate_backup_files_for_write(files)
    output = io.BytesIO()
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8") + b"\n"
    with zipfile.ZipFile(output, "w") as archive:
        for name, data in files:
            archive.writestr(_zip_info(name), data)
        archive.writestr(_zip_info("manifest.json"), encoded)
    data = output.getvalue()
    _read_verified_archive_bytes(data)
    return data


def _safe_archive_name(name: str) -> None:
    if "\\" in name:
        raise ValueError("backup uses non-canonical path separators")
    pure = PurePosixPath(name)
    if pure.as_posix() != name:
        raise ValueError("backup uses a non-canonical archive path")
    if not name or pure.is_absolute() or ".." in pure.parts or not pure.parts or ":" in pure.parts[0]:
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
    names = [
        name for name in entries
        if is_protected_capture_path(name)
    ]
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
    census_keys: set[tuple[str, str, str, str]] = set()
    for name in names:
        parts = PurePosixPath(name).parts
        if name == ".runtime/capture/schema-version":
            continue
        if len(parts) != 4 or parts[:2] != (".runtime", "capture") or not name.endswith(".json"):
            raise ValueError("invalid Capture archive path")
        namespace = parts[2]
        object_id = parts[3][:-5]
        payload = _json(entries, name)
        if namespace == "receipts":
            if not _RECEIPT_ID.fullmatch(object_id):
                raise ValueError("invalid Capture receipt filename")
            item = CaptureReceipt.from_mapping(payload)
            if item.receipt_id != object_id:
                raise ValueError("Capture receipt filename binding is invalid")
            receipts[item.receipt_id] = item
        elif namespace == "observations":
            if not _OBSERVATION_ID.fullmatch(object_id):
                raise ValueError("invalid Capture observation filename")
            item = CollectedObservation.from_mapping(payload)
            if item.observation_id != object_id:
                raise ValueError("Capture observation filename binding is invalid")
            observations[item.observation_id] = item
        elif namespace == "ledger":
            if not _RECEIPT_ID.fullmatch(object_id):
                raise ValueError("invalid Capture ledger filename")
            item = LedgerEntry.from_mapping(payload)
            if item.receipt_id != object_id:
                raise ValueError("Capture ledger filename binding is invalid")
            ledgers[item.receipt_id] = item
        elif namespace == "census":
            if not _CENSUS_NAME.fullmatch(object_id):
                raise ValueError("invalid Capture census filename")
            revision = RevisionRef.from_mapping(payload)
            key_id = (revision.key.adapter_id, revision.key.source_root_id, revision.key.task_id, revision.key.revision_id)
            if key_id in census_keys:
                raise ValueError("duplicate Capture census key")
            census_keys.add(key_id)
        elif namespace == "tombstones":
            if not _TOMBSTONE_ID.fullmatch(object_id):
                raise ValueError("invalid Capture tombstone filename")
            item = CaptureSuppressionTombstone.from_mapping(payload)
            if item.tombstone_id != object_id:
                raise ValueError("Capture tombstone filename binding is invalid")
        elif namespace == "quarantines":
            if not _DIAGNOSTIC_NAME.fullmatch(object_id):
                raise ValueError("invalid Capture quarantine filename")
            SourceQuarantine.from_mapping(payload)
        elif namespace == "conflicts":
            if not _CONFLICT_NAME.fullmatch(object_id):
                raise ValueError("invalid Capture conflict filename")
            if set(payload) != {"schema_version", "code", "created_at"} or payload.get("schema_version") != CAPTURE_SCHEMA_VERSION or payload.get("code") != "source_conflict" or not isinstance(payload.get("created_at"), str):
                raise ValueError("invalid Capture conflict diagnostic")
        elif namespace == "indexes":
            if not _RECEIPT_ID.fullmatch(object_id):
                raise ValueError("invalid Capture manifest filename")
            if set(payload) != {"schema_version", "receipt_id", "observation_ids"} or payload.get("schema_version") != CAPTURE_SCHEMA_VERSION or payload.get("receipt_id") != object_id or not isinstance(payload.get("observation_ids"), list):
                raise ValueError("invalid Capture immutable manifest")
            ids = payload["observation_ids"]
            if len(ids) > 8 or any(not isinstance(item, str) for item in ids) or len(ids) != len(set(ids)):
                raise ValueError("invalid Capture immutable manifest")
            manifests[object_id] = tuple(ids)
        else:
            raise ValueError("unsupported Capture archive path")
    receipt_keys: set[tuple[str, str, str, str]] = set()
    referenced: set[str] = set()
    for receipt_id, receipt in receipts.items():
        key_id = (receipt.adapter_id, receipt.source_root_id, receipt.task_id, receipt.revision_id)
        if key_id in receipt_keys:
            raise ValueError("duplicate Capture receipt key")
        receipt_keys.add(key_id)
        ledger = ledgers.get(receipt_id)
        if ledger is None or ledger.capture_key != receipt.key or ledger.status != receipt.status:
            raise ValueError("Capture ledger does not match receipt")
        if receipt.status == "complete":
            ids = manifests.get(receipt_id)
            if ids is None or receipt.observation_count != len(ids):
                raise ValueError("Capture receipt manifest does not match")
            if any(item not in observations or observations[item].receipt_id != receipt_id for item in ids):
                raise ValueError("Capture receipt observation reference is invalid")
            referenced.update(ids)
    if any(item.receipt_id not in receipts for item in observations.values()):
        raise ValueError("orphan Capture observation")
    if set(observations) != referenced:
        raise ValueError("unreferenced Capture observation")
    if set(manifests) - set(receipts) or set(ledgers) - set(receipts):
        raise ValueError("orphan Capture graph object")


def _validate_manifest(value: Any, entries: dict[str, bytes]) -> None:
    if not isinstance(value, dict):
        raise ValueError("backup manifest must be a mapping")
    capture_present = any(is_protected_capture_path(name) for name in entries)
    expected_fields = {"schema_version", "files"}
    if capture_present:
        expected_fields.update({"capture_schema_version", "capabilities"})
    if set(value) != expected_fields or value.get("schema_version") != ARCHIVE_SCHEMA_VERSION:
        raise ValueError("unsupported backup schema")
    files = value.get("files")
    if not isinstance(files, list) or len(files) > _MAX_ARCHIVE_FILES:
        raise ValueError("backup manifest files are invalid")
    paths: list[str] = []
    total = 0
    for item in files:
        if not isinstance(item, dict) or set(item) != {"path", "sha256", "size"}:
            raise ValueError("backup manifest file entry is invalid")
        path = item.get("path")
        digest = item.get("sha256")
        size = item.get("size")
        if not isinstance(path, str) or path == "manifest.json":
            raise ValueError("backup manifest path is invalid")
        _safe_archive_name(path)
        if _runtime_name_excluded(path):
            raise ValueError("backup contains excluded transient runtime namespace")
        if not _capture_name_allowed(path):
            raise ValueError("backup contains protected or non-canonical Capture path")
        if path.casefold().endswith(".tmp"):
            raise ValueError("backup contains excluded temporary path")
        if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
            raise ValueError("backup manifest checksum is invalid")
        if type(size) is not int or not 0 <= size <= _MAX_FILE_SIZE:
            raise ValueError("backup manifest size is invalid")
        total += size
        paths.append(path)
    if total > _MAX_TOTAL_SIZE:
        raise ValueError("backup manifest exceeds safe limits")
    if len(paths) != len(set(paths)) or len(paths) != len({path.casefold() for path in paths}):
        raise ValueError("backup manifest contains duplicate paths")
    if set(paths) != set(entries) or len(paths) != len(entries):
        raise ValueError("backup manifest file set does not match archive")
    for item in files:
        data = entries[item["path"]]
        if item["size"] != len(data) or item["sha256"] != hashlib.sha256(data).hexdigest():
            raise ValueError("backup checksum mismatch")


def _read_verified_archive_bytes(
    archive_data: bytes,
) -> tuple[dict[str, bytes], dict[str, Any]]:
    if len(archive_data) > _MAX_ARCHIVE_SIZE:
        raise ValueError("backup archive exceeds safe size limit")
    with zipfile.ZipFile(io.BytesIO(archive_data), "r") as archive:
        infos = archive.infolist()
        if any(info.is_dir() for info in infos):
            raise ValueError("backup contains unexpected directory entries")
        names = [info.filename for info in infos]
        if len(names) > _MAX_ARCHIVE_FILES + 1 or len(names) != len(set(names)) or len({name.casefold() for name in names}) != len(names):
            raise ValueError("backup contains duplicate paths")
        for name in names:
            _safe_archive_name(name)
        if any(((info.external_attr >> 16) & 0o170000) == 0o120000 for info in infos):
            raise ValueError("backup contains a symbolic link")
        if any(
            info.file_size > _MAX_FILE_SIZE
            or (info.file_size > 0 and info.compress_size == 0)
            or (info.compress_size > 0 and info.file_size / info.compress_size > _MAX_COMPRESSION_RATIO)
            for info in infos
        ) or sum(info.file_size for info in infos) > _MAX_TOTAL_SIZE + _MAX_MANIFEST_SIZE:
            raise ValueError("backup exceeds safe archive limits")
        if "manifest.json" not in names:
            raise ValueError("backup manifest is missing")
        manifest_info = archive.getinfo("manifest.json")
        if manifest_info.file_size > _MAX_MANIFEST_SIZE:
            raise ValueError("backup manifest exceeds safe limit")
        value = json.loads(archive.read("manifest.json").decode("utf-8"))
        entries = {name: archive.read(name) for name in names if name != "manifest.json"}
    _validate_manifest(value, entries)
    _validate_capture_entries(entries, value)
    return entries, value


def read_verified_archive(backup_path: Path) -> tuple[dict[str, bytes], dict[str, Any]]:
    if backup_path.stat().st_size > _MAX_ARCHIVE_SIZE:
        raise ValueError("backup archive exceeds safe size limit")
    if _is_link_or_reparse(backup_path):
        raise ValueError("backup archive is a symbolic link or reparse point")
    return _read_verified_archive_bytes(backup_path.read_bytes())
