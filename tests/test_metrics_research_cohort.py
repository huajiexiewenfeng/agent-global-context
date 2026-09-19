import importlib
import json
from copy import deepcopy

import pytest

from agc_runtime.metrics_models import freeze_batch, opaque


def api():
    return importlib.import_module('agc_runtime.metrics_research_cohort')


def batch():
    return freeze_batch(start='2026-09-01T00:00:00Z',end='2026-09-08T00:00:00Z',
                        cutoff='2026-09-09T00:00:00Z')


def classifier():
    return dict(method='llm',rule_version='research-contact-v1',
                configuration_digest='a'*64,authorization_ref=opaque('synthetic authorization'))


def task(number=1,**changes):
    value=dict(task_ref=opaque('task-'+str(number)),revision='b'*64,
               delivered_at=f'2026-09-0{number}T12:00:00Z',decision='include',
               reason='research_connection_request',evidence_status='available')
    return dict(value,**changes)


def test_independent_cohort_caps_five_without_recall_selection():
    tasks=[task(n) for n in range(1,8)]
    result=api().freeze_research_cohort(batch(),tasks,classifier=classifier())
    assert result['selected_task_refs']==[t['task_ref'] for t in tasks[:5]]
    assert result['counts']==dict(selected=5,sample_cap=2,excluded=0,ambiguous=0,
                                 evidence_unavailable=0,outside_window=0)
    assert result['coverage']=='selected_frontend_tasks_not_full_population'
    assert result==api().freeze_research_cohort(batch(),list(reversed(tasks)),classifier=classifier())
    assert api().validate_research_cohort(batch(),result)==result


def test_keeps_missing_ambiguous_and_excluded_in_denominator_metadata():
    tasks=[task(1),task(2,evidence_status='unavailable'),
           task(3,decision='ambiguous',reason='task_boundary_unclear'),
           task(4,decision='exclude',reason='not_research_connection'),
           task(5,delivered_at='2026-09-08T00:00:00Z')]
    result=api().freeze_research_cohort(batch(),tasks,classifier=classifier())
    assert len(result['tasks'])==5
    assert result['counts']==dict(selected=1,sample_cap=0,excluded=1,ambiguous=1,
                                 evidence_unavailable=1,outside_window=1)
    assert result['selected_task_refs']==[tasks[0]['task_ref']]


@pytest.mark.parametrize('fault',['duplicate','recall-field','missing-authorization','tamper','reason'])
def test_invalid_cohort_rejected(fault):
    tasks=[task()]; config=classifier()
    if fault=='duplicate': tasks.append(deepcopy(tasks[0]))
    if fault=='recall-field': tasks[0]['agc_called']=True
    if fault=='missing-authorization': config['authorization_ref']=None
    if fault=='reason': tasks[0]['reason']='not_research_connection'
    if fault=='tamper':
        result=api().freeze_research_cohort(batch(),tasks,classifier=config)
        result['selected_task_refs']=[]
        with pytest.raises(ValueError): api().validate_research_cohort(batch(),result)
    else:
        with pytest.raises(ValueError): api().freeze_research_cohort(batch(),tasks,classifier=config)


def test_empty_selected_scope_is_not_claimed_to_be_population_zero():
    result=api().freeze_research_cohort(batch(),[],classifier=classifier())
    assert result['selected_task_refs']==[]
    assert result['status']=='no_selected_cases'
    assert result['coverage']=='selected_frontend_tasks_not_full_population'


def test_explicit_cohort_cli_freezes_metadata_without_model(tmp_path,capsys):
    from agc_runtime.metrics_cli import main
    for name,value in [('batch',batch()),('tasks',[task()]),('classifier',classifier())]:
        (tmp_path/(name+'.json')).write_text(json.dumps(value),encoding='utf-8')
    args=['research-cohort']
    for name in ('batch','tasks','classifier'):
        args.extend(['--'+name,str(tmp_path/(name+'.json'))])
    output=tmp_path/'output'
    args.extend(['--output',str(output)])
    assert main(args)==0
    response=json.loads(capsys.readouterr().out)
    assert response['model_called'] is False
    frozen=json.loads((output/'research-cohort.json').read_text(encoding='utf-8'))
    assert api().validate_research_cohort(batch(),frozen)==frozen
    original=(output/'research-cohort.json').read_bytes()
    assert main(args)!=0
    assert (output/'research-cohort.json').read_bytes()==original
