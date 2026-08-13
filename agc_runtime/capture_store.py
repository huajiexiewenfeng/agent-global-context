"""Isolated, fenced, journaled persistence for disabled Capture."""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import os
import re
import secrets
from pathlib import Path
from typing import Callable, Sequence

from agc_runtime.capture_contracts import (
    CAPTURE_SCHEMA_VERSION, CAPTURE_STATUSES, CaptureKey, CaptureLease, CaptureReceipt,
    CaptureSuppressionTombstone, CollectedObservation, LedgerEntry, RevisionRef,
    SanitizedError, SourceQuarantine, receipt_id_for,
    validate_capture_transition,
)
from agc_runtime.capture_transaction import atomic_write_bytes, atomic_write_json, read_json, safe_unlink
from agc_runtime.locking import capture_write_lock
from agc_runtime.paths import MemoryPaths


_CAPTURE_ID = re.compile(r"^(?:cr|co|ct)_[0-9a-f]{64}$")
_RECEIPT_ID = re.compile(r"^cr_[0-9a-f]{64}$")
_OBSERVATION_ID = re.compile(r"^co_[0-9a-f]{64}$")
_CURSOR_VERSION = 1
_CURSOR_KEY_BYTES = 32


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def root_fingerprint(paths: MemoryPaths) -> str:
    canonical = os.path.normcase(os.path.normpath(str(paths.root.resolve())))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


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


@dataclass(frozen=True)
class CaptureIntegrityDiagnostic:
    code: str
    object_kind: str

    def to_mapping(self) -> dict[str, str]:
        return {"code": self.code, "object_kind": self.object_kind}


@dataclass(frozen=True)
class CaptureSnapshot:
    receipts: tuple[CaptureReceipt, ...] = ()
    observations: tuple[CollectedObservation, ...] = ()
    census: tuple[RevisionRef, ...] = ()
    tombstones: tuple[CaptureSuppressionTombstone, ...] = ()
    source_quarantines: tuple[SourceQuarantine, ...] = ()
    source_conflict_count: int = 0
    diagnostics: tuple[CaptureIntegrityDiagnostic, ...] = ()
    unavailable_ids: frozenset[str] = frozenset()

    @property
    def integrity_state(self) -> str:
        return "degraded" if self.diagnostics else "healthy"


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
        if not self.capture.cursor_hmac_key.exists():
            atomic_write_bytes(self.capture.cursor_hmac_key, secrets.token_bytes(_CURSOR_KEY_BYTES))
        self._read_cursor_key()

    def ensure_layout(self) -> None:
        with capture_write_lock(self.paths):
            self._ensure_layout_locked()

    def _read_cursor_key(self) -> bytes:
        key = self.capture.cursor_hmac_key.read_bytes()
        if len(key) != _CURSOR_KEY_BYTES:
            raise ValueError("invalid Capture cursor key")
        return key

    @staticmethod
    def _cursor_key_id(key: bytes) -> str:
        return hashlib.sha256(b"agc-capture-cursor-key-id\0" + key).hexdigest()

    def cursor_key_status(self) -> dict[str, str | None]:
        try:
            key = self._read_cursor_key()
        except FileNotFoundError:
            return {"state": "missing", "key_id": None}
        except (OSError, ValueError):
            return {"state": "invalid", "key_id": None}
        return {"state": "ready", "key_id": self._cursor_key_id(key)}

    def encode_cursor(self, *, query_digest: str, captured_at: str, observation_id: str) -> str:
        with capture_write_lock(self.paths):
            if not self.capture.cursor_hmac_key.exists():
                atomic_write_bytes(self.capture.cursor_hmac_key, secrets.token_bytes(_CURSOR_KEY_BYTES))
            key = self._read_cursor_key()
            payload = json.dumps(
                {
                    "v": _CURSOR_VERSION,
                    "key_id": self._cursor_key_id(key),
                    "root_fingerprint": root_fingerprint(self.paths),
                    "query_digest": query_digest,
                    "time": captured_at,
                    "id": observation_id,
                },
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
            signature = hmac.new(key, payload, hashlib.sha256).digest()
        return base64.urlsafe_b64encode(payload + signature).decode("ascii").rstrip("=")

    def decode_cursor(self, cursor: object, *, query_digest: str) -> tuple[str, str] | None:
        if cursor is None:
            return None
        if not isinstance(cursor, str) or not cursor:
            raise ValueError("invalid capture cursor")
        try:
            raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
            if len(raw) <= hashlib.sha256().digest_size:
                raise ValueError
            payload, signature = raw[:-32], raw[-32:]
            if not self.capture.cursor_hmac_key.exists():
                raise ValueError
            with capture_write_lock(self.paths):
                key = self._read_cursor_key()
            if not hmac.compare_digest(hmac.new(key, payload, hashlib.sha256).digest(), signature):
                raise ValueError
            value = json.loads(payload.decode("utf-8"))
            if (
                not isinstance(value, dict)
                or set(value) != {"v", "key_id", "root_fingerprint", "query_digest", "time", "id"}
                or value.get("v") != _CURSOR_VERSION
                or value.get("key_id") != self._cursor_key_id(key)
                or value.get("root_fingerprint") != root_fingerprint(self.paths)
                or value.get("query_digest") != query_digest
                or not isinstance(value.get("time"), str)
                or not isinstance(value.get("id"), str)
            ):
                raise ValueError
            return value["time"], value["id"]
        except (binascii.Error, FileNotFoundError, OSError, UnicodeDecodeError, ValueError, TypeError, json.JSONDecodeError) as error:
            raise ValueError("invalid capture cursor") from error

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

    def _transition_journal_path(self, receipt_id: str) -> Path:
        if not _RECEIPT_ID.fullmatch(receipt_id):
            raise ValueError("invalid Capture object identifier")
        path = self.capture.journals / f"tr_{receipt_id}.json"
        if path.parent.resolve() != self.capture.journals.resolve():
            raise ValueError("Capture object path escapes its directory")
        return path

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

    def iter_receipts(self) -> tuple[CaptureReceipt, ...]:
        """Return strictly decoded receipts for the isolated read service."""
        if not self.capture.receipts.exists():
            return ()
        return tuple(
            self._read_receipt(path.stem)
            for path in sorted(self.capture.receipts.glob("*.json"))
        )

    def read_snapshot(self) -> CaptureSnapshot:
        """Decode one content-safe Capture view while holding the root lock.

        The snapshot never treats a corrupt complete receipt as visible and
        reports corruption using fixed machine diagnostics without filesystem
        paths, source locators, statements, or exception text.
        """
        if not self.capture.root.exists():
            return CaptureSnapshot()
        with capture_write_lock(self.paths):
            diagnostics: list[CaptureIntegrityDiagnostic] = []
            unavailable_ids: set[str] = set()

            def degraded(code: str, kind: str) -> None:
                diagnostics.append(CaptureIntegrityDiagnostic(code, kind))

            def json_objects(directory: Path, code: str, kind: str) -> tuple[Path, ...]:
                if not directory.exists() or not directory.is_dir():
                    degraded("missing_capture_namespace", kind)
                    return ()
                objects: list[Path] = []
                for path in sorted(directory.iterdir()):
                    if not path.is_file() or path.suffix.lower() != ".json":
                        degraded(code, kind)
                        continue
                    objects.append(path)
                return tuple(objects)

            observations_by_id: dict[str, CollectedObservation] = {}
            for path in json_objects(self.capture.observations, "invalid_observation", "observation"):
                try:
                    if not _OBSERVATION_ID.fullmatch(path.stem):
                        raise ValueError
                    item = CollectedObservation.from_mapping(read_json(path))
                    if item.observation_id != path.stem or item.observation_id in observations_by_id:
                        raise ValueError
                    observations_by_id[item.observation_id] = item
                except (OSError, TypeError, ValueError):
                    degraded("invalid_observation", "observation")
                    if _OBSERVATION_ID.fullmatch(path.stem):
                        unavailable_ids.add(path.stem)

            manifests: dict[str, tuple[str, ...]] = {}
            for path in json_objects(self.capture.indexes, "invalid_manifest", "manifest"):
                try:
                    if not _RECEIPT_ID.fullmatch(path.stem):
                        raise ValueError
                    manifests[path.stem] = self._read_manifest(path.stem)
                except (OSError, TypeError, ValueError):
                    degraded("invalid_manifest", "manifest")
                    if _RECEIPT_ID.fullmatch(path.stem):
                        unavailable_ids.add(path.stem)

            receipts: list[CaptureReceipt] = []
            visible: list[CollectedObservation] = []
            referenced_observation_ids: set[str] = set()
            visible_receipt_ids: set[str] = set()
            receipt_keys: set[tuple[str, str, str, str]] = set()
            for path in json_objects(self.capture.receipts, "invalid_receipt", "receipt"):
                try:
                    if not _RECEIPT_ID.fullmatch(path.stem):
                        raise ValueError
                    receipt = CaptureReceipt.from_mapping(read_json(path))
                    if receipt.receipt_id != path.stem:
                        raise ValueError
                except (OSError, TypeError, ValueError):
                    degraded("invalid_receipt", "receipt")
                    if _RECEIPT_ID.fullmatch(path.stem):
                        unavailable_ids.add(path.stem)
                    continue
                key_id = (
                    receipt.adapter_id,
                    receipt.source_root_id,
                    receipt.task_id,
                    receipt.revision_id,
                )
                if key_id in receipt_keys:
                    degraded("duplicate_capture_key", "receipt")
                    continue
                if receipt.status == "complete":
                    try:
                        ids = manifests[receipt.receipt_id]
                        if receipt.observation_count != len(ids):
                            raise ValueError
                        bound: list[CollectedObservation] = []
                        for observation_id in ids:
                            observation = observations_by_id[observation_id]
                            if observation.receipt_id != receipt.receipt_id:
                                raise ValueError
                            bound.append(observation)
                    except (KeyError, OSError, TypeError, ValueError):
                        degraded("invalid_manifest", "manifest")
                        unavailable_ids.add(receipt.receipt_id)
                        unavailable_ids.update(
                            item.observation_id
                            for item in observations_by_id.values()
                            if item.receipt_id == receipt.receipt_id
                        )
                        continue
                    referenced_observation_ids.update(ids)
                    visible_receipt_ids.add(receipt.receipt_id)
                    visible.extend(bound)
                receipts.append(receipt)
                receipt_keys.add(key_id)

            for receipt_id in set(manifests) - visible_receipt_ids:
                degraded("orphan_manifest", "manifest")

            for observation_id in set(observations_by_id) - referenced_observation_ids:
                degraded("orphan_observation", "observation")

            census: list[RevisionRef] = []
            census_keys: set[tuple[str, str, str, str]] = set()
            if self.capture.census.exists():
                for path in json_objects(self.capture.census, "invalid_census_revision", "census"):
                    try:
                        revision = RevisionRef.from_mapping(read_json(path))
                    except (OSError, TypeError, ValueError):
                        degraded("invalid_census_revision", "census")
                        continue
                    key_id = (
                        revision.key.adapter_id,
                        revision.key.source_root_id,
                        revision.key.task_id,
                        revision.key.revision_id,
                    )
                    if key_id in census_keys:
                        degraded("duplicate_capture_key", "census")
                        continue
                    census_keys.add(key_id)
                    census.append(revision)

            tombstones: list[CaptureSuppressionTombstone] = []
            tombstone_keys: set[tuple[str, str, str, str]] = set()
            if self.capture.tombstones.exists():
                for path in json_objects(self.capture.tombstones, "invalid_tombstone", "tombstone"):
                    try:
                        tombstone = CaptureSuppressionTombstone.from_mapping(read_json(path))
                        if path.stem != tombstone.tombstone_id:
                            raise ValueError
                    except (OSError, TypeError, ValueError):
                        degraded("invalid_tombstone", "tombstone")
                        continue
                    key = tombstone.capture_key
                    key_id = (key.adapter_id, key.source_root_id, key.task_id, key.revision_id)
                    if key_id in tombstone_keys:
                        degraded("duplicate_capture_key", "tombstone")
                        continue
                    tombstone_keys.add(key_id)
                    tombstones.append(tombstone)

            quarantines: list[SourceQuarantine] = []
            quarantine_keys: set[tuple[str, str]] = set()
            if self.capture.quarantines.exists():
                for path in json_objects(self.capture.quarantines, "invalid_quarantine", "quarantine"):
                    try:
                        value = read_json(path)
                        if value == {
                            "schema_version": CAPTURE_SCHEMA_VERSION,
                            "code": "corrupt_capture_artifact",
                        }:
                            degraded("stored_corruption_diagnostic", "quarantine")
                            continue
                        quarantine = SourceQuarantine.from_mapping(value)
                    except (OSError, TypeError, ValueError):
                        degraded("invalid_quarantine", "quarantine")
                        continue
                    key_id = (quarantine.adapter_id, quarantine.source_root_id)
                    if key_id in quarantine_keys:
                        degraded("duplicate_source_quarantine", "quarantine")
                        continue
                    quarantine_keys.add(key_id)
                    quarantines.append(quarantine)

            conflict_count = 0
            if self.capture.conflicts.exists():
                for path in json_objects(self.capture.conflicts, "invalid_source_conflict", "conflict"):
                    try:
                        value = read_json(path)
                        if (
                            set(value) != {"schema_version", "code", "created_at"}
                            or value.get("schema_version") != CAPTURE_SCHEMA_VERSION
                            or value.get("code") != "source_conflict"
                            or not isinstance(value.get("created_at"), str)
                        ):
                            raise ValueError
                    except (OSError, TypeError, ValueError):
                        degraded("invalid_source_conflict", "conflict")
                        continue
                    conflict_count += 1

            return CaptureSnapshot(
                receipts=tuple(receipts),
                observations=tuple(visible),
                census=tuple(census),
                tombstones=tuple(tombstones),
                source_quarantines=tuple(quarantines),
                source_conflict_count=conflict_count,
                diagnostics=tuple(diagnostics),
                unavailable_ids=frozenset(unavailable_ids),
            )

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
            transition_journal = {
                "schema_version": CAPTURE_SCHEMA_VERSION,
                "operation": "transition",
                "receipt_id": current.receipt_id,
                "expected_status": current.status,
                "target_status": target,
            }
            self._point("before:transition:journal")
            atomic_write_json(self._transition_journal_path(current.receipt_id), transition_journal)
            self._point("after:transition:journal")
            self._point("before:transition:receipt")
            self._write_receipt(updated)
            self._point("after:transition:receipt")
            self._point("before:transition:ledger")
            self._write_ledger(updated, status=target, processed_at=None)
            self._point("after:transition:ledger")
            self._point("before:transition:cleanup")
            safe_unlink(self._transition_journal_path(current.receipt_id))
            self._point("after:transition:cleanup")
            return updated

    def visible_observations(self, receipt_id: str) -> tuple[CollectedObservation, ...]:
        receipt = self._read_receipt(receipt_id)
        if not self._manifest_valid(receipt):
            return ()
        ids = self._read_manifest(receipt_id)
        items = tuple(CollectedObservation.from_mapping(read_json(self._observation_path(item))) for item in ids)
        return tuple(sorted(items, key=lambda item: (item.ordinal, item.observation_id)))

    def iter_visible_observations(self) -> tuple[CollectedObservation, ...]:
        """Expose only observations backed by a complete immutable manifest."""
        items: list[CollectedObservation] = []
        for receipt in self.iter_receipts():
            if receipt.status == "complete":
                items.extend(self.visible_observations(receipt.receipt_id))
        return tuple(items)

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

    def _binding_ids(self, value: object, receipt_id: str) -> tuple[str, ...]:
        if not isinstance(value, dict) or set(value) != {"schema_version", "receipt_id", "observation_ids"}:
            raise ValueError("invalid Capture transaction journal")
        if value.get("schema_version") != CAPTURE_SCHEMA_VERSION or value.get("receipt_id") != receipt_id:
            raise ValueError("invalid Capture transaction journal")
        ids = value.get("observation_ids", [])
        if not isinstance(ids, list) or len(ids) > 8:
            raise ValueError("invalid Capture transaction journal")
        return tuple(self._manifest_value(receipt_id, ids)["observation_ids"])

    def _artifact_binds(self, directory: Path, receipt_id: str, observation_id: str) -> bool:
        path = self._path(directory, observation_id, _OBSERVATION_ID)
        if not path.exists():
            return True
        try:
            observation = CollectedObservation.from_mapping(read_json(path))
        except ValueError:
            return False
        return observation.observation_id == observation_id and observation.receipt_id == receipt_id

    def _safe_cleanup_bound(self, receipt_id: str, ids: Sequence[str], *, remove_manifest: bool) -> bool:
        """Delete only artifacts independently proven to belong to ``receipt_id``."""
        if any(not self._artifact_binds(directory, receipt_id, item) for directory in (self.capture.observations, self.capture.staging) for item in ids):
            return False
        for observation_id in ids:
            safe_unlink(self._stage_path(observation_id))
            if remove_manifest:
                safe_unlink(self._observation_path(observation_id))
        if remove_manifest:
            safe_unlink(self._manifest_path(receipt_id))
        return True

    def _recover_transition_journal(self, path: Path) -> tuple[int, int]:
        try:
            value = read_json(path)
            if set(value) != {"schema_version", "operation", "receipt_id", "expected_status", "target_status"} or value.get("schema_version") != CAPTURE_SCHEMA_VERSION or value.get("operation") != "transition" or not isinstance(value.get("receipt_id"), str) or not _RECEIPT_ID.fullmatch(value["receipt_id"]):
                raise ValueError("invalid transition journal")
            if path.name != f"tr_{value['receipt_id']}.json":
                raise ValueError("transition journal filename binding mismatch")
            expected = value["expected_status"]
            target = value["target_status"]
            if not isinstance(expected, str) or not isinstance(target, str) or expected not in CAPTURE_STATUSES or target not in CAPTURE_STATUSES:
                raise ValueError("invalid transition journal status")
            validate_capture_transition(
                expected, target,
                reopen_reason="explicit_retry" if expected in {"failed", "quarantined"} and target == "queued" else None,
            )
            receipt = self._read_receipt(value["receipt_id"])
            if receipt.status == value["target_status"]:
                self._write_ledger(receipt, status=receipt.status, processed_at=None)
            elif receipt.status != value["expected_status"]:
                raise ValueError("transition journal state mismatch")
            safe_unlink(path)
            return 1, 0
        except (ValueError, TypeError):
            self._quarantine(path)
            return 0, 1

    def recover_transactions(self, *, now: str) -> RecoveryReport:
        if not self.capture.root.exists():
            return RecoveryReport()
        recovered = orphan = partial = duplicate = corrupt = 0
        with capture_write_lock(self.paths):
            self._ensure_layout_locked()
            journal_ids: dict[str, tuple[str, ...]] = {}
            for path in sorted(self.capture.journals.glob("*.json")):
                if path.name.startswith("tr_"):
                    change, bad = self._recover_transition_journal(path)
                    recovered += change; corrupt += bad
                    continue
                if not _RECEIPT_ID.fullmatch(path.stem):
                    corrupt += 1; self._quarantine(path); continue
                try:
                    ids = self._binding_ids(read_json(path), path.stem)
                    if not all(self._artifact_binds(directory, path.stem, item) for directory in (self.capture.observations, self.capture.staging) for item in ids):
                        raise ValueError("journal references foreign observation")
                    journal_ids[path.stem] = ids
                except (ValueError, TypeError):
                    corrupt += 1; self._quarantine(path)
            referenced: set[str] = set()
            active_stage_ids: set[str] = set()
            seen_receipts: set[str] = set()
            for receipt_path in sorted(self.capture.receipts.glob("*.json")):
                if not _RECEIPT_ID.fullmatch(receipt_path.stem):
                    corrupt += 1; self._quarantine(receipt_path); continue
                try:
                    receipt = self._read_receipt(receipt_path.stem)
                except ValueError:
                    corrupt += 1; self._quarantine(receipt_path); continue
                seen_receipts.add(receipt.receipt_id)
                journal_ids_for_receipt = journal_ids.get(receipt.receipt_id)
                has_journal = journal_ids_for_receipt is not None
                if has_journal and receipt.status == "extracting":
                    active_stage_ids.update(journal_ids_for_receipt)
                valid = self._manifest_valid(receipt)
                if receipt.status == "complete" and valid:
                    referenced.update(self._read_manifest(receipt.receipt_id))
                    if has_journal:
                        manifest_ids = self._read_manifest(receipt.receipt_id)
                        if journal_ids_for_receipt != manifest_ids:
                            duplicate += 1
                            safe_unlink(self._journal_path(receipt.receipt_id))
                        else:
                            self._safe_cleanup_bound(receipt.receipt_id, manifest_ids, remove_manifest=False)
                        recovered += 1
                    continue
                if has_journal or receipt.status == "extracting" or (receipt.status == "complete" and not valid):
                    partial += 1
                    ids: tuple[str, ...] = ()
                    try:
                        ids = self._read_manifest(receipt.receipt_id)
                        if has_journal and journal_ids_for_receipt != ids:
                            # Two safe but divergent extraction bindings cannot
                            # both be active. Account for the corruption and
                            # clean both sets below before parking retryable.
                            corrupt += 1
                            ids = tuple(dict.fromkeys((*ids, *journal_ids_for_receipt)))
                        if not self._safe_cleanup_bound(receipt.receipt_id, ids, remove_manifest=True):
                            corrupt += 1
                            self._quarantine(self._manifest_path(receipt.receipt_id))
                            ids = ()
                    except ValueError:
                        ids = journal_ids_for_receipt or ()
                        if not self._safe_cleanup_bound(receipt.receipt_id, ids, remove_manifest=True):
                            corrupt += 1
                            ids = ()
                    if has_journal:
                        safe_unlink(self._journal_path(receipt.receipt_id))
                    retryable = self._retryable(receipt, now)
                    self._write_receipt(retryable)
                    self._write_ledger(retryable, status="retryable", processed_at=None)
                    recovered += 1
            for receipt_id, ids in journal_ids.items():
                if receipt_id in seen_receipts:
                    continue
                partial += 1
                if self._safe_cleanup_bound(receipt_id, ids, remove_manifest=True):
                    safe_unlink(self._journal_path(receipt_id))
                    recovered += 1
                else:
                    corrupt += 1
                    self._quarantine(self._journal_path(receipt_id))
            for path in sorted(self.capture.observations.glob("*.json")):
                if not _OBSERVATION_ID.fullmatch(path.stem):
                    corrupt += 1; self._quarantine(path); continue
                try:
                    observation = CollectedObservation.from_mapping(read_json(path))
                except ValueError:
                    corrupt += 1; self._quarantine(path); continue
                if observation.observation_id not in referenced:
                    orphan += 1; safe_unlink(path)
            for path in sorted(self.capture.staging.glob("*.json")):
                if not _OBSERVATION_ID.fullmatch(path.stem):
                    corrupt += 1; self._quarantine(path); continue
                try:
                    observation = CollectedObservation.from_mapping(read_json(path))
                except ValueError:
                    corrupt += 1; self._quarantine(path); continue
                if observation.observation_id not in active_stage_ids:
                    orphan += 1; safe_unlink(path)
        return RecoveryReport(recovered, orphan, partial, duplicate, corrupt)

    def object_counts(self) -> dict[str, int]:
        if not self.capture.root.exists():
            return {"receipts": 0, "observations": 0, "ledger": 0}
        with capture_write_lock(self.paths):
            return {"receipts": len(list(self.capture.receipts.glob("cr_*.json"))), "observations": len(list(self.capture.observations.glob("co_*.json"))), "ledger": len(list(self.capture.ledger.glob("cr_*.json")))}
