"""Contract tests for the metadata-only Codex Stop Hook."""

from __future__ import annotations

import ast
import errno
import io
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
LAST_MESSAGE_SENTINEL = "LAST_MESSAGE_SENTINEL_MUST_NEVER_BE_PERSISTED_7f14"


@pytest.fixture(scope="module", autouse=True)
def _load_capture_hook_modules():
    global capture_dirty, capture_hook
    from agc_runtime import capture_dirty as dirty_module
    from agc_runtime import capture_hook as hook_module

    capture_dirty = dirty_module
    capture_hook = hook_module


def _configure(memory_root: Path, source_root: Path) -> None:
    memory_root.mkdir(parents=True)
    source_root.mkdir(parents=True, exist_ok=True)
    default = (REPOSITORY_ROOT / "agc_runtime" / "default_config.yaml").read_text(
        encoding="utf-8"
    )
    configured = (
        default.replace("enabled: false", "enabled: true")
        .replace("mode: off", "mode: scanner_only")
        .replace("sources: []", f"sources:\n    - {source_root.as_posix()}")
        .replace("  hook:\n    enabled: false", "  hook:\n    enabled: true")
    )
    (memory_root / "config.yaml").write_text(configured, encoding="utf-8")


def _payload(transcript: Path) -> dict[str, object]:
    return {
        "session_id": "session-123",
        "turn_id": "turn-456",
        "transcript_path": str(transcript),
        "cwd": r"C:\private\project",
        "hook_event_name": "Stop",
        "model": "private-model-name",
        "stop_hook_active": True,
        "last_assistant_message": LAST_MESSAGE_SENTINEL,
    }


def _invoke_main(
    monkeypatch: pytest.MonkeyPatch,
    memory_root: Path,
    raw_input: str,
) -> tuple[int, str, str]:
    stdin = io.StringIO(raw_input)
    stdout = io.StringIO()
    stderr = io.StringIO()
    monkeypatch.setattr(sys, "stdin", stdin)
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setattr(sys, "stderr", stderr)
    result = capture_hook.main(["--root", str(memory_root)])
    return result, stdout.getvalue(), stderr.getvalue()


def _marker_files(memory_root: Path) -> list[Path]:
    return sorted((memory_root / ".runtime" / "capture" / "dirty").glob("*.json"))


def _create_directory_alias(link: Path, target: Path) -> None:
    if os.name != "nt":
        link.symlink_to(target, target_is_directory=True)
        return
    completed = subprocess.run(
        ["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, (
        completed.stdout.decode(errors="replace")
        + completed.stderr.decode(errors="replace")
    )


def test_hook_writes_only_validated_metadata_and_never_reads_transcript(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    memory_root = tmp_path / "memory"
    source_root = tmp_path / "codex-home"
    transcript = source_root / "sessions" / "task.jsonl"
    transcript.parent.mkdir(parents=True)
    transcript.write_bytes(b"TRANSCRIPT_CONTENT_MUST_NOT_BE_READ\n")
    _configure(memory_root, source_root)

    real_open = Path.open

    def reject_transcript_open(path: Path, *args, **kwargs):
        if path.resolve() == transcript.resolve():
            raise AssertionError("Hook opened the transcript")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", reject_transcript_open)
    result, stdout, stderr = _invoke_main(
        monkeypatch, memory_root, json.dumps(_payload(transcript))
    )

    assert (result, stdout, stderr) == (0, "", "")
    marker_paths = _marker_files(memory_root)
    assert len(marker_paths) == 1
    marker = json.loads(marker_paths[0].read_text(encoding="utf-8"))
    assert set(marker) == {
        "schema_version",
        "adapter_id",
        "adapter_version",
        "source_schema_version",
        "source_root_id",
        "task_id",
        "revision_id",
        "locator",
        "observed_at",
        "hook_event",
    }
    assert marker["schema_version"] == 1
    assert marker["adapter_id"] == "codex"
    assert marker["adapter_version"] == "1.0"
    assert marker["source_schema_version"] == "codex-v1"
    assert marker["task_id"] == "session-123"
    assert marker["revision_id"] == "turn-456"
    assert marker["locator"] == "sessions/task.jsonl"
    assert marker["hook_event"] == "Stop"
    assert marker["observed_at"].endswith("Z")
    assert len(marker["source_root_id"]) == 64

    marker_text = marker_paths[0].read_text(encoding="utf-8")
    marker_forbidden = (
        str(memory_root),
        str(source_root),
        str(transcript),
        r"C:\private\project",
        "private-model-name",
        "TRANSCRIPT_CONTENT_MUST_NOT_BE_READ",
    )
    assert all(value not in marker_text for value in marker_forbidden)
    for path in memory_root.rglob("*"):
        if path.is_file():
            persisted = path.read_bytes().decode("utf-8", errors="strict")
            assert LAST_MESSAGE_SENTINEL not in persisted, path


@pytest.mark.parametrize(
    "raw_input",
    ["", "{", "[]", '{"hook_event_name":"Stop"}', "\ud800"],
)
def test_malformed_stop_input_is_silent_and_failure_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    raw_input: str,
):
    memory_root = tmp_path / "memory"
    source_root = tmp_path / "codex-home"
    _configure(memory_root, source_root)

    result, stdout, stderr = _invoke_main(monkeypatch, memory_root, raw_input)

    assert (result, stdout, stderr) == (0, "", "")
    assert _marker_files(memory_root) == []


def test_path_escape_is_silent_and_does_not_create_a_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    memory_root = tmp_path / "memory"
    source_root = tmp_path / "codex-home"
    escaped = tmp_path / "outside" / "task.jsonl"
    escaped.parent.mkdir()
    escaped.write_bytes(b"outside\n")
    _configure(memory_root, source_root)

    result, stdout, stderr = _invoke_main(
        monkeypatch, memory_root, json.dumps(_payload(escaped))
    )

    assert (result, stdout, stderr) == (0, "", "")
    assert _marker_files(memory_root) == []


def test_reparse_escape_is_silent_and_does_not_create_a_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    memory_root = tmp_path / "memory"
    source_root = tmp_path / "codex-home"
    sessions = source_root / "sessions"
    sessions.mkdir(parents=True)
    external = tmp_path / "external"
    external.mkdir()
    transcript = external / "task.jsonl"
    transcript.write_bytes(b"outside\n")
    alias = sessions / "escaped"
    _create_directory_alias(alias, external)
    _configure(memory_root, source_root)

    result, stdout, stderr = _invoke_main(
        monkeypatch, memory_root, json.dumps(_payload(alias / transcript.name))
    )

    assert (result, stdout, stderr) == (0, "", "")
    assert _marker_files(memory_root) == []


def test_spool_collision_preserves_the_installed_immutable_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    memory_root = tmp_path / "memory"
    source_root = tmp_path / "codex-home"
    transcript = source_root / "sessions" / "task.jsonl"
    transcript.parent.mkdir(parents=True)
    transcript.write_bytes(b"opaque\n")
    _configure(memory_root, source_root)
    monkeypatch.setattr(capture_dirty, "_nonce_token", lambda: "a" * 32)

    first = _invoke_main(monkeypatch, memory_root, json.dumps(_payload(transcript)))
    installed = _marker_files(memory_root)
    assert len(installed) == 1
    original = installed[0].read_bytes()
    second = _invoke_main(monkeypatch, memory_root, json.dumps(_payload(transcript)))

    assert first == second == (0, "", "")
    assert _marker_files(memory_root) == installed
    assert installed[0].read_bytes() == original


def test_replayed_event_uses_distinct_immutable_marker_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    memory_root = tmp_path / "memory"
    source_root = tmp_path / "codex-home"
    transcript = source_root / "sessions" / "task.jsonl"
    transcript.parent.mkdir(parents=True)
    transcript.write_bytes(b"opaque\n")
    _configure(memory_root, source_root)

    first = _invoke_main(monkeypatch, memory_root, json.dumps(_payload(transcript)))
    second = _invoke_main(monkeypatch, memory_root, json.dumps(_payload(transcript)))

    assert first == second == (0, "", "")
    markers = _marker_files(memory_root)
    assert len(markers) == 2
    assert markers[0].name != markers[1].name
    assert {path.name.split("_")[1] for path in markers} == {
        markers[0].name.split("_")[1]
    }
    assert not list(markers[0].parent.glob("*.tmp"))


@pytest.mark.parametrize(
    "failure",
    [PermissionError(errno.EACCES, "denied"), OSError(errno.ENOSPC, "full")],
    ids=("permission", "disk"),
)
def test_spool_io_failures_are_silent_failure_open_and_leave_no_partial_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: OSError,
):
    memory_root = tmp_path / "memory"
    source_root = tmp_path / "codex-home"
    transcript = source_root / "sessions" / "task.jsonl"
    transcript.parent.mkdir(parents=True)
    transcript.write_bytes(b"opaque\n")
    _configure(memory_root, source_root)
    monkeypatch.setattr(capture_dirty.os, "fsync", lambda _fd: (_ for _ in ()).throw(failure))

    result, stdout, stderr = _invoke_main(
        monkeypatch, memory_root, json.dumps(_payload(transcript))
    )

    assert (result, stdout, stderr) == (0, "", "")
    dirty = memory_root / ".runtime" / "capture" / "dirty"
    assert not dirty.exists() or list(dirty.iterdir()) == []


def test_spool_still_installs_marker_when_fsync_is_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    memory_root = tmp_path / "memory"
    source_root = tmp_path / "codex-home"
    transcript = source_root / "sessions" / "task.jsonl"
    transcript.parent.mkdir(parents=True)
    transcript.write_bytes(b"opaque\n")
    _configure(memory_root, source_root)
    monkeypatch.delattr(capture_dirty.os, "fsync")

    result, stdout, stderr = _invoke_main(
        monkeypatch, memory_root, json.dumps(_payload(transcript))
    )

    assert (result, stdout, stderr) == (0, "", "")
    assert len(_marker_files(memory_root)) == 1


def test_hook_module_has_no_semantic_or_formal_write_dependencies():
    forbidden = {
        "agc_runtime.capture_scanner",
        "agc_runtime.capture_store",
        "agc_runtime.capture_transaction",
        "agc_runtime.mcp_server",
        "agc_runtime.store",
        "agc_runtime.write_service",
    }
    for module_path in (capture_hook.__file__, capture_dirty.__file__):
        assert module_path is not None
        tree = ast.parse(Path(module_path).read_text(encoding="utf-8"))
        imported = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        } | {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module is not None
        }
        assert imported.isdisjoint(forbidden)
        assert all("extractor" not in name for name in imported)


def test_module_cli_is_silent_and_binds_only_the_requested_memory_root(tmp_path: Path):
    requested_root = tmp_path / "requested-memory"
    unrelated_root = tmp_path / "unrelated-memory"
    source_root = tmp_path / "codex-home"
    transcript = source_root / "sessions" / "task.jsonl"
    transcript.parent.mkdir(parents=True)
    transcript.write_bytes(b"opaque\n")
    _configure(requested_root, source_root)
    _configure(unrelated_root, source_root)

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "agc_runtime.capture_hook",
            "--root",
            str(requested_root),
        ],
        cwd=REPOSITORY_ROOT,
        input=json.dumps(_payload(transcript)),
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    assert completed.stdout == completed.stderr == ""
    assert len(_marker_files(requested_root)) == 1
    assert _marker_files(unrelated_root) == []


def test_invalid_operation_form_is_silent_and_failure_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    stdout = io.StringIO()
    stderr = io.StringIO()
    monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setattr(sys, "stderr", stderr)

    assert capture_hook.main([]) == 0
    assert capture_hook.main(["--root", str(tmp_path), "extra"]) == 0
    assert stdout.getvalue() == stderr.getvalue() == ""
    assert list(tmp_path.rglob("*.json")) == []
