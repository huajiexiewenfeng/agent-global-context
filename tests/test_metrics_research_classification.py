from copy import deepcopy
import json

import pytest

from test_metrics_research_cli import prepare
from test_metrics_research_cohort import batch


def fixture(tmp_path,monkeypatch):
    from agc_runtime.metrics_host import load_host
    from agc_runtime.metrics_research_inputs import prepare_research_inputs
    prepare(tmp_path,monkeypatch)
    refs=json.loads((tmp_path/'references.json').read_text(encoding='utf-8'))
    return prepare_research_inputs(batch(),refs,source_factory=load_host()['research_source_factory'])


def label(preparation):
    entry=preparation['manifest']['entries'][0]
    return dict(task_ref=entry['task_ref'],revision=entry['revision'],
                input_digest=entry['input_ref']['digest'],decision='include',
                reason='research_connection_request')


def classifier():
    from agc_runtime.metrics_models import opaque
    return dict(method='llm',rule_version='research-intent.v1',
                configuration_digest='a'*64,authorization_ref=opaque('synthetic-authorization'))


def test_bound_labels_build_cohort_without_answer_or_quality(tmp_path,monkeypatch):
    from agc_runtime.metrics_research_classification import classification_request,freeze_classified_research
    value=fixture(tmp_path,monkeypatch)
    request=classification_request(batch(),value)
    assert 'runtime research' in json.dumps(request)
    assert 'trace comparison' not in json.dumps(request)
    result=freeze_classified_research(batch(),value,[label(value)],classifier=classifier())
    assert result['cohort']['counts']['selected']==1
    assert result['preparation_manifest']==value['manifest']
    assert result['classification_provenance']=='caller_supplied_unverified'
    assert 'runtime research' not in json.dumps(result)


@pytest.mark.parametrize('change',['missing','duplicate','foreign','revision','digest','quality'])
def test_label_set_must_match_inputs_exactly(tmp_path,monkeypatch,change):
    from agc_runtime.metrics_research_classification import freeze_classified_research
    value=fixture(tmp_path,monkeypatch); labels=[label(value)]
    if change=='missing': labels=[]
    elif change=='duplicate': labels*=2
    elif change=='foreign': labels[0]['task_ref']='opaque_'+'c'*64
    elif change=='revision': labels[0]['revision']='c'*64
    elif change=='digest': labels[0]['input_digest']='c'*64
    else: labels[0]['quality_score']=1
    with pytest.raises(ValueError):
        freeze_classified_research(batch(),value,labels,classifier=classifier())


def test_changed_input_or_manifest_is_rejected(tmp_path,monkeypatch):
    from agc_runtime.metrics_research_classification import classification_request
    value=fixture(tmp_path,monkeypatch)
    changed=deepcopy(value); changed['inputs'][0]['document']['content']='replacement'
    with pytest.raises(ValueError): classification_request(batch(),changed)
    changed=deepcopy(value); changed['manifest']['counts']['ready']=0
    with pytest.raises(ValueError): classification_request(batch(),changed)


def test_unavailable_input_keeps_coverage_without_inventing_classification(tmp_path,monkeypatch):
    from agc_runtime.metrics_models import digest
    from agc_runtime.metrics_research_classification import freeze_classified_research
    value=fixture(tmp_path,monkeypatch)
    entry=value['manifest']['entries'][0]
    entry.update(status='evidence_unavailable',revision=None,input_ref=None)
    value['inputs']=[]
    value['manifest']['counts'].update(ready=0,evidence_unavailable=1)
    manifest=value['manifest']
    manifest['preparation_id']='mrprep_'+digest({k:v for k,v in manifest.items() if k!='preparation_id'})
    result=freeze_classified_research(batch(),value,[],classifier=classifier())
    assert result['labels']==[]
    assert result['cohort']['status']=='no_selected_cases'
    assert result['preparation_manifest']['counts']['evidence_unavailable']==1


def test_structured_payload_and_output_validation(tmp_path,monkeypatch):
    from agc_runtime.metrics_research_classification import classification_payload,freeze_classification_output
    from jsonschema import Draft202012Validator
    value=fixture(tmp_path,monkeypatch)
    payload=classification_payload(batch(),value)
    assert set(payload)=={'case','profile','evidence','instruction','output_schema'}
    assert all(d['role']=='task_input' for d in payload['evidence'])
    schema=payload['output_schema']; Draft202012Validator.check_schema(schema)
    output={'labels':[label(value)]}
    Draft202012Validator(schema).validate(output)
    assert freeze_classification_output(batch(),value,output,classifier=classifier())['cohort']['counts']['selected']==1
    for invalid in ({'labels':output['labels'],'score':1},{'labels':[dict(label(value),reason='intent_unclear')]},
                    {'labels':[]}, {'labels':output['labels']*2}):
        with pytest.raises(ValueError):
            freeze_classification_output(batch(),value,invalid,classifier=classifier())


def test_payload_through_existing_gateway_with_fake_adapter(tmp_path,monkeypatch):
    from agc_runtime.metrics_research_classification import classification_payload
    from test_metrics_gateway import gateway,Adapter
    value=fixture(tmp_path,monkeypatch); payload=classification_payload(batch(),value)
    gateway(tmp_path).evaluate(payload)
    instance=Adapter.instances[-1]
    assert instance.kwargs['output_schema']==payload['output_schema']
    assert instance.payload['evidence']==payload['evidence']
    assert 'trace comparison' not in json.dumps(instance.payload)
