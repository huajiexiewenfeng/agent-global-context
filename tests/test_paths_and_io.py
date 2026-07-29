from pathlib import Path
import json
import socket

import pytest

from agc_runtime.locking import root_write_lock
from agc_runtime.paths import MemoryPaths
from agc_runtime.utf8_io import atomic_write_text, strict_read_text


def test_memory_paths_reject_escape(tmp_path: Path):
    paths = MemoryPaths.from_root(tmp_path / "memory")

    with pytest.raises(ValueError, match="outside memory root"):
        paths.resolve_managed("../escape.md")


def test_atomic_write_is_utf8_without_bom(tmp_path: Path):
    target = tmp_path / "记忆.md"

    atomic_write_text(target, "做难而正确的事情\n")

    raw = target.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert b"\r\n" not in raw
    assert strict_read_text(target) == "做难而正确的事情\n"


def test_strict_read_rejects_invalid_utf8(tmp_path: Path):
    target = tmp_path / "broken.md"
    target.write_bytes(b"\xff")

    with pytest.raises(UnicodeDecodeError):
        strict_read_text(target)


def test_root_write_lock_is_visible_then_released(tmp_path: Path):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    lock_file = paths.locks / "write.lock"

    with root_write_lock(paths):
        assert lock_file.is_file()

    assert not lock_file.exists()


def test_root_write_lock_rejects_second_writer(tmp_path: Path):
    paths = MemoryPaths.from_root(tmp_path / "memory")

    with root_write_lock(paths):
        with pytest.raises(RuntimeError, match="active AGC write lock"):
            with root_write_lock(paths):
                pass


def test_root_write_lock_reclaims_same_host_dead_pid(tmp_path: Path):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    paths.locks.mkdir(parents=True)
    lock_file = paths.locks / "write.lock"
    lock_file.write_text(
        json.dumps(
            {
                "lock_id": "stale",
                "pid": 2_147_483_647,
                "host": socket.gethostname(),
                "acquired_at": "2026-01-01T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )

    with root_write_lock(paths):
        assert "stale" not in lock_file.read_text(encoding="utf-8")

    assert not lock_file.exists()


def test_root_write_lock_does_not_reclaim_foreign_host(tmp_path: Path):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    paths.locks.mkdir(parents=True)
    (paths.locks / "write.lock").write_text(
        json.dumps(
            {
                "lock_id": "foreign",
                "pid": 2_147_483_647,
                "host": "another-host",
                "acquired_at": "2026-01-01T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="active AGC write lock"):
        with root_write_lock(paths):
            pass
