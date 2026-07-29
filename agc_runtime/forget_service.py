import hashlib
import json
import os
import re
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agc_runtime.catalog import rebuild_catalog
from agc_runtime.contracts import ToolResponse
from agc_runtime.locking import root_write_lock
from agc_runtime.paths import MemoryPaths
from agc_runtime.utf8_io import atomic_write_text, strict_read_text


_SCOPE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,79}$")
_AMBIGUOUS_SCOPES = {"all", "global", "everything", "*"}
_TEXT_SUFFIXES = {
    ".md",
    ".json",
    ".jsonl",
    ".txt",
    ".yaml",
    ".yml",
    ".toml",
}


def _failed(code: str, message: str) -> ToolResponse:
    return ToolResponse(
        tool="agc.write",
        action="forget",
        status="failed",
        error={"code": code, "message": message},
    )


def _tombstone_path(paths: MemoryPaths, memory_id: str) -> Path:
    digest = hashlib.sha256(memory_id.encode("utf-8")).hexdigest()
    return paths.tombstones / f"{digest}.json"


def _contains_term(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _rewrite_events(paths: MemoryPaths, memory_id: str) -> None:
    event_file = paths.events / "events.jsonl"
    if not event_file.exists():
        return
    retained = []
    for line in strict_read_text(event_file).splitlines():
        if not line:
            continue
        event = json.loads(line)
        if event.get("object_id") != memory_id:
            retained.append(event)
    atomic_write_text(
        event_file,
        "".join(
            json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n"
            for event in retained
        ),
    )


def _rewrite_receipts(paths: MemoryPaths, memory_id: str) -> None:
    receipt_file = paths.receipts / "source-keys.json"
    if not receipt_file.exists():
        return
    registry = json.loads(strict_read_text(receipt_file))
    registry["sources"] = [
        entry
        for entry in registry.get("sources", [])
        if entry.get("object_id") != memory_id
    ]
    atomic_write_text(
        receipt_file,
        json.dumps(registry, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
    )


def _surgical_remove_terms(text: str, terms: tuple[str, ...]) -> str:
    return "".join(
        line
        for line in text.splitlines(keepends=True)
        if not _contains_term(line, terms)
    )


def _rewrite_migrated_sources(
    paths: MemoryPaths,
    memory_id: str,
    verification_terms: tuple[str, ...],
) -> tuple[Path, ...]:
    rewritten = []
    if not paths.migrations.exists():
        return ()
    for manifest_path in sorted(paths.migrations.glob("*/manifest.json")):
        manifest = json.loads(strict_read_text(manifest_path))
        if manifest.get("status") != "completed":
            continue
        memories = manifest.get("memories", [])
        matches = [
            entry
            for entry in memories
            if isinstance(entry, dict) and entry.get("id") == memory_id
        ]
        if not matches:
            continue
        source_root = Path(manifest["source_root"]).resolve()
        for entry in matches:
            source_path = entry.get("source_path")
            if not isinstance(source_path, str):
                raise ValueError("invalid migration memory source_path")
            pure = Path(*source_path.split("/"))
            original = (source_root / pure).resolve()
            if source_root not in original.parents:
                raise ValueError("migration source path escaped source_root")
            snapshot = manifest_path.parent / "snapshot" / pure
            for target in (original, snapshot):
                if not target.exists():
                    continue
                current = strict_read_text(target)
                updated = _surgical_remove_terms(current, verification_terms)
                atomic_write_text(target, updated)
                rewritten.append(target)

        retained = [
            entry
            for entry in memories
            if not (isinstance(entry, dict) and entry.get("id") == memory_id)
        ]
        manifest["memories"] = retained
        manifest["migrated_ids"] = [
            value
            for value in manifest.get("migrated_ids", [])
            if value != memory_id
        ]
        counts = manifest.get("counts")
        if isinstance(counts, dict):
            counts["memories"] = len(retained)
        atomic_write_text(
            manifest_path,
            json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2)
            + "\n",
        )
        rewritten.append(manifest_path)
    return tuple(rewritten)


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o600 << 16
    return info


def _rewrite_backup_zip(
    path: Path,
    memory_id: str,
    verification_terms: tuple[str, ...],
    tombstone_name: str,
    tombstone_bytes: bytes,
) -> None:
    retained: dict[str, bytes] = {}
    with zipfile.ZipFile(path, "r") as archive:
        for info in archive.infolist():
            if info.is_dir() or info.filename == "manifest.json":
                continue
            data = archive.read(info.filename)
            normalized_name = info.filename.replace("\\", "/")
            if normalized_name.endswith(f"/{memory_id}.md"):
                continue
            if Path(normalized_name).suffix.lower() in _TEXT_SUFFIXES:
                try:
                    text = data.decode("utf-8", errors="strict")
                except UnicodeDecodeError:
                    continue
                if memory_id in text or _contains_term(text, verification_terms):
                    continue
            retained[normalized_name] = data
    retained[tombstone_name] = tombstone_bytes
    files = [
        {
            "path": name,
            "sha256": hashlib.sha256(data).hexdigest(),
            "size": len(data),
        }
        for name, data in sorted(retained.items())
    ]
    manifest = json.dumps(
        {"schema_version": 2, "files": files},
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
    ).encode("utf-8") + b"\n"

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    os.close(descriptor)
    try:
        with zipfile.ZipFile(temporary, "w") as archive:
            for name, data in sorted(retained.items()):
                archive.writestr(_zip_info(name), data)
            archive.writestr(_zip_info("manifest.json"), manifest)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def _purge_matching_files(
    root: Path,
    memory_id: str,
    verification_terms: tuple[str, ...],
    *,
    excluded: set[Path],
    tombstone_name: str,
    tombstone_bytes: bytes,
) -> None:
    if not root.exists():
        return
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path in excluded:
            continue
        if path.suffix.lower() == ".zip":
            _rewrite_backup_zip(
                path,
                memory_id,
                verification_terms,
                tombstone_name,
                tombstone_bytes,
            )
            continue
        relative = str(path.relative_to(root)).replace("\\", "/")
        exact_name = path.name == f"{memory_id}.md"
        matches = memory_id in relative
        if path.suffix.lower() in _TEXT_SUFFIXES:
            text = strict_read_text(path)
            matches = (
                matches
                or memory_id in text
                or _contains_term(text, verification_terms)
            )
        if exact_name or matches:
            path.unlink()


def forget(paths: MemoryPaths, request: Any) -> ToolResponse:
    if not isinstance(request, dict):
        return _failed("invalid_request", "request must be a mapping")
    if request.get("authorization") != "explicit_user_request":
        return _failed(
            "forget_authorization_required",
            "hard forget requires explicit_user_request authorization",
        )
    memory_id = request.get("memory_id")
    if not isinstance(memory_id, str) or not memory_id:
        return _failed("memory_id_required", "exact memory_id is required")
    suppression_scope = request.get("suppression_scope")
    if (
        not isinstance(suppression_scope, str)
        or not _SCOPE_PATTERN.fullmatch(suppression_scope)
        or suppression_scope in _AMBIGUOUS_SCOPES
    ):
        return ToolResponse(
            tool="agc.write",
            action="forget",
            status="needs_adjudication",
            data={"code": "ambiguous_suppression_scope"},
        )
    raw_terms = request.get("verification_terms", [])
    if not isinstance(raw_terms, list) or any(
        not isinstance(term, str) or not term for term in raw_terms
    ) or not raw_terms:
        return _failed(
            "invalid_verification_terms",
            "verification_terms must be a non-empty list of non-empty strings",
        )
    verification_terms = tuple(raw_terms)
    forgotten_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    tombstone = {
        "memory_id": memory_id,
        "status": "forgotten",
        "forgotten_at": forgotten_at,
        "suppression_scope": suppression_scope,
    }
    tombstone_text = (
        json.dumps(tombstone, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    )
    tombstone_bytes = tombstone_text.encode("utf-8")
    tombstone_file = _tombstone_path(paths, memory_id)
    tombstone_name = str(tombstone_file.relative_to(paths.root)).replace("\\", "/")

    with root_write_lock(paths):
        existing_memories = list(paths.memories.glob(f"*/{memory_id}.md"))
        if not existing_memories and tombstone_file.exists():
            existing = json.loads(strict_read_text(tombstone_file))
            return ToolResponse(
                tool="agc.write",
                action="forget",
                status="accepted",
                data={
                    "code": "already_forgotten",
                    "tombstone": existing,
                    "managed_agc_copies_deleted": True,
                    "source_task_deleted": False,
                },
            )
        if not existing_memories:
            return _failed("memory_not_found", f"memory not found: {memory_id}")
        if len(existing_memories) > 1:
            return ToolResponse(
                tool="agc.write",
                action="forget",
                status="needs_adjudication",
                data={"code": "ambiguous_memory_id"},
            )

        _rewrite_events(paths, memory_id)
        _rewrite_receipts(paths, memory_id)
        rewritten_legacy = _rewrite_migrated_sources(
            paths, memory_id, verification_terms
        )
        excluded = {
            paths.locks / "write.lock",
            paths.catalog_json,
            paths.catalog_md,
            tombstone_file,
        }
        excluded.update(
            path
            for path in rewritten_legacy
            if path == paths.root or paths.root in path.parents
        )
        _purge_matching_files(
            paths.root,
            memory_id,
            verification_terms,
            excluded=excluded,
            tombstone_name=tombstone_name,
            tombstone_bytes=tombstone_bytes,
        )
        atomic_write_text(tombstone_file, tombstone_text)
        rebuild_catalog(paths, acquire_lock=False)

        for path in rewritten_legacy:
            if not path.exists():
                raise RuntimeError(
                    f"forget removed a shared registered source: {path}"
                )
            if _contains_term(strict_read_text(path), verification_terms):
                raise RuntimeError(
                    f"forget verification failed for registered source: {path}"
                )
        for path in paths.root.rglob("*"):
            if (
                path.is_file()
                and path != tombstone_file
                and path.suffix.lower() in _TEXT_SUFFIXES
                and _contains_term(strict_read_text(path), verification_terms)
            ):
                raise RuntimeError(
                    f"forget verification failed for managed path: {path}"
                )

    return ToolResponse(
        tool="agc.write",
        action="forget",
        status="accepted",
        data={
            "code": "memory_forgotten",
            "tombstone": tombstone,
            "managed_agc_copies_deleted": True,
            "source_task_deleted": False,
        },
    )
