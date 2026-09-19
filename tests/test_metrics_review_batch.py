import importlib
import json
from types import SimpleNamespace

import pytest

from agc_runtime.metrics_models import freeze_batch
from agc_runtime.metrics_eval import prepare_plan
from agc_runtime.metrics_execution import execute_entry
from test_metrics_judge_input import fixture
from test_metrics_execution import Gateway


def api():
    return importlib.import_module('agc_runtime.metrics_review_batch')


def setup(tmp_path):
    batch=freeze_batch(start='2026-09-11T00:00:00Z',end='2026-09-12T00:00:00Z',cutoff='2099-01-01T00:00:00Z',data_kind='synthetic')
    old,subject,docs=fixture()
    plan=prepare_plan(batch_id=batch['batch_id'],cases=old['cases'],judge=old['judge'],rules=old['rules'])
    gateway=Gateway(plan['judge'])
    args=dict(directory=tmp_path,consent_digest=plan['authorization_digest'],subject=subject,documents=docs,
              revoked_refs=lambda:[],gateway=gateway)
    execute_entry(plan,plan['entries'][0]['entry_id'],**args)
    first=json.loads((tmp_path/plan['entries'][0]['entry_id']/'result.json').read_text())
    gateway.handler=lambda p:SimpleNamespace(output=dict(status='completed',reason=None,candidates=[],matches=[]),usage=None,observed_configuration=None)
    execute_entry(plan,plan['entries'][1]['entry_id'],dependency=first,**args)
    return batch,plan,lambda c:dict(subject=subject,documents=docs,revoked_refs=[])


def test_freeze_and_offline_recompute_without_source_text(tmp_path):
    batch,plan,resolver=setup(tmp_path)
    review=api().freeze_review(batch,plan,tmp_path,resolve_case=resolver)
    assert api().validate_review(review,batch)==review
    assert review['rows'][0]['status']=='usable_judgment'
    assert review['rows'][0]['human_review']=='unreviewed'
    raw=json.dumps(review)
    assert 'CANDIDATE_SECRET' not in raw and 'A synthetic preference' not in raw
    counts=api().review_metrics(review,batch)
    assert counts['M4']['usable_cases']==1
    assert counts['M2']['collected']['groups'][0]['retention']['ratio'] is None


def test_tampered_review_rejected(tmp_path):
    batch,plan,resolver=setup(tmp_path)
    review=api().freeze_review(batch,plan,tmp_path,resolve_case=resolver)
    review['rows'][0]['status']='not_run'
    with pytest.raises(ValueError): api().validate_review(review,batch)


def test_wrong_original_batch_rejected(tmp_path):
    batch,plan,resolver=setup(tmp_path)
    other=freeze_batch(start='2026-01-01T00:00:00Z',end='2026-01-02T00:00:00Z',cutoff='2026-01-02T00:00:00Z')
    with pytest.raises(ValueError): api().freeze_review(other,plan,tmp_path,resolve_case=resolver)


def test_unavailable_evidence_remains_unknown_in_frozen_rows(tmp_path):
    batch,plan,_=setup(tmp_path)
    def missing(c): raise ValueError('unavailable')
    review=api().freeze_review(batch,plan,tmp_path,resolve_case=missing)
    row=review['rows'][0]
    assert row['status']=='unchecked'
    assert row['candidate_verdicts'] is None
    assert api().review_metrics(review,batch)['M2']['collected']['unassessed_cases']==1


def test_research_axes_survive_freezing_without_reason_text(tmp_path):
    from test_metrics_judge_input import research_fixture
    batch=freeze_batch(start='2026-09-11T00:00:00Z',end='2026-09-12T00:00:00Z',cutoff='2099-01-01T00:00:00Z',data_kind='synthetic')
    old,subject,docs=research_fixture(['task_input','task_output','research_background','research_source'])
    plan=prepare_plan(batch_id=batch['batch_id'],cases=old['cases'],judge=old['judge'],rules=old['rules'])
    refs=[d['ref'] for d in docs]
    output=dict(status='completed',reason=None,relevance='specific_useful',misleading='yes',background_accuracy='supported',
        issues=['unsupported_connection'],evidence=dict(source=[refs[3]],research=[refs[2]],connection=[refs[1]]),explanation='PRIVATE DERIVED REASON')
    gateway=Gateway(plan['judge'],lambda p:SimpleNamespace(output=output,usage=None,observed_configuration=None))
    execute_entry(plan,plan['entries'][0]['entry_id'],directory=tmp_path,consent_digest=plan['authorization_digest'],
        subject=subject,documents=docs,revoked_refs=lambda:[],gateway=gateway)
    review=api().freeze_review(batch,plan,tmp_path,resolve_case=lambda c:dict(subject=subject,documents=docs,revoked_refs=[]))
    result=api().review_metrics(review,batch)['M5']
    assert result['relevance']=={'specific_useful':1}
    assert result['misleading']=={'yes':1}
    assert result['human_review']=={'unreviewed':1}
    assert 'PRIVATE DERIVED REASON' not in json.dumps(review)
    from agc_runtime.metrics_report import render_report
    html = render_report(batch, review=review)
    assert html.index('误导风险（优先审查）') < html.index('<h3>联系质量</h3>')
    assert '具体且有帮助' in html and '有误导' in html
    assert 'PRIVATE DERIVED REASON' not in html
    assert '未经人类复核' in html


def test_extra_text_rejected_even_with_recomputed_digest(tmp_path):
    from agc_runtime.metrics_models import digest
    batch,plan,resolver=setup(tmp_path)
    review=api().freeze_review(batch,plan,tmp_path,resolve_case=resolver)
    review['rows'][0]['private_text']='must not persist here'
    review['review_id']='mr_'+digest({k:v for k,v in review.items() if k!='review_id'})
    with pytest.raises(ValueError): api().validate_review(review,batch)


def test_evaluation_after_source_cutoff_has_its_own_observation_time(tmp_path, monkeypatch):
    from agc_runtime import metrics_execution
    monkeypatch.setattr(metrics_execution, '_now', lambda:'2100-01-01T00:00:00Z')
    batch,plan,resolver=setup(tmp_path)
    review=api().freeze_review(batch,plan,tmp_path,resolve_case=resolver,
                              evaluation_cutoff='2100-01-01T00:00:01Z')
    assert review['cutoff']==batch['window']['cutoff']
    assert review['evaluation_cutoff']=='2100-01-01T00:00:01Z'
    assert review['rows'][0]['status']=='usable_judgment'


def test_earlier_evaluation_cutoff_does_not_include_future_results(tmp_path, monkeypatch):
    from agc_runtime import metrics_execution
    monkeypatch.setattr(metrics_execution, '_now', lambda:'2100-01-01T00:00:00Z')
    batch,plan,resolver=setup(tmp_path)
    review=api().freeze_review(batch,plan,tmp_path,resolve_case=resolver,
                              evaluation_cutoff='2099-12-31T00:00:00Z')
    assert review['rows'][0]['status']=='not_run'


def test_legacy_review_remains_readable_and_v2_requires_evaluation_cutoff(tmp_path):
    from agc_runtime.metrics_models import digest
    batch,plan,resolver=setup(tmp_path)
    review=api().freeze_review(batch,plan,tmp_path,resolve_case=resolver)
    review.pop('evaluation_cutoff')
    with pytest.raises(ValueError): api().validate_review(review,batch)
    review['schema_version']='agc.metrics-review.v1'
    review.pop('execution_history',None)
    review['review_id']='mr_'+digest({k:v for k,v in review.items() if k!='review_id'})
    assert api().validate_review(review,batch)==review
