"""Exact, user-authorized hard forget for isolated Capture objects."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agc_runtime.capture_contracts import CaptureKey, CaptureSuppressionTombstone, receipt_id_for, tombstone_id_for
from agc_runtime.capture_forget_transaction import CaptureForgetTransaction
from agc_runtime.capture_schema import capture_key_from_mapping
from agc_runtime.capture_store import CaptureStore
from agc_runtime.capture_transaction import canonical_json_bytes, read_json
from agc_runtime.contracts import ToolResponse
from agc_runtime.locking import root_write_lock
from agc_runtime import managed_backup
from agc_runtime.paths import MemoryPaths


def _failed(code: str, message: str) -> ToolResponse:
    return ToolResponse(tool="agc.write", action="capture_forget", status="failed", error={"code": code, "message": message})


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _target(request: dict[str, Any]) -> tuple[str, str | CaptureKey]:
    if request.get("authorization") != "explicit_user_request":
        raise PermissionError("explicit_user_request authorization is required")
    value = request.get("target")
    if not isinstance(value, dict) or not isinstance(value.get("type"), str):
        raise ValueError("target must be an exact Capture forget union")
    if value["type"] == "observation" and set(value) == {"type", "observation_id"}:
        observation_id = value["observation_id"]
        if not isinstance(observation_id, str) or not observation_id.startswith("co_") or len(observation_id) != 67:
            raise ValueError("observation_id must be an exact Capture observation id")
        return "observation", observation_id
    if value["type"] == "revision" and set(value) == {"type", "adapter_id", "source_root_id", "task_id", "revision_id"}:
        return "revision", capture_key_from_mapping({name: value[name] for name in ("adapter_id", "source_root_id", "task_id", "revision_id")})
    raise ValueError("target must be an exact Capture forget union")


def _entry_name(path: Path, paths: MemoryPaths) -> str:
    return path.relative_to(paths.root).as_posix()


def _read_primary(paths: MemoryPaths) -> dict[str, bytes]:
    return {path.relative_to(paths.root).as_posix(): path.read_bytes() for path in paths.capture.root.rglob("*") if path.is_file() and managed_backup._capture_name_allowed(path.relative_to(paths.root).as_posix())}


def _updated_observation(entries: dict[str, bytes], observation_id: str) -> tuple[dict[str, bytes], str]:
    name = f".runtime/capture/observations/{observation_id}.json"
    value = json.loads(entries[name].decode("utf-8"))
    receipt_id = value["receipt_id"]
    receipt_name = f".runtime/capture/receipts/{receipt_id}.json"
    manifest_name = f".runtime/capture/indexes/{receipt_id}.json"
    receipt = json.loads(entries[receipt_name].decode("utf-8"))
    manifest = json.loads(entries[manifest_name].decode("utf-8"))
    ids = manifest.get("observation_ids")
    if not isinstance(ids, list) or observation_id not in ids:
        raise ValueError("observation is not bound by its immutable manifest")
    updated_ids = [item for item in ids if item != observation_id]
    receipt.update({
        "source_fingerprint": None, "source_hash_schema_version": None,
        "capsule_hash": None, "capsule_schema_version": None,
        "redacted_by_forget": True,
        "forgotten_observation_count": receipt["forgotten_observation_count"] + 1,
        "observation_count": len(updated_ids),
        "zero_reason": "user_forget" if not updated_ids else None,
    })
    # Strict constructors validate every receipt transition before publication.
    from agc_runtime.capture_contracts import CaptureReceipt
    CaptureReceipt.from_mapping(receipt)
    manifest["observation_ids"] = updated_ids
    entries = dict(entries)
    entries.pop(name)
    entries[receipt_name] = canonical_json_bytes(receipt)
    entries[manifest_name] = canonical_json_bytes(manifest)
    return entries, receipt_id


def _updated_revision(entries: dict[str, bytes], key: CaptureKey) -> dict[str, bytes]:
    receipt_id = receipt_id_for(key)
    result = dict(entries)
    tombstone_name = f".runtime/capture/tombstones/{tombstone_id_for(key)}.json"
    # Exact retry is a no-op once only the durable suppression decision remains.
    if tombstone_name in result and f".runtime/capture/receipts/{receipt_id}.json" not in result:
        return result
    manifest_name = f".runtime/capture/indexes/{receipt_id}.json"
    if manifest_name in result:
        manifest = json.loads(result[manifest_name].decode("utf-8"))
        for observation_id in manifest.get("observation_ids", []):
            result.pop(f".runtime/capture/observations/{observation_id}.json", None)
    for name in list(result):
        if name in {f".runtime/capture/receipts/{receipt_id}.json", f".runtime/capture/ledger/{receipt_id}.json", manifest_name, f".runtime/capture/leases/{receipt_id}.json", f".runtime/capture/leases/{receipt_id}.epoch"}:
            result.pop(name, None)
            continue
        if name.startswith(".runtime/capture/census/"):
            try:
                value = json.loads(result[name].decode("utf-8"))
                if value.get("capture_key") == key.to_mapping():
                    result.pop(name)
            except (UnicodeDecodeError, json.JSONDecodeError):
                pass
    tombstone = CaptureSuppressionTombstone.from_mapping({"schema_version": 1, "tombstone_id": tombstone_id_for(key), "capture_key": key.to_mapping(), "created_at": _now(), "reason": "user_forget"})
    result[tombstone_name] = canonical_json_bytes(tombstone.to_mapping())
    return result


def _rewrite_backup(entries: dict[str, bytes], target_kind: str, target: str | CaptureKey) -> tuple[dict[str, bytes], str | None]:
    if target_kind == "observation":
        name = f".runtime/capture/observations/{target}.json"
        return _updated_observation(entries, target) if name in entries else (entries, None)
    return _updated_revision(entries, target), receipt_id_for(target)


def _apply_files(tx: CaptureForgetTransaction, paths: MemoryPaths, before: dict[str, bytes], after: dict[str, bytes]) -> None:
    for name in sorted(set(before) | set(after), key=lambda item: item.encode("utf-8")):
        if before.get(name) == after.get(name):
            continue
        path = paths.resolve_managed(name)
        if name in after:
            tx.write(path, after[name], boundary="primary")
        else:
            tx.delete(path, boundary="primary")


def capture_forget(paths: MemoryPaths, request: dict[str, Any]) -> ToolResponse:
    try:
        kind, target = _target(request)
    except PermissionError as error:
        return _failed("capture_forget_authorization_required", str(error))
    except ValueError as error:
        return _failed("invalid_request", str(error))
    with root_write_lock(paths):
        try:
            CaptureForgetTransaction.recover(paths)
        except ValueError:
            return _failed("invalid_capture_forget_journal", "Capture hard forget recovery journal is invalid")
        before = _read_primary(paths)
        try:
            after, receipt_id = _rewrite_backup(before, kind, target)
        except (KeyError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
            return _failed("capture_forget_target_not_found", "exact Capture target is unavailable")
        backup_updates: list[tuple[Path, bytes]] = []
        try:
            for backup in sorted(paths.backups.glob("*.zip"), key=lambda item: item.name.encode("utf-8")):
                entries, _manifest = managed_backup.read_verified_archive(backup)
                changed, _ = _rewrite_backup(entries, kind, target)
                if changed != entries:
                    files = sorted(changed.items(), key=lambda item: item[0].encode("utf-8"))
                    backup_updates.append((backup, managed_backup.archive_bytes(files, managed_backup.manifest(files))))
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            return _failed("capture_forget_backup_verification_failed", "managed backup verification failed")
        tx = CaptureForgetTransaction(paths)
        try:
            tx.begin(len(set(before) | set(after)) + len(backup_updates))
            _apply_files(tx, paths, before, after)
            for backup, data in backup_updates:
                tx.write(backup, data, boundary="backup")
            # Validate the rewritten primary before publishing the transaction.
            managed_backup._validate_capture_entries(after, managed_backup.manifest(sorted(after.items())))
            tx.commit()
        except Exception:
            tx.rollback()
            return _failed("capture_forget_failed", "Capture hard forget did not complete")
    data: dict[str, Any] = {"code": "capture_forgotten", "source_task_deleted": False}
    if kind == "revision":
        data["tombstone_id"] = tombstone_id_for(target)
    return ToolResponse(tool="agc.write", action="capture_forget", status="accepted", data=data)
