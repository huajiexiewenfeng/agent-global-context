"""Isolated, journaled persistence for the disabled Capture data plane."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
from typing import Callable, Sequence

from agc_runtime.capture_contracts import (
    CAPTURE_SCHEMA_VERSION,
    CaptureKey,
    CaptureLease,
    CaptureReceipt,
    CollectedObservation,
    LedgerEntry,
    SanitizedError,
    receipt_id_for,
)
from agc_runtime.capture_transaction import atomic_write_json, read_json
from agc_runtime.locking import capture_write_lock
from agc_runtime.paths import MemoryPaths


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
    recovered_count: int
    orphan_count: int
    partial_count: int
    duplicate_count: int


class CaptureStore:
    """The Capture namespace is deliberately separate from ``MemoryStore``."""

    def __init__(
        self, paths: MemoryPaths, *, crash_at: str | None = None,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self.paths = paths
        self.capture = paths.capture
        self._crash_at = crash_at
        self._clock = clock or _utc_now

    def ensure_layout(self) -> None:
        self.capture.root.mkdir(parents=True, exist_ok=True)
        for directory in self.capture.directories():
            directory.mkdir(parents=True, exist_ok=True)
        if not self.capture.schema_version.exists():
            self.capture.schema_version.write_bytes(b"1\n")

    def _point(self, point: str) -> None:
        if self._crash_at == point:
            raise RuntimeError(f"injected crash at {point}")

    def _receipt_path(self, receipt_id: str) -> Path:
        return self.capture.receipts / f"{receipt_id}.json"

    def _ledger_path(self, receipt_id: str) -> Path:
        return self.capture.ledger / f"{receipt_id}.json"

    def _lease_path(self, receipt_id: str) -> Path:
        return self.capture.leases / f"{receipt_id}.json"

    def _journal_path(self, receipt_id: str) -> Path:
        return self.capture.journals / f"{receipt_id}.json"

    def _stage_path(self, observation_id: str) -> Path:
        # Observation IDs are globally bound to their receipt and keep Windows
        # paths below MAX_PATH even when a test or profile root is long.
        return self.capture.staging / f"{observation_id}.json"

    def _conflict_path(self, key: CaptureKey) -> Path:
        digest = hashlib.sha256(
            "\0".join((key.adapter_id, key.source_root_id)).encode("utf-8")
        ).hexdigest()
        return self.capture.conflicts / f"source-{digest}.json"

    def _read_receipt_path(self, path: Path) -> CaptureReceipt:
        return CaptureReceipt.from_mapping(read_json(path))

    def read_receipt(self, receipt_id: str) -> CaptureReceipt:
        return self._read_receipt_path(self._receipt_path(receipt_id))

    def _write_receipt(self, receipt: CaptureReceipt) -> None:
        atomic_write_json(self._receipt_path(receipt.receipt_id), receipt.to_mapping())

    def _write_ledger(self, entry: LedgerEntry) -> None:
        atomic_write_json(self._ledger_path(entry.receipt_id), entry.to_mapping())

    def reconcile_discovery(self, batch: DiscoveryBatch) -> ReconcileResult:
        return self.register_extraction(batch.receipt)

    def register_extraction(self, receipt: CaptureReceipt) -> ReconcileResult:
        """Record (or reconcile) a synthetic discovered/extracting receipt."""
        if receipt.status not in {"discovered", "queued", "extracting"}:
            raise ValueError("discovery receipt must be non-terminal")
        self.ensure_layout()
        with capture_write_lock(self.paths):
            target = self._receipt_path(receipt.receipt_id)
            if not target.exists():
                self._write_receipt(receipt)
                self._write_ledger(LedgerEntry(
                    CAPTURE_SCHEMA_VERSION, receipt.key, receipt.receipt_id,
                    receipt.discovered_at, None, receipt.status,
                ))
                return ReconcileResult(receipt.status, True, receipt.receipt_id)
            current = self._read_receipt_path(target)
            same_schema = current.source_hash_schema_version == receipt.source_hash_schema_version
            same_fingerprint = current.source_fingerprint == receipt.source_fingerprint
            if same_schema and same_fingerprint:
                return ReconcileResult(current.status, False, current.receipt_id)
            if not same_schema:
                return ReconcileResult(current.status, False, current.receipt_id)
            self._write_source_conflict(current.key, receipt.updated_at)
            if current.status == "complete":
                return ReconcileResult("complete", False, current.receipt_id)
            quarantined = replace(
                current, status="quarantined", updated_at=receipt.updated_at,
                sanitized_error=SanitizedError("source", "source_conflict", False),
                next_retry_at=None,
            )
            self._write_receipt(quarantined)
            self._write_ledger(LedgerEntry(
                CAPTURE_SCHEMA_VERSION, current.key, current.receipt_id,
                current.discovered_at, None, "quarantined",
            ))
            return ReconcileResult("quarantined", False, current.receipt_id)

    def _write_source_conflict(self, key: CaptureKey, created_at: str) -> None:
        # This diagnostic is intentionally content-free: no source fingerprints,
        # task/revision IDs, source locators, stack traces, or user text.
        atomic_write_json(self._conflict_path(key), {
            "schema_version": CAPTURE_SCHEMA_VERSION,
            "code": "source_conflict",
            "created_at": created_at,
        })

    def source_health(self, adapter_id: str, source_root_id: str) -> str:
        digest = hashlib.sha256(f"{adapter_id}\0{source_root_id}".encode("utf-8")).hexdigest()
        return "degraded" if (self.capture.conflicts / f"source-{digest}.json").exists() else "healthy"

    def acquire_lease(
        self, key: CaptureKey, *, owner_id: str, now: str, ttl_seconds: int,
    ) -> CaptureLease | None:
        if ttl_seconds < 1:
            raise ValueError("lease ttl_seconds must be positive")
        self.ensure_layout()
        receipt_id = receipt_id_for(key)
        expires = (_parse_utc(now) + timedelta(seconds=ttl_seconds)).replace(microsecond=0)
        expires_at = expires.isoformat().replace("+00:00", "Z")
        with capture_write_lock(self.paths):
            path = self._lease_path(receipt_id)
            previous: CaptureLease | None = None
            if path.exists():
                previous = CaptureLease.from_mapping(read_json(path))
                if _parse_utc(previous.expires_at) > _parse_utc(now):
                    return None
            token = 1 if previous is None else previous.fencing_token + 1
            lease = CaptureLease(
                CAPTURE_SCHEMA_VERSION, key, owner_id, token, now, expires_at
            )
            atomic_write_json(path, lease.to_mapping())
            return lease

    def _assert_current_lease(self, lease: CaptureLease) -> None:
        current = CaptureLease.from_mapping(read_json(self._lease_path(receipt_id_for(lease.capture_key))))
        if current != lease:
            raise ValueError("lease is stale or owned by another worker")
        if _parse_utc(lease.expires_at) <= _parse_utc(self._clock()):
            raise ValueError("lease has expired")

    def _unique_observations(
        self, observations: Sequence[CollectedObservation], receipt_id: str,
    ) -> tuple[CollectedObservation, ...]:
        unique: dict[str, CollectedObservation] = {}
        for observation in observations:
            # Dataclasses can be directly constructed/replaced; reserialize here
            # before journaling so invalid IDs/fingerprints cannot leave a retry
            # artifact behind.
            observation.to_mapping()
            if observation.receipt_id != receipt_id:
                raise ValueError("observation receipt binding is invalid")
            unique.setdefault(observation.observation_fingerprint, observation)
        if len(unique) > 8:
            raise ValueError("Capture extraction may contain at most 8 observations")
        return tuple(unique.values())

    def commit_extraction(
        self, lease: CaptureLease, observations: Sequence[CollectedObservation],
        terminal_receipt: CaptureReceipt,
    ) -> CommitResult:
        self.ensure_layout()
        with capture_write_lock(self.paths):
            self._assert_current_lease(lease)
            current = self.read_receipt(lease.capture_key and receipt_id_for(lease.capture_key))
            if current.key != lease.capture_key or terminal_receipt.key != lease.capture_key:
                raise ValueError("receipt key does not match lease")
            if terminal_receipt.receipt_id != current.receipt_id or terminal_receipt.status != "complete":
                raise ValueError("terminal receipt must be complete for the leased key")
            terminal_receipt.to_mapping()
            if terminal_receipt.schema_version != CAPTURE_SCHEMA_VERSION:
                raise ValueError("terminal receipt schema is unsupported")
            bound_fields = (
                "adapter_version", "source_schema_version", "identity_quality",
                "source_fingerprint", "source_hash_schema_version", "capsule_hash",
                "capsule_schema_version", "settled_at", "discovered_at", "attempt_count",
                "extractor_id", "extractor_version", "extractor_schema_version",
                "taxonomy_version", "usage_quality", "redacted_by_forget",
                "forgotten_observation_count",
            )
            if any(
                getattr(terminal_receipt, field) != getattr(current, field)
                for field in bound_fields
            ):
                raise ValueError("terminal receipt changes bound receipt metadata")
            unique = self._unique_observations(observations, current.receipt_id)
            if terminal_receipt.observation_count != len(unique):
                raise ValueError("terminal receipt observation count does not match batch")
            if terminal_receipt.zero_reason is None and not unique:
                raise ValueError("zero-observation terminal receipt requires a reason")
            if terminal_receipt.zero_reason is not None and unique:
                raise ValueError("nonzero terminal receipt cannot have a zero reason")
            if any(
                getattr(terminal_receipt.token_usage, name) < getattr(current.token_usage, name)
                for name in ("input_tokens", "output_tokens", "total_tokens")
            ):
                raise ValueError("token totals must be monotonic")
            if current.status == "complete":
                return CommitResult(current.receipt_id, 0)
            journal = {
                "schema_version": CAPTURE_SCHEMA_VERSION,
                "receipt_id": current.receipt_id,
                "observation_ids": [item.observation_id for item in unique],
                "phase": "prepared",
            }
            self._point("before:journal")
            atomic_write_json(self._journal_path(current.receipt_id), journal)
            self._point("after:journal")
            self._point("before:stage")
            for observation in unique:
                atomic_write_json(self._stage_path(observation.observation_id), observation.to_mapping())
            self._point("after:stage")
            for index, observation in enumerate(unique):
                self._point(f"before:observation:{index}")
                atomic_write_json(self.capture.observations / f"{observation.observation_id}.json", observation.to_mapping())
                self._point(f"after:observation:{index}")
            self._point("before:ledger")
            self._write_ledger(LedgerEntry(
                CAPTURE_SCHEMA_VERSION, current.key, current.receipt_id,
                current.discovered_at, terminal_receipt.updated_at, "complete",
            ))
            self._point("after:ledger")
            self._point("before:receipt")
            self._write_receipt(terminal_receipt)
            self._point("after:receipt")
            self._point("before:cleanup")
            self._cleanup(current.receipt_id)
            self._point("after:cleanup")
            return CommitResult(current.receipt_id, len(unique))

    def _complete_visible(self, receipt: CaptureReceipt) -> bool:
        if receipt.status != "complete" or receipt.observation_count is None:
            return False
        objects = []
        for path in self.capture.observations.glob("co_*.json"):
            try:
                observation = CollectedObservation.from_mapping(read_json(path))
            except ValueError:
                return False
            if observation.receipt_id == receipt.receipt_id:
                objects.append(observation)
        return len(objects) == receipt.observation_count and len({item.observation_id for item in objects}) == len(objects)

    def visible_observations(self, receipt_id: str) -> tuple[CollectedObservation, ...]:
        receipt = self.read_receipt(receipt_id)
        if not self._complete_visible(receipt):
            return ()
        items = [
            CollectedObservation.from_mapping(read_json(path))
            for path in self.capture.observations.glob("co_*.json")
            if read_json(path).get("receipt_id") == receipt_id
        ]
        return tuple(sorted(items, key=lambda item: (item.ordinal, item.observation_id)))

    def _cleanup(self, receipt_id: str) -> None:
        journal_path = self._journal_path(receipt_id)
        if journal_path.exists():
            try:
                names = read_json(journal_path).get("observation_ids", [])
            except ValueError:
                names = []
            for name in names:
                if isinstance(name, str) and name.startswith("co_"):
                    self._stage_path(name).unlink(missing_ok=True)
        journal_path.unlink(missing_ok=True)

    def _retryable(self, receipt: CaptureReceipt, now: str) -> CaptureReceipt:
        return CaptureReceipt.from_mapping({
            **receipt.to_mapping(), "status": "retryable", "updated_at": now,
            "next_retry_at": now, "observation_count": None,
            "filtered_counts": None, "duplicate_suppression_count": None,
            "zero_reason": None,
            "sanitized_error": {"stage": "transaction", "code": "interrupted", "retryable": True},
        })

    def recover_transactions(self, *, now: str) -> RecoveryReport:
        self.ensure_layout()
        recovered = 0
        with capture_write_lock(self.paths):
            journals = {path.stem for path in self.capture.journals.glob("cr_*.json")}
            extracting = set()
            for path in self.capture.receipts.glob("cr_*.json"):
                try:
                    receipt = self._read_receipt_path(path)
                except ValueError:
                    continue
                if receipt.status == "extracting":
                    extracting.add(receipt.receipt_id)
            for receipt_id in sorted(journals | extracting):
                try:
                    receipt = self.read_receipt(receipt_id)
                except ValueError:
                    continue
                if self._complete_visible(receipt):
                    self._cleanup(receipt_id)
                    recovered += 1
                    continue
                journal_path = self._journal_path(receipt_id)
                names: list[str] = []
                if journal_path.exists():
                    try:
                        names = list(read_json(journal_path).get("observation_ids", []))
                    except ValueError:
                        names = []
                for name in names:
                    if isinstance(name, str) and name.startswith("co_"):
                        (self.capture.observations / f"{name}.json").unlink(missing_ok=True)
                        self._stage_path(name).unlink(missing_ok=True)
                if receipt.status == "extracting":
                    retryable = self._retryable(receipt, now)
                    self._write_receipt(retryable)
                    self._write_ledger(LedgerEntry(
                        CAPTURE_SCHEMA_VERSION, receipt.key, receipt.receipt_id,
                        receipt.discovered_at, None, "retryable",
                    ))
                self._cleanup(receipt_id)
                recovered += 1
        return RecoveryReport(recovered, 0, 0, 0)

    def object_counts(self) -> dict[str, int]:
        self.ensure_layout()
        return {
            "receipts": len(list(self.capture.receipts.glob("cr_*.json"))),
            "observations": len(list(self.capture.observations.glob("co_*.json"))),
            "ledger": len(list(self.capture.ledger.glob("cr_*.json"))),
        }
