import codecs
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from agc_runtime.catalog import rebuild_catalog
from agc_runtime.contracts import SourceKey, ToolResponse
from agc_runtime.locking import root_write_lock
from agc_runtime.models import MemoryItem
from agc_runtime.paths import MemoryPaths
from agc_runtime.schema import validate_memory_item
from agc_runtime.store import MemoryStore
from agc_runtime.utf8_io import atomic_write_text, strict_read_text


_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,79}$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_TOP_LEVEL_FIELDS = {
    "action",
    "migration_id",
    "source_root",
    "sources",
    "memories",
}
_SOURCE_FIELDS = {"path", "sha256", "disposition"}
_MEMORY_FIELDS = {"source_path", "memory_markdown"}
_DISPOSITIONS = {"snapshot", "ignored", "excluded_sensitive"}


@dataclass(frozen=True)
class _ValidatedSource:
    relative_path: str
    absolute_path: Path
    sha256: str
    disposition: str
    snapshot_text: str | None
    source_had_bom: bool


@dataclass(frozen=True)
class _ValidatedMemory:
    source_path: str
    item: MemoryItem


def _failed(code: str, message: str) -> ToolResponse:
    return ToolResponse(
        tool="agc.admin",
        action="migrate",
        status="failed",
        error={"code": code, "message": message},
    )


def _strict_mapping(
    value: Any, name: str, fields: set[str]
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a mapping")
    unknown = set(value) - fields
    if unknown:
        raise ValueError(f"unknown {name} field: {sorted(unknown)[0]}")
    missing = fields - set(value)
    if missing:
        raise ValueError(f"missing {name} field: {sorted(missing)[0]}")
    return value


def _non_empty_string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _source_path(source_root: Path, raw_path: Any) -> tuple[str, Path]:
    value = _non_empty_string(raw_path, "source.path")
    if "\\" in value:
        raise ValueError("source.path must use forward slashes")
    pure = PurePosixPath(value)
    if pure.is_absolute() or not pure.parts or "." in pure.parts or ".." in pure.parts:
        raise ValueError("source.path must be relative and remain inside source_root")
    normalized = pure.as_posix()
    absolute = (source_root / Path(*pure.parts)).resolve()
    if absolute == source_root or source_root not in absolute.parents:
        raise ValueError("source.path must remain inside source_root")
    return normalized, absolute


def _decode_legacy_text(raw: bytes, source_path: str) -> tuple[str, bool]:
    had_bom = raw.startswith(codecs.BOM_UTF8)
    payload = raw[len(codecs.BOM_UTF8) :] if had_bom else raw
    try:
        return payload.decode("utf-8", errors="strict"), had_bom
    except UnicodeDecodeError as error:
        raise ValueError(
            f"legacy text source is not valid UTF-8: {source_path}"
        ) from error


def _validate_sources(
    source_root: Path, values: Any
) -> tuple[_ValidatedSource, ...]:
    if not isinstance(values, list):
        raise ValueError("sources must be a list")
    validated = []
    seen: set[str] = set()
    for raw_entry in values:
        entry = _strict_mapping(raw_entry, "source", _SOURCE_FIELDS)
        relative, absolute = _source_path(source_root, entry["path"])
        if relative in seen:
            raise ValueError(f"duplicate source.path: {relative}")
        seen.add(relative)
        expected_hash = _non_empty_string(entry["sha256"], "source.sha256")
        if not _SHA256_PATTERN.fullmatch(expected_hash):
            raise ValueError("source.sha256 must be lowercase SHA-256")
        disposition = _non_empty_string(
            entry["disposition"], "source.disposition"
        )
        if disposition not in _DISPOSITIONS:
            raise ValueError(f"invalid source disposition: {disposition}")
        raw = absolute.read_bytes()
        actual_hash = hashlib.sha256(raw).hexdigest()
        if actual_hash != expected_hash:
            raise RuntimeError(f"source hash mismatch: {relative}")
        snapshot_text = None
        had_bom = False
        if disposition in {"snapshot", "ignored"}:
            text, had_bom = _decode_legacy_text(raw, relative)
            if disposition == "snapshot":
                snapshot_text = text
        validated.append(
            _ValidatedSource(
                relative_path=relative,
                absolute_path=absolute,
                sha256=expected_hash,
                disposition=disposition,
                snapshot_text=snapshot_text,
                source_had_bom=had_bom,
            )
        )
    return tuple(validated)


def _validate_memories(
    values: Any, sources: tuple[_ValidatedSource, ...]
) -> tuple[_ValidatedMemory, ...]:
    if not isinstance(values, list):
        raise ValueError("memories must be a list")
    source_by_path = {source.relative_path: source for source in sources}
    validated = []
    seen_ids: set[str] = set()
    for raw_entry in values:
        entry = _strict_mapping(raw_entry, "memory", _MEMORY_FIELDS)
        source_path = _non_empty_string(
            entry["source_path"], "memory.source_path"
        )
        source = source_by_path.get(source_path)
        if source is None or source.disposition != "snapshot":
            raise ValueError(
                "memory.source_path must reference a declared snapshot source"
            )
        markdown = _non_empty_string(
            entry["memory_markdown"], "memory.memory_markdown"
        )
        item = MemoryItem.from_markdown(markdown)
        validate_memory_item(item)
        if item.id in seen_ids:
            raise ValueError(f"duplicate migrated memory id: {item.id}")
        seen_ids.add(item.id)
        validated.append(_ValidatedMemory(source_path=source_path, item=item))
    return tuple(validated)


def _canonical_request_digest(
    migration_id: str,
    source_root: Path,
    sources: tuple[_ValidatedSource, ...],
    memories: tuple[_ValidatedMemory, ...],
) -> str:
    value = {
        "action": "migrate",
        "migration_id": migration_id,
        "source_root": str(source_root),
        "sources": [
            {
                "path": source.relative_path,
                "sha256": source.sha256,
                "disposition": source.disposition,
            }
            for source in sorted(sources, key=lambda item: item.relative_path)
        ],
        "memories": [
            {
                "source_path": memory.source_path,
                "memory_markdown": memory.item.to_markdown(),
            }
            for memory in sorted(memories, key=lambda item: item.item.id)
        ],
    }
    canonical = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _counts(
    sources: tuple[_ValidatedSource, ...],
    memories: tuple[_ValidatedMemory, ...],
) -> dict[str, int]:
    return {
        "sources": len(sources),
        "snapshots": sum(
            source.disposition == "snapshot" for source in sources
        ),
        "ignored": sum(source.disposition == "ignored" for source in sources),
        "excluded_sensitive": sum(
            source.disposition == "excluded_sensitive" for source in sources
        ),
        "memories": len(memories),
    }


def _response_data(
    migration_id: str, counts: dict[str, int]
) -> dict[str, Any]:
    return {
        "code": "migration_completed",
        "migration_id": migration_id,
        "source_count": counts["sources"],
        "snapshot_count": counts["snapshots"],
        "ignored_count": counts["ignored"],
        "excluded_sensitive_count": counts["excluded_sensitive"],
        "memory_count": counts["memories"],
    }


def _read_manifest(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    value = json.loads(strict_read_text(path))
    if not isinstance(value, dict):
        raise ValueError("migration manifest must be a mapping")
    return value


def _migration_receipt_ids(paths: MemoryPaths, migration_id: str) -> set[str]:
    receipt_file = paths.receipts / "source-keys.json"
    if not receipt_file.exists():
        return set()
    registry = json.loads(strict_read_text(receipt_file))
    return {
        entry["object_id"]
        for entry in registry.get("sources", [])
        if isinstance(entry, dict)
        and entry.get("revision") == migration_id
        and isinstance(entry.get("ref"), str)
        and entry["ref"].startswith("migration:v1:")
        and isinstance(entry.get("object_id"), str)
    }


def _existing_memory_ids(paths: MemoryPaths) -> set[str]:
    if not paths.memories.exists():
        return set()
    values = set()
    for path in paths.memories.rglob("*.md"):
        item = MemoryItem.from_markdown(strict_read_text(path))
        validate_memory_item(item)
        values.add(item.id)
    return values


def _ensure_target_allows_migration(
    paths: MemoryPaths,
    migration_id: str,
    requested_ids: set[str],
) -> None:
    existing_ids = _existing_memory_ids(paths)
    if not existing_ids:
        return
    recorded_ids = _migration_receipt_ids(paths, migration_id)
    if not existing_ids.issubset(recorded_ids & requested_ids):
        raise PermissionError(
            "target contains non-migration Memory Items"
        )


def _initialize_under_lock(paths: MemoryPaths) -> None:
    from agc_runtime.admin_service import CONFIG_TEXT, _managed_directories

    for directory in _managed_directories(paths):
        directory.mkdir(parents=True, exist_ok=True)
    atomic_write_text(paths.root / "schema-version", "2\n")
    atomic_write_text(paths.root / "config.yaml", CONFIG_TEXT)


def _manifest_value(
    migration_id: str,
    request_digest: str,
    source_root: Path,
    sources: tuple[_ValidatedSource, ...],
    memories: tuple[_ValidatedMemory, ...],
    *,
    status: str,
) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "migration_id": migration_id,
        "request_digest": request_digest,
        "source_root": str(source_root),
        "status": status,
        "sources": [
            {
                "path": source.relative_path,
                "sha256": source.sha256,
                "disposition": source.disposition,
                "source_had_bom": source.source_had_bom,
            }
            for source in sorted(sources, key=lambda item: item.relative_path)
        ],
        "memories": [
            {"id": memory.item.id, "source_path": memory.source_path}
            for memory in sorted(memories, key=lambda item: item.item.id)
        ],
        "migrated_ids": sorted(
            (memory.item.id for memory in memories),
            key=lambda value: value.encode("utf-8"),
        ),
        "counts": _counts(sources, memories),
    }


def _migrate_validated(
    paths: MemoryPaths,
    migration_id: str,
    source_root: Path,
    sources: tuple[_ValidatedSource, ...],
    memories: tuple[_ValidatedMemory, ...],
    request_digest: str,
) -> ToolResponse:
    migration_root = paths.migrations / migration_id
    manifest_path = migration_root / "manifest.json"
    existing_manifest = _read_manifest(manifest_path)
    if existing_manifest is not None:
        if existing_manifest.get("request_digest") != request_digest:
            return _failed(
                "migration_id_conflict",
                "migration_id is already registered to a different request",
            )
        if existing_manifest.get("status") == "completed":
            counts = existing_manifest.get("counts")
            if not isinstance(counts, dict):
                return _failed(
                    "invalid_migration_receipt",
                    "completed migration receipt has invalid counts",
                )
            return ToolResponse(
                tool="agc.admin",
                action="migrate",
                status="accepted",
                data=_response_data(migration_id, counts),
            )

    _ensure_target_allows_migration(
        paths,
        migration_id,
        {memory.item.id for memory in memories},
    )
    counts = _counts(sources, memories)
    source_by_path = {source.relative_path: source for source in sources}

    with root_write_lock(paths):
        # MemoryStore's public default still locks. Migration already owns the
        # single root write lock, so this internal call explicitly reuses it.
        current_manifest = _read_manifest(manifest_path)
        if current_manifest is not None:
            if current_manifest.get("request_digest") != request_digest:
                return _failed(
                    "migration_id_conflict",
                    "migration_id is already registered to a different request",
                )
            if current_manifest.get("status") == "completed":
                stored_counts = current_manifest.get("counts")
                if not isinstance(stored_counts, dict):
                    return _failed(
                        "invalid_migration_receipt",
                        "completed migration receipt has invalid counts",
                    )
                return ToolResponse(
                    tool="agc.admin",
                    action="migrate",
                    status="accepted",
                    data=_response_data(migration_id, stored_counts),
                )
        _ensure_target_allows_migration(
            paths,
            migration_id,
            {memory.item.id for memory in memories},
        )
        _initialize_under_lock(paths)
        in_progress_manifest = _manifest_value(
            migration_id,
            request_digest,
            source_root,
            sources,
            memories,
            status="in_progress",
        )
        atomic_write_text(
            manifest_path,
            json.dumps(
                in_progress_manifest,
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            )
            + "\n",
        )
        for source in sources:
            if source.disposition != "snapshot":
                continue
            snapshot = (
                migration_root
                / "snapshot"
                / Path(*PurePosixPath(source.relative_path).parts)
            )
            atomic_write_text(snapshot, source.snapshot_text or "")

        store = MemoryStore(paths)
        for memory in memories:
            source = source_by_path[memory.source_path]
            result = store.create_memory(
                memory.item,
                SourceKey(
                    ref=(
                        f"migration:v1:{memory.source_path}"
                        f"#{memory.item.id}"
                    ),
                    revision=migration_id,
                    content_hash=source.sha256,
                ),
                acquire_lock=False,
            )
            if result.status != "accepted":
                raise RuntimeError(
                    f"migration memory persistence failed: {result.code}"
                )

        rebuild_catalog(paths, acquire_lock=False)
        from agc_runtime.admin_service import _validate_root

        issues = _validate_root(paths)
        if issues:
            raise RuntimeError(
                f"migration validation failed with {len(issues)} issue(s)"
            )
        manifest = _manifest_value(
            migration_id,
            request_digest,
            source_root,
            sources,
            memories,
            status="completed",
        )
        atomic_write_text(
            manifest_path,
            json.dumps(
                manifest, ensure_ascii=False, sort_keys=True, indent=2
            )
            + "\n",
        )

    return ToolResponse(
        tool="agc.admin",
        action="migrate",
        status="accepted",
        data=_response_data(migration_id, counts),
    )


def migrate_v1(
    paths: MemoryPaths, request: dict[str, Any]
) -> ToolResponse:
    try:
        root = _strict_mapping(request, "request", _TOP_LEVEL_FIELDS)
        if root["action"] != "migrate":
            raise ValueError("action must be migrate")
        migration_id = _non_empty_string(
            root["migration_id"], "migration_id"
        )
        if not _ID_PATTERN.fullmatch(migration_id):
            raise ValueError("migration_id must use the safe ID grammar")
        raw_source_root = _non_empty_string(
            root["source_root"], "source_root"
        )
        source_root_value = Path(raw_source_root)
        if not source_root_value.is_absolute():
            raise ValueError("source_root must be absolute")
        source_root = source_root_value.resolve()
        if source_root == paths.root:
            raise ValueError("source_root must differ from target root")

        # Every source and Memory Item is fully validated before any target write.
        sources = _validate_sources(source_root, root["sources"])
        memories = _validate_memories(root["memories"], sources)
        request_digest = _canonical_request_digest(
            migration_id, source_root, sources, memories
        )
        return _migrate_validated(
            paths,
            migration_id,
            source_root,
            sources,
            memories,
            request_digest,
        )
    except RuntimeError as error:
        if str(error).startswith("source hash mismatch:"):
            return _failed("source_hash_mismatch", str(error))
        return _failed("migration_failed", str(error))
    except PermissionError as error:
        return _failed("target_not_empty", str(error))
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        json.JSONDecodeError,
    ) as error:
        return _failed("invalid_request", str(error))
