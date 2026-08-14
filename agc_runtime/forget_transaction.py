import hashlib
import io
import json
import os
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agc_runtime._forget_migration import (
    manifest_with_marker,
    manifest_without_memory,
    matched_manifests,
    rollback_reconciled_manifest,
    source_operations,
)
from agc_runtime._forget_types import ForgetOperation, ForgetPlanError
from agc_runtime.catalog import build_catalog, render_catalog_markdown
from agc_runtime.capture_transaction import safe_unlink
from agc_runtime.migration_manifest import SHA256_PATTERN
from agc_runtime.paths import MemoryPaths
from agc_runtime import managed_backup
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
    "operation_id",
    "status",
    "integrity_sha256",
}
_CAPTURE_PREFIX = ".runtime/capture/"


@dataclass(frozen=True)
class ForgetPlan:
    marker_operations: tuple[ForgetOperation, ...]
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


def _operation_id(request_digest: str) -> str:
    return hashlib.sha256(
        f"forget:{request_digest}".encode("utf-8")
    ).hexdigest()


def _canonical_mapping_hash(
    value: dict[str, Any], integrity_field: str
) -> str:
    content = {
        key: item for key, item in value.items() if key != integrity_field
    }
    canonical = json.dumps(
        content,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
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
            if normalized_name.startswith(_CAPTURE_PREFIX):
                retained[normalized_name] = data
                continue
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
    files = sorted(retained.items(), key=lambda item: item[0].encode("utf-8"))
    manifest = (
        json.dumps(
            managed_backup.manifest(files),
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        ).encode("utf-8")
        + b"\n"
    )
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, data in files:
            archive.writestr(_zip_info(name), data)
        archive.writestr(_zip_info("manifest.json"), manifest)
    return output.getvalue()


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
        if relative.startswith(_CAPTURE_PREFIX):
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
) -> dict[str, Any]:
    journal = {
        "schema_version": 2,
        "operation": "forget",
        "memory_id": memory_id,
        "request_digest": request_digest,
        "operation_id": _operation_id(request_digest),
        "status": "in_progress",
    }
    journal["integrity_sha256"] = _canonical_mapping_hash(
        journal, "integrity_sha256"
    )
    return journal


def _load_journal(
    paths: MemoryPaths,
    journal_path: Path,
    memory_id: str,
    request_digest: str,
) -> dict[str, Any] | None:
    if not journal_path.exists():
        return None
    try:
        value = json.loads(strict_read_text(journal_path))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ForgetPlanError(
            "invalid_forget_journal", "invalid forget journal encoding"
        ) from error
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
    if (
        not isinstance(value["request_digest"], str)
        or not SHA256_PATTERN.fullmatch(value["request_digest"])
        or not isinstance(value["operation_id"], str)
        or not SHA256_PATTERN.fullmatch(value["operation_id"])
        or not isinstance(value["integrity_sha256"], str)
        or not SHA256_PATTERN.fullmatch(value["integrity_sha256"])
        or value["operation_id"] != _operation_id(request_digest)
        or value["integrity_sha256"]
        != _canonical_mapping_hash(value, "integrity_sha256")
    ):
        raise ForgetPlanError(
            "invalid_forget_journal",
            "forget journal integrity mismatch",
        )
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
    operation_id = (
        journal["operation_id"]
        if journal is not None
        else _operation_id(request_digest)
    )
    manifests = matched_manifests(
        paths,
        memory_id,
        retry=retry,
        operation_id=operation_id,
    )
    (
        migration_operations,
        verification_paths,
        pending_by_manifest,
    ) = source_operations(
        paths,
        manifests,
        memory_id,
        terms,
        retry=retry,
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
    marker_operations = []
    for manifest_path, manifest in manifests:
        marked = manifest_with_marker(
            manifest,
            memory_id,
            operation_id,
            "in_progress",
            pending_by_manifest.get(manifest_path),
        )
        marker_operations.append(
            ForgetOperation(
                manifest_path,
                (
                    json.dumps(
                        marked,
                        ensure_ascii=False,
                        sort_keys=True,
                        indent=2,
                    )
                    + "\n"
                ).encode("utf-8"),
                "migration_marker",
            )
        )

        def final_manifest_bytes(
            *,
            base_manifest: dict[str, Any] = marked,
        ) -> bytes:
            updated = manifest_without_memory(
                base_manifest,
                memory_id,
                operation_id,
            )
            return (
                json.dumps(
                    updated,
                    ensure_ascii=False,
                    sort_keys=True,
                    indent=2,
                )
                + "\n"
            ).encode("utf-8")

        operations[manifest_path] = ForgetOperation(
            manifest_path,
            final_manifest_bytes,
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
        journal = _journal_value(memory_id, request_digest)
    return ForgetPlan(
        marker_operations=tuple(marker_operations),
        operations=ordered,
        tombstone=ForgetOperation(
            tombstone_file, tombstone_bytes, "tombstone"
        ),
        verification_paths=tuple(
            sorted(
                set(verification_paths),
                key=lambda path: str(path).encode("utf-8"),
            )
        ),
        journal_path=journal_path,
        journal=journal,
    )


def _apply_forget_operation(operation: ForgetOperation) -> None:
    if operation.content is None:
        safe_unlink(operation.path)
    else:
        content = (
            operation.content()
            if callable(operation.content)
            else operation.content
        )
        _atomic_write_bytes(operation.path, content)


def _rollback_forget_operations(
    applied: list[tuple[ForgetOperation, bool, bytes | None]]
) -> bool:
    succeeded = True
    for operation, existed, original in reversed(applied):
        try:
            if existed and original is not None:
                _atomic_write_bytes(operation.path, original)
            elif not existed:
                safe_unlink(operation.path)
        except Exception:
            succeeded = False
    return succeeded


def _reconcile_rollback_manifests(plan: ForgetPlan) -> None:
    for marker in plan.marker_operations:
        if not isinstance(marker.content, bytes):
            continue
        try:
            content = rollback_reconciled_manifest(
                marker.path, marker.content
            )
            if content is not None:
                _atomic_write_bytes(marker.path, content)
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
        relative = str(path.relative_to(paths.root)).replace("\\", "/")
        if relative.startswith(".runtime/migrations/"):
            continue
        if relative.startswith(_CAPTURE_PREFIX):
            continue
        if path.suffix.lower() == ".zip":
            with zipfile.ZipFile(path, "r") as archive:
                for info in archive.infolist():
                    if info.is_dir():
                        continue
                    normalized_name = info.filename.replace("\\", "/")
                    if normalized_name.startswith(_CAPTURE_PREFIX):
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
