"""Bounded per-snapshot read-ahead, never an approval/content cache across calls."""
from concurrent.futures import ThreadPoolExecutor


class SnapshotJsonReader:
    def __init__(self, read, workers=1):
        if type(workers) is not int or not 1 <= workers <= 8:
            raise ValueError('invalid_snapshot_read_workers')
        self._read = read
        self._workers = workers
        self._pool = None
        self._pending = {}
        self._paths = iter(())

    def __enter__(self):
        if self._workers > 1:
            self._pool = ThreadPoolExecutor(max_workers=self._workers,
                                            thread_name_prefix='agc-snapshot-read')
        return self

    def __exit__(self, *_):
        if self._pool is not None:
            self._pool.shutdown(wait=True, cancel_futures=True)
        self._pending.clear()
        self._paths = iter(())

    def prime(self, paths):
        if self._pool is None:
            return
        for future in self._pending.values():
            future.cancel()
        self._pending.clear()
        self._paths = iter(paths)
        self._fill()

    def _fill(self):
        if self._pool is None:
            return
        while len(self._pending) < self._workers * 2:
            path = next(self._paths, None)
            if path is None:
                break
            self._pending[path] = self._pool.submit(self._read, path)

    def read(self, path):
        future = self._pending.pop(path, None)
        self._fill()
        # Re-raise at the original reader/validator position. Validation remains
        # ordered on the main thread, including corrupt and missing files.
        return self._read(path) if future is None else future.result()
