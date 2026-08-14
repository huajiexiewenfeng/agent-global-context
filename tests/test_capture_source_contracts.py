from __future__ import annotations

from dataclasses import fields
from pathlib import Path

import pytest

from agc_runtime.capture_contracts import CaptureKey, RevisionRef, SourceQuarantine


def _source_contracts():
    from agc_runtime import capture_source

    return capture_source


ROOT_ID = "a" * 64
WINDOW = {"schema_version": 1, "start_at": "2026-08-01T00:00:00Z", "end_at": "2026-08-08T00:00:00Z"}
KEY = {"adapter_id": "codex", "source_root_id": ROOT_ID, "task_id": "task-1", "revision_id": "turn-1"}
REF = {
    "schema_version": 1,
    "capture_key": KEY,
    "rollout_anchor_id": "rollout-1",
    "completed_at": "2026-08-07T12:00:00Z",
    "locator": "sessions/opaque-1.jsonl",
    "identity_quality": "session_id",
    "adapter_version": "1.0",
    "source_schema_version": "codex-v1",
}


def test_source_contracts_are_strict_versioned_and_round_trip_without_paths():
    source = _source_contracts()
    binding = source.SourceBindingKey.from_mapping({"schema_version": 1, "adapter_id": "codex", "source_root_id": ROOT_ID})
    descriptor = source.AdapterDescriptor.from_mapping(
        {
            "schema_version": 1,
            "adapter_id": "codex",
            "adapter_version": "1.0",
            "source_schema_version": "codex-v1",
            "source_root_id": ROOT_ID,
            "capabilities": ["discover", "probe"],
        }
    )
    hint = source.ScanHint.from_mapping(
        {
            "schema_version": 1,
            "adapter_id": "codex",
            "source_root_id": ROOT_ID,
            "hint_schema_version": "codex-cursor-v1",
            "opaque_value": "cursor_0123456789abcdef",
        }
    )
    window = source.TimeWindow.from_mapping(WINDOW)
    batch = source.DiscoveryBatch.from_mapping(
        {
            "schema_version": 1,
            "binding": binding.to_mapping(),
            "window": window.to_mapping(),
            "revisions": [REF],
            "next_hint": hint.to_mapping(),
            "diagnostic_codes": ["partial_tail"],
        }
    )
    probe = source.SourceProbe.from_mapping(
        {
            "schema_version": 1,
            "revision": REF,
            "source_kind": "main",
            "completion_state": "complete",
            "diagnostic_code": None,
        }
    )
    census = source.CensusRun.from_mapping(
        {
            "schema_version": 1,
            "census_id": "census-1",
            "binding": binding.to_mapping(),
            "window": window.to_mapping(),
            "started_at": "2026-08-08T00:00:00Z",
            "frozen_at": "2026-08-08T00:00:01Z",
            "revision_keys": [KEY],
            "source_quarantine_count": 1,
        }
    )
    state = source.ScanState.from_mapping(
        {
            "schema_version": 1,
            "binding": binding.to_mapping(),
            "state_version": 2,
            "hint": hint.to_mapping(),
            "last_scan_at": "2026-08-08T00:00:01Z",
            "lookback_started_at": "2026-08-01T00:00:00Z",
        }
    )

    for dto in (descriptor, binding, hint, window, batch, probe, census, state):
        assert dto.__class__.from_mapping(dto.to_mapping()) == dto
        serialized = repr(dto.to_mapping())
        assert "C:\\" not in serialized and "/Users/" not in serialized and "/home/" not in serialized

    assert batch.revisions == (RevisionRef.from_mapping(REF),)
    assert census.revision_keys == (CaptureKey.from_mapping(KEY),)


def test_hook_contracts_are_metadata_only_and_require_four_part_identity():
    source = _source_contracts()
    envelope_value = {
        "session_id": "task-1",
        "turn_id": "turn-1",
        "transcript_path": "C:/operator-bound/sessions/task.jsonl",
        "cwd": "C:/operator-bound/project",
        "hook_event_name": "Stop",
        "model": "synthetic-model",
        "stop_hook_active": True,
        "last_assistant_message": "must never enter the DirtyMarker",
    }
    marker_value = {
        "schema_version": 1,
        "adapter_id": "codex",
        "adapter_version": "1.0",
        "source_schema_version": "codex-v1",
        "source_root_id": ROOT_ID,
        "task_id": "task-1",
        "revision_id": "turn-1",
        "locator": "sessions/opaque.jsonl",
        "observed_at": "2026-08-08T00:00:00Z",
        "hook_event": "Stop",
    }
    envelope = source.StopHookEnvelope.from_mapping(envelope_value)
    marker = source.DirtyMarker.from_mapping(marker_value)

    assert envelope.session_id == marker.task_id
    assert envelope.turn_id == marker.revision_id
    forbidden = {"prompt", "answer", "content", "last_assistant_message", "absolute_path", "cwd"}
    assert forbidden.isdisjoint({field.name for field in fields(source.DirtyMarker)})

    for missing in ("session_id", "turn_id", "hook_event_name"):
        invalid = dict(envelope_value)
        invalid.pop(missing)
        with pytest.raises(ValueError, match="missing"):
            source.StopHookEnvelope.from_mapping(invalid)

    with pytest.raises(ValueError, match="unknown"):
        source.DirtyMarker.from_mapping({**marker_value, "content": "forbidden"})
    with pytest.raises(ValueError, match="locator"):
        source.DirtyMarker.from_mapping({**marker_value, "locator": "C:\\private\\task.jsonl"})


def test_scan_hint_is_opaque_and_time_window_is_utc_half_open():
    source = _source_contracts()
    with pytest.raises(ValueError, match="opaque"):
        source.ScanHint.from_mapping(
            {
                "schema_version": 1,
                "adapter_id": "codex",
                "source_root_id": ROOT_ID,
                "hint_schema_version": "codex-cursor-v1",
                "opaque_value": "C:\\private\\cursor",
            }
        )
    with pytest.raises(ValueError, match="half-open"):
        source.TimeWindow.from_mapping({**WINDOW, "end_at": WINDOW["start_at"]})
    with pytest.raises(ValueError, match="UTC"):
        source.TimeWindow.from_mapping({**WINDOW, "start_at": "2026-08-01T00:00:00+08:00"})


def test_source_quarantine_is_strict_and_content_free():
    value = {
        "schema_version": 1,
        "adapter_id": "codex",
        "source_root_id": ROOT_ID,
        "created_at": "2026-08-08T00:00:00Z",
        "code": "unknown_source_shape",
    }
    quarantine = SourceQuarantine.from_mapping(value)
    assert quarantine.to_mapping() == value
    assert {field.name for field in fields(SourceQuarantine)} == set(value)
    with pytest.raises(ValueError, match="unknown"):
        SourceQuarantine.from_mapping({**value, "detail": "private transcript"})


def test_source_root_id_is_an_opaque_digest_and_distinct_roots_do_not_collide(tmp_path: Path):
    source = _source_contracts()
    first = tmp_path / "source-a"
    second = tmp_path / "source-b"
    first.mkdir()
    second.mkdir()

    first_id = source.source_root_id_for(first)
    assert len(first_id) == 64
    assert set(first_id) <= set("0123456789abcdef")
    assert str(first) not in first_id
    assert first_id != source.source_root_id_for(second)
