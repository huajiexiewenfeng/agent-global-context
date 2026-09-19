"""Independent Capture evidence must survive missing Trace without changing business."""
import importlib
import json
from datetime import datetime, timezone

import pytest

START = datetime(2026, 9, 11, 1, tzinfo=timezone.utc)
END = datetime(2026, 9, 11, 1, 1, tzinfo=timezone.utc)


def module():
    return importlib.import_module('agc_runtime.metrics_evidence')


def begin(tmp_path, monkeypatch):
    monkeypatch.setenv('AGC_METRICS_EVIDENCE_DIR', str(tmp_path))
    return module().CaptureAttempt.start(action='cycle', started_at=START)


def test_disabled_is_inert(tmp_path, monkeypatch):
    monkeypatch.delenv('AGC_METRICS_EVIDENCE_DIR', raising=False)
    attempt = module().CaptureAttempt.start(action='cycle', started_at=START)
    assert attempt.trace_kwargs == {}
    assert attempt.finish(outcome='completed', trace_status='disabled', finished_at=END) == {}
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('trace_status', ['disabled', 'suppressed', 'unavailable', 'recorded'])
def test_start_and_terminal_are_independent_of_trace(tmp_path, monkeypatch, trace_status):
    attempt = begin(tmp_path, monkeypatch)
    start_file, = tmp_path.glob('*.json')
    before = start_file.read_bytes()
    started = json.loads(before)
    assert started['phase'] == 'started'
    assert started['trace_id'] == attempt.trace_kwargs['trace_id']
    result = attempt.finish(outcome='completed', trace_status=trace_status, finished_at=END,
                            report={'completed_count': 1, 'prompt': 'PRIVATE'})
    assert result['metrics_evidence']['start_status'] == 'recorded'
    assert result['metrics_evidence']['finish_status'] == 'recorded'
    assert start_file.read_bytes() == before
    snapshot = module().read_capture_attempts(tmp_path)
    assert snapshot['status'] == 'available'
    row, = snapshot['attempts']
    assert row['state'] == 'completed'
    assert row['finished']['trace_status'] == trace_status
    assert row['finished']['counts'] == {'completed_count': 1}
    assert 'PRIVATE' not in repr(snapshot)


def test_terminal_cannot_be_overwritten(tmp_path, monkeypatch):
    attempt = begin(tmp_path, monkeypatch)
    attempt.finish(outcome='completed', trace_status='disabled', finished_at=END)
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    result = attempt.finish(outcome='failed', trace_status='unavailable', finished_at=END)
    assert result['metrics_evidence']['finish_status'] == 'unavailable'
    assert before == {p.name: p.read_bytes() for p in tmp_path.iterdir()}


def test_unobserved_and_orphan_not_success(tmp_path, monkeypatch):
    first = begin(tmp_path, monkeypatch)
    second = begin(tmp_path, monkeypatch)
    second.finish(outcome='failed', trace_status='unavailable', error_code='PRIVATE', finished_at=END)
    (tmp_path / (second.attempt_id + '.started.json')).unlink()
    snapshot = module().read_capture_attempts(tmp_path)
    assert {row['state'] for row in snapshot['attempts']} == {'terminal_unobserved', 'orphan_terminal'}
    assert 'PRIVATE' not in repr(snapshot)
    assert first.attempt_id != second.attempt_id


def test_unwritable_or_missing_root_does_not_raise_or_create(tmp_path, monkeypatch):
    missing = tmp_path / 'missing'
    monkeypatch.setenv('AGC_METRICS_EVIDENCE_DIR', str(missing))
    attempt = module().CaptureAttempt.start(action='cycle', started_at=START)
    result = attempt.finish(outcome='completed', trace_status='disabled', finished_at=END)
    assert result['metrics_evidence']['start_status'] == 'unavailable'
    assert result['metrics_evidence']['finish_status'] == 'unavailable'
    assert not missing.exists()


def test_reader_rejects_content_and_wrong_file_binding(tmp_path, monkeypatch):
    attempt = begin(tmp_path, monkeypatch)
    path, = tmp_path.glob('*.json')
    raw = json.loads(path.read_text())
    raw['private'] = 'PRIVATE'
    path.write_text(json.dumps(raw))
    (tmp_path / 'wrong.started.json').write_text(json.dumps({k:v for k,v in raw.items() if k != 'private'}))
    snapshot = module().read_capture_attempts(tmp_path)
    assert snapshot['status'] == 'partial'
    assert snapshot['invalid_records'] == 2
    assert snapshot['attempts'] == []
    assert 'PRIVATE' not in repr(snapshot)


def test_invalid_time_and_action_fail_without_writing(tmp_path, monkeypatch):
    monkeypatch.setenv('AGC_METRICS_EVIDENCE_DIR', str(tmp_path))
    attempt = module().CaptureAttempt.start(action='PRIVATE', started_at=START.replace(tzinfo=None))
    result = attempt.finish(outcome='completed', trace_status='disabled', finished_at=END)
    assert result['metrics_evidence']['start_status'] == 'unavailable'
    assert list(tmp_path.iterdir()) == []


def test_read_missing_is_not_empty_success(tmp_path):
    snapshot = module().read_capture_attempts(tmp_path / 'missing')
    assert snapshot['status'] == 'unavailable'


def test_duplicate_json_fields_are_invalid(tmp_path, monkeypatch):
    begin(tmp_path, monkeypatch)
    path, = tmp_path.glob('*.json')
    text = path.read_text()
    path.write_text(text[:-1] + ',"action":"cycle"}')
    assert module().read_capture_attempts(tmp_path)['invalid_records'] == 1


def test_terminal_write_failure_preserves_start(tmp_path, monkeypatch):
    attempt = begin(tmp_path, monkeypatch)
    def failed_append(*args):
        raise OSError('PRIVATE disk failure')
    monkeypatch.setattr(module(), '_append', failed_append)
    result = attempt.finish(outcome='completed', trace_status='recorded', finished_at=END)
    assert result['metrics_evidence']['start_status'] == 'recorded'
    assert result['metrics_evidence']['finish_status'] == 'unavailable'
    row, = module().read_capture_attempts(tmp_path)['attempts']
    assert row['state'] == 'terminal_unobserved'


def test_version_conflict_is_explicit(tmp_path, monkeypatch):
    attempt = begin(tmp_path, monkeypatch)
    attempt.finish(outcome='completed', trace_status='recorded', finished_at=END)
    path = tmp_path / (attempt.attempt_id + '.finished.json')
    raw = json.loads(path.read_text())
    raw['implementation_version'] = '9.9.9'
    path.write_text(json.dumps(raw))
    row, = module().read_capture_attempts(tmp_path)['attempts']
    assert row['state'] == 'state_conflict'


def test_recorder_does_not_require_python312_path_api(tmp_path, monkeypatch):
    def unavailable_api(*args):
        raise AttributeError('Python 3.10 has no Path.is_junction')
    monkeypatch.setattr(type(tmp_path), 'is_junction', unavailable_api, raising=False)
    attempt = begin(tmp_path, monkeypatch)
    assert attempt.start_status == 'recorded'
