"""Library-only, census-safe reconciliation for explicitly configured sources."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
from typing import Iterable

from agc_runtime.capture_contracts import CaptureKey, RevisionRef
from agc_runtime.capture_ledger import receipt_for_revision, same_revision_metadata
from agc_runtime.capture_source import (
    AdapterDescriptor,
    DirtyMarker,
    DiscoveryBatch,
    SourceAdapter,
    SourceBindingKey,
    TimeWindow,
)
from agc_runtime.capture_store import CaptureStore
from agc_runtime.capture_transaction import read_json, safe_unlink


def _utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


@dataclass(frozen=True)
class ScanReport:
    window: TimeWindow
    known_key_count: int
    accounted_key_count: int
    silent_loss_count: int
    pending_key_count: int
    created_receipt_count: int
    replay_count: int
    source_quarantine_count: int
    source_health: str
    acknowledged_marker_count: int
    advanced_hint_count: int


class CaptureScanner:
    """Reconcile only adapters passed explicitly by the caller."""

    def __init__(
        self,
        store: CaptureStore,
        adapters: Iterable[SourceAdapter],
        *,
        excluded_keys: Iterable[CaptureKey] = (),
        excluded_task_ids: Iterable[str] = (),
    ) -> None:
        self.store = store
        unique: dict[tuple[str, str], tuple[AdapterDescriptor, SourceAdapter]] = {}
        for adapter in tuple(adapters):
            descriptor = AdapterDescriptor.from_mapping(adapter.describe().to_mapping())
            binding = (descriptor.adapter_id, descriptor.source_root_id)
            unique.setdefault(binding, (descriptor, adapter))
        self._adapters = tuple(unique[key] for key in sorted(unique))
        self._excluded_keys = frozenset(
            CaptureKey.from_mapping(key.to_mapping()) for key in excluded_keys
        )
        task_ids = tuple(excluded_task_ids)
        if any(not isinstance(item, str) or not item for item in task_ids):
            raise ValueError("excluded_task_ids must contain non-empty strings")
        self._excluded_task_ids = frozenset(task_ids)

    def scan(self, *, run_started_at: str, force_full: bool = False) -> ScanReport:
        if not isinstance(force_full, bool):
            raise ValueError("force_full must be a boolean")
        started = _utc(run_started_at)
        if started.utcoffset() != timedelta(0):
            raise ValueError("run_started_at must be UTC")
        started_at = _timestamp(started)
        window = TimeWindow.from_mapping(
            {
                "schema_version": 1,
                "start_at": _timestamp(started - timedelta(days=7)),
                "end_at": started_at,
            }
        )

        self.store.recover_transactions(now=started_at)
        configured = {
            (descriptor.adapter_id, descriptor.source_root_id): descriptor
            for descriptor, _adapter in self._adapters
        }
        markers = self._dirty_markers(configured=configured, created_at=started_at)
        known: set[CaptureKey] = set()
        accounting_truth: dict[CaptureKey, RevisionRef] = {}
        resolved_marker_paths: set[Path] = set()
        created = replay = advanced = 0

        for descriptor, adapter in self._adapters:
            binding = SourceBindingKey.from_mapping(
                {
                    "schema_version": 1,
                    "adapter_id": descriptor.adapter_id,
                    "source_root_id": descriptor.source_root_id,
                }
            )
            state = self.store.load_scan_state(
                binding=binding, lookback_started_at=window.start_at
            )
            binding_markers = tuple(
                item
                for item in markers
                if item[1].adapter_id == binding.adapter_id
                and item[1].source_root_id == binding.source_root_id
            )
            raw_batch = adapter.discover(
                None if force_full or binding_markers else state.hint, window
            )
            batch = DiscoveryBatch.from_mapping(raw_batch.to_mapping())
            if batch.binding != binding or batch.window != window:
                raise ValueError("discovery batch binding or window mismatch")
            revisions = tuple(
                self._validate_revision(item, descriptor) for item in batch.revisions
            )
            binding_failed_closed = False

            try:
                self.store.freeze_census(
                    binding=binding,
                    window=window,
                    started_at=started_at,
                    revisions=revisions,
                    source_quarantine_count=len(batch.diagnostic_codes),
                )
            except ValueError as error:
                if str(error) != "census_run_conflict":
                    raise
                binding_failed_closed = True
                self.store.record_source_quarantine(
                    binding, created_at=started_at, code="census_run_conflict"
                )

            for code in batch.diagnostic_codes:
                self.store.record_source_quarantine(
                    binding, created_at=started_at, code=code
                )
            if batch.diagnostic_codes:
                binding_failed_closed = True
            durable = self.store.frozen_revision_records(binding=binding)
            by_key: dict[CaptureKey, list[RevisionRef]] = {}
            for revision in (*durable, *revisions):
                by_key.setdefault(revision.key, []).append(revision)
            conflict_keys = {
                key
                for key, items in by_key.items()
                if any(
                    not same_revision_metadata(items[0], candidate)
                    for candidate in items[1:]
                )
            }
            for key in conflict_keys:
                candidate = next(
                    (item for item in revisions if item.key == key), by_key[key][0]
                )
                try:
                    self.store.register_quarantined_revision(
                        candidate,
                        discovered_at=started_at,
                        code="revision_metadata_conflict",
                    )
                except ValueError as error:
                    if str(error) not in {
                        "receipt_revision_truth_conflict",
                        "untruthful_census_receipt",
                    }:
                        raise
                self.store.record_source_quarantine(
                    binding,
                    created_at=started_at,
                    code="revision_metadata_conflict",
                )
                binding_failed_closed = True

            binding_known = set(by_key)
            known.update(binding_known)
            for path, marker in binding_markers:
                if marker.key in binding_known:
                    resolved_marker_paths.add(path)
                else:
                    self.store.record_source_quarantine(
                        binding,
                        created_at=started_at,
                        code="dirty_revision_unresolved",
                    )
                    binding_failed_closed = True

            durable_by_key: dict[CaptureKey, list[RevisionRef]] = {}
            eligible_by_key: dict[CaptureKey, RevisionRef] = {}
            for revision in durable:
                durable_by_key.setdefault(revision.key, []).append(revision)
                eligible_by_key.setdefault(revision.key, revision)
            for revision in revisions:
                if not binding_failed_closed or any(
                    same_revision_metadata(revision, frozen)
                    for frozen in durable_by_key.get(revision.key, ())
                ):
                    eligible_by_key[revision.key] = revision
            accounting_truth.update(eligible_by_key)

            for revision in eligible_by_key.values():
                if revision.key in conflict_keys:
                    replay += 1
                    continue
                self.store._point("before:census:receipt")
                excluded = (
                    revision.key in self._excluded_keys
                    or revision.key.task_id in self._excluded_task_ids
                )
                try:
                    result = self.store.register_census_receipt(
                        receipt_for_revision(
                            revision,
                            discovered_at=started_at,
                            status="excluded" if excluded else "discovered",
                            exclusion_reason=(
                                "configured_task_exclusion" if excluded else None
                            ),
                        ),
                        revision=revision,
                    )
                except ValueError as error:
                    if str(error) not in {
                        "receipt_revision_truth_conflict",
                        "untruthful_census_receipt",
                    }:
                        raise
                    self.store.record_source_quarantine(
                        binding,
                        created_at=started_at,
                        code="receipt_revision_truth_conflict",
                    )
                    binding_failed_closed = True
                    replay += 1
                    continue
                self.store._point("after:census:receipt")
                if result.created:
                    created += 1
                else:
                    replay += 1

            if (
                not binding_failed_closed
                and all(
                    self.store.is_revision_accounted(accounting_truth[key])
                    for key in binding_known
                )
            ):
                try:
                    self.store.advance_scan_state(
                        binding=binding,
                        expected_version=state.state_version,
                        hint=batch.next_hint,
                        last_scan_at=started_at,
                        lookback_started_at=window.start_at,
                    )
                except ValueError as error:
                    if str(error) != "scan_state_conflict":
                        raise
                else:
                    advanced += 1

        acknowledged = 0
        for path, marker in markers:
            if (
                path in resolved_marker_paths
                and marker.key in accounting_truth
                and self.store.is_revision_accounted(accounting_truth[marker.key])
            ):
                safe_unlink(path)
                acknowledged += 1

        accounted = sum(
            key in accounting_truth
            and self.store.is_revision_accounted(accounting_truth[key])
            for key in known
        )
        quarantines = self.store.source_quarantine_count()
        source_health = (
            "degraded"
            if quarantines > 0
            or any(
                self.store.source_health(item.adapter_id, item.source_root_id)
                == "degraded"
                for item in (descriptor for descriptor, _adapter in self._adapters)
            )
            else "healthy"
        )
        return ScanReport(
            window=window,
            known_key_count=len(known),
            accounted_key_count=accounted,
            silent_loss_count=len(known) - accounted,
            pending_key_count=len(known) - accounted,
            created_receipt_count=created,
            replay_count=replay,
            source_quarantine_count=quarantines,
            source_health=source_health,
            acknowledged_marker_count=acknowledged,
            advanced_hint_count=advanced,
        )

    @staticmethod
    def _validate_revision(
        revision: RevisionRef, descriptor: AdapterDescriptor
    ) -> RevisionRef:
        validated = RevisionRef.from_mapping(revision.to_mapping())
        if (
            validated.key.adapter_id != descriptor.adapter_id
            or validated.key.source_root_id != descriptor.source_root_id
            or validated.adapter_version != descriptor.adapter_version
            or validated.source_schema_version != descriptor.source_schema_version
        ):
            raise ValueError("revision does not match configured source adapter")
        return validated

    def _dirty_markers(
        self,
        *,
        configured: dict[tuple[str, str], AdapterDescriptor],
        created_at: str,
    ) -> tuple[tuple[Path, DirtyMarker], ...]:
        dirty = self.store.paths.capture.dirty
        if not dirty.exists():
            return ()
        markers: list[tuple[Path, DirtyMarker]] = []
        for path in sorted(dirty.glob("*.json")):
            try:
                marker = DirtyMarker.from_mapping(read_json(path))
            except (OSError, TypeError, ValueError):
                binding = SourceBindingKey.from_mapping(
                    {
                        "schema_version": 1,
                        "adapter_id": "unknown",
                        "source_root_id": hashlib.sha256(
                            f"invalid-dirty-marker\0{path.name}".encode("utf-8")
                        ).hexdigest(),
                    }
                )
                self.store.record_source_quarantine(
                    binding, created_at=created_at, code="invalid_dirty_marker"
                )
                continue
            descriptor = configured.get((marker.adapter_id, marker.source_root_id))
            marker_binding = SourceBindingKey.from_mapping(
                {
                    "schema_version": 1,
                    "adapter_id": marker.adapter_id,
                    "source_root_id": marker.source_root_id,
                }
            )
            if descriptor is None:
                self.store.record_source_quarantine(
                    marker_binding,
                    created_at=created_at,
                    code="unconfigured_dirty_binding",
                )
                continue
            if (
                marker.adapter_version != descriptor.adapter_version
                or marker.source_schema_version != descriptor.source_schema_version
            ):
                self.store.record_source_quarantine(
                    marker_binding,
                    created_at=created_at,
                    code="dirty_version_mismatch",
                )
                continue
            markers.append((path, marker))
        return tuple(markers)


__all__ = ["CaptureScanner", "ScanReport"]
