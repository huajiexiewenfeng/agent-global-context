from __future__ import annotations

import json
from pathlib import Path
import pytest

from agc_runtime.capture_scanner import CaptureScanner
from agc_runtime.capture_store import CaptureStore
from agc_runtime.codex_source_adapter import CodexSourceAdapter
from agc_runtime.paths import MemoryPaths
from agc_runtime.capture_transaction import atomic_write_json
from agc_runtime.capture_source import SourceBindingKey
from agc_runtime.capture_source_cache import cache_path


def _source(root: Path, name: str, *, task: str, turn: str, day: str = "2026-10-03") -> Path:
    path = root / "sessions" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    records = (
        {"timestamp": f"{day}T00:00:00Z", "type": "session_meta", "payload": {"id": f"rollout-{task}", "session_id": task, "source": "cli"}},
        {"timestamp": f"{day}T00:01:00Z", "type": "event_msg", "payload": {"type": "task_complete", "turn_id": turn}},
    )
    path.write_text("".join(json.dumps(item) + "\n" for item in records), encoding="utf-8")
    return path


def _scan(paths: MemoryPaths, root: Path, started: str, *, force_full: bool = False):
    adapter = CodexSourceAdapter(root)
    parsed: list[str] = []
    original = adapter._scan_file

    def counted(path: Path):
        parsed.append(path.name)
        return original(path)

    adapter._scan_file = counted
    report = CaptureScanner(CaptureStore(paths, clock=lambda: started), (adapter,)).scan(
        run_started_at=started, force_full=force_full
    )
    return report, parsed


def test_reinstantiated_warm_scan_reuses_only_unchanged_metadata(tmp_path: Path):
    root = tmp_path / "codex"
    paths = MemoryPaths.from_root(tmp_path / "memory")
    _source(root, "a.jsonl", task="task-a", turn="turn-a")
    _source(root, "b.jsonl", task="task-b", turn="turn-b")
    started = "2026-10-04T12:00:00Z"

    cold, cold_parsed = _scan(paths, root, started)
    warm, warm_parsed = _scan(paths, root, "2026-10-04T12:01:00Z")

    assert set(cold_parsed) == {"a.jsonl", "b.jsonl"}
    assert warm_parsed == []
    assert cold.known_key_count == warm.known_key_count == 2
    assert cold.accounted_key_count == warm.accounted_key_count == 2
    assert cold.advanced_hint_count == warm.advanced_hint_count == 1


def test_changed_and_new_files_reparse_without_losing_unchanged_revisions(tmp_path: Path):
    root = tmp_path / "codex"
    paths = MemoryPaths.from_root(tmp_path / "memory")
    changed = _source(root, "a.jsonl", task="task-a", turn="turn-a")
    _source(root, "b.jsonl", task="task-b", turn="turn-b")
    _scan(paths, root, "2026-10-04T12:00:00Z")
    with changed.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"timestamp": "2026-10-03T00:02:00Z", "type": "event_msg", "payload": {"type": "task_complete", "turn_id": "turn-a2"}}) + "\n")
    _source(root, "c.jsonl", task="task-c", turn="turn-c")

    report, parsed = _scan(paths, root, "2026-10-04T12:01:00Z")

    assert set(parsed) == {"a.jsonl", "c.jsonl"}
    assert report.known_key_count == report.accounted_key_count == 4


def test_matching_dirty_marker_reparses_only_its_locator(tmp_path: Path):
    root = tmp_path / "codex"
    paths = MemoryPaths.from_root(tmp_path / "memory")
    _source(root, "a.jsonl", task="task-a", turn="turn-a")
    _source(root, "b.jsonl", task="task-b", turn="turn-b")
    _scan(paths, root, "2026-10-04T12:00:00Z")
    descriptor = CodexSourceAdapter(root).describe()
    marker = paths.capture.dirty / "dirty-a.json"
    atomic_write_json(marker, {"schema_version": 1, "adapter_id": "codex", "adapter_version": descriptor.adapter_version, "source_schema_version": descriptor.source_schema_version, "source_root_id": descriptor.source_root_id, "task_id": "task-a", "revision_id": "turn-a", "locator": "sessions/a.jsonl", "observed_at": "2026-10-04T12:00:30Z", "hook_event": "Stop"})

    report, parsed = _scan(paths, root, "2026-10-04T12:01:00Z")

    assert parsed == ["a.jsonl"]
    assert report.known_key_count == report.accounted_key_count == 2
    assert report.acknowledged_marker_count == 1
    assert not marker.exists()


@pytest.mark.parametrize("corruption", ["version", "root", "digest"])
def test_corrupt_snapshot_and_force_full_reparse_all_files(tmp_path: Path, corruption: str):
    root = tmp_path / "codex"
    paths = MemoryPaths.from_root(tmp_path / "memory")
    _source(root, "a.jsonl", task="task-a", turn="turn-a")
    _scan(paths, root, "2026-10-04T12:00:00Z")
    descriptor = CodexSourceAdapter(root).describe()
    binding = SourceBindingKey(1, "codex", descriptor.source_root_id)
    state = CaptureStore(paths).load_scan_state(binding=binding, lookback_started_at="2026-09-27T12:00:00Z")
    assert state.hint is not None
    path = cache_path(paths.capture.root / "source-cache", descriptor.source_root_id, state.hint.opaque_value)
    value = json.loads(path.read_text(encoding="utf-8"))
    if corruption == "version":
        value["version"] = "invalid-version"
    elif corruption == "root":
        value["source_root_id"] = "0" * 64
    else:
        value["entries"]["sessions/a.jsonl"]["signature"][2] += 1
    path.write_text(json.dumps(value), encoding="utf-8")

    report, parsed = _scan(paths, root, "2026-10-04T12:01:00Z")
    full, full_parsed = _scan(paths, root, "2026-10-04T12:02:00Z", force_full=True)

    assert parsed == ["a.jsonl"]
    assert full_parsed == ["a.jsonl"]
    assert report.known_key_count == full.known_key_count == 1


def test_truncate_replace_and_partial_tail_reparse_changed_locator(tmp_path: Path):
    root = tmp_path / "codex"
    paths = MemoryPaths.from_root(tmp_path / "memory")
    source = _source(root, "a.jsonl", task="task-a", turn="turn-a")
    _source(root, "b.jsonl", task="task-b", turn="turn-b")
    _scan(paths, root, "2026-10-04T12:00:00Z")
    source.write_text(source.read_text(encoding="utf-8").splitlines(keepends=True)[0], encoding="utf-8")
    truncated, truncated_parsed = _scan(paths, root, "2026-10-04T12:01:00Z")
    assert truncated_parsed == ["a.jsonl"]
    assert truncated.advanced_hint_count == 1
    _source(root, "a.jsonl", task="task-replacement", turn="turn-replacement")
    replaced, replaced_parsed = _scan(paths, root, "2026-10-04T12:02:00Z")
    assert replaced_parsed == ["a.jsonl"]
    assert replaced.accounted_key_count == 3  # Two durable keys plus replacement.
    with source.open("a", encoding="utf-8") as handle:
        handle.write('{"timestamp":"2026-10-03T00:03:00Z"')
    partial, partial_parsed = _scan(paths, root, "2026-10-04T12:03:00Z")
    repeated, repeated_parsed = _scan(paths, root, "2026-10-04T12:04:00Z")
    assert partial_parsed == repeated_parsed == ["a.jsonl"]
    assert partial.advanced_hint_count == repeated.advanced_hint_count == 0


def test_adapter_version_change_invalidates_snapshot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "codex"
    paths = MemoryPaths.from_root(tmp_path / "memory")
    _source(root, "a.jsonl", task="task-a", turn="turn-a")
    _scan(paths, root, "2026-10-04T12:00:00Z")
    monkeypatch.setattr(CodexSourceAdapter, "adapter_version", "2.0")

    report, parsed = _scan(paths, root, "2026-10-04T12:01:00Z")

    assert parsed == ["a.jsonl"]
    assert report.known_key_count == 1
    assert report.advanced_hint_count == 0  # Version conflict stays fail-closed.


def test_mismatched_checkpoint_hint_root_falls_back_without_skipping(tmp_path: Path):
    root = tmp_path / "codex"
    paths = MemoryPaths.from_root(tmp_path / "memory")
    _source(root, "a.jsonl", task="task-a", turn="turn-a")
    _scan(paths, root, "2026-10-04T12:00:00Z")
    state_path, = paths.capture.scan_state.glob("state-*.json")
    value = json.loads(state_path.read_text(encoding="utf-8"))
    value["hint"]["source_root_id"] = "0" * 64
    state_path.write_text(json.dumps(value), encoding="utf-8")

    report, parsed = _scan(paths, root, "2026-10-04T12:01:00Z")

    assert parsed == ["a.jsonl"]
    assert report.accounted_key_count == 1
    assert report.advanced_hint_count == 0


def test_unencodable_cache_metadata_falls_back_to_reparse(tmp_path: Path):
    root = tmp_path / "codex"
    paths = MemoryPaths.from_root(tmp_path / "memory")
    _source(root, "a.jsonl", task="task-a", turn="turn-a")
    _scan(paths, root, "2026-10-04T12:00:00Z")
    descriptor = CodexSourceAdapter(root).describe()
    binding = SourceBindingKey(1, "codex", descriptor.source_root_id)
    state = CaptureStore(paths).load_scan_state(binding=binding, lookback_started_at="2026-09-27T12:00:00Z")
    assert state.hint is not None
    path = cache_path(paths.capture.root / "source-cache", descriptor.source_root_id, state.hint.opaque_value)
    value = json.loads(path.read_text(encoding="utf-8"))
    value["entries"]["sessions/\ud800.jsonl"] = value["entries"].pop("sessions/a.jsonl")
    path.write_text(json.dumps(value, ensure_ascii=True), encoding="utf-8")

    report, parsed = _scan(paths, root, "2026-10-04T12:01:00Z")

    assert parsed == ["a.jsonl"]
    assert report.accounted_key_count == 1


def test_rolling_window_and_archive_move_keep_complete_census(tmp_path: Path):
    root = tmp_path / "codex"
    paths = MemoryPaths.from_root(tmp_path / "memory")
    moved = _source(root, "old.jsonl", task="task-old", turn="turn-old", day="2026-10-01")
    _source(root, "fresh.jsonl", task="task-fresh", turn="turn-fresh", day="2026-10-03")
    first, _ = _scan(paths, root, "2026-10-04T12:00:00Z")
    archive = root / "archived_sessions" / moved.name
    archive.parent.mkdir(parents=True)
    moved.rename(archive)

    second, parsed = _scan(paths, root, "2026-10-04T12:01:00Z")
    later, later_parsed = _scan(paths, root, "2026-10-09T12:00:00Z")

    assert first.known_key_count == second.known_key_count == 2
    assert parsed == ["old.jsonl"]
    assert later_parsed == []
    assert later.window.start_at == "2026-10-02T12:00:00Z"
    assert later.known_key_count == later.accounted_key_count == 2  # Durable prior Census remains known.
    adapter = CodexSourceAdapter(root, metadata_cache_root=paths.capture.root / "source-cache")
    binding = SourceBindingKey(1, "codex", adapter.describe().source_root_id)
    hint = CaptureStore(paths).load_scan_state(binding=binding, lookback_started_at=later.window.start_at).hint
    assert hint is not None
    assert [item.key.task_id for item in adapter.discover(hint, later.window).revisions] == ["task-fresh"]


@pytest.mark.parametrize("crash_at", ["after:source-cache:publish", "after:scan-state:publish"])
def test_crash_checkpoint_boundary_never_skips_uncommitted_change(tmp_path: Path, crash_at: str):
    root = tmp_path / "codex"
    paths = MemoryPaths.from_root(tmp_path / "memory")
    source = _source(root, "a.jsonl", task="task-a", turn="turn-a")
    _scan(paths, root, "2026-10-04T12:00:00Z")
    with source.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"timestamp": "2026-10-03T00:02:00Z", "type": "event_msg", "payload": {"type": "task_complete", "turn_id": "turn-a2"}}) + "\n")
    adapter = CodexSourceAdapter(root)
    store = CaptureStore(paths, crash_at=crash_at, clock=lambda: "2026-10-04T12:05:00Z")
    with pytest.raises(RuntimeError, match="injected crash"):
        CaptureScanner(store, (adapter,)).scan(run_started_at="2026-10-04T12:01:00Z")
    binding = SourceBindingKey(1, "codex", adapter.describe().source_root_id)
    state = CaptureStore(paths).load_scan_state(binding=binding, lookback_started_at="2026-09-27T12:00:00Z")

    recovered, parsed = _scan(paths, root, "2026-10-04T12:02:00Z")

    assert state.last_scan_at == ("2026-10-04T12:00:00Z" if crash_at == "after:source-cache:publish" else "2026-10-04T12:01:00Z")
    assert parsed == (["a.jsonl"] if crash_at == "after:source-cache:publish" else [])
    assert recovered.known_key_count == recovered.accounted_key_count == 2


def test_source_change_during_parse_does_not_publish_checkpoint(tmp_path: Path):
    root = tmp_path / "codex"
    paths = MemoryPaths.from_root(tmp_path / "memory")
    source = _source(root, "a.jsonl", task="task-a", turn="turn-a")
    adapter = CodexSourceAdapter(root)
    original = adapter._scan_file

    def changing(path: Path):
        result = original(path)
        with path.open("a", encoding="utf-8") as handle:
            handle.write("\n")
        return result

    adapter._scan_file = changing
    report = CaptureScanner(CaptureStore(paths, clock=lambda: "2026-10-04T12:05:00Z"), (adapter,)).scan(run_started_at="2026-10-04T12:00:00Z")

    assert report.advanced_hint_count == 0
    assert report.source_health == "degraded"
    assert source.is_file()
    recovered, parsed = _scan(paths, root, "2026-10-04T12:01:00Z")
    assert parsed == ["a.jsonl"]
    assert recovered.accounted_key_count == 1


def _forget_revision(paths, root):
    from agc_runtime.write_service import dispatch_write
    result = dispatch_write(paths, {
        "action": "capture_forget", "authorization": "explicit_user_request",
        "target": {"type": "revision", "adapter_id": "codex",
                   "source_root_id": CodexSourceAdapter(root).describe().source_root_id,
                   "task_id": "task-a", "revision_id": "turn-a"},
    })
    assert result.status == "accepted", result


@pytest.mark.parametrize("invalidation", ["forget", "restore"])
def test_cold_scanner_cannot_publish_after_invalidation(tmp_path, monkeypatch, invalidation):
    from agc_runtime.admin_service import dispatch_admin
    root = tmp_path / "codex"
    paths = MemoryPaths.from_root(tmp_path / "memory")
    _source(root, "a.jsonl", task="task-a", turn="turn-a")
    store = CaptureStore(paths, clock=lambda: "2026-10-04T12:00:00Z")
    if invalidation == "restore":
        assert dispatch_admin(paths, {"action": "init"}).status == "accepted"
    original = store.advance_scan_state

    def invalidate_then_publish(**kwargs):
        if invalidation == "forget":
            _forget_revision(paths, root)
        else:
            backup = dispatch_admin(paths, {"action": "backup"})
            assert backup.status == "accepted", backup
            restored = dispatch_admin(paths, {"action": "restore", "backup_path": backup.data["backup_path"]})
            assert restored.status == "accepted", restored
        return original(**kwargs)

    monkeypatch.setattr(store, "advance_scan_state", invalidate_then_publish)
    report = CaptureScanner(store, (CodexSourceAdapter(root),)).scan(run_started_at="2026-10-04T12:00:00Z")
    assert report.advanced_hint_count == 0
    assert not list((paths.capture.root / "source-cache").rglob("*.json"))
    assert not list(paths.capture.scan_state.glob("*.json"))


def test_fresh_scans_after_forget_omit_entire_affected_cache_entry(tmp_path):
    root = tmp_path / "codex"
    paths = MemoryPaths.from_root(tmp_path / "memory")
    source = _source(root, "task-a.jsonl", task="task-a", turn="turn-a")
    _source(root, "b.jsonl", task="task-b", turn="turn-b")
    _scan(paths, root, "2026-10-04T12:00:00Z")
    _forget_revision(paths, root)
    before = source.read_bytes()
    for minute in (1, 2):
        report, parsed = _scan(paths, root, f"2026-10-04T12:0{minute}:00Z")
        assert report.advanced_hint_count == 1
        assert "task-a.jsonl" in parsed
        snapshots = list((paths.capture.root / "source-cache").rglob("*.json"))
        assert snapshots
        for path in snapshots:
            data = path.read_text(encoding="utf-8")
            assert "task-a" not in data
            assert "turn-a" not in data
            assert "task-b" in data
    assert source.read_bytes() == before


def _snapshot_fixture(tmp_path):
    from agc_runtime.capture_source import ScanHint
    from agc_runtime.capture_source_cache import CACHE_VERSION, snapshot_digest
    snapshot = {"version": CACHE_VERSION, "source_root_id": "a" * 64,
                "adapter_version": "1", "source_schema_version": "1", "entries": {}}
    hint = ScanHint(1, "codex", "a" * 64, CACHE_VERSION, snapshot_digest(snapshot))
    return tmp_path / "cache", hint, snapshot


def _directory_link(link, target):
    import os
    import subprocess
    link.parent.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)],
                       check=True, capture_output=True)
    else:
        link.symlink_to(target, target_is_directory=True)


@pytest.mark.parametrize("level", ["root", "parent", "binding"])
@pytest.mark.parametrize("operation", ["read", "publish", "retire"])
def test_cache_rejects_redirected_directories(tmp_path, level, operation):
    from agc_runtime.capture_source_cache import read_snapshot, publish_snapshot_locked, retire_other_snapshots_locked
    root, hint, snapshot = _snapshot_fixture(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    if level == "parent":
        root = tmp_path / "redirect" / "cache"
        _directory_link(root.parent, outside)
    elif level == "root":
        _directory_link(root, outside)
    else:
        _directory_link(root / hint.source_root_id[:16], outside)
    target = cache_path(root, hint.source_root_id, hint.opaque_value)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(snapshot), encoding="utf-8")
    sentinel = target.parent / "sentinel.json"
    sentinel.write_bytes(b"outside sentinel")
    before = {path: path.read_bytes() for path in outside.rglob("*") if path.is_file()}
    if operation == "read":
        assert read_snapshot(root, hint, hint.source_root_id, adapter_version="1", source_schema_version="1") is None
    else:
        with pytest.raises(ValueError, match="unsafe source cache"):
            if operation == "publish":
                publish_snapshot_locked(root, hint, snapshot)
            else:
                retire_other_snapshots_locked(root, hint)
    assert {path: path.read_bytes() for path in outside.rglob("*") if path.is_file()} == before


def test_retirement_preserves_unowned_or_invalid_json(tmp_path):
    from agc_runtime.capture_source_cache import publish_snapshot_locked, retire_other_snapshots_locked
    root, hint, snapshot = _snapshot_fixture(tmp_path)
    publish_snapshot_locked(root, hint, snapshot)
    directory = cache_path(root, hint.source_root_id, hint.opaque_value).parent
    files = [directory / "sentinel.json", directory / (("b" * 64) + ".json")]
    for path in files:
        path.write_bytes(b"not a cache snapshot")
    retire_other_snapshots_locked(root, hint)
    assert all(path.read_bytes() == b"not a cache snapshot" for path in files)


@pytest.mark.parametrize("source_id,digest", [("../outside", "a" * 64), ("a" * 64, "../../escape"), ("\ud800", "a" * 64)])
def test_cache_path_rejects_invalid_identifiers(tmp_path, source_id, digest):
    with pytest.raises(ValueError, match="invalid source cache"):
        cache_path(tmp_path, source_id, digest)


@pytest.mark.parametrize("operation", ["read", "publish", "retire", "epoch"])
def test_cache_rejects_redirected_files(tmp_path, operation):
    from agc_runtime.capture_source_cache import read_snapshot, publish_snapshot_locked, retire_other_snapshots_locked, source_generation_locked
    root, hint, snapshot = _snapshot_fixture(tmp_path)
    outside = tmp_path / "outside.json"
    outside.write_text(json.dumps(snapshot), encoding="utf-8")
    target = root / "source-generation.json" if operation == "epoch" else cache_path(root, hint.source_root_id, hint.opaque_value)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.hardlink_to(outside)
    before = outside.read_bytes()
    if operation == "read":
        assert read_snapshot(root, hint, hint.source_root_id, adapter_version="1", source_schema_version="1") is None
    else:
        with pytest.raises(ValueError, match="unsafe source cache"):
            if operation == "publish":
                publish_snapshot_locked(root, hint, snapshot)
            elif operation == "retire":
                retire_other_snapshots_locked(root, hint)
            else:
                source_generation_locked(root, invalidate=True)
    assert outside.read_bytes() == before
    assert target.samefile(outside)


def test_publication_rejects_mismatched_pending_digest(tmp_path):
    root = tmp_path / "codex"
    paths = MemoryPaths.from_root(tmp_path / "memory")
    _source(root, "a.jsonl", task="task-a", turn="turn-a")
    adapter = CodexSourceAdapter(root)
    original = adapter.pending_metadata_snapshot

    def corrupt(hint):
        snapshot = original(hint)
        snapshot["entries"] = {}
        return snapshot

    adapter.pending_metadata_snapshot = corrupt
    with pytest.raises(ValueError, match="invalid source cache snapshot"):
        CaptureScanner(CaptureStore(paths, clock=lambda: "2026-10-04T12:00:00Z"), (adapter,)).scan(run_started_at="2026-10-04T12:00:00Z")
    assert not list((paths.capture.root / "source-cache").rglob("*.json"))


def test_restore_keeps_capture_lock_through_replacement(tmp_path, monkeypatch):
    from agc_runtime import admin_service
    paths = MemoryPaths.from_root(tmp_path / "memory")
    assert admin_service.dispatch_admin(paths, {"action": "init"}).status == "accepted"
    backup = admin_service.dispatch_admin(paths, {"action": "backup"})
    assert backup.status == "accepted"
    original = admin_service._clear_replaceable_files

    def clear_with_lock(current):
        lock = paths.capture.root / ".writer.lock"
        before = lock.read_bytes()
        original(current)
        assert lock.read_bytes() == before

    monkeypatch.setattr(admin_service, "_clear_replaceable_files", clear_with_lock)
    assert admin_service.dispatch_admin(paths, {"action": "restore", "backup_path": backup.data["backup_path"]}).status == "accepted"
