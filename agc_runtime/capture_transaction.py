"""Small, content-safe persistence primitives for Capture transactions."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping

from agc_runtime.utf8_io import strict_read_text


def canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    """Encode an auditable Capture object as strict UTF-8 JSON with an LF."""
    try:
        return (
            json.dumps(
                value, allow_nan=False, ensure_ascii=False, sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            + b"\n"
        )
    except (TypeError, ValueError, UnicodeEncodeError) as error:
        raise ValueError("Capture transaction value is not canonical JSON") from error


def atomic_write_json(path: Path, value: Mapping[str, Any]) -> None:
    """Install one fully written JSON object, including on Windows."""
    data = canonical_json_bytes(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(strict_read_text(path))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("invalid Capture JSON object") from error
    if not isinstance(value, dict):
        raise ValueError("Capture JSON object must be a mapping")
    return value
