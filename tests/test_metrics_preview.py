import json
import pytest
from agc_runtime.admin_service import dispatch_admin
from agc_runtime.paths import MemoryPaths
from agc_runtime.metrics_business import read_business_records
from test_write_service import principle


def request():
    return dict(action='capture_preview',memory_markdown=principle().to_markdown(),
                disposition='new',capture_observation_ids=['co_'+'a'*64])


def test_preview_returns_complete_item_without_memory_writes(tmp_path,monkeypatch):
    metrics=tmp_path/'metrics'; metrics.mkdir()
    monkeypatch.setenv('AGC_METRICS_EVIDENCE_DIR',str(metrics))
    paths=MemoryPaths.from_root(tmp_path/'memory')
    response=dispatch_admin(paths,request())
    assert response.status=='accepted'
    assert response.data['preview']['memory_markdown']==principle().to_markdown()
    assert response.data['source_verification']=='unchecked'
    assert not paths.root.exists()
    records=read_business_records(metrics/'business')['records']
    end=next(r for r in records if r['phase']=='finished')
    assert end['preview_delivery']=='runtime_returned'
    assert end['confirmation_ref'] is None
    assert end['objects'][0]['version']==response.data['preview']['version']
    assert principle().full_meaning not in json.dumps(records)


def test_invalid_preview_does_not_return_complete_item(tmp_path):
    value=request(); value['capture_observation_ids']*=2
    response=dispatch_admin(MemoryPaths.from_root(tmp_path/'memory'),value)
    assert response.status=='failed'
    assert 'preview' not in response.data


def test_metrics_failure_does_not_block_preview(tmp_path,monkeypatch):
    monkeypatch.setenv('AGC_METRICS_EVIDENCE_DIR',str(tmp_path/'missing-metrics'))
    paths=MemoryPaths.from_root(tmp_path/'memory')
    response=dispatch_admin(paths,request())
    assert response.status=='accepted'
    assert response.data['preview']['memory_markdown']==principle().to_markdown()
    assert 'metrics_evidence_unavailable' in response.warnings
    assert not paths.root.exists()


@pytest.mark.parametrize('field,value',[
    ('memory_markdown',''),
    ('memory_markdown','x'*65537),
    ('disposition','publish'),
    ('capture_observation_ids',[]),
    ('capture_observation_ids',['not-an-observation']),
    ('unexpected',True),
],ids=['empty-markdown','oversize-markdown','invalid-disposition','empty-ids','invalid-id','extra-field'])
def test_rejected_preview_never_records_delivery(tmp_path,monkeypatch,field,value):
    metrics=tmp_path/'metrics'; metrics.mkdir()
    monkeypatch.setenv('AGC_METRICS_EVIDENCE_DIR',str(metrics))
    paths=MemoryPaths.from_root(tmp_path/'memory')
    payload=request(); payload[field]=value
    response=dispatch_admin(paths,payload)
    assert response.status=='failed'
    records=read_business_records(metrics/'business')['records']
    end=next(r for r in records if r['phase']=='finished')
    assert end['preview_delivery']=='unknown'
    assert end['objects']==[]
    assert not paths.root.exists()
