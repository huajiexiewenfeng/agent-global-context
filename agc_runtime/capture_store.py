"""Isolated, fenced, journaled persistence for disabled Capture."""

from __future__ import annotations

import base64
import binascii
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Mapping, Sequence

from agc_runtime.capture_contracts import (
    CAPTURE_SCHEMA_VERSION, CAPTURE_STATUSES, BudgetSettlement, CaptureKey, CaptureLease, CaptureReceipt,
    CaptureSuppressionTombstone, CollectedObservation, LedgerEntry, RevisionRef,
    SanitizedError, SourceQuarantine, TokenReservation, receipt_id_for, tombstone_id_for,
    validate_capture_transition,
)
from agc_runtime.capture_review import CaptureReviewReceipt, parse_capture_observation_ids
from agc_runtime.capture_transaction import (
    atomic_install_json_directory,
    atomic_write_bytes,
    atomic_write_json,
    read_json,
    safe_unlink,
)
from agc_runtime.locking import capture_write_lock
from agc_runtime.paths import MemoryPaths

if TYPE_CHECKING:
    from agc_runtime.capture_source import CensusRun, ScanHint, ScanState, SourceBindingKey, TimeWindow


_CAPTURE_ID = re.compile(r"^(?:cr|co|ct)_[0-9a-f]{64}$")
_RECEIPT_ID = re.compile(r"^cr_[0-9a-f]{64}$")
_OBSERVATION_ID = re.compile(r"^co_[0-9a-f]{64}$")
_CURSOR_VERSION = 1
_CURSOR_KEY_BYTES = 32
_CENSUS_CATALOG_SCHEMA_VERSION = "census-catalog-v1"


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
    review_receipts: tuple[CaptureReviewReceipt, ...] = ()
    census: tuple[RevisionRef, ...] = ()
    tombstones: tuple[CaptureSuppressionTombstone, ...] = ()
    source_quarantines: tuple[SourceQuarantine, ...] = ()
    source_conflict_count: int = 0
    census_runs: tuple[CensusRun, ...] = ()
    scan_states: tuple[ScanState, ...] = ()
    dirty_markers: tuple[DirtyMarker, ...] = ()
    source_conflict_digests: frozenset[str] = frozenset()
    accounted_keys: frozenset[CaptureKey] = frozenset()
    diagnostics: tuple[CaptureIntegrityDiagnostic, ...] = ()
    unavailable_ids: frozenset[str] = frozenset()

    @property
    def integrity_state(self) -> str:
        return "degraded" if self.diagnostics else "healthy"


class CaptureReadBusyError(RuntimeError):
    """The content-safe read snapshot could not acquire the Capture root."""

    def __init__(self) -> None:
        super().__init__("capture_read_busy")


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

    @contextmanager
    def _capture_read_lock(self):
        guard = capture_write_lock(self.paths)
        try:
            guard.__enter__()
        except RuntimeError:
            raise CaptureReadBusyError() from None
        try:
            yield
        finally:
            guard.__exit__(None, None, None)

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
        with self._capture_read_lock():
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
            with self._capture_read_lock():
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

    def _review_path(self, observation_id: str) -> Path:
        return self._path(self.capture.reviews, observation_id, _OBSERVATION_ID)

    def _stage_path(self, observation_id: str) -> Path:
        return self._path(self.capture.staging, observation_id, _OBSERVATION_ID)

    def _conflict_path(self, key: CaptureKey) -> Path:
        digest = hashlib.sha256(f"{key.adapter_id}\0{key.source_root_id}".encode("utf-8")).hexdigest()
        return self.capture.conflicts / f"source-{digest}.json"

    @staticmethod
    def _binding_digest(binding: SourceBindingKey) -> str:
        from agc_runtime.capture_ledger import binding_digest

        return binding_digest(binding.adapter_id, binding.source_root_id)

    def _scan_state_path(self, binding: SourceBindingKey) -> Path:
        return self.capture.scan_state / f"state-{self._binding_digest(binding)}.json"

    def _census_run_path(self, census_id: str) -> Path:
        return self.capture.root / "census-runs" / census_id

    @staticmethod
    def _revision_sort_key(revision: RevisionRef) -> tuple[str, str, str, str]:
        key = revision.key
        return key.adapter_id, key.source_root_id, key.task_id, key.revision_id

    def _read_frozen_run(
        self, path: Path
    ) -> tuple[CensusRun, tuple[RevisionRef, ...]]:
        from agc_runtime.capture_ledger import validate_frozen_census_run
        from agc_runtime.capture_source import CensusRun

        if not path.is_dir() or path.name.startswith("."):
            raise ValueError("invalid frozen Census run")
        if {item.name for item in path.iterdir()} != {"members", "run.json"}:
            raise ValueError("invalid frozen Census run")
        members_path = path / "members"
        if not members_path.is_dir():
            raise ValueError("invalid frozen Census run")
        census = CensusRun.from_mapping(read_json(path / "run.json"))
        if census.census_id != path.name:
            raise ValueError("frozen Census run filename binding mismatch")
        revisions: list[RevisionRef] = []
        for member_path in sorted(members_path.iterdir()):
            if not member_path.is_file() or member_path.suffix != ".json":
                raise ValueError("invalid frozen Census member")
            revision = RevisionRef.from_mapping(read_json(member_path))
            if member_path.name != f"{receipt_id_for(revision.key)}.json":
                raise ValueError("frozen Census member filename binding mismatch")
            if (
                revision.key.adapter_id != census.binding.adapter_id
                or revision.key.source_root_id != census.binding.source_root_id
            ):
                raise ValueError("frozen Census member binding mismatch")
            revisions.append(revision)
        ordered = tuple(sorted(revisions, key=self._revision_sort_key))
        validate_frozen_census_run(census, ordered, run_id=path.name)
        return census, ordered

    def frozen_revision_records(
        self, *, binding: SourceBindingKey | None = None
    ) -> tuple[RevisionRef, ...]:
        """Return hot canonical truth, retaining a cold conflict-diagnosis path."""

        with capture_write_lock(self.paths):
            self._ensure_layout_locked()
            try:
                _runs, revisions = self._ensure_census_catalog_locked()
            except ValueError as error:
                if str(error) != "revision_metadata_conflict":
                    raise
                _runs, revisions = self._read_cold_census_truth(binding=binding)
                return revisions
            if binding is None:
                return revisions
            return tuple(
                item
                for item in revisions
                if item.key.adapter_id == binding.adapter_id
                and item.key.source_root_id == binding.source_root_id
            )

    def _read_cold_census_truth(
        self, *, binding: SourceBindingKey | None = None
    ) -> tuple[tuple[CensusRun, ...], tuple[RevisionRef, ...]]:
        """Decode every frozen member for an explicit cold audit or rebuild."""

        revisions = list(self._read_legacy_census(binding=binding))
        runs: list[CensusRun] = []
        root = self.capture.root / "census-runs"
        if not root.exists():
            return tuple(runs), tuple(revisions)
        for path in sorted(root.iterdir()):
            if path.name.startswith("."):
                continue
            census, members = self._read_frozen_run(path)
            if binding is not None and census.binding != binding:
                continue
            runs.append(census)
            revisions.extend(members)
        return tuple(runs), tuple(revisions)

    def _read_legacy_census(
        self, *, binding: SourceBindingKey | None = None
    ) -> tuple[RevisionRef, ...]:
        revisions: list[RevisionRef] = []
        if not self.capture.census.exists():
            return ()
        for path in sorted(self.capture.census.iterdir()):
            if not path.is_file() or path.suffix != ".json":
                raise ValueError("invalid legacy Census entry")
            revision = RevisionRef.from_mapping(read_json(path))
            if path.name != f"{receipt_id_for(revision.key)}.json":
                raise ValueError("legacy Census filename binding mismatch")
            if binding is None or (
                revision.key.adapter_id == binding.adapter_id
                and revision.key.source_root_id == binding.source_root_id
            ):
                revisions.append(revision)
        return tuple(revisions)

    def _read_census_run_manifest(self, path: Path) -> CensusRun:
        from agc_runtime.capture_source import CensusRun

        if not path.is_dir() or path.name.startswith("."):
            raise ValueError("invalid frozen Census run")
        members_path = path / "members"
        if not members_path.is_dir():
            raise ValueError("invalid frozen Census run")
        census = CensusRun.from_mapping(read_json(path / "run.json"))
        if census.census_id != path.name:
            raise ValueError("frozen Census run filename binding mismatch")
        if (
            _parse_utc(census.window.end_at) != _parse_utc(census.started_at)
            or _parse_utc(census.window.start_at)
            != _parse_utc(census.started_at) - timedelta(days=7)
        ):
            raise ValueError("invalid frozen Census run window")
        if len(census.revision_keys) != len(set(census.revision_keys)):
            raise ValueError("invalid frozen Census run membership")
        if any(
            key.adapter_id != census.binding.adapter_id
            or key.source_root_id != census.binding.source_root_id
            for key in census.revision_keys
        ):
            raise ValueError("frozen Census run binding mismatch")
        return census

    def _read_census_run_manifests(self) -> tuple[CensusRun, ...]:
        root = self.capture.root / "census-runs"
        if not root.exists():
            return ()
        return tuple(
            self._read_census_run_manifest(path)
            for path in sorted(root.iterdir())
            if not path.name.startswith(".")
        )

    @staticmethod
    def _catalog_digest(value: Mapping[str, object]) -> str:
        encoded = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _publish_census_catalog_locked(
        self,
        runs: Sequence[CensusRun],
        revisions: Sequence[RevisionRef],
    ) -> tuple[RevisionRef, ...]:
        revisions = tuple(sorted(revisions, key=self._revision_sort_key))
        run_values = [item.to_mapping() for item in runs]
        revision_values = [item.to_mapping() for item in revisions]
        run_digest = self._catalog_digest({"runs": run_values})
        revision_digest = self._catalog_digest({"revisions": revision_values})
        catalog_id = self._catalog_digest(
            {
                "catalog_schema_version": _CENSUS_CATALOG_SCHEMA_VERSION,
                "run_digest": run_digest,
                "revision_digest": revision_digest,
            }
        )
        manifest = {
            "schema_version": CAPTURE_SCHEMA_VERSION,
            "catalog_schema_version": _CENSUS_CATALOG_SCHEMA_VERSION,
            "catalog_id": catalog_id,
            "run_ids": [item.census_id for item in runs],
            "run_digest": run_digest,
            "revision_count": len(revisions),
            "revision_digest": revision_digest,
        }
        generation_root = self.capture.census_catalog / "g"
        generation = generation_root / catalog_id
        if not generation.exists():
            files: dict[str, Mapping[str, object]] = {"manifest.json": manifest}
            files.update(
                {
                    f"r/{receipt_id_for(item.key)}.json": item.to_mapping()
                    for item in revisions
                }
            )
            atomic_install_json_directory(
                generation,
                files,
                directories=("r",),
            )
        atomic_write_json(
            self.capture.census_catalog / "active.json",
            {
                "schema_version": CAPTURE_SCHEMA_VERSION,
                "catalog_schema_version": _CENSUS_CATALOG_SCHEMA_VERSION,
                "catalog_id": catalog_id,
            },
        )
        if generation_root.exists():
            for path in generation_root.iterdir():
                if path == generation or path.name.startswith("."):
                    continue
                if path.is_symlink() or not path.is_dir():
                    raise ValueError("invalid Census catalog generation")
                if not path.resolve().is_relative_to(generation_root.resolve()):
                    raise ValueError("invalid Census catalog generation")
                shutil.rmtree(path)
        return revisions

    def _rebuild_census_catalog_locked(self) -> tuple[RevisionRef, ...]:
        from agc_runtime.capture_ledger import same_revision_metadata

        runs, records = self._read_cold_census_truth()
        unique: dict[CaptureKey, RevisionRef] = {}
        for revision in records:
            current = unique.get(revision.key)
            if current is not None and not same_revision_metadata(current, revision):
                raise ValueError("revision_metadata_conflict")
            unique.setdefault(revision.key, revision)
        return self._publish_census_catalog_locked(runs, tuple(unique.values()))

    def _read_census_catalog(
        self, runs: Sequence[CensusRun]
    ) -> tuple[RevisionRef, ...]:
        active = read_json(self.capture.census_catalog / "active.json")
        if set(active) != {
            "schema_version",
            "catalog_schema_version",
            "catalog_id",
        } or active.get("schema_version") != CAPTURE_SCHEMA_VERSION or active.get(
            "catalog_schema_version"
        ) != _CENSUS_CATALOG_SCHEMA_VERSION:
            raise ValueError("invalid Census catalog pointer")
        catalog_id = active.get("catalog_id")
        if not isinstance(catalog_id, str) or re.fullmatch(r"[0-9a-f]{64}", catalog_id) is None:
            raise ValueError("invalid Census catalog pointer")
        generation = self.capture.census_catalog / "g" / catalog_id
        if generation.is_symlink() or not generation.is_dir():
            raise ValueError("invalid Census catalog generation")
        if {item.name for item in generation.iterdir()} != {"manifest.json", "r"}:
            raise ValueError("invalid Census catalog generation")
        revisions_path = generation / "r"
        if revisions_path.is_symlink() or not revisions_path.is_dir():
            raise ValueError("invalid Census catalog generation")
        manifest = read_json(generation / "manifest.json")
        expected_fields = {
            "schema_version",
            "catalog_schema_version",
            "catalog_id",
            "run_ids",
            "run_digest",
            "revision_count",
            "revision_digest",
        }
        if (
            set(manifest) != expected_fields
            or manifest.get("schema_version") != CAPTURE_SCHEMA_VERSION
            or manifest.get("catalog_schema_version")
            != _CENSUS_CATALOG_SCHEMA_VERSION
            or manifest.get("catalog_id") != catalog_id
        ):
            raise ValueError("invalid Census catalog manifest")
        run_values = [item.to_mapping() for item in runs]
        run_digest = self._catalog_digest({"runs": run_values})
        if (
            manifest.get("run_ids") != [item.census_id for item in runs]
            or manifest.get("run_digest") != run_digest
        ):
            raise ValueError("stale Census catalog")
        revisions: list[RevisionRef] = []
        unique: dict[CaptureKey, RevisionRef] = {}
        for path in sorted(revisions_path.iterdir()):
            if not path.is_file() or path.suffix != ".json":
                raise ValueError("invalid Census catalog revision")
            revision = RevisionRef.from_mapping(read_json(path))
            if path.name != f"{receipt_id_for(revision.key)}.json":
                raise ValueError("Census catalog filename binding mismatch")
            if revision.key in unique:
                raise ValueError("duplicate Census catalog revision")
            unique[revision.key] = revision
            revisions.append(revision)
        revisions = sorted(revisions, key=self._revision_sort_key)
        revision_values = [item.to_mapping() for item in revisions]
        revision_digest = self._catalog_digest({"revisions": revision_values})
        expected_id = self._catalog_digest(
            {
                "catalog_schema_version": _CENSUS_CATALOG_SCHEMA_VERSION,
                "run_digest": run_digest,
                "revision_digest": revision_digest,
            }
        )
        legacy = self._read_legacy_census()
        expected_keys = {
            *(item.key for item in legacy),
            *(key for run in runs for key in run.revision_keys),
        }
        from agc_runtime.capture_ledger import same_revision_metadata

        if any(
            item.key not in unique
            or not same_revision_metadata(unique[item.key], item)
            for item in legacy
        ):
            raise ValueError("stale Census catalog")
        if (
            set(unique) != expected_keys
            or manifest.get("revision_count") != len(revisions)
            or manifest.get("revision_digest") != revision_digest
            or expected_id != catalog_id
        ):
            raise ValueError("stale Census catalog")
        return tuple(revisions)

    def _ensure_census_catalog_locked(
        self,
    ) -> tuple[tuple[CensusRun, ...], tuple[RevisionRef, ...]]:
        runs = self._read_census_run_manifests()
        try:
            revisions = self._read_census_catalog(runs)
        except (FileNotFoundError, OSError, TypeError, ValueError):
            revisions = self._rebuild_census_catalog_locked()
            runs = self._read_census_run_manifests()
            revisions = self._read_census_catalog(runs)
        return runs, revisions

    def ensure_census_catalog(self) -> tuple[RevisionRef, ...]:
        with capture_write_lock(self.paths):
            self._ensure_layout_locked()
            _runs, revisions = self._ensure_census_catalog_locked()
            return revisions

    def rebuild_census_catalog(self) -> tuple[RevisionRef, ...]:
        """Validate all cold Census evidence and publish one canonical catalog."""

        with capture_write_lock(self.paths):
            self._ensure_layout_locked()
            return self._rebuild_census_catalog_locked()

    def frozen_revisions(
        self, *, binding: SourceBindingKey | None = None
    ) -> tuple[RevisionRef, ...]:
        with capture_write_lock(self.paths):
            self._ensure_layout_locked()
            _runs, revisions = self._ensure_census_catalog_locked()
            if binding is None:
                return revisions
            return tuple(
                item
                for item in revisions
                if item.key.adapter_id == binding.adapter_id
                and item.key.source_root_id == binding.source_root_id
            )

    def _frozen_revisions_read_only(
        self, *, binding: SourceBindingKey | None = None
    ) -> tuple[RevisionRef, ...]:
        """Read canonical truth without mutation when the caller owns consistency."""

        from agc_runtime.capture_ledger import same_revision_metadata

        try:
            revisions = self._read_census_catalog(
                self._read_census_run_manifests()
            )
        except (FileNotFoundError, OSError, TypeError, ValueError):
            _runs, records = self._read_cold_census_truth(binding=binding)
            unique: dict[CaptureKey, RevisionRef] = {}
            for revision in records:
                current = unique.get(revision.key)
                if current is not None and not same_revision_metadata(
                    current, revision
                ):
                    raise ValueError("revision_metadata_conflict")
                unique.setdefault(revision.key, revision)
            revisions = tuple(
                sorted(unique.values(), key=self._revision_sort_key)
            )
        if binding is None:
            return revisions
        return tuple(
            item
            for item in revisions
            if item.key.adapter_id == binding.adapter_id
            and item.key.source_root_id == binding.source_root_id
        )

    def _read_receipt(self, receipt_id: str) -> CaptureReceipt:
        return CaptureReceipt.from_mapping(read_json(self._receipt_path(receipt_id)))

    def read_receipt(self, receipt_id: str) -> CaptureReceipt:
        return self._read_receipt(receipt_id)

    def freeze_census(
        self,
        *,
        binding: SourceBindingKey,
        window: TimeWindow,
        started_at: str,
        revisions: Sequence[RevisionRef],
        source_quarantine_count: int = 0,
    ) -> CensusRun:
        """Durably freeze a content-free Census before Receipt accounting."""

        from agc_runtime.capture_ledger import canonical_census_id, same_revision_metadata
        from agc_runtime.capture_source import CensusRun, SourceBindingKey, TimeWindow

        binding = SourceBindingKey.from_mapping(binding.to_mapping())
        window = TimeWindow.from_mapping(window.to_mapping())
        run_start = _parse_utc(started_at)
        if (
            _parse_utc(window.end_at) != run_start
            or _parse_utc(window.start_at) != run_start - timedelta(days=7)
        ):
            raise ValueError("census must use the exact seven-day run window")
        validated = tuple(
            sorted(
                (RevisionRef.from_mapping(item.to_mapping()) for item in revisions),
                key=self._revision_sort_key,
            )
        )
        if any(
            item.key.adapter_id != binding.adapter_id
            or item.key.source_root_id != binding.source_root_id
            for item in validated
        ):
            raise ValueError("census revision does not match binding")
        if source_quarantine_count < 0:
            raise ValueError("source_quarantine_count must not be negative")
        census_id = canonical_census_id(binding, window, started_at)
        with capture_write_lock(self.paths):
            self._ensure_layout_locked()
            prior_runs = self._read_census_run_manifests()
            try:
                prior_revisions: tuple[RevisionRef, ...] | None = (
                    self._read_census_catalog(prior_runs)
                )
            except (FileNotFoundError, OSError, TypeError, ValueError):
                prior_revisions = None
            run_path = self._census_run_path(census_id)
            if run_path.exists():
                current, current_revisions = self._read_frozen_run(run_path)
                exact_membership = (
                    len(current_revisions) == len(validated)
                    and all(
                        same_revision_metadata(left, right)
                        for left, right in zip(current_revisions, validated)
                    )
                )
                if (
                    not exact_membership
                    or current.binding != binding
                    or current.window != window
                    or current.started_at != started_at
                    or current.source_quarantine_count != source_quarantine_count
                ):
                    raise ValueError("census_run_conflict")
                return current
            census = CensusRun.from_mapping(
                {
                    "schema_version": CAPTURE_SCHEMA_VERSION,
                    "census_id": census_id,
                    "binding": binding.to_mapping(),
                    "window": window.to_mapping(),
                    "started_at": started_at,
                    "frozen_at": self._clock(),
                    "revision_keys": [item.key.to_mapping() for item in validated],
                    "source_quarantine_count": source_quarantine_count,
                }
            )
            files: dict[str, dict[str, object]] = {"run.json": census.to_mapping()}
            files.update(
                {
                    f"members/{receipt_id_for(item.key)}.json": item.to_mapping()
                    for item in validated
                }
            )
            atomic_install_json_directory(run_path, files, directories=("members",))
            if prior_revisions is None:
                safe_unlink(self.capture.census_catalog / "active.json")
                self._rebuild_census_catalog_locked()
            else:
                unique = {item.key: item for item in prior_revisions}
                conflict = False
                for item in validated:
                    current = unique.get(item.key)
                    if current is not None and not same_revision_metadata(current, item):
                        conflict = True
                        break
                    unique.setdefault(item.key, item)
                if not conflict:
                    self._publish_census_catalog_locked(
                        self._read_census_run_manifests(),
                        tuple(unique.values()),
                    )
                else:
                    safe_unlink(self.capture.census_catalog / "active.json")
            return census

    def load_scan_state(
        self, *, binding: SourceBindingKey, lookback_started_at: str
    ) -> ScanState:
        from agc_runtime.capture_source import ScanState, SourceBindingKey

        binding = SourceBindingKey.from_mapping(binding.to_mapping())
        path = self._scan_state_path(binding)
        if path.exists():
            state = ScanState.from_mapping(read_json(path))
            if state.binding != binding:
                raise ValueError("scan state binding mismatch")
            return state
        return ScanState.from_mapping(
            {
                "schema_version": CAPTURE_SCHEMA_VERSION,
                "binding": binding.to_mapping(),
                "state_version": 1,
                "hint": None,
                "last_scan_at": None,
                "lookback_started_at": lookback_started_at,
            }
        )

    def advance_scan_state(
        self,
        *,
        binding: SourceBindingKey,
        expected_version: int,
        hint: ScanHint | None,
        last_scan_at: str,
        lookback_started_at: str,
    ) -> ScanState:
        from agc_runtime.capture_source import ScanState, SourceBindingKey

        binding = SourceBindingKey.from_mapping(binding.to_mapping())
        try:
            desired = ScanState.from_mapping(
                {
                    "schema_version": CAPTURE_SCHEMA_VERSION,
                    "binding": binding.to_mapping(),
                    "state_version": expected_version + 1,
                    "hint": hint.to_mapping() if hint else None,
                    "last_scan_at": last_scan_at,
                    "lookback_started_at": lookback_started_at,
                }
            )
        except ValueError as error:
            if "SourceBindingKey" in str(error):
                raise ValueError("scan state binding mismatch") from error
            raise
        with capture_write_lock(self.paths):
            self._ensure_layout_locked()
            path = self._scan_state_path(binding)
            current_version = 1
            if path.exists():
                current = ScanState.from_mapping(read_json(path))
                if current.binding != binding:
                    raise ValueError("scan state binding mismatch")
                current_version = current.state_version
            if current_version != expected_version:
                raise ValueError("scan_state_conflict")
            atomic_write_json(path, desired.to_mapping())
        return desired

    def ready_revisions(self) -> tuple[CaptureReceipt, ...]:
        ready = {"discovered", "queued", "retryable"}
        return tuple(
            sorted(
                (item for item in self.iter_receipts() if item.status in ready),
                key=lambda item: item.receipt_id,
            )
        )

    def is_key_accounted(self, key: CaptureKey) -> bool:
        key = CaptureKey.from_mapping(key.to_mapping())
        return self._is_accounted(key, revision=None)

    def is_revision_accounted(self, revision: RevisionRef) -> bool:
        """Require Receipt/Ledger accounting to agree with frozen Revision truth."""

        revision = RevisionRef.from_mapping(revision.to_mapping())
        return self._is_accounted(revision.key, revision=revision)

    def _is_accounted(
        self, key: CaptureKey, *, revision: RevisionRef | None
    ) -> bool:
        receipt = self._receipt_path(receipt_id_for(key))
        tombstone = self._path(self.capture.tombstones, tombstone_id_for(key), _CAPTURE_ID)
        if tombstone.exists():
            try:
                return (
                    CaptureSuppressionTombstone.from_mapping(read_json(tombstone)).capture_key
                    == key
                )
            except (OSError, TypeError, ValueError):
                return False
        ledger = self._ledger_path(receipt_id_for(key))
        if not receipt.exists() or not ledger.exists():
            return False
        try:
            current = CaptureReceipt.from_mapping(read_json(receipt))
            entry = LedgerEntry.from_mapping(read_json(ledger))
            if revision is not None:
                from agc_runtime.capture_ledger import validate_receipt_revision_truth

                validate_receipt_revision_truth(current, revision)
        except (OSError, TypeError, ValueError):
            return False
        return (
            current.key == key
            and entry.capture_key == key
            and entry.receipt_id == current.receipt_id
            and entry.status == current.status
        )

    def record_source_quarantine(
        self, binding: SourceBindingKey, *, created_at: str, code: str
    ) -> SourceQuarantine:
        from agc_runtime.capture_ledger import source_quarantine_for
        from agc_runtime.capture_source import SourceBindingKey

        binding = SourceBindingKey.from_mapping(binding.to_mapping())
        quarantine = source_quarantine_for(binding, created_at=created_at, code=code)
        with capture_write_lock(self.paths):
            self._ensure_layout_locked()
            path = self.capture.quarantines / f"source-{self._binding_digest(binding)}.json"
            if path.exists():
                try:
                    existing = SourceQuarantine.from_mapping(read_json(path))
                except (OSError, TypeError, ValueError) as error:
                    raise ValueError("invalid_source_quarantine") from error
                if (
                    existing.adapter_id != quarantine.adapter_id
                    or existing.source_root_id != quarantine.source_root_id
                ):
                    raise ValueError("source_quarantine_binding_conflict")
                if existing.code == quarantine.code:
                    return existing
            atomic_write_json(path, quarantine.to_mapping())
        return quarantine

    def iter_source_quarantines(self) -> tuple[SourceQuarantine, ...]:
        if not self.capture.quarantines.exists():
            return ()
        items: list[SourceQuarantine] = []
        for path in sorted(self.capture.quarantines.glob("source-*.json")):
            try:
                items.append(SourceQuarantine.from_mapping(read_json(path)))
            except (OSError, TypeError, ValueError):
                continue
        return tuple(items)

    def source_quarantine_count(self) -> int:
        return len(self.iter_source_quarantines())

    def register_quarantined_revision(
        self, revision: RevisionRef, *, discovered_at: str, code: str
    ) -> CaptureReceipt:
        from agc_runtime.capture_ledger import (
            quarantined_receipt,
            receipt_for_revision,
            validate_receipt_revision_truth,
        )

        revision = RevisionRef.from_mapping(revision.to_mapping())
        receipt_id = receipt_id_for(revision.key)
        with capture_write_lock(self.paths):
            self._ensure_layout_locked()
            target = self._receipt_path(receipt_id)
            if target.exists():
                current = self._read_receipt(receipt_id)
                validate_receipt_revision_truth(current, revision)
                if current.status == "quarantined":
                    return current
                try:
                    validate_capture_transition(current.status, "quarantined")
                except ValueError:
                    return current
                receipt = quarantined_receipt(
                    current, updated_at=discovered_at, code=code
                )
            else:
                receipt = receipt_for_revision(
                    revision,
                    discovered_at=discovered_at,
                    status="quarantined",
                    error_code=code,
                )
            self._write_receipt(receipt)
            self._write_ledger(receipt, status="quarantined", processed_at=None)
            self._write_source_conflict(receipt.key, discovered_at)
            return receipt

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
        with self._capture_read_lock():
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
            receipts_by_id: dict[str, CaptureReceipt] = {}
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
                receipts_by_id[receipt.receipt_id] = receipt
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

            ledgers_by_id: dict[str, LedgerEntry] = {}
            valid_ledger_receipt_ids: set[str] = set()
            for path in json_objects(self.capture.ledger, "invalid_ledger", "ledger"):
                try:
                    if not _RECEIPT_ID.fullmatch(path.stem):
                        raise ValueError
                    entry = LedgerEntry.from_mapping(read_json(path))
                    if entry.receipt_id != path.stem or entry.receipt_id in ledgers_by_id:
                        raise ValueError
                    ledgers_by_id[entry.receipt_id] = entry
                except (OSError, TypeError, ValueError):
                    degraded("invalid_ledger", "ledger")

            for receipt_id, receipt in receipts_by_id.items():
                entry = ledgers_by_id.get(receipt_id)
                if entry is None:
                    degraded("missing_ledger", "ledger")
                    continue
                expected_processed_at = (
                    receipt.updated_at if receipt.status == "complete" else None
                )
                if (
                    entry.capture_key != receipt.key
                    or entry.status != receipt.status
                    or entry.discovered_at != receipt.discovered_at
                    or entry.processed_at != expected_processed_at
                ):
                    degraded("ledger_receipt_mismatch", "ledger")
                else:
                    valid_ledger_receipt_ids.add(receipt_id)
            for receipt_id in set(ledgers_by_id) - set(receipts_by_id):
                degraded("orphan_ledger", "ledger")

            for receipt_id in set(manifests) - visible_receipt_ids:
                degraded("orphan_manifest", "manifest")

            for observation_id in set(observations_by_id) - referenced_observation_ids:
                degraded("orphan_observation", "observation")

            census: list[RevisionRef] = []
            census_keys: set[tuple[str, str, str, str]] = set()
            census_runs: list[CensusRun] = []
            try:
                catalog_runs, catalog_revisions = self._ensure_census_catalog_locked()
                census_runs.extend(catalog_runs)
                for revision in catalog_revisions:
                    key = revision.key
                    key_id = (
                        key.adapter_id,
                        key.source_root_id,
                        key.task_id,
                        key.revision_id,
                    )
                    if key_id in census_keys:
                        degraded("duplicate_capture_key", "census")
                        continue
                    census_keys.add(key_id)
                    census.append(revision)
            except ValueError as error:
                if str(error) == "revision_metadata_conflict":
                    from agc_runtime.capture_ledger import same_revision_metadata

                    cold_runs, cold_records = self._read_cold_census_truth()
                    census_runs.extend(cold_runs)
                    frozen_by_key: dict[
                        tuple[str, str, str, str], RevisionRef
                    ] = {}
                    for revision in cold_records:
                        key = revision.key
                        key_id = (
                            key.adapter_id,
                            key.source_root_id,
                            key.task_id,
                            key.revision_id,
                        )
                        current = frozen_by_key.get(key_id)
                        if current is not None:
                            if not same_revision_metadata(current, revision):
                                degraded("conflicting_census_revision", "census")
                            continue
                        frozen_by_key[key_id] = revision
                        census_keys.add(key_id)
                        census.append(revision)
                else:
                    degraded("invalid_frozen_census", "census")
            except (OSError, TypeError):
                degraded("invalid_frozen_census", "census")

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

            accounted_keys = {item.capture_key for item in tombstones}
            if census:
                from agc_runtime.capture_ledger import validate_receipt_revision_truth

                for revision in census:
                    if revision.key in accounted_keys:
                        continue
                    receipt_id = receipt_id_for(revision.key)
                    receipt = receipts_by_id.get(receipt_id)
                    if receipt is None or receipt_id not in valid_ledger_receipt_ids:
                        continue
                    try:
                        validate_receipt_revision_truth(receipt, revision)
                    except (TypeError, ValueError):
                        continue
                    accounted_keys.add(revision.key)

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
            conflict_digests: set[str] = set()
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
                    conflict_digests.add(path.stem.removeprefix("source-"))

            scan_states: list[ScanState] = []
            scan_state_paths = json_objects(
                self.capture.scan_state, "invalid_scan_state", "scan_state"
            )
            if scan_state_paths:
                from agc_runtime.capture_source import ScanState
            for path in scan_state_paths:
                try:
                    state = ScanState.from_mapping(read_json(path))
                    if path.name != f"state-{self._binding_digest(state.binding)}.json":
                        raise ValueError
                    scan_states.append(state)
                except (OSError, TypeError, ValueError):
                    degraded("invalid_scan_state", "scan_state")

            dirty_markers: list[DirtyMarker] = []
            dirty_paths = json_objects(
                self.capture.dirty, "invalid_dirty_marker", "dirty_marker"
            )
            if dirty_paths:
                from agc_runtime.capture_source import DirtyMarker
            for path in dirty_paths:
                try:
                    dirty_markers.append(DirtyMarker.from_mapping(read_json(path)))
                except (OSError, TypeError, ValueError):
                    degraded("invalid_dirty_marker", "dirty_marker")

            review_receipts: list[CaptureReviewReceipt] = []
            visible_observation_ids = {item.observation_id for item in visible}
            for path in json_objects(
                self.capture.reviews,
                "invalid_review_receipt",
                "review_receipt",
            ):
                try:
                    if not _OBSERVATION_ID.fullmatch(path.stem):
                        raise ValueError
                    review = CaptureReviewReceipt.from_mapping(read_json(path))
                    if (
                        review.observation_id != path.stem
                        or review.observation_id not in visible_observation_ids
                    ):
                        raise ValueError
                    review_receipts.append(review)
                except (OSError, TypeError, ValueError):
                    degraded("invalid_review_receipt", "review_receipt")
                    if _OBSERVATION_ID.fullmatch(path.stem):
                        unavailable_ids.add(path.stem)

            return CaptureSnapshot(
                receipts=tuple(receipts),
                observations=tuple(visible),
                review_receipts=tuple(review_receipts),
                census=tuple(census),
                tombstones=tuple(tombstones),
                source_quarantines=tuple(quarantines),
                source_conflict_count=conflict_count,
                census_runs=tuple(census_runs),
                scan_states=tuple(scan_states),
                dirty_markers=tuple(dirty_markers),
                source_conflict_digests=frozenset(conflict_digests),
                accounted_keys=frozenset(accounted_keys),
                diagnostics=tuple(diagnostics),
                unavailable_ids=frozenset(unavailable_ids),
            )

    def _validate_review_batch_locked(
        self,
        observation_ids: Sequence[str],
        *,
        outcome: str,
        target_memory_id: str | None,
    ) -> tuple[str, ...]:
        ids = tuple(observation_ids)
        candidate = CaptureReviewReceipt.from_mapping(
            {
                "schema_version": 1,
                "observation_id": ids[0],
                "outcome": outcome,
                "target_memory_id": target_memory_id,
                "reviewed_at": self._clock(),
            }
        )
        for observation_id in ids:
            observation = CollectedObservation.from_mapping(
                read_json(self._observation_path(observation_id))
            )
            receipt = self._read_receipt(observation.receipt_id)
            if (
                receipt.status != "complete"
                or observation_id not in self._read_manifest(receipt.receipt_id)
            ):
                raise ValueError("review observation is not visible")
            path = self._review_path(observation_id)
            if path.exists():
                current = CaptureReviewReceipt.from_mapping(read_json(path))
                if current.observation_id != observation_id:
                    raise ValueError("review receipt filename binding mismatch")
                if (current.outcome, current.target_memory_id) != (
                    candidate.outcome,
                    candidate.target_memory_id,
                ):
                    raise ValueError("review receipt conflicts with terminal outcome")
        return ids

    def validate_review_batch(
        self,
        observation_ids: Sequence[str],
        *,
        outcome: str,
        target_memory_id: str | None,
    ) -> None:
        ids = parse_capture_observation_ids(list(observation_ids))
        with capture_write_lock(self.paths):
            self._ensure_layout_locked()
            self._validate_review_batch_locked(
                ids,
                outcome=outcome,
                target_memory_id=target_memory_id,
            )

    def record_reviews(
        self,
        observation_ids: Sequence[str],
        *,
        outcome: str,
        target_memory_id: str | None,
        reviewed_at: str | None = None,
    ) -> int:
        ids = parse_capture_observation_ids(list(observation_ids))
        timestamp = reviewed_at or self._clock()
        created = 0
        with capture_write_lock(self.paths):
            self._ensure_layout_locked()
            self._validate_review_batch_locked(
                ids,
                outcome=outcome,
                target_memory_id=target_memory_id,
            )
            for observation_id in ids:
                path = self._review_path(observation_id)
                receipt = CaptureReviewReceipt.from_mapping(
                    {
                        "schema_version": 1,
                        "observation_id": observation_id,
                        "outcome": outcome,
                        "target_memory_id": target_memory_id,
                        "reviewed_at": timestamp,
                    }
                )
                if not path.exists():
                    atomic_write_json(path, receipt.to_mapping())
                    created += 1
        return created

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

    def register_census_receipt(
        self, receipt: CaptureReceipt, *, revision: RevisionRef
    ) -> ReconcileResult:
        """Register a metadata-only discovered or explicitly excluded Receipt."""

        from agc_runtime.capture_ledger import validate_receipt_revision_truth

        revision = RevisionRef.from_mapping(revision.to_mapping())
        receipt = validate_receipt_revision_truth(
            receipt, revision, require_census_only=True
        )
        if receipt.status not in {"discovered", "excluded"}:
            raise ValueError("census receipt must be discovered or excluded")
        return self._register_receipt(receipt, revision=revision)

    def register_extraction(self, receipt: CaptureReceipt) -> ReconcileResult:
        receipt.to_mapping()
        if receipt.status not in {"discovered", "queued", "extracting"}:
            raise ValueError("discovery receipt must be non-terminal")
        return self._register_receipt(receipt)

    def _register_receipt(
        self, receipt: CaptureReceipt, *, revision: RevisionRef | None = None
    ) -> ReconcileResult:
        with capture_write_lock(self.paths):
            self._ensure_layout_locked()
            tombstone_path = self._path(
                self.capture.tombstones,
                tombstone_id_for(receipt.key),
                _CAPTURE_ID,
            )
            if tombstone_path.exists():
                tombstone = CaptureSuppressionTombstone.from_mapping(
                    read_json(tombstone_path)
                )
                if tombstone.capture_key == receipt.key:
                    return ReconcileResult("suppressed", False, receipt.receipt_id)
                raise ValueError("Capture suppression tombstone binding is invalid")
            target = self._receipt_path(receipt.receipt_id)
            if not target.exists():
                self._write_receipt(receipt)
                self._point("after:discovery:receipt")
                self._write_ledger(receipt, status=receipt.status, processed_at=None)
                return ReconcileResult(receipt.status, True, receipt.receipt_id)
            current = self._read_receipt(receipt.receipt_id)
            if revision is not None:
                from agc_runtime.capture_ledger import validate_receipt_revision_truth

                validate_receipt_revision_truth(current, revision)
            if receipt.status == "excluded" and current.status != "excluded":
                validate_capture_transition(current.status, "excluded")
                excluded = replace(
                    current,
                    status="excluded",
                    updated_at=receipt.updated_at,
                    next_retry_at=None,
                    sanitized_error=None,
                    exclusion_reason=receipt.exclusion_reason,
                )
                self._write_receipt(excluded)
                self._write_ledger(excluded, status="excluded", processed_at=None)
                return ReconcileResult("excluded", False, excluded.receipt_id)
            if current.source_hash_schema_version != receipt.source_hash_schema_version:
                return ReconcileResult(current.status, False, current.receipt_id)
            if current.source_fingerprint == receipt.source_fingerprint:
                if current.status == "complete" and not self._manifest_valid(current):
                    raise ValueError("complete receipt has no valid immutable manifest")
                ledger_path = self._ledger_path(current.receipt_id)
                repair_ledger = not ledger_path.exists()
                if not repair_ledger:
                    try:
                        ledger = LedgerEntry.from_mapping(read_json(ledger_path))
                        repair_ledger = (
                            ledger.capture_key != current.key
                            or ledger.receipt_id != current.receipt_id
                            or ledger.status != current.status
                        )
                    except (OSError, TypeError, ValueError):
                        repair_ledger = True
                if repair_ledger:
                    self._write_ledger(
                        current,
                        status=current.status,
                        processed_at=(
                            current.updated_at if current.status == "complete" else None
                        ),
                    )
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
        conflict = (self.capture.conflicts / f"source-{digest}.json").exists()
        quarantined = any(
            item.adapter_id == adapter_id and item.source_root_id == source_root_id
            for item in self.iter_source_quarantines()
        )
        return "degraded" if conflict or quarantined else "healthy"

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

    def release_lease(self, lease: CaptureLease) -> None:
        """Release only the exact current lease while preserving its epoch fence."""

        with capture_write_lock(self.paths):
            self._ensure_layout_locked()
            self._assert_lease(lease)
            safe_unlink(self._lease_path(receipt_id_for(lease.capture_key)))

    def begin_extraction(
        self,
        lease: CaptureLease,
        capsule_result: object,
        extractor_descriptor: object,
        *,
        now: str,
    ) -> CaptureReceipt:
        from agc_runtime.capture_capsule import CapsuleResult
        from agc_runtime.capture_extractor import ExtractorDescriptor

        if not isinstance(capsule_result, CapsuleResult) or not isinstance(
            extractor_descriptor, ExtractorDescriptor
        ):
            raise ValueError("capture_runner_contract_invalid")
        descriptor = ExtractorDescriptor.from_mapping(
            extractor_descriptor.to_mapping()
        )
        with capture_write_lock(self.paths):
            self._ensure_layout_locked()
            self._assert_lease(lease)
            current = self._read_receipt(receipt_id_for(lease.capture_key))
            if current.status not in {"discovered", "queued", "retryable"}:
                raise ValueError("receipt is not ready for extraction")
            if current.status == "discovered":
                validate_capture_transition("discovered", "queued")
            elif current.status == "retryable":
                validate_capture_transition("retryable", "queued")
            validate_capture_transition("queued", "extracting")
            updated = replace(
                current,
                status="extracting",
                updated_at=now,
                attempt_count=current.attempt_count + 1,
                next_retry_at=None,
                source_fingerprint=capsule_result.source_fingerprint,
                source_hash_schema_version=capsule_result.source_hash_schema_version,
                capsule_hash=capsule_result.capsule_hash,
                capsule_schema_version=capsule_result.capsule_schema_version,
                extractor_id=descriptor.extractor_id,
                extractor_version=descriptor.extractor_version,
                extractor_schema_version=descriptor.extractor_schema_version,
                taxonomy_version=descriptor.taxonomy_version,
                sanitized_error=None,
            )
            updated = CaptureReceipt.from_mapping(updated.to_mapping())
            self._write_receipt(updated)
            self._write_ledger(updated, status="extracting", processed_at=None)
            return updated

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

    def commit_extraction(
        self,
        lease: CaptureLease,
        observations: Sequence[CollectedObservation],
        terminal_receipt: CaptureReceipt,
        *,
        reservation: TokenReservation | None = None,
        settlement: BudgetSettlement | None = None,
    ) -> CommitResult:
        if (reservation is None) != (settlement is None):
            raise ValueError("budget reservation and settlement must be provided together")
        if reservation is not None and settlement is not None:
            reservation = TokenReservation.from_mapping(reservation.to_mapping())
            settlement = BudgetSettlement.from_mapping(settlement.to_mapping())
            if (
                reservation.capture_key != lease.capture_key
                or settlement.capture_key != lease.capture_key
                or settlement.reservation_id != reservation.reservation_id
                or terminal_receipt.token_usage != settlement.charged_usage
                or terminal_receipt.usage_quality != settlement.usage_quality
            ):
                raise ValueError("capture_budget_conflict")
        with capture_write_lock(self.paths):
            self._ensure_layout_locked()
            self._assert_lease(lease)
            current = self._read_receipt(receipt_id_for(lease.capture_key))
            terminal_receipt.to_mapping()
            if current.key != lease.capture_key or terminal_receipt.key != lease.capture_key or terminal_receipt.receipt_id != current.receipt_id or terminal_receipt.status != "complete":
                raise ValueError("terminal receipt must be complete for the leased key")
            immutable = ("adapter_version", "source_schema_version", "identity_quality", "source_fingerprint", "source_hash_schema_version", "capsule_hash", "capsule_schema_version", "settled_at", "discovered_at", "attempt_count", "extractor_id", "extractor_version", "extractor_schema_version", "taxonomy_version", "redacted_by_forget", "forgotten_observation_count")
            if any(getattr(current, field) != getattr(terminal_receipt, field) for field in immutable):
                raise ValueError("terminal receipt changes bound receipt metadata")
            if reservation is None and current.usage_quality != terminal_receipt.usage_quality:
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
            if reservation is not None and settlement is not None:
                from agc_runtime.capture_budget import persist_settlement_locked

                self._point("before:budget:settlement")
                persist_settlement_locked(self.paths, reservation, settlement)
                self._point("after:budget:settlement")
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

    def transition_with_settlement(
        self,
        lease: CaptureLease,
        *,
        expected: frozenset[str],
        target: str,
        patch: ReceiptTransitionPatch,
        reservation: TokenReservation,
        settlement: BudgetSettlement,
    ) -> CaptureReceipt:
        from agc_runtime.capture_budget import persist_settlement_locked

        if not isinstance(patch, ReceiptTransitionPatch):
            raise ValueError("transition patch must be strict")
        if patch.source_fingerprint is not None:
            raise ValueError("transition patch cannot change immutable metadata")
        reservation = TokenReservation.from_mapping(reservation.to_mapping())
        settlement = BudgetSettlement.from_mapping(settlement.to_mapping())
        if (
            reservation.capture_key != lease.capture_key
            or settlement.capture_key != lease.capture_key
            or settlement.reservation_id != reservation.reservation_id
        ):
            raise ValueError("capture_budget_conflict")
        with capture_write_lock(self.paths):
            self._ensure_layout_locked()
            self._assert_lease(lease)
            current = self._read_receipt(receipt_id_for(lease.capture_key))
            if current.status not in expected:
                raise ValueError("receipt status does not match expected set")
            validate_capture_transition(
                current.status, target, reopen_reason=patch.reopen_reason
            )
            self._point("before:budget:settlement")
            persist_settlement_locked(self.paths, reservation, settlement)
            self._point("after:budget:settlement")
            updated = replace(
                current,
                status=target,
                updated_at=patch.updated_at or self._clock(),
                next_retry_at=patch.next_retry_at,
                sanitized_error=patch.sanitized_error,
                token_usage=settlement.charged_usage,
                usage_quality=settlement.usage_quality,
            )
            updated = CaptureReceipt.from_mapping(updated.to_mapping())
            transition_journal = {
                "schema_version": CAPTURE_SCHEMA_VERSION,
                "operation": "transition",
                "receipt_id": current.receipt_id,
                "expected_status": current.status,
                "target_status": target,
            }
            atomic_write_json(
                self._transition_journal_path(current.receipt_id), transition_journal
            )
            self._write_receipt(updated)
            self._write_ledger(updated, status=target, processed_at=None)
            safe_unlink(self._transition_journal_path(current.receipt_id))
            return updated

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
