"""Library-only, census-safe reconciliation for explicitly configured sources."""

from __future__ import annotations

from dataclasses import dataclass
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
from typing import Iterable

from agc_runtime.capture_contracts import CaptureKey, RevisionRef, CaptureSuppressionTombstone, receipt_id_for
from agc_runtime.capture_ledger import receipt_for_revision, same_revision_metadata
from agc_runtime.capture_source import (
    AdapterDescriptor,
    DirtyMarker,
    DiscoveryBatch,
    ScanState,
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
        incremental: bool = False,
    ) -> None:
        if type(incremental) is not bool:
            raise ValueError("incremental must be a boolean")
        self.store = store
        self._incremental = incremental
        unique: dict[tuple[str, str], tuple[AdapterDescriptor, SourceAdapter]] = {}
        for adapter in tuple(adapters):
            descriptor = AdapterDescriptor.from_mapping(adapter.describe().to_mapping())
            configure_cache = getattr(adapter, "configure_metadata_cache", None)
            if callable(configure_cache):
                configure_cache(store.paths.capture.root / "source-cache")
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

        scheduling = None
        if self._incremental and not force_full:
            recovery = self.store.recover_active_transactions(now=started_at)
            if recovery.status == "capture_bootstrap_required":
                raise RuntimeError("capture_bootstrap_required")
            scheduling = self.store.read_background_scheduling_view(now=started_at)
        else:
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
        trusted_accounted = set(scheduling.accounted_receipt_ids) if scheduling else set()
        trusted_excluded = set(scheduling.excluded_receipt_ids) if scheduling else set()
        trusted_unresolved = {item.receipt_id: item for item in scheduling.receipts} if scheduling else {}
        suppressed_keys: set[CaptureKey] = set()
        if scheduling is not None:
            for path in sorted(self.store.capture.tombstones.glob("*.json")):
                tombstone = CaptureSuppressionTombstone.from_mapping(read_json(path))
                if path.stem != tombstone.tombstone_id:
                    raise RuntimeError("capture_bootstrap_required")
                suppressed_keys.add(tombstone.capture_key)

        def accounted(revision: RevisionRef) -> bool:
            if scheduling is None:
                return self.store.is_revision_accounted(revision)
            if revision.key in suppressed_keys:
                return self.store.is_revision_accounted(revision)
            return receipt_id_for(revision.key) in trusted_accounted or receipt_id_for(revision.key) in trusted_unresolved

        for descriptor, adapter in self._adapters:
            binding = SourceBindingKey.from_mapping(
                {
                    "schema_version": 1,
                    "adapter_id": descriptor.adapter_id,
                    "source_root_id": descriptor.source_root_id,
                }
            )
            invalid_state = False
            generation = self.store.source_scan_generation()
            try:
                state = self.store.load_scan_state(
                    binding=binding, lookback_started_at=window.start_at
                )
            except (OSError, ValueError, TypeError):
                # Scan state is derived. Preserve the suspect file for review,
                # but never let it suppress a source read or advance its CAS.
                invalid_state = True
                state = ScanState.from_mapping({
                    "schema_version": 1,
                    "binding": binding.to_mapping(),
                    "state_version": 1,
                    "hint": None,
                    "last_scan_at": None,
                    "lookback_started_at": window.start_at,
                })
                self.store.record_source_quarantine(
                    binding, created_at=started_at, code="invalid_scan_state"
                )
            binding_markers = tuple(
                item
                for item in markers
                if item[1].adapter_id == binding.adapter_id
                and item[1].source_root_id == binding.source_root_id
            )
            dirty_discover = getattr(adapter, "discover_with_dirty", None)
            if (
                not force_full and binding_markers and callable(dirty_discover)
                and all(marker.locator is not None for _path, marker in binding_markers)
            ):
                raw_batch = dirty_discover(
                    state.hint, window,
                    frozenset(marker.locator for _path, marker in binding_markers),
                )
            else:
                raw_batch = adapter.discover(
                    None if force_full or binding_markers else state.hint, window
                )
            batch = DiscoveryBatch.from_mapping(raw_batch.to_mapping())
            if batch.binding != binding or batch.window != window:
                raise ValueError("discovery batch binding or window mismatch")
            revisions = tuple(
                self._validate_revision(item, descriptor) for item in batch.revisions
            )
            binding_failed_closed = invalid_state

            try:
                frozen_run = self.store.freeze_census(
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

            for code in sorted(batch.diagnostic_codes)[-1:]:
                self.store.record_source_quarantine(
                    binding, created_at=started_at, code=code
                )
            if batch.diagnostic_codes:
                binding_failed_closed = True
            durable = (
                tuple(item for item in scheduling.revisions if item.key.adapter_id == binding.adapter_id
                      and item.key.source_root_id == binding.source_root_id)
                if scheduling is not None
                else self.store.frozen_revision_records(binding=binding)
            )
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

            with ExitStack() as registrations:
                for index, revision in enumerate(eligible_by_key.values()):
                    if index % 32 == 0:
                        registrations.close()
                        registrations.enter_context(self.store.registration_batch())
                    if revision.key in conflict_keys:
                        replay += 1
                        continue
                    self.store._point("before:census:receipt")
                    excluded = (
                        revision.key in self._excluded_keys
                        or revision.key.task_id in self._excluded_task_ids
                    )
                    identifier = receipt_id_for(revision.key)
                    if scheduling is not None and revision.key not in suppressed_keys and (
                        (identifier in trusted_accounted and (not excluded or identifier in trusted_excluded)) or (
                            identifier in trusted_unresolved
                            and not excluded
                        )
                    ):
                        replay += 1
                        continue
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
                        registrations.close()
                        self.store.record_source_quarantine(
                            binding,
                            created_at=started_at,
                            code="receipt_revision_truth_conflict",
                        )
                        registrations.enter_context(self.store.registration_batch())
                        binding_failed_closed = True
                        replay += 1
                        continue
                    self.store._point("after:census:receipt")
                    if result.created:
                        created += 1
                    else:
                        replay += 1
                    if scheduling is not None and result.status != "suppressed":
                        if result.status in {"complete", "excluded", "coalesced"}:
                            trusted_accounted.add(identifier)
                            trusted_unresolved.pop(identifier, None)
                            if result.status == "excluded":
                                trusted_excluded.add(identifier)
                        else:
                            trusted_unresolved[identifier] = self.store.read_receipt(identifier)
            if (
                not binding_failed_closed
                and all(
                    accounted(accounting_truth[key])
                    for key in binding_known
                    if key in accounting_truth
                )
            ):
                try:
                    self.store.advance_scan_state(
                        binding=binding,
                        expected_version=state.state_version,
                        expected_generation=generation,
                        hint=batch.next_hint,
                        last_scan_at=started_at,
                        lookback_started_at=window.start_at,
                        source_cache_snapshot=(
                            adapter.pending_metadata_snapshot(batch.next_hint)
                            if callable(getattr(adapter, "pending_metadata_snapshot", None))
                            else None
                        ),
                    )
                except ValueError as error:
                    if str(error) != "scan_state_conflict":
                        raise
                else:
                    advanced += 1
                self.store.complete_background_census(frozen_run.census_id)

        acknowledged = 0
        for path, marker in markers:
            if (
                path in resolved_marker_paths
                and marker.key in accounting_truth
                and accounted(accounting_truth[marker.key])
            ):
                safe_unlink(path)
                acknowledged += 1

        accounted = sum(
            key in accounting_truth
            and accounted(accounting_truth[key])
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
