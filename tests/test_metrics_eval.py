import importlib
from copy import deepcopy

import pytest


def api():
    return importlib.import_module('agc_runtime.metrics_eval')


def config(**changes):
    return dict(provider='openai',model='gpt-6-astra',reasoning_effort='medium',timeout_seconds=120,
        executable_identity='a'*64,adapter_identity='b'*64,**changes)


def case(scenario='collected'):
    return dict(case_id='id_'+'c'*64,scenario=scenario,subject_digest='d'*64,
                evidence_refs=[dict(ref='id_'+'e'*64,digest='f'*64,version='1')])


def rules():
    return {s:dict(profile_digest='1'*64,prompt_digest='2'*64,schema_digest='3'*64)
            for s in ('required_claims','align_candidates','research_relevance')}


def plan(cases=None,judge=None,definitions=None):
    return api().prepare_plan(batch_id='agcm_'+'4'*64,cases=cases if cases is not None else [case()],
        judge=judge or config(),rules=definitions or rules())


def test_m2_two_steps_m5_one_step_and_no_observed_claim():
    research=case('research'); research['case_id']='id_'+'5'*64
    result=plan([case(),research])
    assert result['max_calls']==3
    assert [e['step'] for e in result['entries']]==['required_claims','align_candidates','research_relevance']
    assert result['judge']['model']=='gpt-6-astra'
    assert result['observed_judge'] is None
    assert api().validate_plan(result)==result


def test_plan_is_canonical_under_case_reordering():
    second=case('zero'); second['case_id']='id_'+'6'*64
    assert plan([case(),second])==plan([second,case()])


@pytest.mark.parametrize('change',['effort','model','evidence','subject','rule','executable','adapter','timeout'])
def test_identity_changes_invalidate_authorization(change):
    cases=[case()]; judge=config(); definitions=rules()
    if change=='effort': judge['reasoning_effort']='low'
    elif change=='model': judge['model']='gpt-5.6-sol'
    elif change=='evidence': cases[0]['evidence_refs'][0]['digest']='9'*64
    elif change=='subject': cases[0]['subject_digest']='9'*64
    elif change=='rule': definitions['align_candidates']['prompt_digest']='9'*64
    elif change=='executable': judge['executable_identity']='9'*64
    elif change=='adapter': judge['adapter_identity']='9'*64
    elif change=='timeout': judge['timeout_seconds']=180
    assert plan(cases,judge,definitions)['authorization_digest']!=plan()['authorization_digest']


def test_missing_effort_and_unknown_configuration_rejected():
    missing=config(); missing.pop('reasoning_effort')
    with pytest.raises(ValueError): plan(judge=missing)
    extra=config(); extra['capture']={'model':'old'}
    with pytest.raises(ValueError): plan(judge=extra)


def test_duplicates_and_pilot_caps_rejected():
    with pytest.raises(ValueError): plan([case(),case()])
    cases=[]
    for i in range(6):
        row=case(); row['case_id']='id_'+str(i)*64; cases.append(row)
    with pytest.raises(ValueError): plan(cases)


def test_authorization_exact_binding_and_revocation():
    value=plan()
    assert api().check_authorization(value,value['authorization_digest'],revoked_refs=[]) is None
    with pytest.raises(ValueError): api().check_authorization(value,'0'*64,revoked_refs=[])
    with pytest.raises(ValueError): api().check_authorization(value,value['authorization_digest'],revoked_refs=[case()['evidence_refs'][0]['ref']])


def test_second_step_requires_exact_dependency_result_and_reuse_matches():
    value=plan(); entry=value['entries'][1]
    with pytest.raises(ValueError): api().execution_key(value,entry['entry_id'])
    key=api().execution_key(value,entry['entry_id'],dependency_digest='7'*64)
    assert key!=api().execution_key(value,entry['entry_id'],dependency_digest='8'*64)
    record=dict(execution_key=key,status='completed',result_digest='9'*64)
    assert api().reusable_result(record,key) is True
    for status in ('error','insufficient_evidence','not_run'):
        assert not api().reusable_result(dict(record,status=status),key)
    assert not api().reusable_result(record,'0'*64)


def test_tampered_plan_rejected_and_return_values_detached():
    value=plan(); changed=deepcopy(value); changed['max_calls']=1
    with pytest.raises(ValueError): api().validate_plan(changed)
    copied=api().validate_plan(value); copied['entries'].clear()
    assert len(value['entries'])==2


def test_plan_cli_is_offline_and_refuses_existing_output(tmp_path):
    import json
    from agc_runtime.metrics_cli import main
    from agc_runtime.metrics_models import freeze_batch
    data={'batch':freeze_batch(start='2026-09-11T00:00:00Z',end='2026-09-12T00:00:00Z',cutoff='2026-09-12T00:00:00Z'),
          'cases':[case()],'judge':config(),'rules':rules()}
    for key,value in data.items():
        (tmp_path/(key+'.json')).write_text(json.dumps(value),encoding='utf-8')
    args=['plan']
    for key in data:
        args.extend(['--'+key,str(tmp_path/(key+'.json'))])
    output=tmp_path/'plan'
    args.extend(['--output',str(output)])
    assert main(args)==0
    result=json.loads((output/'plan.json').read_text())
    assert result['max_calls']==2
    assert main(args)==2


@pytest.mark.parametrize('invalid', ['duplicate', 'oversized', 'tampered'])
def test_plan_cli_rejects_invalid_input_before_creating_output(tmp_path, invalid):
    import json
    from agc_runtime.metrics_cli import main
    from agc_runtime.metrics_models import freeze_batch
    batch=freeze_batch(start='2026-09-11T00:00:00Z',end='2026-09-12T00:00:00Z',cutoff='2026-09-12T00:00:00Z')
    data={'batch':batch,'cases':[case()],'judge':config(),'rules':rules()}
    for key,value in data.items():
        (tmp_path/(key+'.json')).write_text(json.dumps(value),encoding='utf-8')
    if invalid=='duplicate':
        raw=json.dumps(config())
        (tmp_path/'judge.json').write_text(raw[:-1]+',"model":"gpt-6-astra"}',encoding='utf-8')
    elif invalid=='oversized':
        (tmp_path/'cases.json').write_text(json.dumps([case()])+' '*(32*1024*1024),encoding='utf-8')
    else:
        batch['batch_id']='agcm_'+'0'*64
        (tmp_path/'batch.json').write_text(json.dumps(batch),encoding='utf-8')
    args=['plan']
    for key in data:
        args.extend(['--'+key,str(tmp_path/(key+'.json'))])
    output=tmp_path/'plan'
    assert main(args+['--output',str(output)])==2
    assert not output.exists()
