"""Nonblocking OS-owned attempt lifetime lock; no PID or elapsed-time guesses.

Only a validated unfinished attempt plus an inactive lock is recoverable. A
missing/invalid lock is unknown. Releasing this lock never fabricates a terminal.
"""
from contextlib import contextmanager
import os
import stat
import sys

from agc_runtime.metrics_evidence import _root,_linked


class AttemptActive(RuntimeError):
    pass


@contextmanager
def attempt_lock(directory,*,create=False):
    root=_root(directory); path=root/'.attempt.lock'
    if not create and (_linked(path) or not stat.S_ISREG(path.stat().st_mode)):
        raise ValueError('attempt_lock_invalid')
    with path.open('x+b' if create else 'r+b') as handle:
        if create:
            handle.write(b'1'); handle.flush(); os.fsync(handle.fileno())
        handle.seek(0)
        try:
            if sys.platform=='win32':
                import msvcrt
                msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError as error:
            raise AttemptActive('attempt_lock_busy_or_unavailable') from error
        try:
            info=os.fstat(handle.fileno()); current=path.stat()
            if (_linked(path) or not stat.S_ISREG(info.st_mode) or info.st_size!=1
                    or (info.st_dev,info.st_ino)!=(current.st_dev,current.st_ino)
                    or handle.read(2)!=b'1'):
                raise ValueError('attempt_lock_invalid_or_changed')
            yield
        finally:
            handle.seek(0)
            if sys.platform=='win32': msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
            else: fcntl.flock(handle.fileno(),fcntl.LOCK_UN)


def attempt_state(directory):
    try:
        with attempt_lock(directory): return 'inactive'
    except AttemptActive: return 'active'
    except (OSError,ValueError): return 'unknown'
