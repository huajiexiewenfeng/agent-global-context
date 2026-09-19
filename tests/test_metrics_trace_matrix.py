import pytest

from agc_runtime.metrics_compute import compute_metrics
from agc_runtime.metrics_report import render_report
from test_metrics_attempts import records,batch,trace_rows


@pytest.mark.parametrize('same',[True,False])
def test_trace_implementation_version_is_compared(tmp_path,monkeypatch,same):
    rows=records(tmp_path,monkeypatch); events=trace_rows(rows)
    version=rows[0]['implementation_version']
    for event in events: event['payload']['implementation_version']=version if same else '99.0.0'
    metric=compute_metrics(batch(rows,events))['M3']
    assert metric['rows'][0]['fields']['implementation_version']==('matched' if same else 'conflict')
    assert metric['counts']==({'partial':1} if same else {'conflict':1})


def test_matrix_explains_unknown_without_claiming_full_coverage(tmp_path,monkeypatch):
    rows=records(tmp_path,monkeypatch)
    html=render_report(batch(rows,trace_rows(rows)))
    assert 'Trace 字段核验矩阵' in html
    assert '<th scope="col">实现版本</th>' in html
    assert '已匹配' in html and '未知' in html
    assert '不代表完整可追溯率' in html


def test_legacy_frozen_events_remain_readable(tmp_path,monkeypatch):
    from agc_runtime.metrics_models import digest,validate_batch
    rows=records(tmp_path,monkeypatch); frozen=batch(rows,trace_rows(rows))
    frozen['transform_version']='agc.metrics-p2.1'
    for event in frozen['events']: event.pop('implementation_version')
    frozen['batch_id']='agcm_'+digest({k:v for k,v in frozen.items() if k!='batch_id'})
    assert validate_batch(frozen)==frozen
    assert compute_metrics(frozen)['M3']['rows'][0]['fields']['implementation_version']=='unchecked'


def test_version_is_not_matched_when_start_time_conflicts(tmp_path,monkeypatch):
    rows=records(tmp_path,monkeypatch); events=trace_rows(rows)
    events[0]['timestamp']='2026-09-11T00:30:00Z'
    events[0]['payload']['implementation_version']=rows[0]['implementation_version']
    result=compute_metrics(batch(rows,events))['M3']
    assert result['counts']=={'conflict':1}
    assert result['rows'][0]['fields']['implementation_version']=='unchecked'
