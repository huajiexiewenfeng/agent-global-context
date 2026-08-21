from __future__ import annotations

import os
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
        ("task-content", "turn-content", "session_id", "sessions/content-sentinel.jsonl"),
        ("rollout-legacy", "turn-legacy", "legacy_rollout_id", "sessions/legacy-main.jsonl"),
    }
    assert all("sub" not in ref.key.task_id for ref in batch.revisions)
    assert all("started" not in ref.key.revision_id for ref in batch.revisions)
    assert all("aborted" not in ref.key.revision_id for ref in batch.revisions)
    assert "partial_tail" in batch.diagnostic_codes
    assert adapter.describe().capabilities == ("discover", "probe")


def test_codex_app_turn_scoped_non_completion_events_do_not_quarantine_session(
    tmp_path: Path,
):
    from agc_runtime.codex_source_adapter import CodexSourceAdapter

    root = _profile(tmp_path)
    source = root / "sessions" / "codex-app-events.jsonl"
    source.write_text(
        "\n".join(
            (
                '{"timestamp":"2026-08-16T10:00:00Z","type":"session_meta","payload":{"id":"rollout-app","session_id":"task-app","source":"vscode"}}',
                '{"timestamp":"2026-08-16T10:00:10Z","type":"event_msg","payload":{"type":"task_started","turn_id":"turn-app"}}',
                '{"timestamp":"2026-08-16T10:00:20Z","type":"event_msg","payload":{"type":"patch_apply_end","turn_id":"turn-app","success":true}}',
                '{"timestamp":"2026-08-16T10:00:25Z","type":"event_msg","payload":{"type":"item_completed","turn_id":"turn-app","item":{"type":"agent_message"}}}',
                '{"timestamp":"2026-08-16T10:00:30Z","type":"event_msg","payload":{"type":"turn_aborted","turn_id":"turn-aborted","reason":"interrupted"}}',
                '{"timestamp":"2026-08-16T10:01:00Z","type":"event_msg","payload":{"type":"task_complete","turn_id":"turn-app"}}',
            )
        )
        + "\n",
        encoding="utf-8",
    )

    batch = CodexSourceAdapter(root).discover(None, _window())

    assert ("task-app", "turn-app") in {
        (ref.key.task_id, ref.key.revision_id) for ref in batch.revisions
    }
    assert "unknown_completion_shape" not in batch.diagnostic_codes


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


def test_discovery_streams_metadata_without_retaining_content_records(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    import agc_runtime.codex_source_adapter as module

    root = _profile(tmp_path)
    content_file = root / "sessions" / "content-sentinel.jsonl"
    lines = content_file.read_text(encoding="utf-8").splitlines()
    content_file.write_text(
        "\n".join((lines[0], *(lines[1] for _ in range(256)), lines[-1])) + "\n",
        encoding="utf-8",
    )
    original_loads = module.json.loads
    counts = {"live": 0, "maximum": 0}

    class TrackedRecord(dict):
        def __init__(self, value):
            super().__init__(value)
            counts["live"] += 1
            counts["maximum"] = max(counts["maximum"], counts["live"])

        def __del__(self):
            counts["live"] -= 1

    monkeypatch.setattr(module.json, "loads", lambda value: TrackedRecord(original_loads(value)))
    adapter = module.CodexSourceAdapter(root)
    batch = adapter.discover(None, _window())

    assert ("task-content", "turn-content") in {
        (ref.key.task_id, ref.key.revision_id) for ref in batch.revisions
    }
    assert counts == {"live": 0, "maximum": 1}
    assert "CENSUS_CONTENT_MUST_NOT_BE_RETAINED" not in repr(batch.to_mapping())
    assert "CENSUS_CONTENT_MUST_NOT_BE_RETAINED" not in repr(adapter.__dict__)


def test_internal_parse_or_critical_uncertainty_invalidates_the_whole_source(tmp_path: Path):
    from agc_runtime.codex_source_adapter import CodexSourceAdapter

    root = _profile(tmp_path)
    malformed = root / "sessions" / "internal-malformed.jsonl"
    malformed.write_text(
        "\n".join(
            (
                '{"timestamp":"2026-08-16T10:00:00Z","type":"session_meta","payload":{"id":"rollout-malformed","session_id":"task-malformed","source":"cli"}}',
                '{"timestamp":"2026-08-16T10:00:10Z","type":"response_item",BROKEN}',
                '{"timestamp":"2026-08-16T10:01:00Z","type":"event_msg","payload":{"type":"task_complete","turn_id":"turn-malformed"}}',
            )
        )
        + "\n",
        encoding="utf-8",
    )
    critical = root / "sessions" / "critical-drift.jsonl"
    critical.write_text(
        "\n".join(
            (
                '{"timestamp":"2026-08-16T11:00:00Z","type":"session_meta","payload":{"id":"rollout-critical","session_id":"task-critical","source":"cli"}}',
                '{"timestamp":"2026-08-16T11:00:10Z","type":"event_msg","payload":{"type":"task_complete","turn_id":"turn-good"}}',
                '{"timestamp":"2026-08-16T11:00:20Z","type":"event_msg","payload":{"type":"task_complete","turn_id":""}}',
            )
        )
        + "\n",
        encoding="utf-8",
    )
    invalid_utf8 = root / "sessions" / "invalid-utf8.jsonl"
    invalid_utf8.write_bytes(
        b'{"timestamp":"2026-08-16T12:00:00Z","type":"session_meta","payload":{"id":"rollout-utf8","session_id":"task-utf8","source":"cli"}}\n'
        b'{"type":"response_item","payload":{"content":"\xff"}}\n'
        b'{"timestamp":"2026-08-16T12:01:00Z","type":"event_msg","payload":{"type":"task_complete","turn_id":"turn-utf8"}}\n'
    )

    batch = CodexSourceAdapter(root).discover(None, _window())
    keys = {(ref.key.task_id, ref.key.revision_id) for ref in batch.revisions}

    assert not ({("task-malformed", "turn-malformed"), ("task-critical", "turn-good"), ("task-utf8", "turn-utf8")} & keys)
    assert {"source_malformed", "unknown_completion_shape", "source_unreadable"} <= set(
        batch.diagnostic_codes
    )


def test_probe_revalidates_repeated_metadata_and_identity_ignores_path_hints(tmp_path: Path):
    from agc_runtime.codex_source_adapter import CodexSourceAdapter

    root = _profile(tmp_path)
    adapter = CodexSourceAdapter(root)
    before = next(
        ref for ref in adapter.discover(None, _window()).revisions if ref.key.revision_id == "turn-2"
    )
    source = root / before.locator
    original_stat = source.stat()
    os.utime(source, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns + 10_000_000))
    after_mtime = next(
        ref for ref in adapter.discover(None, _window()).revisions if ref.key.revision_id == "turn-2"
    )
    assert after_mtime.key == before.key

    with source.open("a", encoding="utf-8", newline="") as handle:
        handle.write(
            '{"timestamp":"2026-08-10T10:07:00Z","type":"response_item","payload":{"content":"changed last message"}}\n'
        )
    after_message = next(
        ref for ref in adapter.discover(None, _window()).revisions if ref.key.revision_id == "turn-2"
    )
    assert after_message.key == before.key

    with source.open("a", encoding="utf-8", newline="") as handle:
        handle.write(
            '{"timestamp":"2026-08-10T10:08:00Z","type":"session_meta","payload":{"id":"rollout-main","session_id":"different-task","source":"cli"}}\n'
        )
    probe = adapter.probe(before)
    assert (probe.source_kind, probe.completion_state, probe.diagnostic_code) == (
        "unknown",
        "unreadable",
        "source_identity_mismatch",
    )
    with pytest.raises(ValueError, match="identity"):
        tuple(adapter._iter_target_turn_records(before))


def test_target_iterator_fails_closed_on_critical_drift_between_validation_and_load(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from agc_runtime.codex_source_adapter import CodexSourceAdapter

    root = _profile(tmp_path)
    adapter = CodexSourceAdapter(root)
    ref = next(
        item for item in adapter.discover(None, _window()).revisions if item.key.revision_id == "turn-2"
    )
    source = root / ref.locator
    original_scan = adapter._scan_file

    def scan_then_drift(path: Path):
        result = original_scan(path)
        with source.open("a", encoding="utf-8", newline="") as handle:
            handle.write(
                '{"timestamp":"2026-08-10T10:09:00Z","type":"event_msg","payload":{"type":"task_complete","turn_id":""}}\n'
            )
        return result

    monkeypatch.setattr(adapter, "_scan_file", scan_then_drift)

    probe = adapter.probe(ref)
    assert (probe.source_kind, probe.completion_state, probe.diagnostic_code) == (
        "unknown",
        "unreadable",
        "source_unreadable",
    )


def test_target_iterator_requires_metadata_during_second_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from agc_runtime.codex_source_adapter import CodexSourceAdapter

    root = _profile(tmp_path)
    adapter = CodexSourceAdapter(root)
    ref = next(
        item for item in adapter.discover(None, _window()).revisions if item.key.revision_id == "turn-2"
    )
    source = root / ref.locator
    original_scan = adapter._scan_file

    def scan_then_remove_metadata(path: Path):
        result = original_scan(path)
        lines = source.read_text(encoding="utf-8").splitlines()
        source.write_text("\n".join(lines[1:]) + "\n", encoding="utf-8")
        return result

    monkeypatch.setattr(adapter, "_scan_file", scan_then_remove_metadata)

    probe = adapter.probe(ref)
    assert (probe.source_kind, probe.completion_state) == ("unknown", "unreadable")
    assert probe.diagnostic_code in {"source_identity_mismatch", "source_unreadable"}


def test_target_iterator_compares_non_target_completions_during_second_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from agc_runtime.codex_source_adapter import CodexSourceAdapter

    root = _profile(tmp_path)
    adapter = CodexSourceAdapter(root)
    ref = next(
        item for item in adapter.discover(None, _window()).revisions if item.key.revision_id == "turn-2"
    )
    source = root / ref.locator
    original_scan = adapter._scan_file

    def scan_then_conflict(path: Path):
        result = original_scan(path)
        with source.open("a", encoding="utf-8", newline="") as handle:
            handle.write(
                '{"timestamp":"2026-08-10T10:09:00Z","type":"event_msg",'
                '"payload":{"type":"task_complete","turn_id":"turn-1"}}\n'
            )
        return result

    monkeypatch.setattr(adapter, "_scan_file", scan_then_conflict)

    probe = adapter.probe(ref)
    assert (probe.source_kind, probe.completion_state, probe.diagnostic_code) == (
        "unknown",
        "unreadable",
        "source_unreadable",
    )


@pytest.mark.parametrize(
    "event_payload",
    (
        '{"type":"task_started","turn_id":""}',
        '{"type":"future_turn_state","turn_id":"bad id"}',
    ),
)
def test_present_invalid_turn_identity_invalidates_the_whole_source(
    tmp_path: Path, event_payload: str
):
    from agc_runtime.codex_source_adapter import CodexSourceAdapter

    root = _profile(tmp_path)
    uncertain = root / "sessions" / "invalid-turn-identity.jsonl"
    uncertain.write_text(
        "\n".join(
            (
                '{"timestamp":"2026-08-17T10:00:00Z","type":"session_meta",'
                '"payload":{"id":"rollout-invalid-turn","session_id":"task-invalid-turn","source":"cli"}}',
                '{"timestamp":"2026-08-17T10:00:10Z","type":"event_msg","payload":'
                + event_payload
                + "}",
                '{"timestamp":"2026-08-17T10:01:00Z","type":"event_msg",'
                '"payload":{"type":"task_complete","turn_id":"turn-valid"}}',
            )
        )
        + "\n",
        encoding="utf-8",
    )

    batch = CodexSourceAdapter(root).discover(None, _window())

    assert ("task-invalid-turn", "turn-valid") not in {
        (ref.key.task_id, ref.key.revision_id) for ref in batch.revisions
    }
    assert "unknown_completion_shape" in batch.diagnostic_codes


def test_same_key_with_different_completion_metadata_fails_closed(tmp_path: Path):
    from agc_runtime.codex_source_adapter import CodexSourceAdapter

    root = _profile(tmp_path)
    archived = root / "archived_sessions" / "main-archived-copy.jsonl"
    archived.write_text(
        archived.read_text(encoding="utf-8").replace(
            '"2026-08-10T10:02:00Z"', '"2026-08-10T10:02:30Z"'
        ),
        encoding="utf-8",
    )

    batch = CodexSourceAdapter(root).discover(None, _window())

    assert ("task-main", "turn-1") not in {
        (ref.key.task_id, ref.key.revision_id) for ref in batch.revisions
    }
    assert "conflicting_revision_identity" in batch.diagnostic_codes


def test_same_key_conflict_is_detected_before_window_filtering(tmp_path: Path):
    from agc_runtime.codex_source_adapter import CodexSourceAdapter

    root = _profile(tmp_path)
    archived = root / "archived_sessions" / "main-archived-copy.jsonl"
    archived.write_text(
        archived.read_text(encoding="utf-8").replace(
            '"2026-08-10T10:02:00Z"', '"2026-07-31T10:02:00Z"'
        ),
        encoding="utf-8",
    )

    batch = CodexSourceAdapter(root).discover(None, _window())

    assert ("task-main", "turn-1") not in {
        (ref.key.task_id, ref.key.revision_id) for ref in batch.revisions
    }
    assert "conflicting_revision_identity" in batch.diagnostic_codes


def test_conflicting_valid_turn_identity_representations_invalidate_source(tmp_path: Path):
    from agc_runtime.codex_source_adapter import CodexSourceAdapter

    root = _profile(tmp_path)
    conflicting = root / "sessions" / "conflicting-turn-representations.jsonl"
    conflicting.write_text(
        "\n".join(
            (
                '{"timestamp":"2026-08-18T10:00:00Z","type":"session_meta",'
                '"payload":{"id":"rollout-representations",'
                '"session_id":"task-representations","source":"cli"}}',
                '{"timestamp":"2026-08-18T10:01:00Z","type":"event_msg",'
                '"payload":{"type":"task_complete","turn_id":"turn-top",'
                '"turn":{"id":"turn-nested"}}}',
            )
        )
        + "\n",
        encoding="utf-8",
    )

    batch = CodexSourceAdapter(root).discover(None, _window())

    assert not {
        (ref.key.task_id, ref.key.revision_id)
        for ref in batch.revisions
        if ref.key.task_id == "task-representations"
    }
    assert "unknown_completion_shape" in batch.diagnostic_codes


def test_target_iterator_rejects_completion_reordered_before_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from agc_runtime.codex_source_adapter import CodexSourceAdapter

    root = _profile(tmp_path)
    adapter = CodexSourceAdapter(root)
    ref = next(
        item for item in adapter.discover(None, _window()).revisions if item.key.revision_id == "turn-2"
    )
    source = root / ref.locator
    original_scan = adapter._scan_file

    def scan_then_reorder(path: Path):
        result = original_scan(path)
        lines = source.read_text(encoding="utf-8").splitlines()
        completion = lines.pop(3)
        source.write_text("\n".join((completion, *lines)) + "\n", encoding="utf-8")
        return result

    monkeypatch.setattr(adapter, "_scan_file", scan_then_reorder)

    probe = adapter.probe(ref)
    assert (probe.source_kind, probe.completion_state, probe.diagnostic_code) == (
        "unknown",
        "unreadable",
        "source_unreadable",
    )
