"""Bound scheduled Windows cycles before Task Scheduler's launcher timeout."""

from contextlib import contextmanager
import os
import sys
import threading


@contextmanager
def cycle_deadline(seconds: float = 25 * 60):
    """Terminate the worker and inherited children together on deadline.

    The scheduler stops the command launcher at 30 minutes, which can leave
    the Python worker alive. This earlier deadline lives in the actual worker.
    Interrupted transactions and dead-owner locks use normal Capture recovery.
    """
    if sys.platform != 'win32':
        yield
        return
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel.TerminateJobObject.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    job = kernel.CreateJobObjectW(None, None)
    if not job:
        raise OSError(ctypes.get_last_error(), 'capture_deadline_unavailable')
    if not kernel.AssignProcessToJobObject(job, kernel.GetCurrentProcess()):
        error = ctypes.get_last_error()
        kernel.CloseHandle(job)
        raise OSError(error, 'capture_deadline_unavailable')
    stopped = threading.Event()

    def expire():
        if not stopped.wait(seconds):
            kernel.TerminateJobObject(job, 124)
            os._exit(124)

    watchdog = threading.Thread(target=expire, daemon=True)
    watchdog.start()
    try:
        yield
    finally:
        stopped.set()
        watchdog.join()
        kernel.CloseHandle(job)
