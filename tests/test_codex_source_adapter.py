from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from agc_runtime.capture_contracts import CaptureKey


FIXTURES = Path(__file__).parent / "fixtures" / "codex_source" / "v1"


def _profile(tmp_path: Path) -> Path:
    root = tmp_path / "codex-profile"
    shutil.copytree(FIXTURES, root)
    (root / "session_index.jsonl").write_text(
        '{"id":"rollout-main","title":"duplicate hint only"}\n', encoding="utf-8"
    )
    return root


def _window():
    from agc_runtime.capture_source import TimeWindow

    return TimeWindow.from_mapping(
        {
            "schema_version": 1,
            "start_at": "2026-08-01T00:00:00Z",
            "end_at": "2026-08-20T00:00:00Z",
        }
    )


def test_ac_04_only_completed_main_turns_are_revisions(tmp_path: Path):
    from agc_runtime.codex_source_adapter import CodexSourceAdapter

    adapter = CodexSourceAdapter(_profile(tmp_path))
    batch = adapter.discover(None, _window())

    identities = {
        (ref.key.task_id, ref.key.revision_id, ref.identity_quality, ref.locator)
        for ref in batch.revisions
    }
    assert identities == {
        ("task-main", "turn-1", "session_id", "sessions/main-multiple-turns.jsonl"),
        ("task-main", "turn-2", "session_id", "sessions/main-multiple-turns.jsonl"),
        ("rollout-legacy", "turn-legacy", "legacy_rollout_id", "sessions/legacy-main.jsonl"),
    }
    assert all("sub" not in ref.key.task_id for ref in batch.revisions)
    assert all("started" not in ref.key.revision_id for ref in batch.revisions)
    assert all("aborted" not in ref.key.revision_id for ref in batch.revisions)
    assert "partial_tail" in batch.diagnostic_codes
    assert adapter.describe().capabilities == ("discover", "probe")


def test_ac_19_unknown_formats_fail_closed_without_false_conflicts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from agc_runtime.codex_source_adapter import (
        CodexSourceAdapter,
        compare_source_fingerprints,
    )

    root = _profile(tmp_path)
    future = root / "sessions" / "future-completion.jsonl"
    future.write_text(
        "\n".join(
            (
                '{"timestamp":"2026-08-14T10:00:00Z","type":"session_meta","payload":{"id":"rollout-future","session_id":"task-future","source":"cli"}}',
                '{"timestamp":"2026-08-14T10:01:00Z","type":"event_msg","payload":{"type":"turn_settled","turn":{"id":"turn-future"}}}',
            )
        )
        + "\n",
        encoding="utf-8",
    )
    invalid_session = root / "sessions" / "invalid-session-id.jsonl"
    invalid_session.write_text(
        "\n".join(
            (
                '{"timestamp":"2026-08-14T11:00:00Z","type":"session_meta","payload":{"id":"rollout-invalid","session_id":"","source":"cli"}}',
                '{"timestamp":"2026-08-14T11:01:00Z","type":"event_msg","payload":{"type":"task_complete","turn_id":"turn-invalid"}}',
            )
        )
        + "\n",
        encoding="utf-8",
    )
    locked = root / "sessions" / "locked.jsonl"
    locked.write_text("{}\n", encoding="utf-8")
    original_open = Path.open

    def sharing_violation(path: Path, *args, **kwargs):
        if path == locked:
            raise PermissionError(32, "synthetic sharing violation")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", sharing_violation)
    adapter = CodexSourceAdapter(root)
    adapter._iter_target_turn_records = lambda _ref: (_ for _ in ()).throw(  # type: ignore[method-assign]
        AssertionError("census discovery must not load target-turn content")
    )
    batch = adapter.discover(None, _window())

    keys = {(ref.key.task_id, ref.key.revision_id) for ref in batch.revisions}
    assert ("task-unknown", "turn-unknown") not in keys
    assert ("task-future", "turn-future") not in keys
    assert ("rollout-invalid", "turn-invalid") not in keys
    assert {"unknown_source_shape", "unknown_completion_shape", "source_locked"} <= set(
        batch.diagnostic_codes
    )
    assert compare_source_fingerprints("a" * 64, "source-v1", "b" * 64, "source-v1") == "conflict"
    assert compare_source_fingerprints("a" * 64, "source-v1", "b" * 64, "source-v2") == "not_comparable"
    assert compare_source_fingerprints("a" * 64, "source-v1", "a" * 64, "source-v1") == "match"


def test_probe_and_target_turn_iterator_validate_locator_and_completion(tmp_path: Path):
    from agc_runtime.codex_source_adapter import CapabilityUnavailable, CodexSourceAdapter

    adapter = CodexSourceAdapter(_profile(tmp_path))
    ref = next(ref for ref in adapter.discover(None, _window()).revisions if ref.key.revision_id == "turn-2")

    probe = adapter.probe(ref)
    assert (probe.source_kind, probe.completion_state, probe.diagnostic_code) == (
        "main",
        "complete",
        None,
    )
    records = tuple(adapter._iter_target_turn_records(ref))
    assert records[-1]["payload"]["turn_id"] == "turn-2"
    assert all(record.get("type") in {"session_meta", "event_msg", "future_noncritical"} for record in records)

    wrong_task = ref.__class__(
        key=CaptureKey(ref.key.adapter_id, ref.key.source_root_id, "different-task", ref.key.revision_id),
        rollout_anchor_id=ref.rollout_anchor_id,
        completed_at=ref.completed_at,
        locator=ref.locator,
        identity_quality=ref.identity_quality,
        adapter_version=ref.adapter_version,
        source_schema_version=ref.source_schema_version,
    )
    wrong_probe = adapter.probe(wrong_task)
    assert (wrong_probe.source_kind, wrong_probe.completion_state, wrong_probe.diagnostic_code) == (
        "unknown",
        "unreadable",
        "source_identity_mismatch",
    )

    escaped = ref.__class__(
        key=ref.key,
        rollout_anchor_id=ref.rollout_anchor_id,
        completed_at=ref.completed_at,
        locator="../outside.jsonl",
        identity_quality=ref.identity_quality,
        adapter_version=ref.adapter_version,
        source_schema_version=ref.source_schema_version,
    )
    with pytest.raises(ValueError, match="locator"):
        tuple(adapter._iter_target_turn_records(escaped))
    with pytest.raises(CapabilityUnavailable, match="semantic_capture_not_installed"):
        adapter.load_capsule(ref, object())
