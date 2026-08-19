"""Exact, user-authorized hard forget for isolated Capture objects."""
from __future__ import annotations

import json
import re
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agc_runtime.capture_contracts import (
    CaptureKey,
    CaptureReceipt,
    CaptureSuppressionTombstone,
    CollectedObservation,
    LedgerEntry,
    RevisionRef,
    receipt_id_for,
    tombstone_id_for,
)
from agc_runtime.capture_forget_transaction import CaptureForgetTransaction
from agc_runtime.capture_schema import capture_key_from_mapping
from agc_runtime.capture_transaction import canonical_json_bytes
from agc_runtime.contracts import ToolResponse
from agc_runtime.locking import capture_write_lock, root_write_lock
from agc_runtime import managed_backup
from agc_runtime.paths import MemoryPaths


_RUNTIME_PREFIXES = (
    ".runtime/capture/dirty/",
    ".runtime/capture/journals/",
    ".runtime/capture/staging/",
    ".runtime/capture/leases/",
    ".runtime/capture/scan-state/",
    ".runtime/capture/budgets/",
)


def _failed(code: str, message: str) -> ToolResponse:
    return ToolResponse(tool="agc.write", action="capture_forget", status="failed", error={"code": code, "message": message})


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _target(request: dict[str, Any]) -> tuple[str, str | CaptureKey]:
    if request.get("authorization") != "explicit_user_request":
        raise PermissionError("explicit_user_request authorization is required")
    if set(request) != {"action", "authorization", "target"} or request.get("action") != "capture_forget":
        raise ValueError("request must be the exact Capture forget request")
    value = request.get("target")
    if not isinstance(value, dict) or not isinstance(value.get("type"), str):
        raise ValueError("target must be an exact Capture forget union")
    if value["type"] == "observation" and set(value) == {"type", "observation_id"}:
        observation_id = value["observation_id"]
        if not isinstance(observation_id, str) or re.fullmatch(r"co_[0-9a-f]{64}", observation_id) is None:
            raise ValueError("observation_id must be an exact Capture observation id")
        return "observation", observation_id
    if value["type"] == "revision" and set(value) == {"type", "adapter_id", "source_root_id", "task_id", "revision_id"}:
        return "revision", capture_key_from_mapping({name: value[name] for name in ("adapter_id", "source_root_id", "task_id", "revision_id")})
    raise ValueError("target must be an exact Capture forget union")


def _entry_name(path: Path, paths: MemoryPaths) -> str:
    return path.relative_to(paths.root).as_posix()


def _read_primary(paths: MemoryPaths) -> dict[str, bytes]:
    """Read the complete managed Capture tree, excluding local capabilities.

    Hard forget must not depend on the backup allowlist: worker/runtime objects
    can retain a revision after its immutable manifest is missing.  The writer
    lock, cursor secret and this transaction's private before-images are never
    part of the deletion set.
    """
    result: dict[str, bytes] = {}
    capture_root = paths.capture.root.resolve()
    for path in paths.capture.root.rglob("*"):
        if path.is_symlink():
            raise ValueError("Capture artifact must not be a symbolic link")
        if not path.is_file():
            continue
        resolved = path.resolve()
        if not resolved.is_relative_to(capture_root):
            raise ValueError("Capture artifact escapes the managed root")
        relative_capture = resolved.relative_to(capture_root).as_posix()
        if relative_capture in {".writer.lock", "cursor-hmac-key", "schema-version"}:
            continue
        if relative_capture.startswith("forget-staging/"):
            continue
        result[_entry_name(resolved, paths)] = resolved.read_bytes()
    return result


def _strict_json(data: bytes) -> dict[str, Any]:
    value = json.loads(data.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Capture artifact must be a mapping")
    return value


def _manifest(value: dict[str, Any], receipt_id: str) -> tuple[str, ...]:
    if set(value) != {"schema_version", "receipt_id", "observation_ids"}:
        raise ValueError("invalid Capture immutable manifest")
    ids = value.get("observation_ids")
    if value.get("schema_version") != 1 or value.get("receipt_id") != receipt_id or not isinstance(ids, list):
        raise ValueError("invalid Capture immutable manifest")
    if len(ids) > 8 or len(ids) != len(set(ids)) or any(
        not isinstance(item, str) or re.fullmatch(r"co_[0-9a-f]{64}", item) is None for item in ids
    ):
        raise ValueError("invalid Capture immutable manifest")
    return tuple(ids)


def _source_key(observation: CollectedObservation) -> CaptureKey:
    return capture_key_from_mapping({
        name: observation.source[name]
        for name in ("adapter_id", "source_root_id", "task_id", "revision_id")
    })


def _runtime_artifact_matches(value: dict[str, Any], key: CaptureKey, receipt_id: str, observation_ids: set[str]) -> bool:
    """Match only explicit, exact identity fields in private runtime objects."""
    if value.get("capture_key") == key.to_mapping() or value.get("receipt_id") == receipt_id:
        return True
    for field in ("observation_id", "staged_observation_id"):
        if value.get(field) in observation_ids:
            return True
    ids = value.get("observation_ids")
    return isinstance(ids, list) and any(item in observation_ids for item in ids)


def _backup_projection(entries: dict[str, bytes]) -> dict[str, bytes]:
    return {
        name: data
        for name, data in entries.items()
        if managed_backup._capture_name_allowed(name)
        and not managed_backup._has_temporary_component(name)
    }


def _mapping_binds_observation(value: Any, observation_id: str) -> bool:
    if isinstance(value, dict):
        for name, item in value.items():
            if name in {"observation_id", "staged_observation_id"} and item == observation_id:
                return True
            if name == "observation_ids" and isinstance(item, list) and observation_id in item:
                return True
            if _mapping_binds_observation(item, observation_id):
                return True
    elif isinstance(value, list):
        return any(_mapping_binds_observation(item, observation_id) for item in value)
    return False


def _scrub_observation_runtime(entries: dict[str, bytes], observation_id: str) -> dict[str, bytes]:
    result = dict(entries)
    needle = observation_id.encode("ascii")
    exact_staging_name = f".runtime/capture/staging/{observation_id}.json"
    for name, data in tuple(result.items()):
        if not name.startswith(_RUNTIME_PREFIXES):
            continue
        if name == exact_staging_name:
            result.pop(name, None)
            continue
        try:
            value = _strict_json(data)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
            if needle in data:
                raise ValueError("unparseable Capture artifact may retain target observation")
            continue
        if _mapping_binds_observation(value, observation_id):
            result.pop(name, None)
        elif Path(name).stem == observation_id or needle in data:
            raise ValueError("Capture artifact retains an unbound target observation")
    return result


def _updated_observation(entries: dict[str, bytes], observation_id: str) -> tuple[dict[str, bytes], str | None]:
    name = f".runtime/capture/observations/{observation_id}.json"
    observation: CollectedObservation | None = None
    if name in entries:
        observation = CollectedObservation.from_mapping(_strict_json(entries[name]))
        if observation.observation_id != observation_id:
            raise ValueError("Capture observation filename binding is invalid")

    manifest_receipts: list[str] = []
    manifests: dict[str, dict[str, Any]] = {}
    for manifest_name, data in entries.items():
        if not manifest_name.startswith(".runtime/capture/indexes/"):
            continue
        object_id = Path(manifest_name).stem
        value = _strict_json(data)
        ids = _manifest(value, object_id)
        manifests[object_id] = value
        if observation_id in ids:
            manifest_receipts.append(object_id)
    if len(manifest_receipts) > 1:
        raise ValueError("observation is bound by multiple immutable manifests")
    if not manifest_receipts:
        if observation is not None:
            raise ValueError("observation is not bound by its immutable manifest")
        return _scrub_observation_runtime(entries, observation_id), None

    receipt_id = manifest_receipts[0]
    if observation is not None and observation.receipt_id != receipt_id:
        raise ValueError("observation receipt binding is invalid")
    receipt_name = f".runtime/capture/receipts/{receipt_id}.json"
    manifest_name = f".runtime/capture/indexes/{receipt_id}.json"
    receipt_object = CaptureReceipt.from_mapping(_strict_json(entries[receipt_name]))
    if receipt_object.receipt_id != receipt_id:
        raise ValueError("Capture receipt filename binding is invalid")
    if observation is not None and _source_key(observation) != receipt_object.key:
        raise ValueError("observation source binding is invalid")
    receipt = receipt_object.to_mapping()
    manifest = manifests[receipt_id]
    ids = list(_manifest(manifest, receipt_id))
    updated_ids = [item for item in ids if item != observation_id]
    receipt.update({
        "source_fingerprint": None, "source_hash_schema_version": None,
        "capsule_hash": None, "capsule_schema_version": None,
        "redacted_by_forget": True,
        "forgotten_observation_count": receipt["forgotten_observation_count"] + 1,
        "observation_count": len(updated_ids),
        "zero_reason": "user_forget" if not updated_ids else None,
    })
    CaptureReceipt.from_mapping(receipt)
    manifest["observation_ids"] = updated_ids
    result = dict(entries)
    result.pop(name, None)
    result[receipt_name] = canonical_json_bytes(receipt)
    result[manifest_name] = canonical_json_bytes(manifest)
    return _scrub_observation_runtime(result, observation_id), receipt_id


def _updated_revision(entries: dict[str, bytes], key: CaptureKey) -> dict[str, bytes]:
    receipt_id = receipt_id_for(key)
    result = dict(entries)
    tombstone_name = f".runtime/capture/tombstones/{tombstone_id_for(key)}.json"
    target_observations: set[str] = set()
    observations: dict[str, CollectedObservation] = {}
    needles: set[bytes] = {
        receipt_id.encode("ascii"),
        key.task_id.encode("utf-8"),
        key.revision_id.encode("utf-8"),
    }

    result = _forget_revision_from_census_runs(result, key)

    # Discover observations from their strict source identity rather than from
    # a possibly missing or damaged private manifest.
    for name, data in entries.items():
        if not name.startswith(".runtime/capture/observations/"):
            continue
        observation = CollectedObservation.from_mapping(_strict_json(data))
        if name != f".runtime/capture/observations/{observation.observation_id}.json":
            raise ValueError("Capture observation filename binding is invalid")
        observations[observation.observation_id] = observation
        if _source_key(observation) == key:
            target_observations.add(observation.observation_id)
            needles.update({
                observation.observation_id.encode("ascii"),
                observation.statement.encode("utf-8"),
                observation.observation_fingerprint.encode("ascii"),
            })

    for name, data in entries.items():
        if name.startswith(".runtime/capture/receipts/"):
            receipt = CaptureReceipt.from_mapping(_strict_json(data))
            if name != f".runtime/capture/receipts/{receipt.receipt_id}.json":
                raise ValueError("Capture receipt filename binding is invalid")
            if receipt.key == key:
                for value in (receipt.source_fingerprint, receipt.capsule_hash):
                    if value:
                        needles.add(value.encode("ascii"))
                result.pop(name, None)
        elif name.startswith(".runtime/capture/ledger/"):
            ledger = LedgerEntry.from_mapping(_strict_json(data))
            if name != f".runtime/capture/ledger/{ledger.receipt_id}.json":
                raise ValueError("Capture ledger filename binding is invalid")
            if ledger.capture_key == key:
                result.pop(name, None)
        elif name.startswith(".runtime/capture/census/"):
            revision = RevisionRef.from_mapping(_strict_json(data))
            if revision.key == key:
                result.pop(name, None)
        elif name.startswith(".runtime/capture/tombstones/"):
            tombstone = CaptureSuppressionTombstone.from_mapping(_strict_json(data))
            if name != f".runtime/capture/tombstones/{tombstone.tombstone_id}.json":
                raise ValueError("Capture tombstone filename binding is invalid")
            if tombstone.capture_key == key and name != tombstone_name:
                raise ValueError("duplicate Capture tombstone binding")
        elif name.startswith(".runtime/capture/indexes/"):
            value = _strict_json(data)
            object_id = Path(name).stem
            ids = _manifest(value, object_id)
            if object_id == receipt_id:
                for observation_id in ids:
                    observation = observations.get(observation_id)
                    if observation is None:
                        continue
                    if _source_key(observation) != key:
                        raise ValueError("Capture manifest references a foreign observation")
                    target_observations.add(observation_id)
                result.pop(name, None)

    for observation_id in target_observations:
        result.pop(f".runtime/capture/observations/{observation_id}.json", None)

    for name, data in tuple(result.items()):
        if name.startswith(_RUNTIME_PREFIXES):
            if Path(name).stem in {receipt_id, *target_observations}:
                result.pop(name, None)
                continue
            try:
                value = _strict_json(data)
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
                if any(needle in data for needle in needles):
                    raise ValueError("unparseable Capture artifact may retain target data")
                continue
            if _runtime_artifact_matches(value, key, receipt_id, target_observations):
                result.pop(name, None)

    # Fail closed if an object that could not be attributed still contains a
    # target identifier or content needle.  No mutation has occurred yet.
    for name, data in result.items():
        if name == tombstone_name:
            continue
        if any(needle and needle in data for needle in needles):
            raise ValueError("Capture artifact retains target data")

    if tombstone_name in result:
        tombstone = CaptureSuppressionTombstone.from_mapping(
            _strict_json(result[tombstone_name])
        )
        if tombstone.capture_key != key:
            raise ValueError("Capture tombstone filename binding is invalid")
    else:
        tombstone = CaptureSuppressionTombstone.from_mapping({"schema_version": 1, "tombstone_id": tombstone_id_for(key), "capture_key": key.to_mapping(), "created_at": _now(), "reason": "user_forget"})
        result[tombstone_name] = canonical_json_bytes(tombstone.to_mapping())
    return result


def _forget_revision_from_census_runs(
    entries: dict[str, bytes], key: CaptureKey
) -> dict[str, bytes]:
    """Remove one revision from every strict immutable Census run copy."""

    prefix = ".runtime/capture/census-runs/"
    grouped: dict[str, dict[str, bytes]] = {}
    for name, data in entries.items():
        if not name.startswith(prefix):
            continue
        relative = name[len(prefix) :]
        parts = relative.split("/")
        if len(parts) < 2 or not parts[0]:
            raise ValueError("invalid frozen Census artifact path")
        grouped.setdefault(parts[0], {})["/".join(parts[1:])] = data
    if not grouped:
        return dict(entries)

    result = dict(entries)
    canonical_groups: dict[str, dict[str, bytes]] = {}
    target_needles = (
        receipt_id_for(key).encode("ascii"),
        key.task_id.encode("utf-8"),
        key.revision_id.encode("utf-8"),
    )
    for directory, objects in grouped.items():
        if directory.startswith(".census-") and directory.endswith(".tmp"):
            contains_target = False
            for relative, data in objects.items():
                if any(needle in relative.encode("utf-8") or needle in data for needle in target_needles):
                    contains_target = True
                    break
                if relative.startswith("members/") and relative.count("/") == 1:
                    try:
                        if RevisionRef.from_mapping(_strict_json(data)).key == key:
                            contains_target = True
                            break
                    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
                        # Hidden staging is non-authoritative. Raw identity
                        # needles above still make target-bearing corruption
                        # removable; unrelated partial state must not block
                        # an authorized forget.
                        pass
            if contains_target:
                group_prefix = f"{prefix}{directory}/"
                for name in tuple(result):
                    if name.startswith(group_prefix):
                        result.pop(name, None)
            continue
        canonical_groups[directory] = objects

    if not canonical_groups:
        return result

    from agc_runtime.capture_ledger import validate_frozen_census_run
    from agc_runtime.capture_source import CensusRun

    for directory, objects in canonical_groups.items():
        if "run.json" not in objects:
            raise ValueError("frozen Census run is missing metadata")
        census = CensusRun.from_mapping(_strict_json(objects["run.json"]))
        revisions: list[RevisionRef] = []
        member_names: dict[CaptureKey, str] = {}
        for relative, data in objects.items():
            if relative == "run.json":
                continue
            if not relative.startswith("members/") or relative.count("/") != 1:
                raise ValueError("invalid frozen Census artifact path")
            revision = RevisionRef.from_mapping(_strict_json(data))
            expected = f"members/{receipt_id_for(revision.key)}.json"
            if relative != expected or revision.key in member_names:
                raise ValueError("invalid frozen Census member binding")
            revisions.append(revision)
            member_names[revision.key] = relative

        validation_id = census.census_id if directory.startswith(".") else directory
        validate_frozen_census_run(census, revisions, run_id=validation_id)
        if key not in member_names:
            continue

        remaining = tuple(
            sorted(
                (revision for revision in revisions if revision.key != key),
                key=lambda item: (
                    item.key.adapter_id,
                    item.key.source_root_id,
                    item.key.task_id,
                    item.key.revision_id,
                ),
            )
        )
        group_prefix = f"{prefix}{directory}/"
        if not remaining:
            for name in tuple(result):
                if name.startswith(group_prefix):
                    result.pop(name, None)
            continue

        target_name = f"{group_prefix}{member_names[key]}"
        result.pop(target_name, None)
        updated = CensusRun.from_mapping(
            replace(census, revision_keys=tuple(item.key for item in remaining)).to_mapping()
        )
        validate_frozen_census_run(updated, remaining, run_id=validation_id)
        result[f"{group_prefix}run.json"] = canonical_json_bytes(updated.to_mapping())
    return result


def _rewrite_backup(entries: dict[str, bytes], target_kind: str, target: str | CaptureKey) -> tuple[dict[str, bytes], str | None]:
    if target_kind == "observation":
        return _updated_observation(entries, target)
    return _updated_revision(entries, target), receipt_id_for(target)


def _apply_files(tx: CaptureForgetTransaction, paths: MemoryPaths, before: dict[str, bytes], after: dict[str, bytes]) -> None:
    empty_candidates: set[Path] = set()
    for name in sorted(set(before) | set(after), key=lambda item: item.encode("utf-8")):
        if before.get(name) == after.get(name):
            continue
        path = paths.resolve_managed(name)
        if name in after:
            tx.write(path, after[name], boundary="primary")
        else:
            tx.delete(path, boundary="primary")
            if name.startswith(".runtime/capture/census-runs/"):
                root = paths.capture.root / "census-runs"
                candidate = path.parent
                while candidate != root:
                    empty_candidates.add(candidate)
                    candidate = candidate.parent
    for directory in sorted(
        empty_candidates, key=lambda item: len(item.parts), reverse=True
    ):
        if directory.exists() and not any(directory.iterdir()):
            tx.remove_empty_census_directory(directory)


def capture_forget(paths: MemoryPaths, request: dict[str, Any]) -> ToolResponse:
    try:
        kind, target = _target(request)
    except PermissionError as error:
        return _failed("capture_forget_authorization_required", str(error))
    except ValueError as error:
        return _failed("invalid_request", str(error))
    try:
        with root_write_lock(paths):
            with capture_write_lock(paths):
                try:
                    CaptureForgetTransaction.recover(paths)
                except ValueError:
                    return _failed("invalid_capture_forget_journal", "Capture hard forget recovery journal is invalid")
                try:
                    before = _read_primary(paths)
                    after, receipt_id = _rewrite_backup(before, kind, target)
                except (KeyError, ValueError, UnicodeDecodeError, json.JSONDecodeError):
                    return _failed("capture_forget_target_not_found", "exact Capture target is unavailable")
                backup_updates: list[tuple[Path, bytes]] = []
                try:
                    for backup in sorted(
                        (item for item in paths.backups.rglob("*.zip")
                         if not item.is_symlink() and item.resolve().is_relative_to(paths.backups.resolve())
                         and ".tmp" not in item.parts),
                        key=lambda item: item.relative_to(paths.backups).as_posix().encode("utf-8"),
                    ):
                        entries, _manifest_value = managed_backup.read_verified_archive(backup)
                        changed, _ = _rewrite_backup(entries, kind, target)
                        if changed != entries:
                            files = sorted(changed.items(), key=lambda item: item[0].encode("utf-8"))
                            backup_updates.append((backup, managed_backup.archive_bytes(files, managed_backup.manifest(files))))
                except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
                    return _failed("capture_forget_backup_verification_failed", "managed backup verification failed")
                tx = CaptureForgetTransaction(paths)
                try:
                    primary_change_count = sum(
                        before.get(name) != after.get(name)
                        for name in set(before) | set(after)
                    )
                    tx.begin(primary_change_count + len(backup_updates))
                    _apply_files(tx, paths, before, after)
                    for backup, data in backup_updates:
                        tx.write(backup, data, boundary="backup")
                    # Runtime-only artifacts are intentionally outside backup
                    # schema. Validate the durable projection before commit.
                    projection = _backup_projection(after)
                    projection[".runtime/capture/schema-version"] = paths.capture.schema_version.read_bytes()
                    managed_backup._validate_capture_entries(
                        projection, managed_backup.manifest(sorted(projection.items()))
                    )
                    tx.commit()
                except Exception:
                    tx.rollback()
                    return _failed("capture_forget_failed", "Capture hard forget did not complete")
    except RuntimeError:
        return _failed("capture_forget_busy", "Capture hard forget is busy")
    data: dict[str, Any] = {"code": "capture_forgotten", "source_task_deleted": False}
    if kind == "revision":
        data["tombstone_id"] = tombstone_id_for(target)
    return ToolResponse(tool="agc.write", action="capture_forget", status="accepted", data=data)
