from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import sys

import pytest

from agc_runtime.capture_contracts import (
    CaptureSuppressionTombstone,
    RevisionRef,
    tombstone_id_for,
)
from agc_runtime.capture_store import CaptureStore
from agc_runtime.capture_transaction import atomic_write_json
from agc_runtime.paths import MemoryPaths


STARTED = "2026-08-13T12:00:00Z"
ROOT_ID = "3" * 64
OTHER_ROOT_ID = "4" * 64


@pytest.fixture(scope="module", autouse=True)
def _unload_deferred_capture_source_modules():
    global AdapterDescriptor, CaptureScanner, DiscoveryBatch, ScanHint
    global SourceBindingKey, SourceProbe, TimeWindow
    from agc_runtime.capture_scanner import CaptureScanner as _CaptureScanner
    from agc_runtime.capture_source import (
        AdapterDescriptor as _AdapterDescriptor,
        DiscoveryBatch as _DiscoveryBatch,
        ScanHint as _ScanHint,
        SourceBindingKey as _SourceBindingKey,
        SourceProbe as _SourceProbe,
        TimeWindow as _TimeWindow,
    )

    AdapterDescriptor = _AdapterDescriptor
    CaptureScanner = _CaptureScanner
    DiscoveryBatch = _DiscoveryBatch
    ScanHint = _ScanHint
    SourceBindingKey = _SourceBindingKey
    SourceProbe = _SourceProbe
    TimeWindow = _TimeWindow
    yield
    for name in (
        "agc_runtime.capture_scanner",
        "agc_runtime.capture_ledger",
        "agc_runtime.codex_source_adapter",
        "agc_runtime.capture_source",
    ):
        sys.modules.pop(name, None)


def _revision(
    revision_id: str,
    *,
    completed_at: str = "2026-08-12T12:00:00Z",
    locator: str | None = None,
    anchor: str = "rollout-1",
    root_id: str = ROOT_ID,
) -> RevisionRef:
    return RevisionRef.from_mapping(
        {
            "schema_version": 1,
            "capture_key": {
                "adapter_id": "synthetic",
                "source_root_id": root_id,
                "task_id": f"task-{revision_id}",
                "revision_id": revision_id,
            },
            "rollout_anchor_id": anchor,
            "completed_at": completed_at,
            "locator": locator or f"sessions/{revision_id}.jsonl",
            "identity_quality": "session_id",
            "adapter_version": "1",
            "source_schema_version": "1",
        }
    )


@dataclass
class SyntheticAdapter:
    revisions: tuple[RevisionRef, ...]
    diagnostics: tuple[str, ...] = ()
    next_hint_value: str | None = "offset_100"
    discover_count: int = 0
    root_id: str = ROOT_ID
    received_hints: list[object] = field(default_factory=list)

    def describe(self) -> AdapterDescriptor:
        root = self.revisions[0].key.source_root_id if self.revisions else self.root_id
        return AdapterDescriptor.from_mapping(
            {
                "schema_version": 1,
                "adapter_id": "synthetic",
                "adapter_version": "1",
                "source_schema_version": "1",
                "source_root_id": root,
                "capabilities": ["discover", "probe"],
            }
        )

    def discover(self, hint, window) -> DiscoveryBatch:
        self.discover_count += 1
        self.received_hints.append(hint)
        descriptor = self.describe()
        next_hint = None
        if self.next_hint_value is not None:
            next_hint = ScanHint.from_mapping(
                {
                    "schema_version": 1,
                    "adapter_id": descriptor.adapter_id,
                    "source_root_id": descriptor.source_root_id,
                    "hint_schema_version": "synthetic-v1",
                    "opaque_value": self.next_hint_value,
                }
            )
        return DiscoveryBatch.from_mapping(
            {
                "schema_version": 1,
                "binding": SourceBindingKey(
                    1, descriptor.adapter_id, descriptor.source_root_id
                ).to_mapping(),
                "window": window.to_mapping(),
                "revisions": [item.to_mapping() for item in self.revisions],
                "next_hint": next_hint.to_mapping() if next_hint else None,
                "diagnostic_codes": list(self.diagnostics),
            }
        )

    def probe(self, ref: RevisionRef) -> SourceProbe:
        return SourceProbe.from_mapping(
            {
                "schema_version": 1,
                "revision": ref.to_mapping(),
                "source_kind": "main",
                "completion_state": "complete",
                "diagnostic_code": None,
            }
        )


def test_ac_03_synthetic_seven_day_census_has_full_accounting(tmp_path: Path):
    revisions = tuple(
        _revision(name)
        for name in (
            "normal",
            "zero-future",
            "eight",
            "over-eight",
            "continued",
            "excluded",
            "corrupt-known",
        )
    )
    paths = MemoryPaths.from_root(tmp_path / "memory")
    store = CaptureStore(paths, clock=lambda: STARTED)
    suppressed = revisions[5]
    tombstone = CaptureSuppressionTombstone.from_mapping(
        {
            "schema_version": 1,
            "tombstone_id": tombstone_id_for(suppressed.key),
            "capture_key": suppressed.key.to_mapping(),
            "created_at": "2026-08-13T11:59:58Z",
            "reason": "user_forget",
        }
    )
    atomic_write_json(
        paths.capture.tombstones / f"{tombstone.tombstone_id}.json",
        tombstone.to_mapping(),
    )
    earlier = "2026-08-13T11:59:59Z"
    store.freeze_census(
        binding=SourceBindingKey(1, "synthetic", ROOT_ID),
        window=TimeWindow(
            1, "2026-08-06T11:59:59Z", earlier
        ),
        started_at=earlier,
        revisions=(_revision("corrupt-known", anchor="conflicting-anchor"),),
    )
    scanner = CaptureScanner(
        store,
        (SyntheticAdapter(revisions, diagnostics=("unknown_source_shape",)),),
    )

    report = scanner.scan(run_started_at=STARTED)

    snapshot = CaptureStore(paths).read_snapshot()
    assert report.window.start_at == "2026-08-06T12:00:00Z"
    assert report.window.end_at == STARTED
    assert report.known_key_count == len(revisions)
    assert report.accounted_key_count == len(revisions)
    assert report.silent_loss_count == 0
    assert report.source_health == "degraded"
    assert report.source_quarantine_count == 1
    assert {item.status for item in snapshot.receipts} == {
        "discovered",
        "quarantined",
    }
    assert {item.capture_key for item in snapshot.tombstones} == {suppressed.key}
    assert suppressed.key not in {item.key for item in snapshot.receipts}
    assert not (
        {"complete", "excluded", "coalesced", "retryable"}
        & {item.status for item in snapshot.receipts}
    )
    assert len(snapshot.census) == len(revisions)


def test_ac_06_reconciliation_recovers_missed_duplicate_and_moved_sources(tmp_path: Path):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    first = _revision("first", locator="sessions/first.jsonl")
    late = _revision("late", completed_at="2026-08-07T00:00:00Z")
    same_logical_other_root = _revision("first", root_id=OTHER_ROOT_ID)
    with pytest.raises(RuntimeError, match="injected crash"):
        CaptureScanner(
            CaptureStore(
                paths, crash_at="before:census:receipt", clock=lambda: STARTED
            ),
            (SyntheticAdapter((first,)),),
        ).scan(run_started_at=STARTED)
    first_report = CaptureScanner(
        CaptureStore(paths, clock=lambda: STARTED),
        (
            SyntheticAdapter((first,)),
            SyntheticAdapter(
                (same_logical_other_root,), root_id=OTHER_ROOT_ID
            ),
        ),
    ).scan(run_started_at=STARTED)
    marker_path = paths.capture.dirty / "dirty-late.json"
    atomic_write_json(
        marker_path,
        {
            "schema_version": 1,
            "adapter_id": "synthetic",
            "adapter_version": "1",
            "source_schema_version": "1",
            "source_root_id": ROOT_ID,
            "task_id": late.key.task_id,
            "revision_id": late.key.revision_id,
            "locator": late.locator,
            "observed_at": STARTED,
            "hook_event": "Stop",
        },
    )
    moved_and_late = SyntheticAdapter(
        (
            _revision("first", locator="archived_sessions/first.jsonl"),
            late,
        )
    )

    later_run = "2026-08-13T12:00:01Z"
    restarted = CaptureScanner(
        CaptureStore(paths, clock=lambda: later_run),
        (
            moved_and_late,
            SyntheticAdapter(
                (same_logical_other_root,), root_id=OTHER_ROOT_ID
            ),
        ),
    )
    second_report = restarted.scan(run_started_at=later_run)
    third_report = restarted.scan(run_started_at=later_run)

    shrink_run = "2026-08-13T12:00:02Z"
    shrink = SyntheticAdapter(
        moved_and_late.revisions,
        diagnostics=("file_shrink", "scan_hint_invalidated"),
    )
    shrink_report = CaptureScanner(
        CaptureStore(paths, clock=lambda: shrink_run), (shrink,)
    ).scan(run_started_at=shrink_run)

    anchor_run = "2026-08-13T12:00:03Z"
    changed_anchor = SyntheticAdapter(
        (
            _revision(
                "first",
                locator="archived_sessions/first.jsonl",
                anchor="rebuilt-anchor",
            ),
            late,
        )
    )
    anchor_report = CaptureScanner(
        CaptureStore(paths, clock=lambda: anchor_run), (changed_anchor,)
    ).scan(run_started_at=anchor_run)

    snapshot = CaptureStore(paths).read_snapshot()
    assert first_report.accounted_key_count == 2
    assert second_report.accounted_key_count == 3
    assert second_report.replay_count == 2
    assert second_report.acknowledged_marker_count == 1
    assert moved_and_late.received_hints[0] is None
    assert not marker_path.exists()
    assert len(snapshot.receipts) == len(snapshot.census) == 3
    assert third_report.created_receipt_count == 0
    assert third_report.silent_loss_count == 0
    assert shrink.received_hints[0] is not None
    assert shrink_report.advanced_hint_count == 0
    assert anchor_report.advanced_hint_count == 0
    assert anchor_report.source_health == "degraded"
    roots = {item.key.source_root_id for item in snapshot.receipts}
    assert roots == {ROOT_ID, OTHER_ROOT_ID}


def test_hint_does_not_advance_when_accounting_commit_is_interrupted(tmp_path: Path):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    revision = _revision("interrupted")
    crashing = CaptureStore(paths, crash_at="before:census:receipt", clock=lambda: STARTED)

    try:
        CaptureScanner(crashing, (SyntheticAdapter((revision,)),)).scan(
            run_started_at=STARTED
        )
    except RuntimeError as error:
        assert "injected crash" in str(error)
    else:
        raise AssertionError("crash injection did not fire")

    binding = SourceBindingKey(1, "synthetic", ROOT_ID)
    state = CaptureStore(paths).load_scan_state(
        binding=binding, lookback_started_at="2026-08-06T12:00:00Z"
    )
    assert state.hint is None


def test_receipt_only_interruption_replays_ledger_before_hint_and_marker_ack(
    tmp_path: Path,
):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    revision = _revision("receipt-only")
    marker_path = paths.capture.dirty / "dirty-receipt-only.json"
    atomic_write_json(
        marker_path,
        {
            "schema_version": 1,
            "adapter_id": "synthetic",
            "adapter_version": "1",
            "source_schema_version": "1",
            "source_root_id": ROOT_ID,
            "task_id": revision.key.task_id,
            "revision_id": revision.key.revision_id,
            "locator": revision.locator,
            "observed_at": STARTED,
            "hook_event": "Stop",
        },
    )
    crashing = CaptureStore(
        paths, crash_at="after:discovery:receipt", clock=lambda: STARTED
    )

    try:
        CaptureScanner(crashing, (SyntheticAdapter((revision,)),)).scan(
            run_started_at=STARTED
        )
    except RuntimeError as error:
        assert "injected crash" in str(error)
    else:
        raise AssertionError("crash injection did not fire")

    receipt_id = __import__(
        "agc_runtime.capture_contracts", fromlist=["receipt_id_for"]
    ).receipt_id_for(revision.key)
    assert (paths.capture.receipts / f"{receipt_id}.json").exists()
    assert not (paths.capture.ledger / f"{receipt_id}.json").exists()
    assert marker_path.exists()

    report = CaptureScanner(
        CaptureStore(paths, clock=lambda: STARTED), (SyntheticAdapter((revision,)),)
    ).scan(run_started_at=STARTED)

    assert (paths.capture.ledger / f"{receipt_id}.json").exists()
    assert report.acknowledged_marker_count == 1
    assert report.advanced_hint_count == 1


def test_duplicate_configured_source_binding_is_enumerated_once(tmp_path: Path):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    adapter = SyntheticAdapter((_revision("once"),))

    report = CaptureScanner(
        CaptureStore(paths, clock=lambda: STARTED), (adapter, adapter)
    ).scan(run_started_at=STARTED)

    assert adapter.discover_count == 1
    assert report.known_key_count == report.accounted_key_count == 1


def test_restart_uses_frozen_census_truth_when_current_discovery_is_empty(
    tmp_path: Path,
):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    revision = _revision("frozen-pending")
    marker_path = paths.capture.dirty / "frozen-pending.json"
    atomic_write_json(
        marker_path,
        {
            "schema_version": 1,
            "adapter_id": "synthetic",
            "adapter_version": "1",
            "source_schema_version": "1",
            "source_root_id": ROOT_ID,
            "task_id": revision.key.task_id,
            "revision_id": revision.key.revision_id,
            "locator": revision.locator,
            "observed_at": STARTED,
            "hook_event": "Stop",
        },
    )
    with pytest.raises(RuntimeError, match="injected crash"):
        CaptureScanner(
            CaptureStore(paths, crash_at="before:census:receipt", clock=lambda: STARTED),
            (SyntheticAdapter((revision,)),),
        ).scan(run_started_at=STARTED)

    empty = SyntheticAdapter(())
    pending = CaptureScanner(
        CaptureStore(paths, clock=lambda: STARTED), (empty,)
    ).scan(run_started_at=STARTED)

    assert pending.known_key_count == 1
    assert pending.accounted_key_count == 0
    assert pending.silent_loss_count == pending.pending_key_count == 1
    assert pending.advanced_hint_count == 0
    assert pending.acknowledged_marker_count == 0
    assert marker_path.exists()

    recovered = CaptureScanner(
        CaptureStore(paths, clock=lambda: STARTED),
        (SyntheticAdapter((revision,)),),
    ).scan(run_started_at=STARTED)
    assert recovered.accounted_key_count == 1
    assert recovered.silent_loss_count == recovered.pending_key_count == 0
    assert recovered.advanced_hint_count == recovered.acknowledged_marker_count == 1


def test_dirty_marker_forces_hintless_discovery_and_blocks_progress_until_accounted(
    tmp_path: Path,
):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    binding = SourceBindingKey(1, "synthetic", ROOT_ID)
    store = CaptureStore(paths, clock=lambda: STARTED)
    initial = store.load_scan_state(
        binding=binding, lookback_started_at="2026-08-06T12:00:00Z"
    )
    store.advance_scan_state(
        binding=binding,
        expected_version=initial.state_version,
        hint=ScanHint(1, "synthetic", ROOT_ID, "synthetic-v1", "old_offset"),
        last_scan_at=STARTED,
        lookback_started_at=initial.lookback_started_at,
    )
    revision = _revision("dirty-pending")
    marker_path = paths.capture.dirty / "dirty-pending.json"
    atomic_write_json(
        marker_path,
        {
            "schema_version": 1,
            "adapter_id": "synthetic",
            "adapter_version": "1",
            "source_schema_version": "1",
            "source_root_id": ROOT_ID,
            "task_id": revision.key.task_id,
            "revision_id": revision.key.revision_id,
            "locator": revision.locator,
            "observed_at": STARTED,
            "hook_event": "Stop",
        },
    )
    empty = SyntheticAdapter(())

    pending = CaptureScanner(store, (empty,)).scan(run_started_at=STARTED)

    assert empty.received_hints == [None]
    assert pending.known_key_count == pending.pending_key_count == 1
    assert pending.silent_loss_count == 1
    assert pending.advanced_hint_count == pending.acknowledged_marker_count == 0
    assert marker_path.exists()

    available = SyntheticAdapter((revision,))
    reconciled = CaptureScanner(CaptureStore(paths), (available,)).scan(
        run_started_at="2026-08-13T12:00:01Z"
    )
    assert available.received_hints == [None]
    assert reconciled.silent_loss_count == reconciled.pending_key_count == 0
    assert reconciled.advanced_hint_count == reconciled.acknowledged_marker_count == 1


def test_invalid_and_unconfigured_dirty_markers_persistently_degrade_health(
    tmp_path: Path,
):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    invalid = paths.capture.dirty / "invalid.json"
    mismatched = paths.capture.dirty / "mismatched.json"
    atomic_write_json(invalid, {"schema_version": 1, "private": "must-not-persist"})
    atomic_write_json(
        mismatched,
        {
            "schema_version": 1,
            "adapter_id": "synthetic",
            "adapter_version": "1",
            "source_schema_version": "1",
            "source_root_id": "9" * 64,
            "task_id": "task-mismatch",
            "revision_id": "turn-mismatch",
            "locator": "sessions/mismatch.jsonl",
            "observed_at": STARTED,
            "hook_event": "Stop",
        },
    )

    first = CaptureScanner(CaptureStore(paths), (SyntheticAdapter(()),)).scan(
        run_started_at=STARTED
    )
    second = CaptureScanner(CaptureStore(paths), (SyntheticAdapter(()),)).scan(
        run_started_at=STARTED
    )

    assert first.source_health == second.source_health == "degraded"
    assert first.source_quarantine_count >= 2
    assert invalid.exists() and mismatched.exists()
    persisted = "".join(
        path.read_text(encoding="utf-8")
        for path in paths.capture.quarantines.glob("*.json")
    )
    assert "must-not-persist" not in persisted


def test_durable_source_quarantine_keeps_health_degraded_after_diagnostic_clears(
    tmp_path: Path,
):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    first = CaptureScanner(
        CaptureStore(paths),
        (SyntheticAdapter((), diagnostics=("unknown_source_shape",)),),
    ).scan(run_started_at=STARTED)
    clean_adapter = SyntheticAdapter(())
    restarted = CaptureScanner(CaptureStore(paths), (clean_adapter,)).scan(
        run_started_at=STARTED
    )

    assert first.source_health == restarted.source_health == "degraded"
    assert restarted.source_quarantine_count >= 1
