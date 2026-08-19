from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

import pytest

from agc_runtime.capture_contracts import CaptureKey, RevisionRef
from agc_runtime.capture_store import CaptureStore
from agc_runtime.paths import MemoryPaths


ROOT_ID = "1" * 64
STARTED = "2026-08-13T12:00:00Z"


@pytest.fixture(scope="module", autouse=True)
def _unload_deferred_capture_source_modules():
    global ScanHint, SourceBindingKey, TimeWindow
    from agc_runtime.capture_source import ScanHint as _ScanHint
    from agc_runtime.capture_source import SourceBindingKey as _SourceBindingKey
    from agc_runtime.capture_source import TimeWindow as _TimeWindow

    ScanHint = _ScanHint
    SourceBindingKey = _SourceBindingKey
    TimeWindow = _TimeWindow
    yield
    for name in (
        "agc_runtime.capture_scanner",
        "agc_runtime.capture_ledger",
        "agc_runtime.codex_source_adapter",
        "agc_runtime.capture_source",
    ):
        sys.modules.pop(name, None)


def _binding(root_id: str = ROOT_ID) -> SourceBindingKey:
    return SourceBindingKey.from_mapping(
        {"schema_version": 1, "adapter_id": "synthetic", "source_root_id": root_id}
    )


def _revision(
    revision_id: str = "turn-1",
    *,
    anchor: str = "rollout-1",
    locator: str = "sessions/active.jsonl",
) -> RevisionRef:
    return RevisionRef.from_mapping(
        {
            "schema_version": 1,
            "capture_key": {
                "adapter_id": "synthetic",
                "source_root_id": ROOT_ID,
                "task_id": "task-1",
                "revision_id": revision_id,
            },
            "rollout_anchor_id": anchor,
            "completed_at": "2026-08-12T12:00:00Z",
            "locator": locator,
            "identity_quality": "session_id",
            "adapter_version": "1",
            "source_schema_version": "1",
        }
    )


def test_freeze_census_persists_exact_seven_day_half_open_window_and_revisions(
    tmp_path: Path,
):
    store = CaptureStore(MemoryPaths.from_root(tmp_path / "memory"), clock=lambda: STARTED)
    start = (
        datetime.fromisoformat(STARTED.replace("Z", "+00:00")) - timedelta(days=7)
    ).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    window = TimeWindow.from_mapping(
        {"schema_version": 1, "start_at": start, "end_at": STARTED}
    )

    census = store.freeze_census(
        binding=_binding(),
        window=window,
        started_at=STARTED,
        revisions=(_revision(),),
        source_quarantine_count=0,
    )

    assert census.window.start_at == "2026-08-06T12:00:00Z"
    assert census.window.end_at == STARTED
    assert census.revision_keys == (_revision().key,)
    assert store.read_snapshot().census == (_revision(),)


def test_freeze_census_rejects_a_window_not_bound_to_the_run_start(tmp_path: Path):
    store = CaptureStore(MemoryPaths.from_root(tmp_path / "memory"), clock=lambda: STARTED)
    wrong = TimeWindow.from_mapping(
        {
            "schema_version": 1,
            "start_at": "2026-08-05T12:00:00Z",
            "end_at": STARTED,
        }
    )

    with pytest.raises(ValueError, match="seven-day"):
        store.freeze_census(
            binding=_binding(),
            window=wrong,
            started_at=STARTED,
            revisions=(_revision(),),
        )


def test_scan_state_is_root_bound_atomic_and_optimistically_versioned(tmp_path: Path):
    store = CaptureStore(MemoryPaths.from_root(tmp_path / "memory"))
    binding = _binding()
    initial = store.load_scan_state(
        binding=binding, lookback_started_at="2026-08-06T12:00:00Z"
    )
    hint = ScanHint.from_mapping(
        {
            "schema_version": 1,
            "adapter_id": binding.adapter_id,
            "source_root_id": binding.source_root_id,
            "hint_schema_version": "synthetic-v1",
            "opaque_value": "offset_100",
        }
    )

    advanced = store.advance_scan_state(
        binding=binding,
        expected_version=initial.state_version,
        hint=hint,
        last_scan_at=STARTED,
        lookback_started_at=initial.lookback_started_at,
    )

    assert advanced.state_version == initial.state_version + 1
    assert store.load_scan_state(
        binding=binding, lookback_started_at="2026-01-01T00:00:00Z"
    ) == advanced
    with pytest.raises(ValueError, match="scan_state_conflict"):
        store.advance_scan_state(
            binding=binding,
            expected_version=initial.state_version,
            hint=None,
            last_scan_at=STARTED,
            lookback_started_at=initial.lookback_started_at,
        )
    other = SourceBindingKey.from_mapping(
        {"schema_version": 1, "adapter_id": "synthetic", "source_root_id": "2" * 64}
    )
    with pytest.raises(ValueError, match="binding"):
        store.advance_scan_state(
            binding=other,
            expected_version=advanced.state_version,
            hint=hint,
            last_scan_at=STARTED,
            lookback_started_at=advanced.lookback_started_at,
        )


def test_census_exact_replay_allows_archive_move_but_rejects_anchor_change(tmp_path: Path):
    store = CaptureStore(MemoryPaths.from_root(tmp_path / "memory"), clock=lambda: STARTED)
    window = TimeWindow.from_mapping(
        {
            "schema_version": 1,
            "start_at": "2026-08-06T12:00:00Z",
            "end_at": STARTED,
        }
    )
    first = _revision()
    moved = _revision(locator="archived_sessions/moved.jsonl")
    changed = _revision(anchor="rollout-rebuilt")

    store.freeze_census(
        binding=_binding(), window=window, started_at=STARTED, revisions=(first,)
    )
    store.freeze_census(
        binding=_binding(), window=window, started_at=STARTED, revisions=(moved,)
    )
    assert store.read_snapshot().census == (first,)
    with pytest.raises(ValueError, match="census_run_conflict"):
        store.freeze_census(
            binding=_binding(), window=window, started_at=STARTED, revisions=(changed,)
        )


def test_frozen_run_is_immutable_and_membership_conflict_cannot_overwrite(
    tmp_path: Path,
):
    store = CaptureStore(MemoryPaths.from_root(tmp_path / "memory"), clock=lambda: STARTED)
    window = TimeWindow.from_mapping(
        {
            "schema_version": 1,
            "start_at": "2026-08-06T12:00:00Z",
            "end_at": STARTED,
        }
    )
    first = _revision("turn-1")
    second = _revision("turn-2")
    frozen = store.freeze_census(
        binding=_binding(), window=window, started_at=STARTED, revisions=(first,)
    )
    run_path = store.paths.capture.root / "census-runs" / frozen.census_id

    assert run_path.is_dir()
    assert (run_path / "run.json").is_file()
    assert len(list((run_path / "members").glob("*.json"))) == 1
    replay = store.freeze_census(
        binding=_binding(),
        window=window,
        started_at=STARTED,
        revisions=(_revision("turn-1", locator="archived_sessions/moved.jsonl"),),
    )
    assert replay == frozen

    with pytest.raises(ValueError, match="census_run_conflict"):
        store.freeze_census(
            binding=_binding(),
            window=window,
            started_at=STARTED,
            revisions=(first, second),
        )
    assert store.frozen_revisions(binding=_binding()) == (first,)
    assert len(list((run_path / "members").glob("*.json"))) == 1


def test_census_directory_publication_failure_leaves_no_partial_truth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from agc_runtime import capture_transaction

    store = CaptureStore(MemoryPaths.from_root(tmp_path / "memory"), clock=lambda: STARTED)
    window = TimeWindow.from_mapping(
        {
            "schema_version": 1,
            "start_at": "2026-08-06T12:00:00Z",
            "end_at": STARTED,
        }
    )
    monkeypatch.setattr(
        capture_transaction.os,
        "rename",
        lambda _source, _target: (_ for _ in ()).throw(OSError("publish failed")),
    )

    with pytest.raises(OSError, match="publish failed"):
        store.freeze_census(
            binding=_binding(),
            window=window,
            started_at=STARTED,
            revisions=(_revision(),),
        )

    assert store.frozen_revisions(binding=_binding()) == ()
    runs = store.paths.capture.root / "census-runs"
    assert not runs.exists() or list(runs.iterdir()) == []


def test_ready_revisions_are_durable_unfinished_receipts(tmp_path: Path):
    from agc_runtime.capture_ledger import receipt_for_revision

    store = CaptureStore(MemoryPaths.from_root(tmp_path / "memory"), clock=lambda: STARTED)
    receipt = receipt_for_revision(_revision(), discovered_at=STARTED)
    store.register_extraction(receipt)

    assert store.ready_revisions() == (receipt,)
