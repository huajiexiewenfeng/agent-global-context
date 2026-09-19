from copy import deepcopy
from types import SimpleNamespace
import json

import pytest

from test_metrics_research_classification import fixture,label
from test_metrics_research_cohort import batch
from test_metrics_gateway import gateway


def setup(tmp_path,monkeypatch):
    from agc_runtime.metrics_classification_execution import prepare_classification_plan
    preparation=fixture(tmp_path,monkeypatch)
    config=gateway(tmp_path).configuration
    class Fake:
        configuration=config
        calls=0
        def evaluate(self,payload):
            self.calls+=1
            return SimpleNamespace(output={'labels':[label(preparation)]},usage=None,observed_configuration=None)
    model=Fake()
    plan=prepare_classification_plan(batch(),preparation,judge=config)
    directory=tmp_path/'execution'; directory.mkdir()
    ledger=tmp_path/'ledger'; ledger.mkdir()
    args=dict(directory=directory,ledger_directory=ledger,gateway=model,
              consent_digest=plan['authorization_digest'],resolve_preparation=lambda:deepcopy(preparation))
    return preparation,plan,model,args


def test_executes_once_with_content_free_artifacts(tmp_path,monkeypatch):
    from agc_runtime.metrics_classification_execution import execute_classification
    _,plan,model,args=setup(tmp_path,monkeypatch)
    result=execute_classification(batch(),plan,**args)
    assert result['status']=='completed' and model.calls==1
    files=list(args['directory'].rglob('*.json'))
    assert any(p.name=='classification.json' for p in files)
    assert all('runtime research' not in p.read_text(encoding='utf-8') for p in files)
    second=tmp_path/'second'; second.mkdir(); args['directory']=second
    with pytest.raises(ValueError): execute_classification(batch(),plan,**args)
    assert model.calls==1


@pytest.mark.parametrize('mode',['consent','source','configuration'])
def test_preflight_rejects_without_model_call(tmp_path,monkeypatch,mode):
    from agc_runtime.metrics_classification_execution import execute_classification
    value,plan,model,args=setup(tmp_path,monkeypatch)
    if mode=='consent': args['consent_digest']='0'*64
    elif mode=='source':
        value['inputs'][0]['document']['content']='changed'
        args['resolve_preparation']=lambda:value
    else: model.configuration=dict(model.configuration,reasoning_effort='low')
    with pytest.raises(ValueError): execute_classification(batch(),plan,**args)
    assert model.calls==0
    assert list(args['ledger_directory'].iterdir())==[]


@pytest.mark.parametrize('mode',['invalid_output','revoked_after_call','exception','changed_configuration'])
def test_failure_is_retained_and_never_retried(tmp_path,monkeypatch,mode):
    from agc_runtime.metrics_classification_execution import execute_classification
    value,plan,model,args=setup(tmp_path,monkeypatch)
    original=model.evaluate
    def evaluate(payload):
        outcome=original(payload)
        if mode=='invalid_output': outcome.output={'labels':[]}
        elif mode=='exception': raise RuntimeError('private secret text')
        elif mode=='changed_configuration': model.configuration=dict(model.configuration,reasoning_effort='low')
        return outcome
    model.evaluate=evaluate
    if mode=='revoked_after_call':
        def resolve():
            if model.calls: raise ValueError('revoked')
            return value
        args['resolve_preparation']=resolve
    result=execute_classification(batch(),plan,**args)
    assert result['status']=='classification_error' and model.calls==1
    assert 'private secret text' not in json.dumps(result)
    assert not list(args['directory'].rglob('classification.json'))
    # Even after failure, a fresh output folder cannot refund the send slot.
    model.configuration=plan['judge']
    args['resolve_preparation']=lambda:value
    second=tmp_path/'retry'; second.mkdir(); args['directory']=second
    with pytest.raises(ValueError,match='already_reserved'):
        execute_classification(batch(),plan,**args)
    assert model.calls==1


def test_empty_preparation_never_reserves_or_calls(tmp_path,monkeypatch):
    from agc_runtime.metrics_classification_execution import prepare_classification_plan,execute_classification
    from agc_runtime.metrics_research_inputs import prepare_research_inputs
    _,_,model,args=setup(tmp_path,monkeypatch)
    def forbidden(refs): raise AssertionError('no source needed')
    value=prepare_research_inputs(batch(),[],source_factory=forbidden)
    plan=prepare_classification_plan(batch(),value,judge=model.configuration)
    args.update(consent_digest=plan['authorization_digest'],resolve_preparation=lambda:value)
    assert plan['max_calls']==0
    assert execute_classification(batch(),plan,**args)['status']=='no_ready_inputs'
    assert model.calls==0
    assert list(args['ledger_directory'].iterdir())==[]
