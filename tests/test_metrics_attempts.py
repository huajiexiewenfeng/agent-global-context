import json
from datetime import datetime, timezone

from agc_runtime.metrics_evidence import CaptureAttempt, read_capture_attempts
from agc_runtime.metrics_models import freeze_batch, validate_batch, digest
from agc_runtime.metrics_compute import compute_metrics
from agc_runtime.metrics_collect import collect_batch
from agc_runtime.metrics_cli import main

START = '2026-09-11T00:00:00Z'
END = '2026-09-12T00:00:00Z'


def records(tmp_path, monkeypatch, completed=True):
    monkeypatch.setenv('AGC_METRICS_EVIDENCE_DIR', str(tmp_path))
    a = CaptureAttempt.start(action='cycle', started_at=datetime(2026,9,11,1,tzinfo=timezone.utc))
    if completed:
        a.finish(outcome='completed', trace_status='unavailable', finished_at=datetime(2026,9,11,2,tzinfo=timezone.utc))
    return [json.loads(p.read_text()) for p in sorted(tmp_path.glob('*.json'))]


def batch(rows, events=None):
    return freeze_batch(start=START, end=END, cutoff=END, operations=rows, events=events)


def test_independent_attempt_included_without_any_trace(tmp_path, monkeypatch):
    frozen = batch(records(tmp_path, monkeypatch), [])
    assert frozen['schema_version'] == 'agc.metrics-batch.v2'
    assert validate_batch(frozen) == frozen
    result = compute_metrics(frozen)
    assert result['M1']['counts'] == {'completed': 1}
    assert result['M1']['method']['population'] == '窗口内开始的独立 Capture CLI 尝试'
    assert result['M3']['counts'] == {'not_observed': 1}
    assert result['M3']['denominator'] is None


def test_unavailable_trace_is_unchecked_not_missing(tmp_path, monkeypatch):
    result = compute_metrics(batch(records(tmp_path, monkeypatch)))
    assert result['M3']['counts'] == {'unchecked': 1}


def test_start_cohort_and_cutoff(tmp_path, monkeypatch):
    rows = records(tmp_path, monkeypatch)
    rows[0]['timestamp'] = '2026-09-12T01:00:00Z'  # finished sorted first
    result = compute_metrics(batch(rows, []))
    assert result['M1']['counts'] == {'terminal_unobserved': 1}


def test_reproducible_and_content_minimized(tmp_path, monkeypatch):
    rows = records(tmp_path, monkeypatch)
    frozen = batch(rows, [])
    assert frozen == batch(list(reversed(rows)), [])
    assert rows[0]['attempt_id'] not in json.dumps(frozen)
    frozen['operations'][0]['action'] = 'private'
    frozen['batch_id'] = 'agcm_' + digest({k:v for k,v in frozen.items() if k != 'batch_id'})
    import pytest
    with pytest.raises(ValueError):
        validate_batch(frozen)


def test_explicit_collector_and_cli(tmp_path, monkeypatch, capsys):
    directory = tmp_path / 'attempts'
    directory.mkdir()
    records(directory, monkeypatch)
    before = {p.name:p.read_bytes() for p in directory.iterdir()}
    frozen = collect_batch(start=START, end=END, cutoff=END, attempts_dir=directory)
    assert len(frozen['operations']) == 2
    assert before == {p.name:p.read_bytes() for p in directory.iterdir()}
    output = tmp_path / 'report'
    assert main(['prepare', '--start',START,'--end',END,'--attempts-dir',str(directory),'--output',str(output)]) == 0
    assert '独立 Capture CLI' in (output / 'report.html').read_text(encoding='utf-8')


def test_legacy_batch_still_uses_v1():
    frozen = freeze_batch(start=START, end=END, cutoff=END, events=[])
    assert frozen['schema_version'] == 'agc.metrics-batch.v1'
    assert compute_metrics(frozen)['M1']['status'] == 'empty'


def trace_rows(rows, terminal='trace.root.completed'):
    start = next(r for r in rows if r['phase'] == 'started')
    return [dict(event_id=str(i), trace_id=start['trace_id'], span_id=start['span_id'],
        parent_span_id=None, principal_ref={'id':'agent-global-context.capture','kind':'runtime'},
        timestamp=time, event_type=kind, payload={}) for i, (kind,time) in enumerate([
            ('trace.root.started',start['timestamp']), (terminal,'2026-09-11T01:30:00Z')])]


def test_matching_trace_is_only_partial_not_full_verification(tmp_path, monkeypatch):
    rows = records(tmp_path, monkeypatch)
    result = compute_metrics(batch(rows, trace_rows(rows)))['M3']
    assert result['counts'] == {'partial':1}
    assert result['rows'][0]['fields']['start'] == 'matched'
    assert result['rows'][0]['fields']['terminal'] == 'matched'
    assert result['rows'][0]['fields']['configuration_identity'] == 'unknown'
    assert result['denominator'] is None


def test_trace_terminal_disagreement_is_conflict(tmp_path, monkeypatch):
    rows = records(tmp_path, monkeypatch)
    assert compute_metrics(batch(rows, trace_rows(rows,'trace.root.failed')))['M3']['counts'] == {'conflict':1}


def test_missing_trace_source_does_not_claim_field_absence(tmp_path, monkeypatch):
    row, = compute_metrics(batch(records(tmp_path,monkeypatch)))['M3']['rows']
    assert row['fields']['identity'] == 'unchecked'


def test_business_duplicates_conflicts_and_orphans(tmp_path, monkeypatch):
    rows = records(tmp_path,monkeypatch)
    duplicated = compute_metrics(batch(rows+rows,[]))['M1']
    assert duplicated['counts'] == {'completed':1}
    assert duplicated['duplicate_operation_records'] == 2
    terminal = next(r for r in rows if r['phase'] == 'finished')
    conflicting = rows + [dict(terminal, outcome='failed',error_code='capture_busy')]
    assert compute_metrics(batch(conflicting,[]))['M1']['counts'] == {'state_conflict':1}
    orphan = compute_metrics(batch([terminal],[]))['M1']
    assert orphan['sample_count'] == 0
    assert orphan['orphan_business_terminals'] == 1


def test_sample_is_bounded_from_business_inventory(tmp_path, monkeypatch):
    rows = []
    for i in range(12):
        directory = tmp_path / str(i)
        directory.mkdir()
        rows.extend(records(directory,monkeypatch))
    result = compute_metrics(batch(rows,[]))
    assert result['M1']['sample_count'] == 12
    assert result['M3']['sample_count'] == 10
    assert result['M3']['counts'] == {'not_observed':10}


def test_output_inside_attempt_source_rejected(tmp_path, monkeypatch):
    records(tmp_path,monkeypatch)
    assert main(['prepare','--start',START,'--end',END,'--attempts-dir',str(tmp_path),
                 '--output',str(tmp_path/'report')]) == 2
    assert not (tmp_path/'report').exists()
