from pathlib import Path
import pytest
from tests.test_capture_store import _receipt
from agc_runtime.capture_store import CaptureStore
from agc_runtime.paths import MemoryPaths


def test_capture_identifier_paths_need_no_filesystem_resolution(tmp_path, monkeypatch):
    store = CaptureStore(MemoryPaths.from_root(tmp_path))
    def forbidden(*args, **kwargs):
        pytest.fail('validated leaf construction must not resolve the same directory twice')
    monkeypatch.setattr(Path, 'resolve', forbidden)
    assert store._receipt_path('cr_' + 'a' * 64) == store.capture.receipts / ('cr_' + 'a' * 64 + '.json')
    for bad in ('../escape', 'cr_../escape', 'cr_' + 'a' * 64 + '/escape'):
        with pytest.raises(ValueError):
            store._receipt_path(bad)


def test_registration_batch_initializes_layout_once(tmp_path, monkeypatch):
    store = CaptureStore(MemoryPaths.from_root(tmp_path))
    original = store._ensure_layout_locked
    calls = []
    def counted():
        calls.append(1)
        return original()
    monkeypatch.setattr(store, '_ensure_layout_locked', counted)
    with store.registration_batch():
        for _ in range(5):
            store.register_extraction(_receipt(status='discovered'))
    assert len(calls) == 1
    assert not (store.capture.root / '.writer.lock').exists()
