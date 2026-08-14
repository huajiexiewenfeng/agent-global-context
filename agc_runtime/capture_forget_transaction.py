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

from agc_runtime.capture_transaction import _flush_parent, atomic_write_bytes, atomic_write_json, safe_unlink
from agc_runtime.paths import MemoryPaths


_PRIMARY_NAMESPACES = frozenset({"receipts", "observations", "ledger", "census", "tombstones", "quarantines", "conflicts", "indexes", "dirty", "journals", "staging", "leases", "scan-state", "budgets"})


def _managed_target(paths: MemoryPaths, path: Path) -> str:
    """Return a canonical safe target or reject before-image redirection."""
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(paths.root).as_posix()
    except ValueError as error:
        raise ValueError("invalid Capture forget target") from error
    if relative.startswith(".runtime/capture/"):
        parts = relative.split("/")
        if len(parts) < 4 or parts[2] not in _PRIMARY_NAMESPACES or any(not part or part in {".", ".."} for part in parts):
            raise ValueError("invalid Capture forget target")
        return relative
    if relative.startswith(".runtime/backups/") and resolved.suffix == ".zip" and resolved.is_relative_to(paths.backups.resolve()):
        return relative
    raise ValueError("invalid Capture forget target")


class CaptureForgetTransaction:
    def __init__(self, paths: MemoryPaths, *, point: Callable[[str], None] | None = None) -> None:
        self.paths = paths
        self._point = point or (lambda _name: None)
        self._before: dict[Path, bytes | None] = {}
        self._token = uuid.uuid4().hex
        self._journal = paths.capture.journals / f"capture-forget-{self._token}.json"
        self._images = paths.capture.root / "forget-staging" / f"capture-forget-{self._token}"

    def begin(self, operation_count: int) -> None:
        self._images.mkdir(parents=True, exist_ok=True)
        atomic_write_json(self._journal, {"schema_version": 1, "operation": "capture_forget", "state": "active", "operation_count": operation_count, "before_images": []})

    def _remember(self, path: Path) -> None:
        if path in self._before:
            return
        relative = _managed_target(self.paths, path)
        value = path.read_bytes() if path.exists() else None
        self._before[path] = value
        image_name = f"{len(self._before):04d}.before"
        image = self._images / image_name
        if value is not None:
            atomic_write_bytes(image, value)
        journal = json.loads(self._journal.read_text(encoding="utf-8"))
        journal["before_images"].append({
            "target": relative,
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
        # Cleanup is the commit boundary. A diagnostic callback cannot turn a
        # fully published, journal-free transaction back into a failed write.
        try:
            self._point("after:cleanup")
        except Exception:
            pass

    def _cleanup(self) -> None:
        # Before-images are removed and durably flushed first. If that fails,
        # the active journal remains available for exact retry/recovery.
        if self._images.exists():
            shutil.rmtree(self._images)
            _flush_parent(self._images.parent)
        safe_unlink(self._journal)

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
                images = paths.capture.root / "forget-staging" / f"capture-forget-{token}"
                for entry in reversed(value["before_images"]):
                    if not isinstance(entry, dict) or set(entry) != {"target", "image", "existed"} or not isinstance(entry["target"], str) or not isinstance(entry["image"], str) or not isinstance(entry["existed"], bool):
                        raise ValueError("invalid Capture forget journal")
                    target = paths.resolve_managed(entry["target"])
                    _managed_target(paths, target)
                    image = images / entry["image"]
                    if image.parent != images or "/" in entry["image"] or "\\" in entry["image"]:
                        raise ValueError("invalid Capture forget journal")
                    if entry["existed"]:
                        atomic_write_bytes(target, image.read_bytes())
                    else:
                        target.unlink(missing_ok=True)
                shutil.rmtree(images)
                journal.unlink(missing_ok=True)
                recovered += 1
            except (OSError, ValueError, json.JSONDecodeError) as error:
                # A foreign/corrupt journal must never direct recovery outside
                # its own namespace. Preserve the evidence as a fixed
                # content-free quarantine record and only remove its named
                # dedicated staging directory when its token was canonical.
                token = journal.stem.removeprefix("capture-forget-")
                if token and all(ch in "0123456789abcdef" for ch in token):
                    shutil.rmtree(paths.capture.root / "forget-staging" / f"capture-forget-{token}", ignore_errors=True)
                quarantine = paths.capture.quarantines / f"invalid-forget-journal-{uuid.uuid4().hex}.json"
                atomic_write_json(quarantine, {"schema_version": 1, "code": "corrupt_capture_artifact"})
                journal.unlink(missing_ok=True)
                raise ValueError("invalid Capture forget journal") from error
        return recovered
