import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any

from agc_runtime.paths import MemoryPaths
from agc_runtime.store import MemoryStore
from agc_runtime.utf8_io import strict_read_text


SAFE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,79}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
DISPOSITIONS = {"snapshot", "ignored", "excluded_sensitive"}
_FIELDS = {
    "schema_version",
    "migration_id",
    "request_digest",
    "integrity_sha256",
    "source_root",
    "status",
    "sources",
    "memories",
    "migrated_ids",
    "counts",
}
_SOURCE_FIELDS = {
    "path",
    "sha256",
    "disposition",
    "source_had_bom",
}
_MEMORY_FIELDS = {"id", "source_path"}
_COUNT_FIELDS = {
    "sources",
    "snapshots",
    "ignored",
    "excluded_sensitive",
    "memories",
}


class MigrationManifestError(ValueError):
    pass


def _mapping(value: Any, name: str, fields: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise MigrationManifestError(f"{name} must be a mapping")
    unknown = set(value) - fields
    if unknown:
        raise MigrationManifestError(
            f"unknown {name} field: {sorted(unknown)[0]}"
        )
    missing = fields - set(value)
    if missing:
        raise MigrationManifestError(
            f"missing {name} field: {sorted(missing)[0]}"
        )
    return value


def _string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise MigrationManifestError(f"{name} must be a non-empty string")
    return value


def _relative_source_path(raw: Any) -> str:
    value = _string(raw, "manifest source.path")
    if "\\" in value:
        raise MigrationManifestError(
            "manifest source.path must use forward slashes"
        )
    pure = PurePosixPath(value)
    if (
        pure.is_absolute()
        or not pure.parts
        or "." in pure.parts
        or ".." in pure.parts
    ):
        raise MigrationManifestError(
            "manifest source.path must be safe and relative"
        )
    return pure.as_posix()


def _canonical_bytes(value: dict[str, Any]) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def migration_manifest_integrity(value: dict[str, Any]) -> str:
    content = {
        key: item for key, item in value.items() if key != "integrity_sha256"
    }
    return hashlib.sha256(_canonical_bytes(content)).hexdigest()


def validate_migration_manifest(
    value: Any, *, expected_migration_id: str | None = None
) -> dict[str, Any]:
    manifest = _mapping(value, "manifest", _FIELDS)
    if manifest["schema_version"] != 2:
        raise MigrationManifestError("manifest schema_version must be 2")
    migration_id = _string(
        manifest["migration_id"], "manifest migration_id"
    )
    if not SAFE_ID_PATTERN.fullmatch(migration_id):
        raise MigrationManifestError("invalid manifest migration_id")
    if (
        expected_migration_id is not None
        and migration_id != expected_migration_id
    ):
        raise MigrationManifestError(
            "manifest migration_id does not match its directory"
        )
    request_digest = _string(
        manifest["request_digest"], "manifest request_digest"
    )
    integrity = _string(
        manifest["integrity_sha256"], "manifest integrity_sha256"
    )
    if not SHA256_PATTERN.fullmatch(request_digest):
        raise MigrationManifestError("invalid manifest request_digest")
    if not SHA256_PATTERN.fullmatch(integrity):
        raise MigrationManifestError("invalid manifest integrity_sha256")
    if migration_manifest_integrity(manifest) != integrity:
        raise MigrationManifestError("migration manifest integrity mismatch")
    source_root = _string(
        manifest["source_root"], "manifest source_root"
    )
    if not Path(source_root).is_absolute():
        raise MigrationManifestError("manifest source_root must be absolute")
    if manifest["status"] not in {"in_progress", "completed"}:
        raise MigrationManifestError("invalid manifest status")

    raw_sources = manifest["sources"]
    if not isinstance(raw_sources, list):
        raise MigrationManifestError("manifest sources must be a list")
    source_by_path: dict[str, dict[str, Any]] = {}
    for raw_source in raw_sources:
        source = _mapping(
            raw_source, "manifest source", _SOURCE_FIELDS
        )
        path = _relative_source_path(source["path"])
        if path in source_by_path:
            raise MigrationManifestError(
                f"duplicate manifest source path: {path}"
            )
        sha256 = _string(
            source["sha256"], "manifest source.sha256"
        )
        if not SHA256_PATTERN.fullmatch(sha256):
            raise MigrationManifestError(
                "manifest source.sha256 must be lowercase SHA-256"
            )
        if source["disposition"] not in DISPOSITIONS:
            raise MigrationManifestError(
                "invalid manifest source disposition"
            )
        if not isinstance(source["source_had_bom"], bool):
            raise MigrationManifestError(
                "manifest source_had_bom must be boolean"
            )
        source_by_path[path] = source

    raw_memories = manifest["memories"]
    if not isinstance(raw_memories, list):
        raise MigrationManifestError("manifest memories must be a list")
    memory_ids: set[str] = set()
    for raw_memory in raw_memories:
        memory = _mapping(
            raw_memory, "manifest memory", _MEMORY_FIELDS
        )
        memory_id = _string(memory["id"], "manifest memory.id")
        if not SAFE_ID_PATTERN.fullmatch(memory_id):
            raise MigrationManifestError("invalid manifest memory id")
        if memory_id in memory_ids:
            raise MigrationManifestError(
                f"duplicate manifest memory id: {memory_id}"
            )
        memory_ids.add(memory_id)
        source = source_by_path.get(
            _relative_source_path(memory["source_path"])
        )
        if source is None or source["disposition"] != "snapshot":
            raise MigrationManifestError(
                "manifest memory must reference a snapshot source"
            )

    migrated_ids = manifest["migrated_ids"]
    expected_ids = sorted(
        memory_ids, key=lambda item: item.encode("utf-8")
    )
    if migrated_ids != expected_ids:
        raise MigrationManifestError(
            "manifest migrated_ids do not match memories"
        )
    counts = _mapping(
        manifest["counts"], "manifest counts", _COUNT_FIELDS
    )
    if any(
        not isinstance(counts[name], int)
        or isinstance(counts[name], bool)
        or counts[name] < 0
        for name in _COUNT_FIELDS
    ):
        raise MigrationManifestError(
            "manifest counts must be non-negative integers"
        )
    expected_counts = {
        "sources": len(raw_sources),
        "snapshots": sum(
            source["disposition"] == "snapshot"
            for source in raw_sources
        ),
        "ignored": sum(
            source["disposition"] == "ignored"
            for source in raw_sources
        ),
        "excluded_sensitive": sum(
            source["disposition"] == "excluded_sensitive"
            for source in raw_sources
        ),
        "memories": len(raw_memories),
    }
    if counts != expected_counts:
        raise MigrationManifestError(
            "manifest counts do not match its entries"
        )
    return manifest


def resolve_migration_path(paths: MemoryPaths, relative: Path) -> Path:
    try:
        return paths.resolve_managed(relative)
    except ValueError as error:
        raise MigrationManifestError(
            f"migration path escapes managed root: {relative}"
        ) from error


def load_migration_manifest(
    paths: MemoryPaths,
    path: Path,
    *,
    expected_migration_id: str | None = None,
) -> dict[str, Any] | None:
    try:
        relative = path.relative_to(paths.root)
    except ValueError as error:
        raise MigrationManifestError(
            "manifest path is outside the managed root"
        ) from error
    resolved = resolve_migration_path(paths, relative)
    if not resolved.exists():
        return None
    try:
        value = json.loads(strict_read_text(resolved))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise MigrationManifestError(
            f"invalid migration manifest: {error}"
        ) from error
    return validate_migration_manifest(
        value, expected_migration_id=expected_migration_id
    )


def migration_receipts(
    paths: MemoryPaths, migration_id: str
) -> list[dict[str, Any]]:
    receipt_file = paths.receipts / "source-keys.json"
    if not receipt_file.exists():
        return []
    registry = json.loads(strict_read_text(receipt_file))
    return [
        entry
        for entry in registry.get("sources", [])
        if isinstance(entry, dict)
        and entry.get("revision") == migration_id
        and isinstance(entry.get("ref"), str)
        and entry["ref"].startswith("migration:v1:")
    ]


def validate_completed_manifest_evidence(
    paths: MemoryPaths, manifest: dict[str, Any]
) -> None:
    validate_migration_manifest(
        manifest, expected_migration_id=manifest.get("migration_id")
    )
    if manifest["status"] != "completed":
        raise MigrationManifestError(
            "legacy forget requires a completed migration manifest"
        )
    source_by_path = {
        source["path"]: source for source in manifest["sources"]
    }
    receipts = migration_receipts(paths, manifest["migration_id"])
    store = MemoryStore(paths)
    for memory in manifest["memories"]:
        source = source_by_path[memory["source_path"]]
        expected_ref = (
            f"migration:v1:{memory['source_path']}#{memory['id']}"
        )
        if not any(
            entry.get("ref") == expected_ref
            and entry.get("revision") == manifest["migration_id"]
            and entry.get("content_hash") == source["sha256"]
            and entry.get("object_id") == memory["id"]
            for entry in receipts
        ):
            raise MigrationManifestError(
                f"migration source receipt mismatch: {memory['id']}"
            )
        try:
            item = store.get_memory(memory["id"])
        except (FileNotFoundError, RuntimeError, ValueError) as error:
            raise MigrationManifestError(
                f"persisted migration memory missing: {memory['id']}"
            ) from error
        if item.id != memory["id"]:
            raise MigrationManifestError(
                f"persisted migration memory mismatch: {memory['id']}"
            )
