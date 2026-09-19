import importlib
import json
from types import SimpleNamespace

import pytest

from agc_runtime.metrics_execution import execute_entry
from test_metrics_judge_input import fixture
from test_metrics_execution import Gateway

CUTOFF='2099-01-01T00:00:00Z'


def api():
    return importlib.import_module('agc_runtime.metrics_result_reader')


def completed(tmp_path):
    plan,subject,docs=fixture()
    gateway=Gateway(plan['judge'])
    args=dict(directory=tmp_path,consent_digest=plan['authorization_digest'],subject=subject,
              documents=docs,revoked_refs=lambda:[],gateway=gateway)
    execute_entry(plan,plan['entries'][0]['entry_id'],**args)
    first=json.loads((tmp_path/plan['entries'][0]['entry_id']/'result.json').read_text())
    gateway.handler=lambda p:SimpleNamespace(output=dict(status='completed',reason=None,candidates=[],matches=[]),usage=None,observed_configuration=None)
    execute_entry(plan,plan['entries'][1]['entry_id'],dependency=first,**args)
    return plan,lambda case_id:dict(subject=subject,documents=docs,revoked_refs=[])


def summary(plan,tmp_path,resolver):
    return api().summarize_execution_directory(plan,tmp_path,cutoff=CUTOFF,resolve_case=resolver)


def test_persisted_two_step_execution_becomes_verified_m4(tmp_path):
    plan,resolver=completed(tmp_path)
    result=summary(plan,tmp_path,resolver)
    assert result['usable_cases']==1 and result['planned_steps']==2
    assert result['counts']=={'usable_judgment':1}


@pytest.mark.parametrize('fault',['result','receipt','missing_receipt','start_binding','foreign_usage'])
def test_tampered_or_partial_files_never_count_usable(tmp_path,fault):
    plan,resolver=completed(tmp_path)
    directory=tmp_path/plan['entries'][1]['entry_id']
    if fault=='missing_receipt': (directory/'receipt.json').unlink()
    else:
        name='result.json' if fault=='result' else 'started.json' if fault=='start_binding' else 'receipt.json'
        path=directory/name; value=json.loads(path.read_text())
        if fault=='result': value['assessment']['reason']='tampered'
        elif fault=='receipt': value['input_digest']='0'*64
        elif fault=='start_binding': value['attempt_id']='mea_'+'0'*64
        else: value['usage']={'private':'not token metadata'}
        path.write_text(json.dumps(value))
    result=summary(plan,tmp_path,resolver)
    assert result['usable_cases']==0
    assert result['invalid_records'] or result['counts'].get('evaluation_error')


def test_unavailable_source_remains_unchecked_not_verified(tmp_path):
    plan,_=completed(tmp_path)
    def missing(case_id): raise ValueError('source unavailable')
    result=summary(plan,tmp_path,missing)
    assert result['counts']=={'unchecked':1}
    assert result['usable_cases']==0


def test_revocation_prevents_old_result_reuse(tmp_path):
    plan,resolver=completed(tmp_path)
    def revoked(case_id):
        value=resolver(case_id)
        value['revoked_refs']=[value['documents'][0]['ref']]
        return value
    assert summary(plan,tmp_path,revoked)['usable_cases']==0


def test_reader_is_read_only(tmp_path):
    import hashlib
    plan,resolver=completed(tmp_path)
    def snapshot(): return {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in tmp_path.rglob('*.json')}
    before=snapshot()
    summary(plan,tmp_path,resolver)
    assert snapshot()==before


def test_alignment_cannot_precede_reference_completion(tmp_path):
    plan,resolver=completed(tmp_path)
    first=tmp_path/plan['entries'][0]['entry_id']/'finished.json'
    value=json.loads(first.read_text()); value['finished_at']='2098-01-01T00:00:00Z'
    first.write_text(json.dumps(value))
    result=summary(plan,tmp_path,resolver)
    assert result['usable_cases']==0


def test_duplicate_receipt_fields_rejected(tmp_path):
    plan,resolver=completed(tmp_path)
    path=tmp_path/plan['entries'][0]['entry_id']/'receipt.json'
    raw=path.read_text()
    path.write_text(raw[:-1]+',"usage":null}')
    assert summary(plan,tmp_path,resolver)['usable_cases']==0
