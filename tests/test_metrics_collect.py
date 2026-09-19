import json
import sqlite3

from test_metrics_batch import START, END, PRINCIPAL, api, event


def trace_db(path, rows):
    with sqlite3.connect(path) as connection:
        connection.execute('CREATE TABLE events(event_id TEXT, trace_id TEXT, span_id TEXT, parent_span_id TEXT, timestamp TEXT, event_type TEXT, principal_ref TEXT, payload_json TEXT)')
        for row in rows:
            connection.execute('INSERT INTO events VALUES(?,?,?,?,?,?,?,?)', (
                row['event_id'], row['trace_id'], row['span_id'], None, row['timestamp'], row['event_type'],
                json.dumps(row['principal_ref']), json.dumps(row['payload'])))


def collect(**kwargs):
    return api('metrics_collect').collect_batch(start=START, end=END, cutoff=END, **kwargs)


def test_collector_read_only_no_raw_payload_export(tmp_path):
    path = tmp_path / 'trace.sqlite3'
    trace_db(path, [event(message='PRIVATE-CONTENT'), event('end', kind='trace.root.completed')])
    before = path.read_bytes()
    value = collect(trace_db=path)
    assert len(value['events']) == 2
    assert before == path.read_bytes()
    assert 'PRIVATE-CONTENT' not in json.dumps(value)
    assert str(tmp_path) not in json.dumps(value)
    assert next(s for s in value['sources'] if s['name'] == 'trace')['status'] == 'available'
    assert next(s for s in value['sources'] if s['name'] == 'trace')['source_id'].startswith('id_')


def test_missing_and_bad_schema_not_created_or_reported_as_zero(tmp_path):
    missing = tmp_path / 'missing.db'
    wrong = tmp_path / 'wrong.db'
    with sqlite3.connect(wrong) as db:
        db.execute('CREATE TABLE unrelated(x TEXT)')
    assert next(s for s in collect(trace_db=missing)['sources'] if s['name'] == 'trace')['status'] == 'unavailable'
    assert not missing.exists()
    assert next(s for s in collect(trace_db=wrong)['sources'] if s['name'] == 'trace')['status'] == 'schema_mismatch'


def test_receipt_projection_and_forget_exclusion(tmp_path):
    root = tmp_path / 'receipts'; root.mkdir()
    for name, forgotten in [('r1', False), ('r2', True)]:
        (root / (name + '.json')).write_text(json.dumps(dict(receipt_id=name, updated_at=START,
            status='complete', redacted_by_forget=forgotten, statement='PRIVATE')), encoding='utf-8')
    value = collect(receipts_dir=root)
    assert len(value['receipts']) == 1
    assert 'PRIVATE' not in json.dumps(value)
    assert any(x['reason'] == 'revoked' for x in value['excluded'])


def test_eval_is_metadata_only_and_not_judge_accuracy(tmp_path):
    path = tmp_path / 'eval.db'
    result = dict(schema_version='eval.result.v0.1', result_id='result-1', evaluation_key='k1',
        case_id='case-1', profile_ref={'id':'agc.capture-quality','version':'1'}, status='pass',
        started_at=START, finished_at=START, subject={'principal_ref':PRINCIPAL},
        recommendations=['PRIVATE'], evaluator={'judge_id':'fixture','judge_version':'1'})
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE results(result_json TEXT)')
        db.execute('INSERT INTO results VALUES(?)', (json.dumps(result),))
    value = collect(eval_db=path)
    assert len(value['evaluations']) == 1
    assert 'PRIVATE' not in json.dumps(value)
    metric = api('metrics_compute').compute_metrics(value)['M4']
    assert metric['counts'] == {'stored_pass_unchecked': 1}
    assert metric['denominator'] is None


def test_malformed_json_is_counted_without_echoing_content(tmp_path):
    path = tmp_path / 'trace.db'
    trace_db(path, [event()])
    with sqlite3.connect(path) as db:
        db.execute("UPDATE events SET payload_json='PRIVATE{'")
    value = collect(trace_db=path)
    assert value['events'] == []
    assert value['sources'][0]['invalid_records'] == 1
    assert value['sources'][0]['status'] == 'partial'
    assert 'PRIVATE' not in json.dumps(value)


def test_missing_columns_are_schema_mismatch(tmp_path):
    path = tmp_path / 'trace.db'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE events(event_id TEXT)')
    assert collect(trace_db=path)['sources'][0]['status'] == 'schema_mismatch'


def test_explicit_window_before_source_access(tmp_path):
    import pytest
    with pytest.raises(ValueError):
        api('metrics_collect').collect_batch(start='invalid',end=END,cutoff=END,trace_db=tmp_path/'nothing.db')
    assert list(tmp_path.iterdir()) == []
