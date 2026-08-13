"""Isolated, fenced, journaled persistence for disabled Capture."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
import hashlib
import re
from pathlib import Path
from typing import Callable, Sequence

from agc_runtime.capture_contracts import (
    CAPTURE_SCHEMA_VERSION, CaptureKey, CaptureLease, CaptureReceipt,
    CollectedObservation, LedgerEntry, SanitizedError, receipt_id_for,
    validate_capture_transition,
)
from agc_runtime.capture_transaction import atomic_write_bytes, atomic_write_json, read_json, safe_unlink
from agc_runtime.locking import capture_write_lock
from agc_runtime.paths import MemoryPaths


_CAPTURE_ID = re.compile(r"^(?:cr|co|ct)_[0-9a-f]{64}$")
_RECEIPT_ID = re.compile(r"^cr_[0-9a-f]{64}$")
_OBSERVATION_ID = re.compile(r"^co_[0-9a-f]{64}$")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


@dataclass(frozen=True)
class DiscoveryBatch:
    receipt: CaptureReceipt


@dataclass(frozen=True)
class ReconcileResult:
    status: str
    created: bool
    receipt_id: str


@dataclass(frozen=True)
class CommitResult:
    receipt_id: str
    created_observation_count: int


@dataclass(frozen=True)
class RecoveryReport:
    recovered_count: int = 0
    orphan_count: int = 0
    partial_count: int = 0
    duplicate_count: int = 0
    corrupt_count: int = 0


@dataclass(frozen=True)
class ReceiptTransitionPatch:
    """Only status-local, non-semantic Receipt fields may be patched."""
    updated_at: str | None = None
    next_retry_at: str | None = None
    sanitized_error: SanitizedError | None = None
    reopen_reason: str | None = None
    source_fingerprint: str | None = None  # Explicitly rejected as immutable.


class CaptureStore:
    def __init__(self, paths: MemoryPaths, *, crash_at: str | None = None, clock: Callable[[], str] | None = None) -> None:
        self.paths = paths
        self.capture = paths.capture
        self._crash_at = crash_at
        self._clock = clock or _utc_now

    def _ensure_layout_locked(self) -> None:
        self.capture.root.mkdir(parents=True, exist_ok=True)
        for directory in self.capture.directories():
            directory.mkdir(parents=True, exist_ok=True)
        marker = self.capture.schema_version
        if not marker.exists():
            atomic_write_bytes(marker, b"1\n")

    def ensure_layout(self) -> None:
        with capture_write_lock(self.paths):
            self._ensure_layout_locked()

    def _point(self, point: str) -> None:
        if self._crash_at == point:
            raise RuntimeError(f"injected crash at {point}")

    def _path(self, directory: Path, identifier: str, pattern: re.Pattern[str]) -> Path:
        if not pattern.fullmatch(identifier):
            raise ValueError("invalid Capture object identifier")
        path = directory / f"{identifier}.json"
        if path.parent.resolve() != directory.resolve():
            raise ValueError("Capture object path escapes its directory")
        return path

    def _receipt_path(self, receipt_id: str) -> Path:
        return self._path(self.capture.receipts, receipt_id, _RECEIPT_ID)

    def _ledger_path(self, receipt_id: str) -> Path:
        return self._path(self.capture.ledger, receipt_id, _RECEIPT_ID)

    def _lease_path(self, receipt_id: str) -> Path:
        return self._path(self.capture.leases, receipt_id, _RECEIPT_ID)

    def _epoch_path(self, receipt_id: str) -> Path:
        if not _RECEIPT_ID.fullmatch(receipt_id):
            raise ValueError("invalid Capture object identifier")
        path = self.capture.leases / f"{receipt_id}.epoch.json"
        if path.parent.resolve() != self.capture.leases.resolve():
            raise ValueError("Capture object path escapes its directory")
        return path

    def _journal_path(self, receipt_id: str) -> Path:
        return self._path(self.capture.journals, receipt_id, _RECEIPT_ID)

    def _manifest_path(self, receipt_id: str) -> Path:
        return self._path(self.capture.indexes, receipt_id, _RECEIPT_ID)

    def _observation_path(self, observation_id: str) -> Path:
        return self._path(self.capture.observations, observation_id, _OBSERVATION_ID)

    def _stage_path(self, observation_id: str) -> Path:
        return self._path(self.capture.staging, observation_id, _OBSERVATION_ID)

    def _conflict_path(self, key: CaptureKey) -> Path:
        digest = hashlib.sha256(f"{key.adapter_id}\0{key.source_root_id}".encode("utf-8")).hexdigest()
        return self.capture.conflicts / f"source-{digest}.json"

    def _read_receipt(self, receipt_id: str) -> CaptureReceipt:
        return CaptureReceipt.from_mapping(read_json(self._receipt_path(receipt_id)))

    def read_receipt(self, receipt_id: str) -> CaptureReceipt:
        return self._read_receipt(receipt_id)

    def _write_receipt(self, receipt: CaptureReceipt) -> None:
        atomic_write_json(self._receipt_path(receipt.receipt_id), receipt.to_mapping())

    def _write_ledger(self, receipt: CaptureReceipt, *, status: str, processed_at: str | None) -> None:
        entry = LedgerEntry(CAPTURE_SCHEMA_VERSION, receipt.key, receipt.receipt_id, receipt.discovered_at, processed_at, status)
        atomic_write_json(self._ledger_path(receipt.receipt_id), entry.to_mapping())

    def _epoch(self, receipt_id: str, key: CaptureKey) -> int:
        value = read_json(self._epoch_path(receipt_id))
        if set(value) != {"schema_version", "receipt_id", "fencing_token"} or value.get("schema_version") != CAPTURE_SCHEMA_VERSION or value.get("receipt_id") != receipt_id or type(value.get("fencing_token")) is not int or value["fencing_token"] < 1:
            raise ValueError("invalid lease epoch")
        if receipt_id != receipt_id_for(key):
            raise ValueError("lease epoch key binding is invalid")
        return value["fencing_token"]

    def reconcile_discovery(self, batch: DiscoveryBatch) -> ReconcileResult:
        return self.register_extraction(batch.receipt)

    def register_extraction(self, receipt: CaptureReceipt) -> ReconcileResult:
        receipt.to_mapping()
        if receipt.status not in {"discovered", "queued", "extracting"}:
            raise ValueError("discovery receipt must be non-terminal")
        with capture_write_lock(self.paths):
            self._ensure_layout_locked()
            target = self._receipt_path(receipt.receipt_id)
            if not target.exists():
                self._write_receipt(receipt)
                self._write_ledger(receipt, status=receipt.status, processed_at=None)
                return ReconcileResult(receipt.status, True, receipt.receipt_id)
            current = self._read_receipt(receipt.receipt_id)
            if current.source_hash_schema_version != receipt.source_hash_schema_version:
                return ReconcileResult(current.status, False, current.receipt_id)
            if current.source_fingerprint == receipt.source_fingerprint:
                if current.status == "complete" and not self._manifest_valid(current):
                    raise ValueError("complete receipt has no valid immutable manifest")
                return ReconcileResult(current.status, False, current.receipt_id)
            self._write_source_conflict(current.key, receipt.updated_at)
            if current.status == "complete":
                return ReconcileResult("complete", False, current.receipt_id)
            quarantined = replace(current, status="quarantined", updated_at=receipt.updated_at, sanitized_error=SanitizedError("source", "source_conflict", False), next_retry_at=None)
            self._write_receipt(quarantined)
            self._write_ledger(quarantined, status="quarantined", processed_at=None)
            return ReconcileResult("quarantined", False, current.receipt_id)

    def _write_source_conflict(self, key: CaptureKey, created_at: str) -> None:
        atomic_write_json(self._conflict_path(key), {"schema_version": CAPTURE_SCHEMA_VERSION, "code": "source_conflict", "created_at": created_at})

    def source_health(self, adapter_id: str, source_root_id: str) -> str:
        digest = hashlib.sha256(f"{adapter_id}\0{source_root_id}".encode("utf-8")).hexdigest()
        return "degraded" if (self.capture.conflicts / f"source-{digest}.json").exists() else "healthy"

    def acquire_lease(self, key: CaptureKey, *, owner_id: str, now: str, ttl_seconds: int) -> CaptureLease | None:
        key.to_mapping()
        if ttl_seconds < 1:
            raise ValueError("lease ttl_seconds must be positive")
        receipt_id = receipt_id_for(key)
        expires_at = (_parse_utc(now) + timedelta(seconds=ttl_seconds)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        with capture_write_lock(self.paths):
            self._ensure_layout_locked()
            lease_path = self._lease_path(receipt_id)
            previous: CaptureLease | None = None
            if lease_path.exists():
                previous = CaptureLease.from_mapping(read_json(lease_path))
                if previous.capture_key != key:
                    raise ValueError("lease key binding is invalid")
                if _parse_utc(previous.expires_at) > _parse_utc(now):
                    return None
            epoch_path = self._epoch_path(receipt_id)
            high_water = self._epoch(receipt_id, key) if epoch_path.exists() else 0
            token = max(high_water, previous.fencing_token if previous else 0) + 1
            atomic_write_json(epoch_path, {"schema_version": CAPTURE_SCHEMA_VERSION, "receipt_id": receipt_id, "fencing_token": token})
            lease = CaptureLease(CAPTURE_SCHEMA_VERSION, key, owner_id, token, now, expires_at)
            atomic_write_json(lease_path, lease.to_mapping())
            return lease

    def _assert_lease(self, lease: CaptureLease) -> None:
        try:
            lease.to_mapping()
            receipt_id = receipt_id_for(lease.capture_key)
            current = CaptureLease.from_mapping(read_json(self._lease_path(receipt_id)))
            high_water = self._epoch(receipt_id, lease.capture_key)
        except ValueError as error:
            raise ValueError("lease or fencing epoch is invalid") from error
        if current != lease or high_water != lease.fencing_token:
            raise ValueError("lease is stale, forged, or below fencing epoch")
        if _parse_utc(lease.expires_at) <= _parse_utc(self._clock()):
            raise ValueError("lease has expired")

    def _unique_observations(self, observations: Sequence[CollectedObservation], receipt_id: str) -> tuple[CollectedObservation, ...]:
        if len(observations) > 8:
            raise ValueError("Capture extraction may contain at most 8 observations")
        unique: dict[str, CollectedObservation] = {}
        for observation in observations:
            observation.to_mapping()
            if observation.receipt_id != receipt_id:
                raise ValueError("observation receipt binding is invalid")
            unique.setdefault(observation.observation_fingerprint, observation)
        return tuple(unique.values())

    def _manifest_value(self, receipt_id: str, ids: Sequence[str]) -> dict[str, object]:
        if not _RECEIPT_ID.fullmatch(receipt_id) or any(not _OBSERVATION_ID.fullmatch(item) for item in ids) or len(set(ids)) != len(ids):
            raise ValueError("invalid Capture immutable manifest")
        return {"schema_version": CAPTURE_SCHEMA_VERSION, "receipt_id": receipt_id, "observation_ids": list(ids)}

    def _read_manifest(self, receipt_id: str) -> tuple[str, ...]:
        value = read_json(self._manifest_path(receipt_id))
        if set(value) != {"schema_version", "receipt_id", "observation_ids"} or value.get("schema_version") != CAPTURE_SCHEMA_VERSION or value.get("receipt_id") != receipt_id or not isinstance(value.get("observation_ids"), list):
            raise ValueError("invalid Capture immutable manifest")
        ids = value["observation_ids"]
        if any(not isinstance(item, str) or not _OBSERVATION_ID.fullmatch(item) for item in ids) or len(set(ids)) != len(ids) or len(ids) > 8:
            raise ValueError("invalid Capture immutable manifest")
        return tuple(ids)

    def _manifest_valid(self, receipt: CaptureReceipt) -> bool:
        try:
            ids = self._read_manifest(receipt.receipt_id)
            if receipt.status != "complete" or receipt.observation_count != len(ids):
                return False
            for observation_id in ids:
                observation = CollectedObservation.from_mapping(read_json(self._observation_path(observation_id)))
                if observation.receipt_id != receipt.receipt_id or observation.observation_id != observation_id:
                    return False
            return True
        except ValueError:
            return False

    def commit_extraction(self, lease: CaptureLease, observations: Sequence[CollectedObservation], terminal_receipt: CaptureReceipt) -> CommitResult:
        with capture_write_lock(self.paths):
            self._ensure_layout_locked()
            self._assert_lease(lease)
            current = self._read_receipt(receipt_id_for(lease.capture_key))
            terminal_receipt.to_mapping()
            if current.key != lease.capture_key or terminal_receipt.key != lease.capture_key or terminal_receipt.receipt_id != current.receipt_id or terminal_receipt.status != "complete":
                raise ValueError("terminal receipt must be complete for the leased key")
            immutable = ("adapter_version", "source_schema_version", "identity_quality", "source_fingerprint", "source_hash_schema_version", "capsule_hash", "capsule_schema_version", "settled_at", "discovered_at", "attempt_count", "extractor_id", "extractor_version", "extractor_schema_version", "taxonomy_version", "usage_quality", "redacted_by_forget", "forgotten_observation_count")
            if any(getattr(current, field) != getattr(terminal_receipt, field) for field in immutable):
                raise ValueError("terminal receipt changes bound receipt metadata")
            unique = self._unique_observations(observations, current.receipt_id)
            if terminal_receipt.observation_count != len(unique):
                raise ValueError("terminal receipt observation count does not match batch")
            if terminal_receipt.duplicate_suppression_count != len(observations) - len(unique):
                raise ValueError("terminal receipt duplicate suppression count does not match batch")
            if (not unique) != (terminal_receipt.zero_reason is not None):
                raise ValueError("terminal receipt zero reason does not match batch")
            if any(getattr(terminal_receipt.token_usage, field) < getattr(current.token_usage, field) for field in ("input_tokens", "output_tokens", "total_tokens")):
                raise ValueError("token totals must be monotonic")
            if current.status == "complete":
                if self._read_manifest(current.receipt_id) != tuple(item.observation_id for item in unique):
                    raise ValueError("exact replay does not match immutable manifest")
                return CommitResult(current.receipt_id, 0)
            ids = tuple(item.observation_id for item in unique)
            journal = self._manifest_value(current.receipt_id, ids)
            self._point("before:journal")
            atomic_write_json(self._journal_path(current.receipt_id), journal)
            self._point("after:journal")
            self._point("before:stage")
            for observation in unique:
                atomic_write_json(self._stage_path(observation.observation_id), observation.to_mapping())
            self._point("after:stage")
            atomic_write_json(self._manifest_path(current.receipt_id), journal)
            for index, observation in enumerate(unique):
                self._point(f"before:observation:{index}")
                atomic_write_json(self._observation_path(observation.observation_id), observation.to_mapping())
                self._point(f"after:observation:{index}")
            self._point("before:ledger")
            self._write_ledger(terminal_receipt, status="complete", processed_at=terminal_receipt.updated_at)
            self._point("after:ledger")
            self._point("before:receipt")
            self._write_receipt(terminal_receipt)
            self._point("after:receipt")
            self._point("before:cleanup")
            self._cleanup_ids(current.receipt_id, ids, remove_manifest=False)
            self._point("after:cleanup")
            return CommitResult(current.receipt_id, len(unique))

    def transition(self, lease: CaptureLease, *, expected: frozenset[str], target: str, patch: ReceiptTransitionPatch) -> CaptureReceipt:
        if not isinstance(patch, ReceiptTransitionPatch):
            raise ValueError("transition patch must be strict")
        if patch.source_fingerprint is not None:
            raise ValueError("transition patch cannot change immutable metadata")
        with capture_write_lock(self.paths):
            self._ensure_layout_locked()
            self._assert_lease(lease)
            current = self._read_receipt(receipt_id_for(lease.capture_key))
            if current.status not in expected:
                raise ValueError("receipt status does not match expected set")
            validate_capture_transition(current.status, target, reopen_reason=patch.reopen_reason)
            updated = replace(current, status=target, updated_at=patch.updated_at or self._clock(), next_retry_at=patch.next_retry_at, sanitized_error=patch.sanitized_error)
            if target == "queued":
                # Task 2's strict pre-extraction contract requires a reopened
                # receipt to shed prior extraction metadata before retry.
                updated = replace(
                    updated, source_fingerprint=None,
                    source_hash_schema_version=None, capsule_hash=None,
                    capsule_schema_version=None, extractor_id=None,
                    extractor_version=None, extractor_schema_version=None,
                    taxonomy_version=None,
                )
            updated = CaptureReceipt.from_mapping(updated.to_mapping())
            self._write_receipt(updated)
            self._write_ledger(updated, status=target, processed_at=None)
            return updated

    def visible_observations(self, receipt_id: str) -> tuple[CollectedObservation, ...]:
        receipt = self._read_receipt(receipt_id)
        if not self._manifest_valid(receipt):
            return ()
        ids = self._read_manifest(receipt_id)
        items = tuple(CollectedObservation.from_mapping(read_json(self._observation_path(item))) for item in ids)
        return tuple(sorted(items, key=lambda item: (item.ordinal, item.observation_id)))

    def _cleanup_ids(self, receipt_id: str, ids: Sequence[str], *, remove_manifest: bool) -> None:
        for observation_id in ids:
            safe_unlink(self._stage_path(observation_id))
            if remove_manifest:
                safe_unlink(self._observation_path(observation_id))
        safe_unlink(self._journal_path(receipt_id))
        if remove_manifest:
            safe_unlink(self._manifest_path(receipt_id))

    def _retryable(self, receipt: CaptureReceipt, now: str) -> CaptureReceipt:
        return CaptureReceipt.from_mapping({**receipt.to_mapping(), "status": "retryable", "updated_at": now, "next_retry_at": now, "observation_count": None, "filtered_counts": None, "duplicate_suppression_count": None, "zero_reason": None, "sanitized_error": {"stage": "transaction", "code": "interrupted", "retryable": True}})

    def _quarantine(self, path: Path) -> None:
        digest = hashlib.sha256(path.name.encode("utf-8")).hexdigest()
        atomic_write_json(self.capture.quarantines / f"corrupt-{digest}.json", {"schema_version": CAPTURE_SCHEMA_VERSION, "code": "corrupt_capture_artifact"})
        safe_unlink(path)

    def recover_transactions(self, *, now: str) -> RecoveryReport:
        if not self.capture.root.exists():
            return RecoveryReport()
        recovered = orphan = partial = duplicate = corrupt = 0
        with capture_write_lock(self.paths):
            self._ensure_layout_locked()
            journal_ids: set[str] = set()
            for path in sorted(self.capture.journals.glob("*.json")):
                if not _RECEIPT_ID.fullmatch(path.stem):
                    corrupt += 1; self._quarantine(path); continue
                try:
                    self._read_manifest(path.stem) if False else self._manifest_value(path.stem, read_json(path).get("observation_ids", []))
                    journal_ids.add(path.stem)
                except (ValueError, TypeError):
                    corrupt += 1; self._quarantine(path)
            referenced: set[str] = set()
            for receipt_path in sorted(self.capture.receipts.glob("*.json")):
                if not _RECEIPT_ID.fullmatch(receipt_path.stem):
                    corrupt += 1; self._quarantine(receipt_path); continue
                try:
                    receipt = self._read_receipt(receipt_path.stem)
                except ValueError:
                    corrupt += 1; self._quarantine(receipt_path); continue
                has_journal = receipt.receipt_id in journal_ids
                valid = self._manifest_valid(receipt)
                if receipt.status == "complete" and valid:
                    referenced.update(self._read_manifest(receipt.receipt_id))
                    if has_journal:
                        self._cleanup_ids(receipt.receipt_id, self._read_manifest(receipt.receipt_id), remove_manifest=False); recovered += 1
                    continue
                if has_journal or receipt.status == "extracting" or (receipt.status == "complete" and not valid):
                    partial += 1
                    ids: tuple[str, ...] = ()
                    try:
                        ids = self._read_manifest(receipt.receipt_id)
                    except ValueError:
                        try:
                            ids = tuple(read_json(self._journal_path(receipt.receipt_id)).get("observation_ids", [])) if has_journal else ()
                        except ValueError:
                            ids = ()
                    ids = tuple(item for item in ids if isinstance(item, str) and _OBSERVATION_ID.fullmatch(item))
                    self._cleanup_ids(receipt.receipt_id, ids, remove_manifest=True)
                    retryable = self._retryable(receipt, now)
                    self._write_receipt(retryable)
                    self._write_ledger(retryable, status="retryable", processed_at=None)
                    recovered += 1
            for path in sorted(self.capture.observations.glob("*.json")):
                if not _OBSERVATION_ID.fullmatch(path.stem):
                    corrupt += 1; self._quarantine(path); continue
                try:
                    observation = CollectedObservation.from_mapping(read_json(path))
                except ValueError:
                    corrupt += 1; self._quarantine(path); continue
                if observation.observation_id not in referenced:
                    orphan += 1; safe_unlink(path)
        return RecoveryReport(recovered, orphan, partial, duplicate, corrupt)

    def object_counts(self) -> dict[str, int]:
        if not self.capture.root.exists():
            return {"receipts": 0, "observations": 0, "ledger": 0}
        with capture_write_lock(self.paths):
            return {"receipts": len(list(self.capture.receipts.glob("cr_*.json"))), "observations": len(list(self.capture.observations.glob("co_*.json"))), "ledger": len(list(self.capture.ledger.glob("cr_*.json")))}
