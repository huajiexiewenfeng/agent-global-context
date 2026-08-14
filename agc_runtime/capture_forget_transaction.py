"""Small rollback transaction for Capture hard forget.

The on-disk journal is intentionally content-free: it is only a crash marker;
the before images live in a private staging directory and are removed on either
successful commit or rollback.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping

from agc_runtime.capture_contracts import SourceQuarantine
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
        safe_unlink(path)
        self._point(f"after:{boundary}")

    def rollback(self) -> None:
        for path, data in reversed(tuple(self._before.items())):
            if data is None:
                safe_unlink(path)
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
                if journal.is_symlink():
                    raise ValueError("invalid Capture forget journal")
                value = json.loads(journal.read_text(encoding="utf-8"))
                if (
                    not isinstance(value, dict)
                    or set(value) != {"schema_version", "operation", "state", "operation_count", "before_images"}
                    or value["schema_version"] != 1
                    or value["operation"] != "capture_forget"
                    or value["state"] != "active"
                    or type(value["operation_count"]) is not int
                    or value["operation_count"] < 0
                    or not isinstance(value["before_images"], list)
                    or value["operation_count"] != len(value["before_images"])
                ):
                    raise ValueError("invalid Capture forget journal")
                token = journal.stem.removeprefix("capture-forget-")
                if re.fullmatch(r"[0-9a-f]{32}", token) is None:
                    raise ValueError("invalid Capture forget journal")
                images = paths.capture.root / "forget-staging" / f"capture-forget-{token}"
                if images.is_symlink() or not images.is_dir():
                    raise ValueError("invalid Capture forget journal")
                images_root = (paths.capture.root / "forget-staging").resolve()
                if not images.resolve().is_relative_to(images_root):
                    raise ValueError("invalid Capture forget journal")
                plan: list[tuple[Path, bytes | None]] = []
                targets: set[Path] = set()
                image_names: set[str] = set()
                for entry in value["before_images"]:
                    if not isinstance(entry, dict) or set(entry) != {"target", "image", "existed"} or not isinstance(entry["target"], str) or not isinstance(entry["image"], str) or not isinstance(entry["existed"], bool):
                        raise ValueError("invalid Capture forget journal")
                    target = paths.resolve_managed(entry["target"])
                    _managed_target(paths, target)
                    if target in targets:
                        raise ValueError("invalid Capture forget journal")
                    targets.add(target)
                    image = images / entry["image"]
                    if (
                        image.parent != images
                        or re.fullmatch(r"[0-9]{4}\.before", entry["image"]) is None
                        or entry["image"] in image_names
                    ):
                        raise ValueError("invalid Capture forget journal")
                    image_names.add(entry["image"])
                    if entry["existed"]:
                        if image.is_symlink() or not image.is_file() or image.resolve().parent != images.resolve():
                            raise ValueError("invalid Capture forget journal")
                        before = image.read_bytes()
                    else:
                        if image.exists():
                            raise ValueError("invalid Capture forget journal")
                        before = None
                    plan.append((target, before))
                for target, before in reversed(plan):
                    if before is None:
                        safe_unlink(target)
                    else:
                        atomic_write_bytes(target, before)
                shutil.rmtree(images)
                _flush_parent(images.parent)
                safe_unlink(journal)
                recovered += 1
            except (OSError, ValueError, json.JSONDecodeError) as error:
                # A foreign/corrupt journal must never direct recovery outside
                # its own namespace. Preserve the evidence as a fixed
                # content-free quarantine record and only remove its named
                # dedicated staging directory when its token was canonical.
                token = journal.stem.removeprefix("capture-forget-")
                if re.fullmatch(r"[0-9a-f]{32}", token):
                    images = paths.capture.root / "forget-staging" / f"capture-forget-{token}"
                    images_root = (paths.capture.root / "forget-staging").resolve()
                    if (
                        images.exists()
                        and not images.is_symlink()
                        and images.resolve().is_relative_to(images_root)
                    ):
                        shutil.rmtree(images, ignore_errors=True)
                        _flush_parent(images.parent)
                quarantine = paths.capture.quarantines / f"invalid-forget-journal-{uuid.uuid4().hex}.json"
                quarantine_value = SourceQuarantine.from_mapping({
                    "schema_version": 1,
                    "adapter_id": "capture_recovery",
                    "source_root_id": hashlib.sha256(journal.name.encode("utf-8")).hexdigest(),
                    "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                    "code": "corrupt_capture_artifact",
                })
                atomic_write_json(quarantine, quarantine_value.to_mapping())
                safe_unlink(journal)
                raise ValueError("invalid Capture forget journal") from error
        return recovered
