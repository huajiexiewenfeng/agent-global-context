from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys

import pytest

from agc_runtime.capture_contracts import RevisionRef
from agc_runtime.capture_store import CaptureStore
from agc_runtime.capture_transaction import atomic_write_json
from agc_runtime.paths import MemoryPaths


STARTED = "2026-08-13T12:00:00Z"
ROOT_ID = "3" * 64


@pytest.fixture(scope="module", autouse=True)
def _unload_deferred_capture_source_modules():
    global AdapterDescriptor, CaptureScanner, DiscoveryBatch, ScanHint
    global SourceBindingKey, SourceProbe
    from agc_runtime.capture_scanner import CaptureScanner as _CaptureScanner
    from agc_runtime.capture_source import (
        AdapterDescriptor as _AdapterDescriptor,
        DiscoveryBatch as _DiscoveryBatch,
        ScanHint as _ScanHint,
        SourceBindingKey as _SourceBindingKey,
        SourceProbe as _SourceProbe,
    )

    AdapterDescriptor = _AdapterDescriptor
    CaptureScanner = _CaptureScanner
    DiscoveryBatch = _DiscoveryBatch
    ScanHint = _ScanHint
    SourceBindingKey = _SourceBindingKey
    SourceProbe = _SourceProbe
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

    def describe(self) -> AdapterDescriptor:
        root = self.revisions[0].key.source_root_id if self.revisions else ROOT_ID
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
    scanner = CaptureScanner(
        CaptureStore(paths, clock=lambda: STARTED),
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
    assert {item.status for item in snapshot.receipts} == {"discovered"}
    assert len(snapshot.census) == len(revisions)


def test_ac_06_reconciliation_recovers_missed_duplicate_and_moved_sources(tmp_path: Path):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    first = _revision("first", locator="sessions/first.jsonl")
    late = _revision("late", completed_at="2026-08-07T00:00:00Z")
    adapter = SyntheticAdapter((first,))
    scanner = CaptureScanner(CaptureStore(paths, clock=lambda: STARTED), (adapter,))
    first_report = scanner.scan(run_started_at=STARTED)
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
    adapter.revisions = (
        _revision("first", locator="archived_sessions/first.jsonl"),
        late,
    )

    restarted = CaptureScanner(CaptureStore(paths, clock=lambda: STARTED), (adapter,))
    second_report = restarted.scan(run_started_at=STARTED)
    third_report = restarted.scan(run_started_at=STARTED)

    snapshot = CaptureStore(paths).read_snapshot()
    assert first_report.accounted_key_count == 1
    assert second_report.accounted_key_count == 2
    assert second_report.replay_count == 1
    assert second_report.acknowledged_marker_count == 1
    assert not marker_path.exists()
    assert len(snapshot.receipts) == len(snapshot.census) == 2
    assert third_report.created_receipt_count == 0
    assert third_report.silent_loss_count == 0


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
