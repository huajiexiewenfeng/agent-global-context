"""Immutable, content-free dirty-marker spool for Capture reconciliation."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import uuid
from pathlib import Path
from typing import Any, Mapping

from agc_runtime.capture_source import DirtyMarker


def _canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )


def _nonce_token() -> str:
    return uuid.uuid4().hex


def _stable_key(marker: DirtyMarker) -> str:
    key = {
        "adapter_id": marker.adapter_id,
        "revision_id": marker.revision_id,
        "source_root_id": marker.source_root_id,
        "task_id": marker.task_id,
    }
    return hashlib.sha256(_canonical_json_bytes(key)).hexdigest()


def _flush_file(descriptor: int) -> None:
    fsync = getattr(os, "fsync", None)
    if fsync is not None:
        fsync(descriptor)


def _flush_directory(directory: Path) -> None:
    try:
        descriptor = os.open(directory, os.O_RDONLY)
    except (AttributeError, OSError):
        return
    try:
        _flush_file(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def write_dirty_marker(memory_root: Path, marker: DirtyMarker) -> Path:
    """Atomically install one immutable marker under the bound memory root."""

    validated = DirtyMarker.from_mapping(marker.to_mapping())
    root = memory_root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("memory root must be an existing directory")
    dirty = root / ".runtime" / "capture" / "dirty"
    dirty.mkdir(parents=True, exist_ok=True)
    resolved_dirty = dirty.resolve(strict=True)
    if resolved_dirty == root or root not in resolved_dirty.parents:
        raise ValueError("dirty spool escaped memory root")

    final = resolved_dirty / f"dm_{_stable_key(validated)}_{_nonce_token()}.json"
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{final.name}.", suffix=".tmp", dir=resolved_dirty
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(_canonical_json_bytes(validated.to_mapping()))
            stream.flush()
            _flush_file(stream.fileno())
        if final.exists():
            raise FileExistsError("dirty marker collision")
        os.replace(temporary, final)
        _flush_directory(resolved_dirty)
        return final
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


__all__ = ["write_dirty_marker"]
