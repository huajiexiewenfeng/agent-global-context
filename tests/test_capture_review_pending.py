"""Preview dispatch is neither a review outcome nor formal-memory approval."""
import json

import pytest

from agc_runtime.capture_review_notification import capture_review_status, record_capture_review_notice
from agc_runtime.capture_store import CaptureStore
from agc_runtime.paths import MemoryPaths
from tests.test_capture_review_notification import NOW, _seed


def test_delivered_preview_advances_queue_without_reviewing_observations(tmp_path):
    paths = MemoryPaths.from_root(tmp_path / 'memory')
    _seed(paths, 20, oldest_hours=48)
    first = capture_review_status(paths, now=NOW)
    record_capture_review_notice(paths, first['batch_digest'], now=NOW,
                                 batch_observation_ids=first['batch_observation_ids'])
    later = capture_review_status(paths, now='2026-09-01T12:00:00Z')
    assert later['unreviewed_count'] == 20
    assert later['pending_confirmation_count'] == 10
    assert later['undispatched_count'] == 10
    assert not set(first['batch_observation_ids']) & set(later['batch_observation_ids'])
    assert later['should_notify'] is True
    assert CaptureStore(paths).read_review_snapshot().review_receipts == ()
    assert capture_review_status(paths, now=NOW)['should_notify'] is False


def test_repeated_delivery_is_idempotent_and_pending_only_is_not_new_work(tmp_path):
    paths = MemoryPaths.from_root(tmp_path / 'memory')
    _seed(paths, 10)
    batch = capture_review_status(paths, now=NOW)
    first = record_capture_review_notice(paths, batch['batch_digest'], now=NOW,
                                        batch_observation_ids=batch['batch_observation_ids'])
    second = record_capture_review_notice(paths, batch['batch_digest'], now='2026-09-02T12:00:00Z',
                                         batch_observation_ids=batch['batch_observation_ids'])
    assert first == second
    status = capture_review_status(paths, now='2026-09-02T12:00:00Z')
    assert status['ready_reason'] == 'awaiting_confirmation'
    assert status['unreviewed_count'] == status['pending_confirmation_count'] == 10
    assert status['batch_observation_ids'] == []
    assert status['should_notify'] is False


@pytest.mark.parametrize('change', ['digest', 'duplicate', 'unknown'])
def test_dispatch_binding_rejects_invalid_batches_without_writes(tmp_path, change):
    paths = MemoryPaths.from_root(tmp_path / 'memory')
    _seed(paths, 10)
    batch = capture_review_status(paths, now=NOW)
    ids, digest = batch['batch_observation_ids'], batch['batch_digest']
    if change == 'digest':
        digest = 'f' * 64
    elif change == 'duplicate':
        ids = [ids[0], ids[0]]
    else:
        from agc_runtime.capture_review_notification import _batch_digest
        ids = ['co_' + 'f' * 64]
        digest = _batch_digest(ids)
    with pytest.raises(ValueError):
        record_capture_review_notice(paths, digest, now=NOW, batch_observation_ids=ids)
    assert not (paths.cache / 'capture-review-pending').exists()


def test_corrupt_pending_state_fails_closed_instead_of_redispatching(tmp_path):
    paths = MemoryPaths.from_root(tmp_path / 'memory')
    _seed(paths, 10)
    directory = paths.cache / 'capture-review-pending'
    directory.mkdir(parents=True)
    (directory / ('f' * 64 + '.json')).write_text('{}', encoding='utf-8')
    status = capture_review_status(paths, now=NOW)
    assert status['should_notify'] is False
    assert status['ready_reason'] == 'pending_state_invalid'
    assert status['batch_observation_ids'] == []


@pytest.mark.parametrize('shape', ['file', 'wrong_extension'])
def test_pending_namespace_damage_fails_closed(tmp_path, shape):
    paths = MemoryPaths.from_root(tmp_path / 'memory')
    _seed(paths, 10)
    directory = paths.cache / 'capture-review-pending'
    paths.cache.mkdir(parents=True, exist_ok=True)
    if shape == 'file':
        directory.write_text('{}', encoding='utf-8')
    else:
        directory.mkdir()
        (directory / 'lost.txt').write_text('{}', encoding='utf-8')
    status = capture_review_status(paths, now=NOW)
    assert status['should_notify'] is False
    assert status['ready_reason'] == 'pending_state_invalid'


def test_valid_but_unselected_subset_cannot_skip_review(tmp_path):
    from agc_runtime.capture_review_notification import _batch_digest
    paths = MemoryPaths.from_root(tmp_path / 'memory')
    _seed(paths, 10)
    ids = capture_review_status(paths, now=NOW)['batch_observation_ids'][:1]
    with pytest.raises(ValueError, match='capture_review_batch_stale'):
        record_capture_review_notice(paths, _batch_digest(ids), now=NOW, batch_observation_ids=ids)
