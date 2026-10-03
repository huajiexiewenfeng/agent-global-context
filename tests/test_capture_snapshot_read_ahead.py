import pytest

from agc_runtime.capture_store import CaptureStore
from test_capture_forget import _populated, _revision
from agc_runtime.metrics_research_access import CaptureResearchAccess


@pytest.mark.parametrize('corrupt', [None, 'receipts', 'indexes', 'ledger', 'observations'])
@pytest.mark.parametrize('valid_name', [False, True])
def test_read_ahead_preserves_full_snapshot_and_corruption(tmp_path, corrupt, valid_name):
    paths, _, receipt, _ = _populated(tmp_path)
    if corrupt:
        directory = getattr(paths.capture, corrupt)
        target = next(directory.glob('*.json')) if valid_name else directory / 'invalid.json'
        target.write_text('{', encoding='utf-8')
    store = CaptureStore(paths)
    expected = store.read_snapshot()
    assert store.read_snapshot(read_workers=8) == expected
    if corrupt:
        assert expected.integrity_state != 'healthy'
        with pytest.raises(ValueError):
            CaptureResearchAccess(paths).check(_revision(receipt.key))


def test_metrics_requests_bounded_parallel_snapshot(tmp_path, monkeypatch):
    paths, _, receipt, _ = _populated(tmp_path)
    original = CaptureStore.read_snapshot
    workers = []
    def measured(self, **kwargs):
        workers.append(kwargs.get('read_workers', 1))
        return original(self, **kwargs)
    monkeypatch.setattr(CaptureStore, 'read_snapshot', measured)
    CaptureResearchAccess(paths).check(_revision(receipt.key))
    assert workers == [8]


def test_read_ahead_is_bounded_and_exception_is_not_hidden(tmp_path):
    from agc_runtime.capture_snapshot_io import SnapshotJsonReader
    from agc_runtime.capture_transaction import read_json
    paths = [tmp_path / f'{i}.json' for i in range(20)]
    for index, path in enumerate(paths):
        path.write_text('{' if index == 7 else '{"value": 1}', encoding='utf-8')
    with SnapshotJsonReader(read_json, 2) as reader:
        reader.prime(paths)
        for index, path in enumerate(paths):
            assert len(reader._pending) <= 4
            if index == 7:
                with pytest.raises(ValueError):
                    reader.read(path)
            else:
                assert reader.read(path) == {'value': 1}
    assert not reader._pending


def test_parallel_reads_overlap_and_are_joined_on_exit(tmp_path):
    import threading
    from agc_runtime.capture_snapshot_io import SnapshotJsonReader
    from agc_runtime.capture_transaction import read_json
    paths = [tmp_path / f'{i}.json' for i in range(4)]
    for path in paths:
        path.write_text('{}', encoding='utf-8')
    started = threading.Barrier(3)
    release = threading.Event()
    calls = []
    guard = threading.Lock()
    def read(path):
        with guard:
            calls.append(path)
            first_pair = len(calls) <= 2
        if first_pair:
            started.wait(timeout=5)
            assert release.wait(timeout=5)
        return read_json(path)
    with SnapshotJsonReader(read, 2) as reader:
        reader.prime(paths)
        try:
            started.wait(timeout=5)
            assert len(calls) == 2
        finally:
            release.set()
        assert [reader.read(path) for path in paths] == [{}, {}, {}, {}]
    assert len(calls) == 4


def _two_census_runs(tmp_path):
    from agc_runtime.capture_source import SourceBindingKey, TimeWindow
    paths, store, receipt, _ = _populated(tmp_path)
    store = CaptureStore(paths, clock=lambda: '2026-08-14T12:00:00Z')
    for day in (13, 14):
        store.freeze_census(
            binding=SourceBindingKey(1, receipt.adapter_id, receipt.source_root_id),
            window=TimeWindow(1, f'2026-08-{day - 7:02d}T12:00:00Z',
                              f'2026-08-{day:02d}T12:00:00Z'),
            started_at=f'2026-08-{day:02d}T12:00:00Z',
            revisions=(_revision(receipt.key),),
        )
    return paths, store, receipt


def test_snapshot_census_reads_overlap_and_join_before_unlock(tmp_path, monkeypatch):
    import threading
    from concurrent.futures import ThreadPoolExecutor
    paths, store, _ = _two_census_runs(tmp_path)
    expected = store.read_snapshot()
    original = CaptureStore._read_census_run_manifest
    pair_started = threading.Barrier(3)
    release = threading.Event()
    active = set()
    guard = threading.Lock()

    def measured(self, path):
        with guard:
            active.add(path)
        try:
            pair_started.wait(timeout=2)
            assert release.wait(timeout=5)
            return original(self, path)
        finally:
            with guard:
                active.remove(path)

    monkeypatch.setattr(CaptureStore, '_read_census_run_manifest', measured)
    with ThreadPoolExecutor(max_workers=1) as caller:
        result = caller.submit(store.read_snapshot, read_workers=8)
        try:
            pair_started.wait(timeout=2)
            assert (paths.capture.root / '.writer.lock').exists()
            assert len(active) == 2
        finally:
            release.set()
        assert result.result(timeout=5) == expected
    assert not active
    assert not (paths.capture.root / '.writer.lock').exists()


@pytest.mark.parametrize('defect', ['invalid_json', 'missing_members', 'wrong_id'])
def test_parallel_census_preserves_corruption_denial(tmp_path, defect):
    import json
    paths, store, receipt = _two_census_runs(tmp_path)
    run = sorted((paths.capture.root / 'census-runs').iterdir())[0]
    if defect == 'invalid_json':
        (run / 'run.json').write_text('{', encoding='utf-8')
    elif defect == 'missing_members':
        (run / 'members').rename(run / 'moved-members')
    else:
        value = json.loads((run / 'run.json').read_text(encoding='utf-8'))
        value['census_id'] = 'invalid'
        (run / 'run.json').write_text(json.dumps(value), encoding='utf-8')
    expected = store.read_snapshot()
    assert expected.integrity_state != 'healthy'
    assert store.read_snapshot(read_workers=8) == expected
    with pytest.raises(ValueError):
        CaptureResearchAccess(paths).check(_revision(receipt.key))
