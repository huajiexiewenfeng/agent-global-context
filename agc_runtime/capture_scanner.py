"""Library-only, census-safe reconciliation for explicitly configured sources."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

from agc_runtime.capture_contracts import CaptureKey, RevisionRef
from agc_runtime.capture_ledger import receipt_for_revision
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
    created_receipt_count: int
    replay_count: int
    source_quarantine_count: int
    source_health: str
    acknowledged_marker_count: int
    advanced_hint_count: int


class CaptureScanner:
    """Reconcile only adapters passed explicitly by the caller."""

    def __init__(self, store: CaptureStore, adapters: Iterable[SourceAdapter]) -> None:
        self.store = store
        unique: dict[tuple[str, str], tuple[AdapterDescriptor, SourceAdapter]] = {}
        for adapter in tuple(adapters):
            descriptor = AdapterDescriptor.from_mapping(adapter.describe().to_mapping())
            binding = (descriptor.adapter_id, descriptor.source_root_id)
            unique.setdefault(binding, (descriptor, adapter))
        self._adapters = tuple(unique[key] for key in sorted(unique))

    def scan(self, *, run_started_at: str) -> ScanReport:
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
        markers = self._dirty_markers()
        known: set[CaptureKey] = set()
        created = replay = quarantines = advanced = 0

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
            raw_batch = adapter.discover(state.hint, window)
            batch = DiscoveryBatch.from_mapping(raw_batch.to_mapping())
            if batch.binding != binding or batch.window != window:
                raise ValueError("discovery batch binding or window mismatch")
            revisions = tuple(
                self._validate_revision(item, descriptor) for item in batch.revisions
            )
            known.update(item.key for item in revisions)

            try:
                self.store.freeze_census(
                    binding=binding,
                    window=window,
                    started_at=started_at,
                    revisions=revisions,
                    source_quarantine_count=len(batch.diagnostic_codes),
                )
            except ValueError as error:
                if str(error) != "revision_metadata_conflict":
                    raise
                for revision in revisions:
                    try:
                        self.store.freeze_census(
                            binding=binding,
                            window=window,
                            started_at=started_at,
                            revisions=(revision,),
                            source_quarantine_count=len(batch.diagnostic_codes),
                        )
                    except ValueError as item_error:
                        if str(item_error) != "revision_metadata_conflict":
                            raise
                        self.store.register_quarantined_revision(
                            revision,
                            discovered_at=started_at,
                            code="revision_metadata_conflict",
                        )
                        self.store.record_source_quarantine(
                            binding,
                            created_at=started_at,
                            code="revision_metadata_conflict",
                        )
                        quarantines += 1

            for code in batch.diagnostic_codes:
                self.store.record_source_quarantine(
                    binding, created_at=started_at, code=code
                )
            if batch.diagnostic_codes:
                quarantines += 1

            for revision in revisions:
                self.store._point("before:census:receipt")
                result = self.store.register_extraction(
                    receipt_for_revision(revision, discovered_at=started_at)
                )
                self.store._point("after:census:receipt")
                if result.created:
                    created += 1
                else:
                    replay += 1

            if all(self.store.is_key_accounted(item.key) for item in revisions):
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
            if self.store.is_key_accounted(marker.key):
                safe_unlink(path)
                acknowledged += 1

        accounted = sum(self.store.is_key_accounted(key) for key in known)
        source_health = (
            "degraded"
            if quarantines
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

    def _dirty_markers(self) -> tuple[tuple[Path, DirtyMarker], ...]:
        dirty = self.store.paths.capture.dirty
        if not dirty.exists():
            return ()
        markers: list[tuple[Path, DirtyMarker]] = []
        for path in sorted(dirty.glob("*.json")):
            try:
                marker = DirtyMarker.from_mapping(read_json(path))
            except (OSError, TypeError, ValueError):
                continue
            markers.append((path, marker))
        return tuple(markers)


__all__ = ["CaptureScanner", "ScanReport"]
