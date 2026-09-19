import json

import pytest

from test_metrics_review_batch import setup
from agc_runtime.metrics_result_reader import verify_saved_step


def test_execution_registers_content_free_exact_dependencies(tmp_path):
    batch,plan,resolver=setup(tmp_path)
    entry=plan['entries'][0]
    location=tmp_path/entry['entry_id']/'dependencies.json'
    value=json.loads(location.read_text(encoding='utf-8'))
    assert value['plan_id']==plan['plan_id']
    assert value['entry_id']==entry['entry_id']
    assert value['evidence_refs']==plan['cases'][0]['evidence_refs']
    assert value['artifacts']==['result.json','receipt.json']
    assert 'CANDIDATE_SECRET' not in json.dumps(value)
    assert verify_saved_step(plan,tmp_path,entry['entry_id'],resolve_case=resolver)['status']=='usable_judgment'


@pytest.mark.parametrize('mode',['missing','changed'])
def test_missing_or_changed_registration_blocks_reuse(tmp_path,mode):
    batch,plan,resolver=setup(tmp_path)
    entry=plan['entries'][0]
    path=tmp_path/entry['entry_id']/'dependencies.json'
    if mode=='missing': path.unlink()
    else:
        value=json.loads(path.read_text(encoding='utf-8')); value['evidence_refs']=[]
        path.write_text(json.dumps(value),encoding='utf-8')
    with pytest.raises(ValueError):
        verify_saved_step(plan,tmp_path,entry['entry_id'],resolve_case=resolver)


def test_registration_failure_prevents_model_call(tmp_path,monkeypatch):
    from agc_runtime import metrics_execution
    from test_metrics_execution import run
    original=metrics_execution._write
    def write(path,value):
        if path.name=='dependencies.json': raise OSError('fixture failure')
        original(path,value)
    monkeypatch.setattr(metrics_execution,'_write',write)
    result,gateway,_=run(tmp_path)
    assert gateway.calls==0
    assert result['status']=='evaluation_error'
    assert not list(tmp_path.rglob('result.json'))
