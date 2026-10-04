"""Explicit Capture integrity audit and reconstructible active-work checkpoint.

The checkpoint is a single atomic document. It is never a source of Capture
truth; loss or invalidation requires a new explicit full audit.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib
import re
import uuid
from typing import TYPE_CHECKING

from agc_runtime.capture_contracts import CAPTURE_SCHEMA_VERSION
from agc_runtime.capture_source_cache import checked_path, source_generation_locked
from agc_runtime.capture_transaction import atomic_write_json, canonical_json_bytes, read_json, safe_unlink
from agc_runtime.locking import capture_write_lock

if TYPE_CHECKING:
    from agc_runtime.capture_store import CaptureStore


_VERSION = "capture-active-v1"
_RECEIPT = re.compile(r"cr_[0-9a-f]{64}\Z")
_AUDIT_HOURS = 24


@dataclass(frozen=True)
class AuditResult:
    status: str
    scope: str
    completed_at: str | None
    valid_until: str | None
    input_generation: str | None
    diagnostics: tuple[str, ...] = ()
    next_action: str | None = None


def _path(store: CaptureStore):
    return checked_path(store.capture.root, store.capture.root / "active-workset.json")


def _seal_path(store: CaptureStore):
    return checked_path(store.capture.root, store.capture.root / "active-workset-seal.json")


def _generation_locked(store: CaptureStore) -> str:
    from agc_runtime.capture_store import root_fingerprint

    config = store.paths.root / "config.yaml"
    config_bytes = config.read_bytes() if config.exists() else b"default"
    value = {
        "root": root_fingerprint(store.paths),
        "schema": CAPTURE_SCHEMA_VERSION,
        "version": _VERSION,
        "config_sha256": hashlib.sha256(config_bytes).hexdigest(),
        "source_generation": source_generation_locked(store.capture.root),
    }
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _digest(value: dict) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def load_workset_locked(store: CaptureStore) -> dict | None:
    """Strict validation; None means bootstrap, never an empty active set."""
    path = _path(store)
    if not path.exists():
        return None
    try:
        value = read_json(path)
        if not isinstance(value, dict) or set(value) != {
            "version", "input_generation", "completed_at", "baseline_id",
            "active", "generation", "baseline_status", "digest",
        }:
            return None
        body = {key: item for key, item in value.items() if key != "digest"}
        if (value["version"] != _VERSION or value["digest"] != _digest(body)
                or value["input_generation"] != _generation_locked(store)
                or not isinstance(value["completed_at"], str)
                or not isinstance(value["baseline_id"], str)
                or re.fullmatch(r"[0-9a-f]{32}", value["baseline_id"]) is None
                or not isinstance(value["generation"], int)
                or value["generation"] < 0
                or value["baseline_status"] not in {"healthy", "recovery_needed"}
                or not isinstance(value["active"], list)
                or value["active"] != sorted(set(value["active"]))
                or any(not isinstance(item, str) or _RECEIPT.fullmatch(item) is None for item in value["active"])):
            return None
        seal = read_json(_seal_path(store))
        if seal != {
            "version": _VERSION,
            "baseline_id": value["baseline_id"],
            "generation": value["generation"],
            "workset_digest": value["digest"],
        }:
            return None
        datetime.fromisoformat(value["completed_at"].replace("Z", "+00:00"))
        return value
    except (OSError, TypeError, ValueError):
        return None


def _write_locked(store: CaptureStore, body: dict) -> None:
    digest = _digest(body)
    atomic_write_json(_path(store), {**body, "digest": digest})
    # Two atomic publications intentionally fail closed if interrupted between
    # them. The independent seal detects an older valid index replay.
    atomic_write_json(_seal_path(store), {
        "version": _VERSION,
        "baseline_id": body["baseline_id"],
        "generation": body["generation"],
        "workset_digest": digest,
    })


def mark_active_locked(store: CaptureStore, receipt_id: str) -> None:
    if _RECEIPT.fullmatch(receipt_id) is None:
        raise ValueError("invalid Capture receipt identifier")
    current = load_workset_locked(store)
    if current is None or receipt_id in current["active"]:
        return
    body = {key: item for key, item in current.items() if key != "digest"}
    body["active"] = sorted((*current["active"], receipt_id))
    body["generation"] += 1
    _write_locked(store, body)
    from agc_runtime.capture_schedule import bind_workset_locked

    updated = load_workset_locked(store)
    if updated is not None:
        bind_workset_locked(store, current, updated)


def retire_active_locked(store: CaptureStore, receipt_id: str) -> None:
    current = load_workset_locked(store)
    if current is None or receipt_id not in current["active"]:
        return
    body = {key: item for key, item in current.items() if key != "digest"}
    body["active"] = [item for item in current["active"] if item != receipt_id]
    body["generation"] += 1
    from agc_runtime.capture_schedule import prepare_retire_locked

    prepare_retire_locked(store, current, body, receipt_id)
    _write_locked(store, body)


def invalidate_locked(store: CaptureStore) -> None:
    from agc_runtime.capture_schedule import invalidate_locked as invalidate_schedule_locked

    invalidate_schedule_locked(store)
    safe_unlink(_seal_path(store))
    safe_unlink(_path(store))


def run_full_audit(store: CaptureStore, *, now: str) -> AuditResult:
    """Read full relationships and cold Census under one native Capture lock."""
    from agc_runtime.capture_ledger import same_revision_metadata

    completed = datetime.fromisoformat(now.replace("Z", "+00:00"))
    with capture_write_lock(store.paths):
        store._ensure_layout_locked()
        # A failed/interrupted new audit must not leave an earlier credential
        # available as if the newly examined state had passed.
        invalidate_locked(store)
        generation = _generation_locked(store)
        snapshot = store._read_snapshot_locked()
        diagnostics = [item.code for item in snapshot.diagnostics]
        active: set[str] = {item.receipt_id for item in snapshot.receipts if item.status == "extracting"}
        for receipt_path in store.capture.receipts.glob("*.json"):
            if _RECEIPT.fullmatch(receipt_path.stem) is None:
                continue
            try:
                receipt = store._read_receipt(receipt_path.stem)
                ledger_path = store._ledger_path(receipt.receipt_id)
                if not ledger_path.exists():
                    active.add(receipt.receipt_id)
                else:
                    from agc_runtime.capture_contracts import LedgerEntry
                    ledger = LedgerEntry.from_mapping(read_json(ledger_path))
                    if ledger.status != receipt.status or ledger.capture_key != receipt.key:
                        active.add(receipt.receipt_id)
            except (OSError, TypeError, ValueError):
                pass
        owned_stage_ids: set[str] = set()
        for journal_path in store.capture.journals.iterdir():
            journal_id = journal_path.stem.removeprefix("tr_")
            if (not journal_path.is_file() or journal_path.suffix != ".json"
                    or _RECEIPT.fullmatch(journal_id) is None):
                diagnostics.append("invalid_transaction_journal")
            else:
                active.add(journal_id)
                if not journal_path.stem.startswith("tr_"):
                    try:
                        ids = store._binding_ids(read_json(journal_path), journal_id)
                        if any(not store._artifact_binds(store.capture.staging, journal_id, item) for item in ids):
                            raise ValueError("invalid staged binding")
                        owned_stage_ids.update(ids)
                    except (OSError, TypeError, ValueError):
                        diagnostics.append("invalid_transaction_journal")
        for stage_path in store.capture.staging.iterdir():
            if (not stage_path.is_file() or stage_path.suffix != ".json"
                    or stage_path.stem not in owned_stage_ids):
                diagnostics.append("orphan_staging")
        try:
            cold_runs, cold_revisions = store._read_cold_census_truth()
            packed = {item.key: item for item in snapshot.census}
            cold = {}
            conflicting_duplicate = False
            for revision in cold_revisions:
                previous = cold.get(revision.key)
                if previous is not None and not same_revision_metadata(previous, revision):
                    conflicting_duplicate = True
                cold.setdefault(revision.key, revision)
            if (conflicting_duplicate or set(cold) != set(packed)
                    or any(not same_revision_metadata(cold[key], packed[key]) for key in cold)
                    or {run.census_id for run in cold_runs} != {run.census_id for run in snapshot.census_runs}):
                diagnostics.append("cold_census_mismatch")
        except (OSError, TypeError, ValueError):
            diagnostics.append("invalid_cold_census")
        recoverable_diagnostics = {"missing_ledger", "ledger_receipt_mismatch", "orphan_manifest", "orphan_observation"}
        if diagnostics and (not active or any(item not in recoverable_diagnostics for item in diagnostics)):
            invalidate_locked(store)
            return AuditResult("integrity_failed", "full_historical_integrity", now, None, generation, tuple(sorted(set(diagnostics))), "repair_integrity_then_audit")
        body = {
            "version": _VERSION,
            "input_generation": generation,
            "completed_at": now,
            "baseline_id": uuid.uuid4().hex,
            "active": sorted(active),
            "generation": 0,
            "baseline_status": "recovery_needed" if active else "healthy",
        }
        _write_locked(store, body)
        if active:
            return AuditResult("recovery_needed", "full_historical_integrity", now, None, generation, tuple(sorted(set(diagnostics))), "recover_active_then_audit")
        from agc_runtime.capture_schedule import bootstrap_locked

        workset = load_workset_locked(store)
        if workset is None:
            return AuditResult("integrity_failed", "full_historical_integrity", now, None, generation, ("invalid_active_workset",), "repair_integrity_then_audit")
        bootstrap_locked(store, snapshot, workset)
        valid_until = (completed + timedelta(hours=_AUDIT_HOURS)).isoformat().replace("+00:00", "Z")
        return AuditResult("healthy", "full_historical_integrity", now, valid_until, generation)
