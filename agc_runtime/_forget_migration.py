import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any

from agc_runtime._forget_types import ForgetOperation, ForgetPlanError
from agc_runtime.migration_manifest import (
    MigrationManifestError,
    load_migration_manifest,
    migration_manifest_integrity,
    resolve_migration_path,
    validate_completed_manifest_evidence,
    validate_migration_manifest,
)
from agc_runtime.paths import MemoryPaths


def _contains_term(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _exact_term_rewrite(text: str, terms: tuple[str, ...]) -> str:
    updated = text
    for term in terms:
        updated = updated.replace(term, "")
    return updated


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


def _load_manifest_for_forget(
    paths: MemoryPaths, path: Path
) -> dict[str, Any]:
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


def matched_manifests(
    paths: MemoryPaths,
    memory_id: str,
    *,
    retry: bool,
    operation_id: str,
) -> list[tuple[Path, dict[str, Any]]]:
    matched = []
    for path in _manifest_paths(paths):
        manifest = _load_manifest_for_forget(paths, path)
        has_memory = any(
            entry.get("id") == memory_id
            for entry in manifest["memories"]
        )
        has_marker = any(
            marker["operation_id"] == operation_id
            and marker["memory_id"] == memory_id
            for marker in manifest["forget_operations"]
        )
        if not has_memory and not (retry and has_marker):
            continue
        if not retry or not has_marker:
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


def source_operations(
    paths: MemoryPaths,
    manifests: list[tuple[Path, dict[str, Any]]],
    memory_id: str,
    terms: tuple[str, ...],
    *,
    retry: bool,
) -> tuple[list[ForgetOperation], tuple[Path, ...]]:
    operations = []
    verification_paths = []
    for manifest_path, manifest in manifests:
        source_root = Path(manifest["source_root"]).resolve()
        forgotten_source_paths = {
            entry["source_path"]
            for entry in manifest["memories"]
            if entry["id"] == memory_id
        }
        if not forgotten_source_paths:
            continue
        retained_source_paths = {
            entry["source_path"]
            for entry in manifest["memories"]
            if entry["id"] != memory_id
        }
        for source in manifest["sources"]:
            if (
                source["disposition"] != "snapshot"
                or source["path"] not in forgotten_source_paths
            ):
                continue
            pure = Path(*PurePosixPath(source["path"]).parts)
            lexical_original = source_root / pure
            original = lexical_original.resolve()
            if original == source_root or source_root not in original.parents:
                raise ForgetPlanError(
                    "migration_path_escape",
                    f"legacy source escaped source_root: {source['path']}",
                )
            if original != Path(source["canonical_path"]):
                raise ForgetPlanError(
                    "legacy_source_replaced",
                    f"registered legacy source was redirected: {lexical_original}",
                )
            snapshot = _resolved_managed(
                paths, manifest_path.parent / "snapshot" / pure
            )
            if not original.is_file():
                raise ForgetPlanError(
                    "legacy_source_missing",
                    f"registered migration file is missing: {original}",
                )
            raw = original.read_bytes()
            current_stat = original.stat()
            identity = source["file_identity"]
            identity_matches = (
                current_stat.st_dev == identity["device"]
                and current_stat.st_ino == identity["inode"]
            )
            current_hash = hashlib.sha256(raw).hexdigest()
            already_rewritten = False
            if current_hash != source["current_sha256"]:
                try:
                    current_text = raw.decode("utf-8", errors="strict")
                except UnicodeDecodeError as error:
                    raise ForgetPlanError(
                        "legacy_source_changed",
                        f"registered legacy source changed: {original}",
                    ) from error
                if not retry or _contains_term(current_text, terms):
                    raise ForgetPlanError(
                        "legacy_source_changed",
                        f"registered legacy source changed: {original}",
                    )
                already_rewritten = True
            elif not identity_matches and not retry:
                raise ForgetPlanError(
                    "legacy_source_replaced",
                    f"registered legacy source identity changed: {original}",
                )
            try:
                text = raw.decode("utf-8", errors="strict")
            except UnicodeDecodeError as error:
                raise ForgetPlanError(
                    "invalid_migration_source",
                    f"migration text is not UTF-8: {original}",
                ) from error
            if not already_rewritten:
                operations.append(
                    ForgetOperation(
                        original,
                        _exact_term_rewrite(text, terms).encode("utf-8"),
                        "legacy",
                    )
                )
            verification_paths.append(original)

            snapshot_is_retained = source["path"] in retained_source_paths
            if not snapshot.is_file():
                if retry and not snapshot_is_retained:
                    continue
                raise ForgetPlanError(
                    "migration_snapshot_missing",
                    f"registered migration file is missing: {snapshot}",
                )
            if snapshot_is_retained:
                try:
                    snapshot_text = snapshot.read_bytes().decode(
                        "utf-8", errors="strict"
                    )
                except UnicodeDecodeError as error:
                    raise ForgetPlanError(
                        "invalid_migration_source",
                        f"migration text is not UTF-8: {snapshot}",
                    ) from error
                operations.append(
                    ForgetOperation(
                        snapshot,
                        _exact_term_rewrite(
                            snapshot_text, terms
                        ).encode("utf-8"),
                        "snapshot",
                    )
                )
                verification_paths.append(snapshot)
            else:
                operations.append(
                    ForgetOperation(snapshot, None, "snapshot")
                )
    return operations, tuple(verification_paths)


def manifest_with_marker(
    manifest: dict[str, Any],
    memory_id: str,
    operation_id: str,
    status: str,
) -> dict[str, Any]:
    updated = json.loads(json.dumps(manifest))
    retained_markers = [
        marker
        for marker in updated["forget_operations"]
        if marker["operation_id"] != operation_id
    ]
    existing = next(
        (
            marker
            for marker in updated["forget_operations"]
            if marker["operation_id"] == operation_id
        ),
        None,
    )
    marker_status = (
        "completed"
        if existing is not None and existing["status"] == "completed"
        else status
    )
    retained_markers.append(
        {
            "operation_id": operation_id,
            "memory_id": memory_id,
            "status": marker_status,
        }
    )
    updated["forget_operations"] = retained_markers
    updated["integrity_sha256"] = migration_manifest_integrity(updated)
    return validate_migration_manifest(
        updated, expected_migration_id=updated["migration_id"]
    )


def _refresh_source_state(
    source_root: Path, source: dict[str, Any]
) -> None:
    pure = Path(*PurePosixPath(source["path"]).parts)
    lexical = source_root / pure
    resolved = lexical.resolve()
    if resolved == source_root or source_root not in resolved.parents:
        raise RuntimeError(
            f"legacy source escaped source_root: {source['path']}"
        )
    raw = resolved.read_bytes()
    stat = resolved.stat()
    source["current_sha256"] = hashlib.sha256(raw).hexdigest()
    source["canonical_path"] = str(resolved)
    source["file_identity"] = {
        "device": stat.st_dev,
        "inode": stat.st_ino,
    }


def manifest_without_memory(
    manifest: dict[str, Any],
    memory_id: str,
    operation_id: str,
) -> dict[str, Any]:
    updated = json.loads(json.dumps(manifest))
    forgotten_source_paths = {
        entry["source_path"]
        for entry in updated["memories"]
        if entry["id"] == memory_id
    }
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
        if not (
            source["disposition"] == "snapshot"
            and source["path"] in forgotten_source_paths
            and source["path"] not in retained_source_paths
        )
    ]
    source_root = Path(updated["source_root"]).resolve()
    for source in updated["sources"]:
        if (
            source["disposition"] == "snapshot"
            and source["path"] in forgotten_source_paths
        ):
            _refresh_source_state(source_root, source)
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
    updated = manifest_with_marker(
        updated, memory_id, operation_id, "completed"
    )
    updated["integrity_sha256"] = migration_manifest_integrity(updated)
    return validate_migration_manifest(
        updated, expected_migration_id=updated["migration_id"]
    )
