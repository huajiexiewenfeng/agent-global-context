import json
import os
import socket
import sys
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from agc_runtime.paths import MemoryPaths
from agc_runtime.utf8_io import strict_read_text


def _windows_pid_is_running(pid: int) -> bool:
    import ctypes
    from ctypes import wintypes

    process_query_limited_information = 0x1000
    still_active = 259
    error_access_denied = 5

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    open_process = kernel32.OpenProcess
    open_process.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    open_process.restype = wintypes.HANDLE
    get_exit_code_process = kernel32.GetExitCodeProcess
    get_exit_code_process.argtypes = [wintypes.HANDLE, wintypes.LPDWORD]
    get_exit_code_process.restype = wintypes.BOOL
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [wintypes.HANDLE]
    close_handle.restype = wintypes.BOOL

    handle = open_process(process_query_limited_information, False, pid)
    if not handle:
        return ctypes.get_last_error() == error_access_denied
    try:
        exit_code = wintypes.DWORD()
        if not get_exit_code_process(handle, ctypes.byref(exit_code)):
            return True
        return exit_code.value == still_active
    finally:
        close_handle(handle)


def _pid_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        return _windows_pid_is_running(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except (OSError, OverflowError):
        return False
    return True


def _reclaim_dead_same_host_lock(lock_file: Path) -> bool:
    try:
        current = json.loads(strict_read_text(lock_file))
        pid = current.get("pid")
        host = current.get("host")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    if host != socket.gethostname() or not isinstance(pid, int):
        return False
    if _pid_is_running(pid):
        return False
    stale = lock_file.with_name(f"{lock_file.name}.stale.{uuid.uuid4().hex}")
    try:
        os.replace(lock_file, stale)
        stale.unlink(missing_ok=True)
    except FileNotFoundError:
        pass
    return True


@contextmanager
def root_write_lock(paths: MemoryPaths) -> Iterator[Path]:
    paths.locks.mkdir(parents=True, exist_ok=True)
    lock_file = paths.locks / "write.lock"
    lock_id = uuid.uuid4().hex
    payload = {
        "lock_id": lock_id,
        "pid": os.getpid(),
        "host": socket.gethostname(),
        "acquired_at": datetime.now(timezone.utc).isoformat(),
    }

    for attempt in range(2):
        try:
            descriptor = os.open(lock_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
            break
        except FileExistsError as error:
            if attempt == 0 and _reclaim_dead_same_host_lock(lock_file):
                continue
            raise RuntimeError("active AGC write lock exists") from error

    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, sort_keys=True)
            stream.write("\n")
        yield lock_file
    finally:
        if lock_file.exists():
            try:
                current = json.loads(strict_read_text(lock_file))
            except (UnicodeDecodeError, json.JSONDecodeError):
                current = {}
            if current.get("lock_id") == lock_id:
                lock_file.unlink()


@contextmanager
def capture_write_lock(paths: MemoryPaths) -> Iterator[Path]:
    """Serialize Capture transactions without sharing formal-memory receipts."""
    paths.capture.root.mkdir(parents=True, exist_ok=True)
    lock_file = paths.capture.root / ".writer.lock"
    lock_id = uuid.uuid4().hex
    payload = {
        "lock_id": lock_id, "pid": os.getpid(), "host": socket.gethostname(),
        "acquired_at": datetime.now(timezone.utc).isoformat(),
    }
    for attempt in range(2):
        try:
            descriptor = os.open(lock_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
            break
        except FileExistsError as error:
            if attempt == 0 and _reclaim_dead_same_host_lock(lock_file):
                continue
            raise RuntimeError("active Capture write lock exists") from error
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, sort_keys=True)
            stream.write("\n")
        yield lock_file
    finally:
        if lock_file.exists():
            try:
                current = json.loads(strict_read_text(lock_file))
            except (UnicodeDecodeError, json.JSONDecodeError):
                current = {}
            if current.get("lock_id") == lock_id:
                lock_file.unlink()


@contextmanager
def capture_runner_lock(paths: MemoryPaths) -> Iterator[Path]:
    """Allow at most one long-running Capture model worker per Memory Root."""

    paths.capture.leases.mkdir(parents=True, exist_ok=True)
    lock_file = paths.capture.leases / ".runner.lock"
    lock_id = uuid.uuid4().hex
    payload = {
        "lock_id": lock_id,
        "pid": os.getpid(),
        "host": socket.gethostname(),
        "acquired_at": datetime.now(timezone.utc).isoformat(),
    }
    for attempt in range(2):
        try:
            descriptor = os.open(lock_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
            break
        except FileExistsError as error:
            if attempt == 0 and _reclaim_dead_same_host_lock(lock_file):
                continue
            raise RuntimeError("active Capture runner lock exists") from error
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, sort_keys=True)
            stream.write("\n")
        yield lock_file
    finally:
        if lock_file.exists():
            try:
                current = json.loads(strict_read_text(lock_file))
            except (UnicodeDecodeError, json.JSONDecodeError):
                current = {}
            if current.get("lock_id") == lock_id:
                lock_file.unlink()
