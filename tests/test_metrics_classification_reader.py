import json
from copy import deepcopy

import pytest

from test_metrics_classification_execution import setup
from test_metrics_research_cohort import batch


def completed(tmp_path,monkeypatch):
    from agc_runtime.metrics_classification_execution import execute_classification
    value,plan,model,args=setup(tmp_path,monkeypatch)
    assert execute_classification(batch(),plan,**args)['status']=='completed'
    return value,plan,model,{k:args[k] for k in ('directory','ledger_directory','resolve_preparation')}


def test_verified_read_has_no_model_calls_or_writes(tmp_path,monkeypatch):
    from agc_runtime.metrics_classification_reader import read_classification
    _,plan,model,args=completed(tmp_path,monkeypatch)
    before={p:p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    result=read_classification(batch(),plan,**args)
    assert result['status']=='verified_classification'
    assert result['classification']['cohort']['counts']['selected']==1
    assert model.calls==1
    assert before=={p:p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}


@pytest.mark.parametrize('artifact',['classification','receipt','started','finished','ledger','dependencies'])
def test_tampered_artifact_rejected(tmp_path,monkeypatch,artifact):
    from agc_runtime.metrics_classification_reader import read_classification
    _,plan,_,args=completed(tmp_path,monkeypatch)
    path=(args['ledger_directory']/(plan['plan_id']+'.json') if artifact=='ledger'
          else args['directory']/plan['plan_id']/(artifact+'.json'))
    content=json.loads(path.read_text(encoding='utf-8')); content['unexpected']='bad'
    path.write_text(json.dumps(content),encoding='utf-8')
    with pytest.raises(ValueError): read_classification(batch(),plan,**args)


def test_revoked_source_does_not_return_saved_labels(tmp_path,monkeypatch):
    from agc_runtime.metrics_classification_reader import read_classification
    _,plan,_,args=completed(tmp_path,monkeypatch)
    def revoked(): raise ValueError('unavailable')
    args['resolve_preparation']=revoked
    with pytest.raises(ValueError): read_classification(batch(),plan,**args)


def test_missing_terminal_is_not_success(tmp_path,monkeypatch):
    from agc_runtime.metrics_classification_reader import read_classification
    _,plan,_,args=completed(tmp_path,monkeypatch)
    (args['directory']/plan['plan_id']/'finished.json').unlink()
    with pytest.raises(ValueError): read_classification(batch(),plan,**args)


@pytest.mark.parametrize('change',['usage','observed','time','error'])
def test_semantic_receipt_and_terminal_checks(tmp_path,monkeypatch,change):
    from agc_runtime.metrics_classification_reader import read_classification
    _,plan,_,args=completed(tmp_path,monkeypatch)
    location=args['directory']/plan['plan_id']
    if change=='error': (location/'error.json').write_text('{}',encoding='utf-8')
    else:
        path=location/('finished.json' if change=='time' else 'receipt.json')
        value=json.loads(path.read_text(encoding='utf-8'))
        if change=='usage': value['usage']=dict(input_tokens=1,output_tokens=2,total_tokens=8)
        elif change=='observed': value['observed_configuration']=dict(provider='openai',model='wrong',reasoning_effort='medium')
        else: value['finished_at']='2000-01-01T00:00:00Z'
        path.write_text(json.dumps(value),encoding='utf-8')
    with pytest.raises(ValueError): read_classification(batch(),plan,**args)
