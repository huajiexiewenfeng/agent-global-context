import hashlib
import io
import json
import os
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from agc_runtime.catalog import build_catalog, render_catalog_markdown
from agc_runtime.migration_manifest import (
    SAFE_ID_PATTERN,
    MigrationManifestError,
    load_migration_manifest,
    migration_manifest_integrity,
    resolve_migration_path,
    validate_completed_manifest_evidence,
    validate_migration_manifest,
)
from agc_runtime.paths import MemoryPaths
from agc_runtime.utf8_io import strict_read_text


_TEXT_SUFFIXES = {
    ".md",
    ".json",
    ".jsonl",
    ".txt",
    ".yaml",
    ".yml",
    ".toml",
}
_JOURNAL_FIELDS = {
    "schema_version",
    "operation",
    "memory_id",
    "request_digest",
    "status",
    "migration_ids",
}


class ForgetPlanError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ForgetOperation:
    path: Path
    content: bytes | None
    category: str


@dataclass(frozen=True)
class ForgetPlan:
    operations: tuple[ForgetOperation, ...]
    tombstone: ForgetOperation
    verification_paths: tuple[Path, ...]
    journal_path: Path
    journal: dict[str, Any]


def _tombstone_path(paths: MemoryPaths, memory_id: str) -> Path:
    digest = hashlib.sha256(memory_id.encode("utf-8")).hexdigest()
    return paths.tombstones / f"{digest}.json"


def _journal_path(paths: MemoryPaths, memory_id: str) -> Path:
    digest = hashlib.sha256(memory_id.encode("utf-8")).hexdigest()
    return paths.tombstones / "in-progress" / f"{digest}.json"


def _contains_term(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _request_digest(request: dict[str, Any]) -> str:
    canonical = json.dumps(
        request, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _exact_term_rewrite(text: str, terms: tuple[str, ...]) -> str:
    updated = text
    for term in terms:
        updated = updated.replace(term, "")
    return updated


def _atomic_write_bytes(path: Path, data: bytes) -> None:
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


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o600 << 16
    return info


def _rewritten_backup_bytes(
    path: Path,
    memory_id: str,
    verification_terms: tuple[str, ...],
    tombstone_name: str,
    tombstone_bytes: bytes,
) -> bytes:
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
                if memory_id in text or _contains_term(
                    text, verification_terms
                ):
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
    manifest = (
        json.dumps(
            {"schema_version": 2, "files": files},
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        ).encode("utf-8")
        + b"\n"
    )
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, data in sorted(retained.items()):
            archive.writestr(_zip_info(name), data)
        archive.writestr(_zip_info("manifest.json"), manifest)
    return output.getvalue()


def _resolved_managed(paths: MemoryPaths, path: Path) -> Path:
    try:
        relative = path.relative_to(paths.root)
        resolved = resolve_migration_path(paths, relative)
    except ValueError as error:
        raise ForgetPlanError(
            "migration_path_escape",
            f"managed migration path escaped root: {path}",
        ) from error
    if resolved != path.resolve():
        raise ForgetPlanError(
            "migration_path_escape",
            f"managed migration path was redirected: {path}",
        )
    return resolved


def _manifest_paths(paths: MemoryPaths) -> list[Path]:
    migrations = _resolved_managed(paths, paths.migrations)
    if not migrations.exists():
        return []
    return sorted(migrations.glob("*/manifest.json"))


def _load_manifest_for_forget(paths: MemoryPaths, path: Path) -> dict[str, Any]:
    resolved = _resolved_managed(paths, path)
    migration_id = resolved.parent.name
    try:
        manifest = load_migration_manifest(
            paths,
            resolved,
            expected_migration_id=migration_id,
        )
    except MigrationManifestError as error:
        code = (
            "migration_path_escape"
            if "path escapes managed root" in str(error)
            else "invalid_migration_manifest"
        )
        raise ForgetPlanError(code, str(error)) from error
    if manifest is None:
        raise ForgetPlanError(
            "invalid_migration_manifest",
            f"migration manifest disappeared: {resolved}",
        )
    return manifest


def _matched_manifests(
    paths: MemoryPaths,
    memory_id: str,
    journal: dict[str, Any] | None,
) -> list[tuple[Path, dict[str, Any]]]:
    if journal is None:
        candidates = _manifest_paths(paths)
    else:
        candidates = [
            paths.migrations / migration_id / "manifest.json"
            for migration_id in journal["migration_ids"]
        ]
    matched = []
    for path in candidates:
        manifest = _load_manifest_for_forget(paths, path)
        has_memory = any(
            entry.get("id") == memory_id
            for entry in manifest["memories"]
        )
        if journal is None and not has_memory:
            continue
        if journal is None:
            try:
                validate_completed_manifest_evidence(paths, manifest)
            except MigrationManifestError as error:
                message = str(error)
                code = (
                    "migration_evidence_mismatch"
                    if "receipt mismatch" in message
                    or "persisted migration memory" in message
                    else "invalid_migration_manifest"
                )
                raise ForgetPlanError(code, message) from error
        matched.append((path.resolve(), manifest))
    return matched


def _validated_source_targets(
    paths: MemoryPaths,
    manifests: list[tuple[Path, dict[str, Any]]],
    terms: tuple[str, ...],
    *,
    retry: bool,
) -> tuple[
    list[ForgetOperation],
    tuple[Path, ...],
    tuple[Path, ...],
]:
    operations = []
    legacy_paths = []
    snapshot_paths = []
    for manifest_path, manifest in manifests:
        source_root = Path(manifest["source_root"]).resolve()
        for source in manifest["sources"]:
            if source["disposition"] != "snapshot":
                continue
            pure = Path(*PurePosixPath(source["path"]).parts)
            original = (source_root / pure).resolve()
            if original == source_root or source_root not in original.parents:
                raise ForgetPlanError(
                    "migration_path_escape",
                    f"legacy source escaped source_root: {source['path']}",
                )
            snapshot = _resolved_managed(
                paths, manifest_path.parent / "snapshot" / pure
            )
            for target, category in (
                (original, "legacy"),
                (snapshot, "snapshot"),
            ):
                if not target.is_file():
                    raise ForgetPlanError(
                        "legacy_source_missing"
                        if category == "legacy"
                        else "migration_snapshot_missing",
                        f"registered migration file is missing: {target}",
                    )
                raw = target.read_bytes()
                already_rewritten = False
                if category == "legacy":
                    current_hash = hashlib.sha256(raw).hexdigest()
                    if current_hash != source["sha256"]:
                        try:
                            current_text = raw.decode("utf-8", errors="strict")
                        except UnicodeDecodeError as error:
                            raise ForgetPlanError(
                                "legacy_source_changed",
                                f"registered legacy source changed: {target}",
                            ) from error
                        if not retry or _contains_term(current_text, terms):
                            raise ForgetPlanError(
                                "legacy_source_changed",
                                f"registered legacy source changed: {target}",
                            )
                        already_rewritten = True
                try:
                    text = raw.decode("utf-8", errors="strict")
                except UnicodeDecodeError as error:
                    raise ForgetPlanError(
                        "invalid_migration_source",
                        f"migration text is not UTF-8: {target}",
                    ) from error
                updated = _exact_term_rewrite(text, terms).encode("utf-8")
                if not already_rewritten:
                    operations.append(
                        ForgetOperation(target, updated, category)
                    )
            legacy_paths.append(original)
            snapshot_paths.append(snapshot)
    return operations, tuple(legacy_paths), tuple(snapshot_paths)


def _manifest_without_memory(
    manifest: dict[str, Any], memory_id: str
) -> dict[str, Any]:
    updated = json.loads(json.dumps(manifest))
    updated["memories"] = [
        entry
        for entry in updated["memories"]
        if entry["id"] != memory_id
    ]
    retained_source_paths = {
        entry["source_path"] for entry in updated["memories"]
    }
    updated["sources"] = [
        source
        for source in updated["sources"]
        if source["path"] in retained_source_paths
    ]
    updated["migrated_ids"] = [
        value for value in updated["migrated_ids"] if value != memory_id
    ]
    updated["counts"]["sources"] = len(updated["sources"])
    updated["counts"]["snapshots"] = sum(
        source["disposition"] == "snapshot"
        for source in updated["sources"]
    )
    updated["counts"]["ignored"] = sum(
        source["disposition"] == "ignored"
        for source in updated["sources"]
    )
    updated["counts"]["excluded_sensitive"] = sum(
        source["disposition"] == "excluded_sensitive"
        for source in updated["sources"]
    )
    updated["counts"]["memories"] = len(updated["memories"])
    updated["integrity_sha256"] = migration_manifest_integrity(updated)
    return validate_migration_manifest(
        updated, expected_migration_id=updated["migration_id"]
    )


def _events_operation(
    paths: MemoryPaths, memory_id: str
) -> ForgetOperation | None:
    event_file = paths.events / "events.jsonl"
    if not event_file.exists():
        return None
    retained = []
    for line in strict_read_text(event_file).splitlines():
        if not line:
            continue
        event = json.loads(line)
        if event.get("object_id") != memory_id:
            retained.append(event)
    content = "".join(
        json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n"
        for event in retained
    ).encode("utf-8")
    return ForgetOperation(event_file, content, "managed_purge")


def _receipts_operation(
    paths: MemoryPaths, memory_id: str
) -> ForgetOperation | None:
    receipt_file = paths.receipts / "source-keys.json"
    if not receipt_file.exists():
        return None
    registry = json.loads(strict_read_text(receipt_file))
    registry["sources"] = [
        entry
        for entry in registry.get("sources", [])
        if entry.get("object_id") != memory_id
    ]
    content = (
        json.dumps(registry, ensure_ascii=False, sort_keys=True, indent=2)
        + "\n"
    ).encode("utf-8")
    return ForgetOperation(receipt_file, content, "managed_purge")


def _catalog_operations(
    paths: MemoryPaths, memory_id: str
) -> tuple[ForgetOperation, ForgetOperation]:
    catalog = build_catalog(paths)
    catalog["cards"] = [
        card for card in catalog["cards"] if card["id"] != memory_id
    ]
    catalog["memory_count"] = len(catalog["cards"])
    json_bytes = (
        json.dumps(catalog, ensure_ascii=False, sort_keys=True, indent=2)
        + "\n"
    ).encode("utf-8")
    markdown_bytes = render_catalog_markdown(catalog).encode("utf-8")
    return (
        ForgetOperation(paths.catalog_json, json_bytes, "managed_purge"),
        ForgetOperation(paths.catalog_md, markdown_bytes, "managed_purge"),
    )


def _generic_managed_operations(
    paths: MemoryPaths,
    memory_id: str,
    terms: tuple[str, ...],
    excluded: set[Path],
    tombstone_name: str,
    tombstone_bytes: bytes,
) -> list[ForgetOperation]:
    operations = []
    if not paths.root.exists():
        return operations
    migrations_prefix = ".runtime/migrations/"
    for path in sorted(paths.root.rglob("*")):
        if not path.is_file() or path in excluded:
            continue
        relative = str(path.relative_to(paths.root)).replace("\\", "/")
        if relative.startswith(migrations_prefix):
            continue
        if path.suffix.lower() == ".zip":
            operations.append(
                ForgetOperation(
                    path,
                    _rewritten_backup_bytes(
                        path,
                        memory_id,
                        terms,
                        tombstone_name,
                        tombstone_bytes,
                    ),
                    "managed_purge",
                )
            )
            continue
        matches = path.name == f"{memory_id}.md" or memory_id in relative
        if path.suffix.lower() in _TEXT_SUFFIXES:
            text = strict_read_text(path)
            matches = (
                matches
                or memory_id in text
                or _contains_term(text, terms)
            )
        if matches:
            operations.append(
                ForgetOperation(path, None, "managed_purge")
            )
    return operations


def _journal_value(
    memory_id: str,
    request_digest: str,
    manifest_paths: tuple[Path, ...],
) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "operation": "forget",
        "memory_id": memory_id,
        "request_digest": request_digest,
        "status": "in_progress",
        "migration_ids": sorted(
            path.parent.name for path in manifest_paths
        ),
    }


def _migration_id_list(value: Any) -> list[str]:
    if (
        not isinstance(value, list)
        or any(
            not isinstance(item, str)
            or not SAFE_ID_PATTERN.fullmatch(item)
            for item in value
        )
        or len(value) != len(set(value))
    ):
        raise ForgetPlanError(
            "invalid_forget_journal",
            "migration_ids must be a unique list of safe IDs",
        )
    return value


def _load_journal(
    paths: MemoryPaths,
    journal_path: Path,
    memory_id: str,
    request_digest: str,
) -> dict[str, Any] | None:
    if not journal_path.exists():
        return None
    value = json.loads(strict_read_text(journal_path))
    if not isinstance(value, dict) or set(value) != _JOURNAL_FIELDS:
        raise ForgetPlanError(
            "invalid_forget_journal", "invalid forget journal schema"
        )
    if (
        value["schema_version"] != 2
        or value["operation"] != "forget"
        or value["status"] != "in_progress"
        or value["memory_id"] != memory_id
    ):
        raise ForgetPlanError(
            "invalid_forget_journal", "invalid forget journal identity"
        )
    if value["request_digest"] != request_digest:
        raise ForgetPlanError(
            "forget_request_conflict",
            "in-progress forget belongs to a different request",
        )
    _migration_id_list(value["migration_ids"])
    return value


def _prepare_forget_plan(
    paths: MemoryPaths,
    memory_id: str,
    terms: tuple[str, ...],
    request_digest: str,
    tombstone: dict[str, Any],
    journal_path: Path,
    journal: dict[str, Any] | None,
) -> ForgetPlan:
    retry = journal is not None
    manifests = _matched_manifests(paths, memory_id, journal)
    migration_operations, legacy_paths, snapshot_paths = (
        _validated_source_targets(
            paths, manifests, terms, retry=retry
        )
    )
    tombstone_text = (
        json.dumps(tombstone, ensure_ascii=False, sort_keys=True, indent=2)
        + "\n"
    )
    tombstone_bytes = tombstone_text.encode("utf-8")
    tombstone_file = _tombstone_path(paths, memory_id)
    tombstone_name = str(tombstone_file.relative_to(paths.root)).replace(
        "\\", "/"
    )
    operations: dict[Path, ForgetOperation] = {
        operation.path: operation for operation in migration_operations
    }
    manifest_paths = []
    for manifest_path, manifest in manifests:
        manifest_paths.append(manifest_path)
        updated = _manifest_without_memory(manifest, memory_id)
        operations[manifest_path] = ForgetOperation(
            manifest_path,
            (
                json.dumps(
                    updated,
                    ensure_ascii=False,
                    sort_keys=True,
                    indent=2,
                )
                + "\n"
            ).encode("utf-8"),
            "migration_manifest",
        )

    specialized = [
        _events_operation(paths, memory_id),
        _receipts_operation(paths, memory_id),
        *_catalog_operations(paths, memory_id),
    ]
    for operation in specialized:
        if operation is not None:
            operations[operation.path] = operation
    excluded = {
        paths.locks / "write.lock",
        journal_path,
        paths.catalog_json,
        paths.catalog_md,
        paths.events / "events.jsonl",
        paths.receipts / "source-keys.json",
        tombstone_file,
        *operations,
    }
    for operation in _generic_managed_operations(
        paths,
        memory_id,
        terms,
        excluded,
        tombstone_name,
        tombstone_bytes,
    ):
        operations[operation.path] = operation

    category_order = {
        "legacy": 0,
        "snapshot": 1,
        "migration_manifest": 2,
        "managed_purge": 3,
    }
    ordered = tuple(
        sorted(
            operations.values(),
            key=lambda operation: (
                category_order[operation.category],
                str(operation.path).encode("utf-8"),
            ),
        )
    )
    if journal is None:
        journal = _journal_value(
            memory_id,
            request_digest,
            tuple(manifest_paths),
        )
    return ForgetPlan(
        operations=ordered,
        tombstone=ForgetOperation(
            tombstone_file, tombstone_bytes, "tombstone"
        ),
        verification_paths=tuple(
            sorted(
                {*legacy_paths, *snapshot_paths},
                key=lambda path: str(path).encode("utf-8"),
            )
        ),
        journal_path=journal_path,
        journal=journal,
    )


def _apply_forget_operation(operation: ForgetOperation) -> None:
    if operation.content is None:
        operation.path.unlink(missing_ok=True)
    else:
        _atomic_write_bytes(operation.path, operation.content)


def _rollback_forget_operations(
    applied: list[tuple[ForgetOperation, bool, bytes | None]]
) -> None:
    for operation, existed, original in reversed(applied):
        try:
            if existed and original is not None:
                _atomic_write_bytes(operation.path, original)
            elif not existed:
                operation.path.unlink(missing_ok=True)
        except Exception:
            continue


def _verify_forget_plan(
    paths: MemoryPaths,
    plan: ForgetPlan,
    memory_id: str,
    terms: tuple[str, ...],
) -> None:
    for path in plan.verification_paths:
        if not path.is_file():
            raise RuntimeError(
                f"forget removed a shared registered source: {path}"
            )
        if _contains_term(strict_read_text(path), terms):
            raise RuntimeError(
                f"forget verification failed for registered source: {path}"
            )
    if list(paths.memories.glob(f"*/{memory_id}.md")):
        raise RuntimeError("forget verification found the Memory file")
    for path in paths.root.rglob("*"):
        if (
            not path.is_file()
            or path == plan.journal_path
            or path == paths.locks / "write.lock"
        ):
            continue
        if path.suffix.lower() == ".zip":
            with zipfile.ZipFile(path, "r") as archive:
                for info in archive.infolist():
                    if info.is_dir():
                        continue
                    data = archive.read(info.filename)
                    try:
                        text = data.decode("utf-8", errors="strict")
                    except UnicodeDecodeError:
                        continue
                    if _contains_term(text, terms):
                        raise RuntimeError(
                            f"forget verification failed in backup: {path}"
                        )
            continue
        if path.suffix.lower() in _TEXT_SUFFIXES and _contains_term(
            strict_read_text(path), terms
        ):
            raise RuntimeError(
                f"forget verification failed for managed path: {path}"
            )
