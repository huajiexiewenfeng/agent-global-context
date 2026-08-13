"""Content-safe atomic persistence primitives for Capture transactions."""

from __future__ import annotations

import ctypes
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping

from agc_runtime.utf8_io import strict_read_text


def canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    try:
        return json.dumps(
            value, allow_nan=False, ensure_ascii=False, sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8") + b"\n"
    except (TypeError, ValueError, UnicodeEncodeError) as error:
        raise ValueError("Capture transaction value is not canonical JSON") from error


def _flush_parent(path: Path) -> None:
    """Ask the platform to persist a directory entry after replace/unlink.

    This is the best available local durability barrier, not a claim about a
    particular disk controller's power-loss guarantees.
    """
    if sys.platform != "win32":
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.restype = ctypes.c_void_p
    handle = create_file(str(path), 0x40000000, 0x7, None, 3, 0x02000000, None)
    if handle == ctypes.c_void_p(-1).value:
        raise OSError(ctypes.get_last_error(), "could not open Capture directory")
    try:
        if not kernel32.FlushFileBuffers(handle):
            raise OSError(ctypes.get_last_error(), "could not flush Capture directory")
    finally:
        kernel32.CloseHandle(handle)


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        _flush_parent(path.parent)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def atomic_write_json(path: Path, value: Mapping[str, Any]) -> None:
    atomic_write_bytes(path, canonical_json_bytes(value))


def safe_unlink(path: Path) -> None:
    path.unlink(missing_ok=True)
    _flush_parent(path.parent)


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(strict_read_text(path))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("invalid Capture JSON object") from error
    if not isinstance(value, dict):
        raise ValueError("Capture JSON object must be a mapping")
    return value
