"""Small rollback transaction for Capture hard forget.

The on-disk journal is intentionally content-free: it is only a crash marker;
the before images live in a private staging directory and are removed on either
successful commit or rollback.
"""
from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path
from typing import Callable, Mapping

from agc_runtime.capture_transaction import atomic_write_bytes, atomic_write_json
from agc_runtime.paths import MemoryPaths


class CaptureForgetTransaction:
    def __init__(self, paths: MemoryPaths, *, point: Callable[[str], None] | None = None) -> None:
        self.paths = paths
        self._point = point or (lambda _name: None)
        self._before: dict[Path, bytes | None] = {}
        self._token = uuid.uuid4().hex
        self._journal = paths.capture.journals / f"capture-forget-{self._token}.json"
        self._images = paths.capture.staging / f"capture-forget-{self._token}"

    def begin(self, operation_count: int) -> None:
        self._images.mkdir(parents=True, exist_ok=True)
        atomic_write_json(self._journal, {"schema_version": 1, "operation": "capture_forget", "state": "active", "operation_count": operation_count, "before_images": []})

    def _remember(self, path: Path) -> None:
        if path in self._before:
            return
        value = path.read_bytes() if path.exists() else None
        self._before[path] = value
        image_name = f"{len(self._before):04d}.before"
        image = self._images / image_name
        if value is not None:
            atomic_write_bytes(image, value)
        journal = json.loads(self._journal.read_text(encoding="utf-8"))
        journal["before_images"].append({
            "target": path.relative_to(self.paths.root).as_posix(),
            "image": image_name,
            "existed": value is not None,
        })
        atomic_write_json(self._journal, journal)

    def write(self, path: Path, data: bytes, *, boundary: str) -> None:
        self._remember(path)
        self._point(f"before:{boundary}")
        atomic_write_bytes(path, data)
        self._point(f"after:{boundary}")

    def delete(self, path: Path, *, boundary: str) -> None:
        self._remember(path)
        self._point(f"before:{boundary}")
        path.unlink(missing_ok=True)
        self._point(f"after:{boundary}")

    def rollback(self) -> None:
        for path, data in reversed(tuple(self._before.items())):
            if data is None:
                path.unlink(missing_ok=True)
            else:
                atomic_write_bytes(path, data)
        self._cleanup()

    def commit(self) -> None:
        self._point("before:commit")
        self._cleanup()
        self._point("after:cleanup")

    def _cleanup(self) -> None:
        self._journal.unlink(missing_ok=True)
        shutil.rmtree(self._images, ignore_errors=True)

    @classmethod
    def recover(cls, paths: MemoryPaths) -> int:
        """Rollback interrupted Capture forgets using private before-images."""
        recovered = 0
        for journal in sorted(paths.capture.journals.glob("capture-forget-*.json")):
            try:
                value = json.loads(journal.read_text(encoding="utf-8"))
                if set(value) != {"schema_version", "operation", "state", "operation_count", "before_images"} or value["schema_version"] != 1 or value["operation"] != "capture_forget" or value["state"] != "active" or not isinstance(value["before_images"], list):
                    raise ValueError("invalid Capture forget journal")
                token = journal.stem.removeprefix("capture-forget-")
                if not token or any(ch not in "0123456789abcdef" for ch in token):
                    raise ValueError("invalid Capture forget journal")
                images = paths.capture.staging / f"capture-forget-{token}"
                for entry in reversed(value["before_images"]):
                    if not isinstance(entry, dict) or set(entry) != {"target", "image", "existed"} or not isinstance(entry["target"], str) or not isinstance(entry["image"], str) or not isinstance(entry["existed"], bool):
                        raise ValueError("invalid Capture forget journal")
                    target = paths.resolve_managed(entry["target"])
                    image = images / entry["image"]
                    if image.parent != images or "/" in entry["image"] or "\\" in entry["image"]:
                        raise ValueError("invalid Capture forget journal")
                    if entry["existed"]:
                        atomic_write_bytes(target, image.read_bytes())
                    else:
                        target.unlink(missing_ok=True)
                journal.unlink(missing_ok=True)
                shutil.rmtree(images, ignore_errors=True)
                recovered += 1
            except (OSError, ValueError, json.JSONDecodeError):
                raise ValueError("invalid Capture forget journal")
        return recovered
