import importlib
from copy import deepcopy

import pytest

from agc_runtime.metrics_models import digest, canonical
from agc_runtime.metrics_eval import prepare_plan
from test_metrics_eval import config


def api():
    return importlib.import_module('agc_runtime.metrics_judge_input')


def fixture():
    docs=[dict(ref='id_'+'a'*64,version='1',role='safe_input',content={'signals':['A synthetic preference']}),
          dict(ref='id_'+'b'*64,version='2',role='candidate',content={'text':'CANDIDATE_SECRET'})]
    subject=dict(stage='observation',version='2',evidence_roles={d['ref']:d['role'] for d in docs})
    case=dict(case_id='id_'+'c'*64,scenario='collected',subject_digest=digest(subject),
              evidence_refs=[dict(ref=d['ref'],version=d['version'],digest=digest(d)) for d in docs])
    plan=prepare_plan(batch_id='agcm_'+'d'*64,cases=[case],judge=config(),rules=api().rule_identities())
    return plan,subject,docs


def build(plan,subject,docs,index=0,**kwargs):
    return api().build_input(plan,plan['entries'][index]['entry_id'],subject=subject,
                             documents=docs,revoked_refs=[],**kwargs)


def test_required_payload_blind_to_candidates_and_scenario():
    plan,subject,docs=fixture()
    payload=build(plan,subject,docs)
    serialized=canonical(payload)
    assert 'CANDIDATE_SECRET' not in serialized
    assert docs[1]['ref'] not in serialized
    assert 'collected' not in canonical(payload['case'])
    assert [d['role'] for d in payload['evidence']]==['safe_input']
    assert payload['profile']['version']=='1.1'
    docs[0]['content']['signals'].clear()
    assert payload['evidence'][0]['content']['signals']


@pytest.mark.parametrize('fault',['digest','version','role','missing','extra','subject','rules','revoked'])
def test_input_binding_rejects_changes(fault):
    plan,subject,docs=fixture()
    revoked=[]
    if fault=='digest': docs[0]['content']={}
    elif fault=='version': docs[0]['version']='other'
    elif fault=='role': docs[0]['role']='candidate'
    elif fault=='missing': docs.pop()
    elif fault=='extra': docs.append(deepcopy(docs[0]))
    elif fault=='subject': subject['stage']='formal_memory'
    elif fault=='rules':
        rules=api().rule_identities(); rules['required_claims']['prompt_digest']='0'*64
        plan=prepare_plan(batch_id=plan['batch_id'],cases=plan['cases'],judge=plan['judge'],rules=rules)
    else: revoked=[docs[0]['ref']]
    with pytest.raises(ValueError):
        api().build_input(plan,plan['entries'][0]['entry_id'],subject=subject,documents=docs,revoked_refs=revoked)


def test_alignment_uses_frozen_reference_and_candidates():
    from agc_runtime.metrics_assessment import freeze_assessment
    plan,subject,docs=fixture()
    ref=dict(status='completed',reason=None,claims=[dict(claim_id='r1',text='Synthetic reference',certainty='required',evidence=[docs[0]['ref']])])
    first=freeze_assessment(plan,plan['entries'][0]['entry_id'],ref)
    payload=build(plan,subject,docs,index=1,dependency=first)
    assert payload['case']['required_claims']==ref
    assert len(payload['evidence'])==2
    with pytest.raises(ValueError): build(plan,subject,docs,index=1)


def test_required_reference_cannot_cite_hidden_candidate():
    from agc_runtime.metrics_assessment import freeze_assessment
    plan,subject,docs=fixture()
    bad=dict(status='completed',reason=None,claims=[dict(claim_id='r1',text='Leaked reference',certainty='required',evidence=[docs[1]['ref']])])
    first=freeze_assessment(plan,plan['entries'][0]['entry_id'],bad)
    with pytest.raises(ValueError): build(plan,subject,docs,index=1,dependency=first)


def research_fixture(roles):
    docs=[dict(ref='id_'+str(index)*64,version='1',role=role,content={'text':'Synthetic '+role})
          for index,role in enumerate(roles)]
    subject=dict(stage='research_task',version='1',evidence_roles={d['ref']:d['role'] for d in docs})
    case=dict(case_id='id_'+'c'*64,scenario='research',subject_digest=digest(subject),
              evidence_refs=[dict(ref=d['ref'],version=d['version'],digest=digest(d)) for d in docs])
    plan=prepare_plan(batch_id='agcm_'+'d'*64,cases=[case],judge=config(),rules=api().rule_identities())
    return plan,subject,docs


def test_research_missing_historical_background_is_not_fabricated():
    plan,subject,docs=research_fixture(['task_input','task_output','research_source'])
    payload=build(plan,subject,docs)
    assert {d['role'] for d in payload['evidence']}=={'task_input','task_output','research_source'}
    assert 'background_accuracy must be unknown' in payload['instruction']


def test_undelivered_task_cannot_be_evaluated_as_no_help():
    plan,subject,docs=research_fixture(['task_input','research_source'])
    with pytest.raises(ValueError): build(plan,subject,docs)


def test_current_memory_cannot_be_silently_added_as_background():
    plan,subject,docs=research_fixture(['task_input','task_output','current_memory'])
    with pytest.raises(ValueError): build(plan,subject,docs)


def test_missing_candidate_artifact_is_not_a_legitimate_zero():
    plan,subject,docs=fixture()
    docs=docs[:1]
    subject['evidence_roles']={docs[0]['ref']:'safe_input'}
    case=dict(plan['cases'][0],scenario='zero',subject_digest=digest(subject),
              evidence_refs=[dict(ref=docs[0]['ref'],version='1',digest=digest(docs[0]))])
    plan=prepare_plan(batch_id=plan['batch_id'],cases=[case],judge=config(),rules=api().rule_identities())
    with pytest.raises(ValueError): build(plan,subject,docs)
