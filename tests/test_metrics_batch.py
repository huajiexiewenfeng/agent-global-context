import copy
import importlib
import importlib.util
import json

import pytest

START = '2026-09-03T00:00:00+08:00'
END = '2026-09-10T00:00:00+08:00'
PRINCIPAL = {'id': 'agent-global-context.capture', 'kind': 'runtime'}


def api(name):
    assert importlib.util.find_spec('agc_runtime.' + name), 'metrics module is not implemented'
    return importlib.import_module('agc_runtime.' + name)


def event(identifier='e1', trace='t1', kind='trace.root.started', time=START, **payload):
    return dict(event_id=identifier, trace_id=trace, span_id=trace, parent_span_id=None,
                timestamp=time, event_type=kind, principal_ref=PRINCIPAL, payload=payload)


def batch(**kwargs):
    return api('metrics_models').freeze_batch(start=START, end=END, cutoff=END, **kwargs)


def test_freeze_is_stable_sorted_detached_and_content_minimized():
    rows = [event('b', payload='SECRET'), event('a', error={'message': 'SECRET', 'type': 'capture_busy'})]
    first = batch(events=rows)
    assert first == batch(events=list(reversed(rows)))
    rows[0]['payload']['extra'] = 'later'
    assert 'SECRET' not in json.dumps(first)
    assert 'later' not in json.dumps(first)
    assert first['window']['start'] == '2026-09-02T16:00:00Z'
    assert first['definition_version'] == '1.1'


@pytest.mark.parametrize('changes', [dict(start='2026-09-03'), dict(end=START), dict(cutoff=START)])
def test_reject_invalid_or_naive_window(changes):
    args = dict(start=START, end=END, cutoff=END)
    args.update(changes)
    with pytest.raises(ValueError):
        api('metrics_models').freeze_batch(**args)


def test_tampered_batch_is_rejected():
    value = batch(events=[event()])
    value['events'][0]['event_type'] = 'trace.root.failed'
    with pytest.raises(ValueError, match='batch'):
        api('metrics_models').validate_batch(value)


def test_foreign_principal_invalid_time_and_out_of_range_are_accounted():
    foreign = event('foreign'); foreign['principal_ref'] = {'id': 'other', 'kind': 'runtime'}
    value = batch(events=[foreign, event('bad', time='bad'), event('old', time='2020-01-01T00:00:00Z')])
    assert value['events'] == []
    assert {x['reason'] for x in value['excluded']} == {'out_of_scope', 'invalid_record', 'outside_window'}
    assert '"bad"' not in json.dumps(value)


def test_missing_sources_are_not_healthy_empty_sources():
    value = batch()
    assert {s['status'] for s in value['sources']} == {'not_provided'}


def test_unknown_fields_on_loaded_batch_are_rejected():
    value = copy.deepcopy(batch())
    value['secret'] = 'private'
    with pytest.raises(ValueError):
        api('metrics_models').validate_batch(value)


@pytest.mark.parametrize('field,value', [('event_type','unrecognized'),('event_id','not-an-opaque-id'),('reference_present','yes')])
def test_rehashed_invalid_schema_still_rejected(field, value):
    model = api('metrics_models')
    frozen = batch(events=[event()])
    frozen['events'][0][field] = value
    frozen['batch_id'] = 'agcm_' + model.digest({k:v for k,v in frozen.items() if k != 'batch_id'})
    with pytest.raises(ValueError, match='batch'):
        model.validate_batch(frozen)
