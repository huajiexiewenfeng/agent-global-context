import importlib
from copy import deepcopy

import pytest

from agc_runtime.metrics_models import canonical, digest, opaque
from agc_runtime.metrics_research_cohort import freeze_research_cohort
from agc_runtime.metrics_judge_input import build_input
from test_metrics_research_cohort import batch, classifier, task
from test_metrics_eval import config


class Source:
    def __init__(self):
        self.changed=False
        self.missing=False
        self.role='research_background'
        self.calls=[]

    def prepare(self,reference):
        self.calls.append(deepcopy(reference))
        if self.missing:
            raise ValueError('source_missing')
        docs=[dict(ref=opaque(reference['task_ref']+role),version='1',role=role,
                   content='PRIVATE SYNTHETIC '+role+(' changed' if self.changed else ''))
              for role in ('task_input','task_output',self.role)]
        return dict(task_ref=reference['task_ref'],revision=reference['revision'],documents=docs)


def setup():
    module=importlib.import_module('agc_runtime.metrics_research_plan')
    cohort=freeze_research_cohort(batch(),[task(),task(2,decision='ambiguous',reason='intent_unclear')],
                                   classifier=classifier())
    source=Source()
    result=module.prepare_research_plan(batch(),cohort,source=source,judge=config())
    return module,cohort,source,result


def test_research_plan_uses_selected_tasks_and_persists_no_content():
    module,cohort,source,result=setup()
    assert result['plan']['max_calls']==1
    assert 'PRIVATE SYNTHETIC' not in canonical(result)
    assert source.calls==[dict(task_ref=task()['task_ref'],revision=task()['revision'])]
    resolve=module.research_plan_resolver(batch(),cohort,result['plan'],result['source_map'],source=source)
    entry=result['plan']['entries'][0]
    resolved=resolve(entry['case_id'])
    payload=build_input(result['plan'],entry['entry_id'],**resolved)
    assert payload['profile']['id'].endswith('research_relevance')
    assert len(payload['evidence'])==3
    assert result['source_map']['cohort_id']==cohort['cohort_id']


@pytest.mark.parametrize('fault',['changed','missing'])
def test_live_source_change_blocks_frozen_plan(fault):
    module,cohort,source,result=setup()
    resolve=module.research_plan_resolver(batch(),cohort,result['plan'],result['source_map'],source=source)
    setattr(source,fault,True)
    with pytest.raises(ValueError): resolve(result['plan']['cases'][0]['case_id'])


def test_current_memory_cannot_substitute_historical_background():
    module,cohort,source,_=setup()
    source.role='current_memory'
    with pytest.raises(ValueError): module.prepare_research_plan(batch(),cohort,source=source,judge=config())


def test_rehashed_map_cannot_redirect_selected_task():
    module,cohort,source,result=setup()
    mapping=result['source_map']
    mapping['entries'][0]['reference']['task_ref']=task(2)['task_ref']
    mapping['map_id']='mrsm_'+digest({k:v for k,v in mapping.items() if k!='map_id'})
    with pytest.raises(ValueError):
        module.research_plan_resolver(batch(),cohort,result['plan'],mapping,source=source)


def test_empty_cohort_yields_empty_plan_without_source_reads():
    module=importlib.import_module('agc_runtime.metrics_research_plan')
    cohort=freeze_research_cohort(batch(),[],classifier=classifier())
    source=Source()
    result=module.prepare_research_plan(batch(),cohort,source=source,judge=config())
    assert result['plan']['max_calls']==0
    assert source.calls==[]


def test_research_executes_reuses_and_invalidates_through_real_runner(tmp_path):
    from types import SimpleNamespace
    from agc_runtime.metrics_runner import run_plan
    from agc_runtime.metrics_review_batch import freeze_review
    from agc_runtime.metrics_report import render_report
    from test_metrics_execution import Gateway
    module,cohort,source,result=setup()
    plan=result['plan']
    resolve=module.research_plan_resolver(batch(),cohort,plan,result['source_map'],source=source)
    output=tmp_path/'run'; output.mkdir()
    ledger=tmp_path/'ledger'; ledger.mkdir()
    def judge(payload):
        refs={d['role']:d['ref'] for d in payload['evidence']}
        return SimpleNamespace(output=dict(status='completed',reason=None,
            relevance='partial_or_generic',misleading='no',background_accuracy='supported',issues=[],
            evidence=dict(source=[],research=[refs['research_background']],connection=[refs['task_output']]),
            explanation='Synthetic partial research connection.'),usage=None,observed_configuration=None)
    gateway=Gateway(plan['judge'],judge)
    args=dict(directory=output,ledger_directory=ledger,consent_digest=plan['authorization_digest'],
              gateway=gateway,resolve_case=resolve)
    assert run_plan(plan,**args)['entries'][0]['status']=='executed'
    assert run_plan(plan,**args)['entries'][0]['status']=='reused'
    assert gateway.calls==1
    review=freeze_review(batch(),plan,output,resolve_case=resolve)
    html=render_report(batch(),review=review)
    assert 'PRIVATE SYNTHETIC' not in html
    assert 'partial_or_generic' in html
    source.missing=True
    assert run_plan(plan,**args)['entries'][0]['status']=='evidence_unavailable'
    assert gateway.calls==1
