import hashlib
import json
import os
import re
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from agc_runtime.catalog import (
    build_catalog,
    rebuild_catalog,
    render_catalog_markdown,
)
from agc_runtime.capture_contracts import (
    CaptureLease,
    CaptureReceipt,
    CaptureSuppressionTombstone,
    CollectedObservation,
    LedgerEntry,
    RevisionRef,
    SourceQuarantine,
)
from agc_runtime.capture_review import CaptureReviewReceipt
from agc_runtime.capture_status_service import capture_status
from agc_runtime.capture_store import CaptureStore
from agc_runtime.capture_transaction import safe_unlink
from agc_runtime.contracts import ToolResponse
from agc_runtime.locking import capture_write_lock, root_write_lock
from agc_runtime import managed_backup
from agc_runtime.migration_service import migrate_v1
from agc_runtime.models import MemoryItem
from agc_runtime.paths import MemoryPaths
from agc_runtime.policy import validate_transition
from agc_runtime.runtime_config import default_config_text, load_runtime_config
from agc_runtime.schema import validate_memory_item
from agc_runtime.store import MemoryStore
from agc_runtime.utf8_io import atomic_write_text, strict_read_text


CONFIG_TEXT = default_config_text()
_TEXT_SUFFIXES = {
    "",
    ".md",
    ".json",
    ".jsonl",
    ".txt",
    ".yaml",
    ".yml",
    ".toml",
}
_SAFE_CAPTURE_FILENAME = re.compile(r"^(?:cr|co|ct)_[0-9a-f]{64}\.json$")


def _failed(action: str, code: str, message: str, **data: Any) -> ToolResponse:
    return ToolResponse(
        tool="agc.admin",
        action=action,
        status="failed",
        data=data,
        error={"code": code, "message": message},
    )


def _managed_directories(paths: MemoryPaths) -> tuple[Path, ...]:
    return (
        paths.memories,
        paths.contexts,
        paths.candidates / "ordinary",
        paths.candidates / "conflicted",
        paths.events,
        paths.archive,
        paths.queue,
        paths.receipts,
        paths.locks,
        paths.cache,
        paths.backups,
        paths.tombstones,
        paths.migrations,
    )


def _handle_init(paths: MemoryPaths, _request: dict[str, Any]) -> ToolResponse:
    with root_write_lock(paths):
        for directory in (*_managed_directories(paths), *paths.capture.directories()):
            directory.mkdir(parents=True, exist_ok=True)
        CaptureStore(paths).ensure_layout()
        atomic_write_text(paths.root / "schema-version", "2\n")
        atomic_write_text(paths.root / "config.yaml", CONFIG_TEXT)
        atomic_write_text(paths.capture.schema_version, "1\n")
        catalog = rebuild_catalog(paths, acquire_lock=False)
    return ToolResponse(
        tool="agc.admin",
        action="init",
        status="accepted",
        data={"code": "initialized", "memory_count": catalog["memory_count"]},
    )


def _issue(issues: list[dict[str, str]], path: Path, message: str) -> None:
    issues.append({"path": str(path), "message": message})


def _strict_decode_managed(paths: MemoryPaths, issues: list[dict[str, str]]) -> None:
    if not paths.root.exists():
        return
    for path in sorted(paths.root.rglob("*")):
        if not path.is_file():
            continue
        relative = str(path.relative_to(paths.root)).replace("\\", "/")
        if relative.startswith(".runtime/locks/") or relative.startswith(
            ".runtime/backups/"
        ) or relative.startswith(".runtime/capture/") or relative.endswith(".tmp"):
            continue
        is_migration_text = relative.startswith(".runtime/migrations/")
        if not is_migration_text and path.suffix.lower() not in _TEXT_SUFFIXES:
            _issue(issues, path, "unsupported binary managed file")
            continue
        try:
            strict_read_text(path)
        except UnicodeDecodeError as error:
            _issue(issues, path, f"invalid UTF-8: {error}")


def _validate_memories(
    paths: MemoryPaths, issues: list[dict[str, str]]
) -> None:
    seen: dict[str, Path] = {}
    if not paths.memories.exists():
        return
    for path in sorted(paths.memories.rglob("*.md")):
        try:
            item = MemoryItem.from_markdown(strict_read_text(path))
            validate_memory_item(item)
            if item.id in seen:
                _issue(
                    issues,
                    path,
                    f"duplicate memory id also present at {seen[item.id]}",
                )
            else:
                seen[item.id] = path
            if path.stem != item.id:
                _issue(issues, path, "memory filename does not match id")
            if path.parent.name != item.kind:
                _issue(issues, path, "memory directory does not match kind")
        except (ValueError, OSError, UnicodeDecodeError) as error:
            _issue(issues, path, str(error))


def _validate_receipts(
    paths: MemoryPaths, issues: list[dict[str, str]]
) -> None:
    receipt_file = paths.receipts / "source-keys.json"
    if not receipt_file.exists():
        return
    try:
        registry = json.loads(strict_read_text(receipt_file))
        sources = registry["sources"]
        seen: set[tuple[str, str, str]] = set()
        for entry in sources:
            key = (
                entry["ref"],
                entry["revision"],
                entry["content_hash"],
            )
            if key in seen:
                _issue(issues, receipt_file, "duplicate exact source key")
            seen.add(key)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        _issue(issues, receipt_file, f"invalid source receipt registry: {error}")


def _validate_capture(
    paths: MemoryPaths,
    issues: list[dict[str, str]],
    *,
    reject_runtime_payloads: bool = True,
) -> None:
    if not paths.capture.root.exists():
        return
    try:
        if strict_read_text(paths.capture.schema_version) != "1\n":
            _capture_issue(issues, paths, paths.capture.schema_version, "Capture schema-version must be 1")
    except UnicodeDecodeError:
        _capture_issue(
            issues,
            paths,
            paths.capture.schema_version,
            "Capture schema-version is not valid UTF-8",
        )
    except OSError:
        _capture_issue(issues, paths, paths.capture.schema_version, "Capture schema-version is missing")
    parsers = {
        paths.capture.receipts: CaptureReceipt.from_mapping,
        paths.capture.observations: CollectedObservation.from_mapping,
        paths.capture.reviews: CaptureReviewReceipt.from_mapping,
        paths.capture.ledger: LedgerEntry.from_mapping,
        paths.capture.census: RevisionRef.from_mapping,
        paths.capture.quarantines: SourceQuarantine.from_mapping,
        paths.capture.tombstones: CaptureSuppressionTombstone.from_mapping,
    }
    review_receipts: dict[str, tuple[CaptureReviewReceipt, Path]] = {}
    for directory, parser in parsers.items():
        if not directory.exists():
            continue
        for path in sorted(directory.rglob("*")):
            if not path.is_file():
                continue
            if path.suffix.lower() != ".json":
                _capture_issue(issues, paths, path, "unsupported Capture object file")
                continue
            try:
                parsed = parser(json.loads(strict_read_text(path)))
                if directory == paths.capture.reviews:
                    review = parsed
                    if path.name != f"{review.observation_id}.json":
                        _capture_issue(
                            issues,
                            paths,
                            path,
                            "Capture review receipt filename binding is invalid",
                        )
                    elif review.observation_id in review_receipts:
                        _capture_issue(
                            issues,
                            paths,
                            path,
                            "duplicate Capture review receipt",
                        )
                    else:
                        review_receipts[review.observation_id] = (review, path)
            except OSError:
                _capture_issue(
                    issues, paths, path, "Capture object could not be read"
                )
            except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
                _capture_issue(issues, paths, path, f"invalid Capture object: {error}")
    if review_receipts:
        try:
            visible_ids = {
                item.observation_id
                for item in CaptureStore(paths).iter_visible_observations()
            }
        except (OSError, TypeError, ValueError):
            visible_ids = set()
        memory_store = MemoryStore(paths)
        for observation_id, (review, path) in review_receipts.items():
            if observation_id not in visible_ids:
                _capture_issue(
                    issues,
                    paths,
                    path,
                    "orphan Capture review receipt",
                )
            if review.outcome == "draft" and review.target_memory_id is not None:
                try:
                    memory_store.get_memory(review.target_memory_id)
                except (OSError, RuntimeError, TypeError, ValueError):
                    _capture_issue(
                        issues,
                        paths,
                        path,
                        "Capture review target memory is unavailable",
                    )
    if paths.capture.conflicts.exists():
        for path in sorted(paths.capture.conflicts.glob("*.json")):
            try:
                value = json.loads(strict_read_text(path))
                if set(value) != {"schema_version", "code", "created_at"} or value.get("schema_version") != 1 or value.get("code") != "source_conflict" or not isinstance(value.get("created_at"), str):
                    raise ValueError("invalid conflict")
            except (ValueError, OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
                _capture_issue(issues, paths, path, "unsupported Capture payload")
    if paths.capture.indexes.exists():
        for path in sorted(paths.capture.indexes.rglob("*")):
            if not path.is_file():
                continue
            try:
                value = json.loads(strict_read_text(path))
                object_id = path.stem
                if (
                    path.suffix.lower() != ".json"
                    or not re.fullmatch(r"cr_[0-9a-f]{64}", object_id)
                    or set(value) != {"schema_version", "receipt_id", "observation_ids"}
                    or value.get("schema_version") != 1
                    or value.get("receipt_id") != object_id
                    or not isinstance(value.get("observation_ids"), list)
                ):
                    raise ValueError("invalid Capture immutable manifest")
            except (ValueError, OSError, UnicodeDecodeError, json.JSONDecodeError):
                _capture_issue(issues, paths, path, "unsupported Capture payload")
    if reject_runtime_payloads:
        for directory in (
            paths.capture.dirty,
            paths.capture.journals,
            paths.capture.staging,
            paths.capture.scan_state,
            paths.capture.budgets,
        ):
            if not directory.exists():
                continue
            for path in sorted(directory.rglob("*")):
                if path.is_file():
                    _capture_issue(issues, paths, path, "unsupported Capture payload")


def _capture_issue(
    issues: list[dict[str, str]], paths: MemoryPaths, path: Path, message: str
) -> None:
    relative = path.relative_to(paths.capture.root)
    if relative.as_posix() == "schema-version":
        safe_relative = "schema-version"
    else:
        directory = relative.parts[0] if len(relative.parts) > 1 else "objects"
        filename = relative.name
        safe_name = (
            filename
            if _SAFE_CAPTURE_FILENAME.fullmatch(filename)
            else "<invalid-name>"
        )
        safe_relative = f"{directory}/{safe_name}"
    issues.append(
        {"path": f".runtime/capture/{safe_relative}", "message": message}
    )


def _validate_events(paths: MemoryPaths, issues: list[dict[str, str]]) -> None:
    event_file = paths.events / "events.jsonl"
    if not event_file.exists():
        return
    try:
        event_lines = strict_read_text(event_file).splitlines()
    except (OSError, UnicodeDecodeError) as error:
        _issue(issues, event_file, f"invalid event log encoding: {error}")
        return
    for line_number, line in enumerate(
        event_lines, start=1
    ):
        if not line:
            continue
        try:
            event = json.loads(line)
            old = event.get("old_lifecycle")
            new = event.get("new_lifecycle")
            if old is not None and new is not None:
                validate_transition(old, new)
        except (ValueError, TypeError, json.JSONDecodeError) as error:
            _issue(issues, event_file, f"line {line_number}: {error}")


def _validate_catalog(
    paths: MemoryPaths, issues: list[dict[str, str]]
) -> None:
    try:
        expected = build_catalog(paths)
    except (ValueError, OSError, UnicodeDecodeError):
        return
    if not paths.catalog_json.exists():
        _issue(issues, paths.catalog_json, "generated catalog is missing")
        return
    try:
        actual = json.loads(strict_read_text(paths.catalog_json))
    except (ValueError, OSError, UnicodeDecodeError) as error:
        _issue(issues, paths.catalog_json, f"invalid generated catalog: {error}")
        return
    if actual != expected:
        _issue(issues, paths.catalog_json, "generated catalog is stale")
    if not paths.catalog_md.exists():
        _issue(issues, paths.catalog_md, "generated Markdown catalog is missing")
    else:
        try:
            actual_markdown = strict_read_text(paths.catalog_md)
        except (OSError, UnicodeDecodeError) as error:
            _issue(
                issues,
                paths.catalog_md,
                f"invalid generated Markdown catalog: {error}",
            )
        else:
            if actual_markdown != render_catalog_markdown(expected):
                _issue(
                    issues,
                    paths.catalog_md,
                    "generated Markdown catalog is stale",
                )


def _validate_fixed_config(
    paths: MemoryPaths, issues: list[dict[str, str]]
) -> None:
    schema_file = paths.root / "schema-version"
    config_file = paths.root / "config.yaml"
    try:
        if strict_read_text(schema_file) != "2\n":
            _issue(issues, schema_file, "schema-version must be 2")
    except OSError as error:
        _issue(issues, schema_file, f"schema-version is missing: {error}")
    try:
        if not config_file.exists():
            raise OSError("config.yaml does not exist")
        load_runtime_config(paths)
    except (OSError, ValueError) as error:
        _issue(issues, config_file, f"config.yaml is missing: {error}")


def _validate_root(
    paths: MemoryPaths, *, reject_capture_runtime: bool = True
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    _strict_decode_managed(paths, issues)
    _validate_fixed_config(paths, issues)
    _validate_memories(paths, issues)
    _validate_receipts(paths, issues)
    _validate_capture(paths, issues, reject_runtime_payloads=reject_capture_runtime)
    _validate_events(paths, issues)
    _validate_catalog(paths, issues)
    return issues


def _handle_validate(
    paths: MemoryPaths, _request: dict[str, Any]
) -> ToolResponse:
    issues = _validate_root(paths)
    return ToolResponse(
        tool="agc.admin",
        action="validate",
        status="failed" if issues else "accepted",
        data={
            "code": "validation_failed" if issues else "valid",
            "invalid_count": len(issues),
            "issues": issues,
        },
        error=(
            {
                "code": "validation_failed",
                "message": f"{len(issues)} validation issue(s) found",
            }
            if issues
            else None
        ),
    )


def _handle_backup(paths: MemoryPaths, _request: dict[str, Any]) -> ToolResponse:
    with root_write_lock(paths):
      with capture_write_lock(paths):
        issues = _validate_root(paths, reject_capture_runtime=False)
        if issues:
            return _failed(
                "backup",
                "validation_failed",
                "refusing to back up an invalid memory root",
                invalid_count=len(issues),
                issues=issues,
            )
        try:
            files = managed_backup.backup_files(paths)
            manifest = managed_backup.manifest(files)
        except ValueError:
            return _failed(
                "backup",
                "validation_failed",
                "refusing to create a backup outside safe archive limits",
                invalid_count=1,
            )
        # Capture's immutable graph must be coherent in the locked snapshot;
        # otherwise a backup would preserve a silently unusable receipt set.
        try:
            managed_backup._validate_capture_entries(dict(files), manifest)
        except ValueError:
            return _failed(
                "backup",
                "validation_failed",
                "refusing to back up an invalid Capture graph",
                invalid_count=1,
            )
        try:
            archive_data = managed_backup.archive_bytes(files, manifest)
        except ValueError:
            return _failed(
                "backup",
                "validation_failed",
                "refusing to create a backup outside safe archive limits",
                invalid_count=1,
            )
        manifest_id = hashlib.sha256(
            json.dumps(
                manifest, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
        ).hexdigest()
        archive_path = paths.backups / f"agc-backup-{manifest_id}.zip"
        managed_backup.atomic_write_bytes(archive_path, archive_data)
    return ToolResponse(
        tool="agc.admin",
        action="backup",
        status="accepted",
        data={
            "code": "backup_created",
            "backup_path": str(archive_path),
            "archive_sha256": hashlib.sha256(archive_data).hexdigest(),
            "manifest": manifest,
        },
    )


def _read_tombstones_from_files(
    files: dict[str, bytes],
) -> dict[str, dict[str, Any]]:
    tombstones = {}
    for name, data in files.items():
        if not name.startswith(".runtime/tombstones/") or not name.endswith(
            ".json"
        ):
            continue
        value = json.loads(data.decode("utf-8"))
        memory_id = value.get("memory_id")
        if isinstance(memory_id, str):
            tombstones[memory_id] = value
    return tombstones


def _read_current_tombstones(paths: MemoryPaths) -> dict[str, dict[str, Any]]:
    values = {}
    if not paths.tombstones.exists():
        return values
    for path in paths.tombstones.glob("*.json"):
        value = json.loads(strict_read_text(path))
        memory_id = value.get("memory_id")
        if isinstance(memory_id, str):
            values[memory_id] = value
    return values


def _preserve_during_restore(paths: MemoryPaths, path: Path) -> bool:
    try:
        relative = str(path.relative_to(paths.root)).replace("\\", "/")
    except ValueError:
        return True
    return (
        relative.startswith(".runtime/locks/")
        or relative.startswith(".runtime/backups/")
        or relative.startswith(".runtime/tombstones/")
        or relative == ".runtime/capture/cursor-hmac-key"
    )


def _current_replaceable_files(paths: MemoryPaths) -> dict[str, bytes]:
    if not paths.root.exists():
        return {}
    return {
        str(path.relative_to(paths.root)).replace("\\", "/"): path.read_bytes()
        for path in paths.root.rglob("*")
        if path.is_file() and not _preserve_during_restore(paths, path)
    }


def _clear_replaceable_files(paths: MemoryPaths) -> None:
    if not paths.root.exists():
        return
    for path in sorted(paths.root.rglob("*"), reverse=True):
        if path.is_file() and not _preserve_during_restore(paths, path):
            safe_unlink(path)
    run_root = paths.capture.root / "census-runs"
    if run_root.exists():
        for path in sorted(run_root.rglob("*"), reverse=True):
            if path.is_dir():
                try:
                    path.rmdir()
                except OSError:
                    pass


def _restore_file_snapshot(
    paths: MemoryPaths, snapshot: dict[str, bytes]
) -> None:
    _clear_replaceable_files(paths)
    for name, data in sorted(snapshot.items()):
        target = paths.resolve_managed(Path(*PurePosixPath(name).parts))
        managed_backup.atomic_write_bytes(target, data)


def _suppress_restored_ids(paths: MemoryPaths, memory_ids: set[str]) -> None:
    for memory_id in memory_ids:
        for path in paths.memories.glob(f"*/{memory_id}.md"):
            safe_unlink(path)
        for path in paths.archive.rglob(f"{memory_id}.md"):
            safe_unlink(path)
        for path in paths.candidates.rglob("*.json"):
            try:
                value = json.loads(strict_read_text(path))
            except (ValueError, UnicodeDecodeError):
                continue
            if value.get("candidate_id") == memory_id:
                safe_unlink(path)

    event_file = paths.events / "events.jsonl"
    if event_file.exists():
        retained = []
        for line in strict_read_text(event_file).splitlines():
            if not line:
                continue
            event = json.loads(line)
            if event.get("object_id") not in memory_ids:
                retained.append(event)
        atomic_write_text(
            event_file,
            "".join(
                json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n"
                for event in retained
            ),
        )
    receipt_file = paths.receipts / "source-keys.json"
    if receipt_file.exists():
        registry = json.loads(strict_read_text(receipt_file))
        registry["sources"] = [
            entry
            for entry in registry.get("sources", [])
            if entry.get("object_id") not in memory_ids
        ]
        atomic_write_text(
            receipt_file,
            json.dumps(registry, ensure_ascii=False, sort_keys=True, indent=2)
            + "\n",
        )


def _restore_path(paths: MemoryPaths, request: dict[str, Any]) -> Path:
    raw = request.get("backup_path")
    if raw is not None:
        if not isinstance(raw, str) or not raw:
            raise ValueError("backup_path must be a non-empty string")
        return Path(raw).resolve()
    backups = sorted(paths.backups.glob("*.zip"))
    if not backups:
        raise FileNotFoundError("no AGC backup is available")
    return backups[-1].resolve()


def _prevalidated_restore_entries(
    entries: dict[str, bytes], suppressed: set[str]
) -> list[tuple[str, PurePosixPath, str]]:
    prepared: list[tuple[str, PurePosixPath, str]] = []
    for name, data in sorted(entries.items()):
        if (
            name.startswith(".runtime/locks/")
            or name.startswith(".runtime/backups/")
            or name == ".runtime/capture/cursor-hmac-key"
        ):
            continue
        pure = PurePosixPath(name)
        if (
            len(pure.parts) >= 3
            and pure.parts[0] == "memories"
            and pure.stem in suppressed
        ):
            continue
        try:
            text = data.decode("utf-8", errors="strict")
        except UnicodeDecodeError as error:
            raise ValueError(f"non-UTF-8 managed backup entry: {name}") from error
        prepared.append((name, pure, text))
    return prepared


def _handle_restore(paths: MemoryPaths, request: dict[str, Any]) -> ToolResponse:
    backup_path = _restore_path(paths, request)
    with root_write_lock(paths):
        with capture_write_lock(paths):
            try:
                entries, _manifest_value = managed_backup.read_verified_archive(
                    backup_path
                )
                archive_tombstones = _read_tombstones_from_files(entries)
            except (
                OSError,
                ValueError,
                KeyError,
                TypeError,
                UnicodeDecodeError,
                json.JSONDecodeError,
                zipfile.BadZipFile,
            ) as error:
                return _failed(
                    "restore",
                    "backup_verification_failed",
                    str(error),
                )
            current_tombstones = _read_current_tombstones(paths)
            tombstones = {**archive_tombstones, **current_tombstones}
            suppressed = set(tombstones)
            try:
                prepared = _prevalidated_restore_entries(entries, suppressed)
            except ValueError as error:
                return _failed(
                    "restore",
                    "backup_verification_failed",
                    str(error),
                )
            snapshot = _current_replaceable_files(paths)
            try:
                _clear_replaceable_files(paths)
                for _name, pure, text in prepared:
                    target = paths.resolve_managed(Path(*pure.parts))
                    atomic_write_text(target, text)
                for value in tombstones.values():
                    memory_id = value["memory_id"]
                    digest = hashlib.sha256(memory_id.encode("utf-8")).hexdigest()
                    atomic_write_text(
                        paths.tombstones / f"{digest}.json",
                        json.dumps(
                            value, ensure_ascii=False, sort_keys=True, indent=2
                        )
                        + "\n",
                    )
                _suppress_restored_ids(paths, suppressed)
                catalog = rebuild_catalog(paths, acquire_lock=False)
            except BaseException:
                _restore_file_snapshot(paths, snapshot)
                raise

    return ToolResponse(
        tool="agc.admin",
        action="restore",
        status="accepted",
        data={
            "code": "backup_restored",
            "backup_path": str(backup_path),
            "memory_count": catalog["memory_count"],
            "suppressed_memory_ids": sorted(
                suppressed, key=lambda value: value.encode("utf-8")
            ),
        },
    )


def _handle_rebuild_catalog(
    paths: MemoryPaths, _request: dict[str, Any]
) -> ToolResponse:
    catalog = rebuild_catalog(paths)
    return ToolResponse(
        tool="agc.admin",
        action="rebuild_catalog",
        status="accepted",
        data={"code": "catalog_rebuilt", "memory_count": catalog["memory_count"]},
    )


def _handle_migrate(
    paths: MemoryPaths, request: dict[str, Any]
) -> ToolResponse:
    return migrate_v1(paths, request)


def _handle_capture_status(
    paths: MemoryPaths, _request: dict[str, Any]
) -> ToolResponse:
    return ToolResponse(
        tool="agc.admin", action="capture_status", status="accepted",
        data=capture_status(paths),
    )


_HANDLERS = {
    "init": _handle_init,
    "validate": _handle_validate,
    "rebuild_catalog": _handle_rebuild_catalog,
    "backup": _handle_backup,
    "restore": _handle_restore,
    "migrate": _handle_migrate,
    "capture_status": _handle_capture_status,
}


def dispatch_admin(paths: MemoryPaths, request: Any) -> ToolResponse:
    if not isinstance(request, dict):
        return _failed("admin", "invalid_request", "request must be a mapping")
    action = request.get("action")
    if not isinstance(action, str) or action not in _HANDLERS:
        return _failed(
            action if isinstance(action, str) else "",
            "invalid_action",
            "unsupported agc.admin action",
        )
    try:
        if action == "capture_status":
            return _handle_capture_status(paths, request)
        return _HANDLERS[action](paths, request)
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        if action == "capture_status":
            return _failed(action, "invalid_runtime_config", "runtime configuration is invalid")
        return _failed(action, "invalid_request", "request is invalid")
    except OSError:
        if action == "capture_status":
            return _failed(action, "invalid_runtime_config", "runtime configuration is invalid")
        return _failed(action, "admin_failed", "admin operation failed")
    except RuntimeError:
        return _failed(action, "admin_busy", "admin operation is temporarily unavailable")
