"""Validated, content-free Codex discovery snapshots.

Snapshots are immutable. A scan-state hint is the only authority to reuse one;
an orphan snapshot from an interrupted scan is never a checkpoint.
"""

from __future__ import annotations

import hashlib
import re
import stat
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from agc_runtime.capture_source import ScanHint
from agc_runtime.capture_transaction import atomic_write_json, canonical_json_bytes, read_json, safe_unlink


CACHE_VERSION = "codex-source-cache-v1"
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")


def snapshot_digest(snapshot: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(snapshot)).hexdigest()


def cache_path(root: Path, source_root_id: str, digest: str) -> Path:
    # A short binding directory avoids Windows MAX_PATH failures for Capture
    # roots beneath an already deep profile path. Full identity is in content.
    if any(not isinstance(item, str) or not _SHA.fullmatch(item) for item in (source_root_id, digest)):
        raise ValueError("invalid source cache identifier")
    return root / source_root_id[:16] / f"{digest}.json"


def checked_path(root: Path, path: Path) -> Path:
    """Reject redirects, including junctions and redirected ancestors of root."""
    try:
        root = root.absolute()
        path = path.absolute()
        path.relative_to(root)
        for candidate in (*reversed(path.parents), path):
            if ".." in candidate.parts:
                raise ValueError("unsafe source cache path")
            try:
                info = candidate.lstat()
            except FileNotFoundError:
                continue
            if (stat.S_ISLNK(info.st_mode)
                    or getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
                    or (stat.S_ISREG(info.st_mode) and info.st_nlink > 1)):
                raise ValueError("unsafe source cache path")
        if not path.resolve().is_relative_to(root.resolve()):
            raise ValueError("unsafe source cache path")
    except (OSError, UnicodeError, ValueError) as error:
        raise ValueError("unsafe source cache path") from error
    return path


def source_generation_locked(root: Path, *, invalidate: bool = False) -> str:
    """Caller holds Capture lock. Epoch is never restored or rolled back."""
    path = checked_path(root, root / "source-generation.json")
    if not invalidate and path.exists():
        value = read_json(path)
        if (set(value) != {"schema_version", "generation"} or value["schema_version"] != 1
                or not isinstance(value["generation"], str)
                or re.fullmatch(r"[0-9a-f]{32}", value["generation"]) is None):
            raise ValueError("invalid source generation")
        return value["generation"]
    generation = uuid.uuid4().hex
    atomic_write_json(path, {"schema_version": 1, "generation": generation})
    return generation


def valid_snapshot(
    value: Any, source_root_id: str, *, adapter_version: str | None = None,
    source_schema_version: str | None = None,
) -> bool:
    if not isinstance(source_root_id, str) or not _SHA.fullmatch(source_root_id):
        return False
    if not isinstance(value, dict) or set(value) != {"version", "source_root_id", "adapter_version", "source_schema_version", "entries"}:
        return False
    if value["version"] != CACHE_VERSION or value["source_root_id"] != source_root_id:
        return False
    if not isinstance(value["adapter_version"], str) or not isinstance(value["source_schema_version"], str):
        return False
    if adapter_version is not None and value["adapter_version"] != adapter_version:
        return False
    if source_schema_version is not None and value["source_schema_version"] != source_schema_version:
        return False
    entries = value["entries"]
    if not isinstance(entries, dict):
        return False
    for locator, entry in entries.items():
        if not isinstance(locator, str) or not locator.startswith(("sessions/", "archived_sessions/")) or ".." in Path(locator).parts:
            return False
        try:
            locator.encode("utf-8")
        except UnicodeError:
            return False
        if not isinstance(entry, dict) or set(entry) != {"signature", "identity", "completions"}:
            return False
        signature = entry["signature"]
        identity = entry["identity"]
        completions = entry["completions"]
        if not isinstance(signature, list) or len(signature) != 5 or any(type(item) is not int or item < 0 for item in signature):
            return False
        if not isinstance(identity, list) or len(identity) != 4 or any(not isinstance(item, str) for item in identity):
            return False
        if not _IDENTIFIER.fullmatch(identity[0]) or not _IDENTIFIER.fullmatch(identity[1]):
            return False
        if identity[2] not in {"session_id", "legacy_rollout_id"} or identity[3] not in {"main", "subagent"}:
            return False
        if not isinstance(completions, list) or any(not isinstance(item, list) or len(item) != 2 or any(not isinstance(part, str) for part in item) for item in completions):
            return False
        for revision_id, completed_at in completions:
            if not _IDENTIFIER.fullmatch(revision_id) or not completed_at.endswith("Z"):
                return False
            try:
                datetime.fromisoformat(completed_at[:-1] + "+00:00")
            except ValueError:
                return False
    return True


def read_snapshot(
    root: Path, hint: ScanHint, source_root_id: str, *,
    adapter_version: str, source_schema_version: str,
) -> dict[str, Any] | None:
    if (hint.hint_schema_version != CACHE_VERSION or not isinstance(hint.opaque_value, str)
            or not _SHA.fullmatch(hint.opaque_value) or hint.source_root_id != source_root_id):
        return None
    try:
        path = checked_path(root, cache_path(root, source_root_id, hint.opaque_value))
        value = read_json(path)
    except (OSError, ValueError, TypeError):
        return None
    if not valid_snapshot(value, source_root_id, adapter_version=adapter_version, source_schema_version=source_schema_version):
        return None
    try:
        if snapshot_digest(value) != hint.opaque_value:
            return None
    except ValueError:
        return None
    return value


def publish_snapshot_locked(root: Path, hint: ScanHint, snapshot: dict[str, Any]) -> None:
    if (
        hint.hint_schema_version != CACHE_VERSION
        or not valid_snapshot(snapshot, hint.source_root_id)
        or snapshot_digest(snapshot) != hint.opaque_value
    ):
        raise ValueError("invalid source cache snapshot")
    path = cache_path(root, hint.source_root_id, hint.opaque_value)
    checked_path(root, path)
    path.parent.mkdir(parents=True, exist_ok=True)
    checked_path(root, path)
    atomic_write_json(path, snapshot)


def retire_other_snapshots_locked(root: Path, hint: ScanHint) -> None:
    directory = checked_path(root, cache_path(root, hint.source_root_id, hint.opaque_value).parent)
    for path in directory.glob("*.json"):
        checked_path(root, path)
        if path.name == f"{hint.opaque_value}.json" or not _SHA.fullmatch(path.stem):
            continue
        try:
            value = read_json(path)
            owned = valid_snapshot(value, hint.source_root_id) and snapshot_digest(value) == path.stem
        except (OSError, ValueError, TypeError):
            continue
        if owned:
            safe_unlink(checked_path(root, path))
