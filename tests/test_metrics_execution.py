import importlib
import json
from types import SimpleNamespace

import pytest

from test_metrics_judge_input import fixture


def api():
    return importlib.import_module('agc_runtime.metrics_execution')


class Gateway:
    def __init__(self,configuration,handler=None):
        self.configuration=configuration
        self.handler=handler
        self.calls=0

    def evaluate(self,payload):
        self.calls+=1
        if self.handler:
            return self.handler(payload)
        return SimpleNamespace(output=dict(status='completed',reason=None,claims=[]),usage=None,observed_configuration=None)


def run(tmp_path,*,gateway=None,consent=None,revocations=lambda:(),dependency=None,index=0):
    plan,subject,docs=fixture()
    gateway=gateway or Gateway(plan['judge'])
    result=api().execute_entry(plan,plan['entries'][index]['entry_id'],directory=tmp_path,
        consent_digest=consent or plan['authorization_digest'],subject=subject,documents=docs,
        revoked_refs=revocations,gateway=gateway,dependency=dependency)
    return result,gateway,plan


def test_start_precedes_call_and_success_is_persisted(tmp_path):
    plan,_,_=fixture()
    def handler(payload):
        assert list(tmp_path.rglob('started.json'))
        assert not list(tmp_path.rglob('finished.json'))
        assert [d['role'] for d in payload['evidence']]==['safe_input']
        return SimpleNamespace(output=dict(status='completed',reason=None,claims=[]),usage=dict(input_tokens=2,output_tokens=1,total_tokens=3),observed_configuration=None)
    result,gateway,_=run(tmp_path,gateway=Gateway(plan['judge'],handler))
    assert gateway.calls==1 and result['status']=='completed'
    assert result['result_digest']
    assert len(list(tmp_path.rglob('result.json')))==1
    assert json.loads(next(tmp_path.rglob('receipt.json')).read_text())['observed_configuration'] is None


def test_no_silent_repeat_or_overwrite(tmp_path):
    result,gateway,plan=run(tmp_path)
    with pytest.raises(ValueError): run(tmp_path,gateway=gateway)
    assert gateway.calls==1


@pytest.mark.parametrize('fault',['consent','configuration','revocation'])
def test_preflight_rejection_never_calls_gateway(tmp_path,fault):
    plan,_,docs=fixture(); gateway=Gateway(dict(plan['judge']))
    kwargs={}
    if fault=='consent': kwargs['consent']='0'*64
    elif fault=='configuration': gateway.configuration['reasoning_effort']='low'
    else: kwargs['revocations']=lambda:[docs[0]['ref']]
    with pytest.raises(ValueError): run(tmp_path,gateway=gateway,**kwargs)
    assert gateway.calls==0
    assert not list(tmp_path.iterdir())


def test_gateway_error_keeps_start_and_sanitized_terminal(tmp_path):
    plan,_,_=fixture()
    def fail(payload): raise RuntimeError('PRIVATE EXCEPTION BODY')
    result,_,_=run(tmp_path,gateway=Gateway(plan['judge'],fail))
    assert result['status']=='evaluation_error'
    assert 'PRIVATE EXCEPTION BODY' not in ''.join(p.read_text() for p in tmp_path.rglob('*.json'))
    assert list(tmp_path.rglob('started.json')) and list(tmp_path.rglob('finished.json'))


def test_interruption_retains_only_started(tmp_path):
    plan,_,_=fixture()
    def fail(payload): raise KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt): run(tmp_path,gateway=Gateway(plan['judge'],fail))
    assert list(tmp_path.rglob('started.json'))
    assert not list(tmp_path.rglob('finished.json'))


def test_unseen_candidate_citation_is_rejected_after_call(tmp_path):
    plan,_,docs=fixture()
    def bad(payload):
        return SimpleNamespace(output=dict(status='completed',reason=None,claims=[dict(claim_id='r',text='Synthetic',certainty='required',evidence=[docs[1]['ref']])]),usage=None,observed_configuration=None)
    result,gateway,_=run(tmp_path,gateway=Gateway(plan['judge'],bad))
    assert gateway.calls==1 and result['status']=='evaluation_error'
    assert not list(tmp_path.rglob('result.json'))


def test_start_write_failure_prevents_model_call(tmp_path,monkeypatch):
    plan,_,_=fixture(); gateway=Gateway(plan['judge'])
    def fail(*args): raise OSError('disk unavailable')
    monkeypatch.setattr(api(),'_write',fail)
    with pytest.raises(OSError): run(tmp_path,gateway=gateway)
    assert gateway.calls==0


def test_revoked_after_call_never_persists_assessment(tmp_path):
    plan,_,docs=fixture()
    gateway=Gateway(plan['judge'])
    result,_,_=run(tmp_path,gateway=gateway,
        revocations=lambda:[docs[0]['ref']] if gateway.calls else [])
    assert result['status']=='evaluation_error'
    assert gateway.calls==1
    assert not list(tmp_path.rglob('result.json'))


def test_insufficient_result_remains_distinct_in_artifact(tmp_path):
    plan,_,_=fixture()
    def insufficient(payload):
        return SimpleNamespace(output=dict(status='insufficient_evidence',reason='Evidence too ambiguous',claims=[]),
                               usage=None,observed_configuration=None)
    result,_,_=run(tmp_path,gateway=Gateway(plan['judge'],insufficient))
    assert result['status']=='completed'
    saved=json.loads(next(tmp_path.rglob('result.json')).read_text())
    assert saved['assessment']['status']=='insufficient_evidence'
    assert saved['human_review']=='unreviewed'


def test_receipt_write_failure_cannot_claim_completed(tmp_path,monkeypatch):
    original=api()._write
    def fail_receipt(path,value):
        if path.name=='receipt.json': raise OSError('disk failure')
        original(path,value)
    monkeypatch.setattr(api(),'_write',fail_receipt)
    result,_,_=run(tmp_path)
    assert result['status']=='evaluation_error' and result['result_digest'] is None
