import importlib
import json
from copy import deepcopy

import pytest

from agc_runtime.capture_contracts import RevisionRef, receipt_id_for
from agc_runtime.metrics_models import digest


def api():
    return importlib.import_module('agc_runtime.metrics_source_bindings')


def research(tmp_path,monkeypatch):
    from test_metrics_research_cli import prepare
    from agc_runtime.metrics_cli import main
    common,_=prepare(tmp_path,monkeypatch)
    output=tmp_path/'planned'
    assert main(['prepare-research-plan',*common,'--output',str(output)])==0
    read=lambda p:json.loads(p.read_text(encoding='utf-8'))
    return read(output/'plan.json'),read(output/'source-map.json'),read(tmp_path/'references.json')


def test_research_binding_identifies_exact_native_revision_without_body(tmp_path,monkeypatch):
    plan,mapping,refs=research(tmp_path,monkeypatch)
    value=api().evaluation_source_bindings(plan,mapping,native_references=refs)
    row=value['entries'][0]
    assert row['subject_ref']==plan['cases'][0]['case_id']
    assert row['receipt_id']==receipt_id_for(RevisionRef.from_mapping(refs[0]).key)
    assert row['native_reference_digest']==digest(refs[0])
    assert 'runtime research' not in json.dumps(value)
    assert 'locator' not in json.dumps(value)
    other=deepcopy(refs)
    other[0]['capture_key']['revision_id']='another-revision'
    changed=api().evaluation_source_bindings(plan,mapping,native_references=other)
    # Live source verification is separate; native revisions must not collapse.
    assert changed['entries'][0]['receipt_id']!=row['receipt_id']


@pytest.mark.parametrize('fault',['missing','duplicate','foreign','map_identity'])
def test_research_binding_refuses_missing_or_ambiguous_join(tmp_path,monkeypatch,fault):
    plan,mapping,refs=research(tmp_path,monkeypatch)
    if fault=='missing': refs=[]
    elif fault=='duplicate': refs=refs+refs
    elif fault=='foreign': refs[0]['capture_key']['task_id']='different-task'
    else: mapping['map_id']='mrsm_'+'0'*64
    with pytest.raises(ValueError):
        api().evaluation_source_bindings(plan,mapping,native_references=refs)


def test_capture_binding_uses_reference_receipt_not_metric_document_hash(tmp_path,monkeypatch):
    from test_metrics_host import host
    from test_metrics_research_cohort import batch
    from agc_runtime.metrics_capture_plan import prepare_capture_plan
    _,_,gateway=host(tmp_path,monkeypatch)
    from agc_runtime.metrics_host import load_host
    reference=dict(schema_version='eval.evidence-ref.v0.1',provider='agc',kind='capture-item',
                   version='1',ref='cr_'+'a'*64,digest='sha256:'+'b'*64)
    prepared=prepare_capture_plan(batch(),[reference],source=load_host()['source'],judge=gateway.configuration)
    value=api().evaluation_source_bindings(prepared['plan'],prepared['source_map'])
    assert value['entries'][0]['receipt_id']==reference['ref']
    assert value['entries'][0]['native_reference_digest'] is None


def test_classification_binding_only_covers_ready_inputs(tmp_path,monkeypatch):
    from test_metrics_research_classification import fixture
    from test_metrics_research_cohort import batch
    from test_metrics_eval import config
    from agc_runtime.metrics_classification_execution import prepare_classification_plan
    prep=fixture(tmp_path,monkeypatch)
    refs=json.loads((tmp_path/'references.json').read_text())
    plan=prepare_classification_plan(batch(),prep,judge=config())
    value=api().classification_source_bindings(batch(),plan,prep,refs)
    assert len(value['entries'])==1
    assert value['entries'][0]['receipt_id']==receipt_id_for(RevisionRef.from_mapping(refs[0]).key)
    wrong=deepcopy(refs); wrong[0]['capture_key']['revision_id']='other-revision'
    with pytest.raises(ValueError):
        api().classification_source_bindings(batch(),plan,prep,wrong)


def test_host_research_execution_registers_source_join(tmp_path,monkeypatch):
    from test_metrics_evidence_cli import setup
    gateway,_,_=setup(tmp_path,monkeypatch)
    files=list((tmp_path/'host'/'send-ledger'/'source-bindings').glob('*.json'))
    assert len(files)==1
    value=json.loads(files[0].read_text())
    ref=RevisionRef.from_mapping(json.loads((tmp_path/'references.json').read_text())[0])
    assert value['entries'][0]['receipt_id']==receipt_id_for(ref.key)
    assert gateway.calls==1


def test_binding_inventory_failure_prevents_host_send(tmp_path,monkeypatch):
    from agc_runtime.metrics_cli import main
    plan,mapping,_=research(tmp_path,monkeypatch)
    inventory=tmp_path/'host'/'send-ledger'/'source-bindings'
    inventory.write_text('not a directory')
    execution=tmp_path/'execution'; execution.mkdir()
    args=['evaluate-research','--plan',str(tmp_path/'planned'/'plan.json'),
          '--source-map',str(tmp_path/'planned'/'source-map.json'),
          '--output',str(execution),'--consent',plan['authorization_digest']]
    for flag in ('batch','cohort','references'):
        args.extend(['--'+flag,str(tmp_path/(flag+'.json'))])
    assert main(args)==2
    assert not list(execution.rglob('result.json'))


def test_inventory_is_idempotent_but_not_overwritable(tmp_path,monkeypatch):
    plan,mapping,refs=research(tmp_path,monkeypatch)
    value=api().evaluation_source_bindings(plan,mapping,native_references=refs)
    ledger=tmp_path/'host'/'send-ledger'
    assert api().register_source_bindings(ledger,value)==value
    assert api().register_source_bindings(ledger,value)==value
    refs[0]['capture_key']['revision_id']='different-revision'
    changed=api().evaluation_source_bindings(plan,mapping,native_references=refs)
    with pytest.raises(ValueError): api().register_source_bindings(ledger,changed)
    assert api().read_source_bindings(ledger,plan['plan_id'])==value


def test_classification_cli_keeps_ready_input_with_other_duplicate_ambiguous_refs(tmp_path,monkeypatch):
    from test_metrics_classification_cli import setup
    from agc_runtime.metrics_cli import main
    gateway,_,args,execution=setup(tmp_path,monkeypatch)
    ref_path=tmp_path/'references.json'
    ready=json.loads(ref_path.read_text())[0]
    other=deepcopy(ready); other['capture_key']['task_id']='different-task'
    ref_path.write_text(json.dumps([ready,other,other]))
    output=tmp_path/'mixed-classification-plan'
    assert main(['prepare-classification-plan','--batch',str(tmp_path/'batch.json'),
                 '--references',str(ref_path),'--output',str(output)])==0
    plan=json.loads((output/'plan.json').read_text())
    assert plan['input_count']==1
    args[args.index('--plan')+1]=str(output/'plan.json')
    args[-1]=plan['authorization_digest']
    assert main(args)==0
    assert gateway.calls==1
    assert list(execution.rglob('classification.json'))
    binding=api().read_source_bindings(tmp_path/'host'/'send-ledger',plan['plan_id'])
    assert [e['receipt_id'] for e in binding['entries']]==[receipt_id_for(RevisionRef.from_mapping(ready).key)]


@pytest.mark.parametrize('fault',['missing','changed'])
def test_directory_registration_binds_source_inventory_identity(tmp_path,monkeypatch,fault):
    from test_metrics_evidence_cli import setup
    from agc_runtime.metrics_artifact_registry import verify_registration
    from pathlib import Path
    setup(tmp_path,monkeypatch)
    ledger=tmp_path/'host'/'send-ledger'
    registered=json.loads(next((ledger/'artifact-registry').glob('*.json')).read_text())
    source_path=next((ledger/'source-bindings').glob('*.json'))
    source=json.loads(source_path.read_text())
    assert registered.get('source_binding_id')==source['binding_id']
    if fault=='missing': source_path.unlink()
    else:
        source['entries'][0]['receipt_id']='cr_'+'f'*64
        source['binding_id']='msb_'+digest({k:v for k,v in source.items() if k!='binding_id'})
        source_path.write_text(json.dumps(source))
    with pytest.raises(ValueError):
        verify_registration(ledger,Path(registered['directory']),registered['dependencies'])


def test_host_does_not_downgrade_to_unbound_registration_before_send(tmp_path,monkeypatch):
    from agc_runtime import metrics_artifact_registry
    from test_metrics_research_cli import prepare
    from agc_runtime.metrics_cli import main
    original=metrics_artifact_registry.register_execution_directory
    def vanished(ledger,directory,expected,**kwargs):
        for path in (ledger/'source-bindings').glob('*.json'):
            path.unlink()
        return original(ledger,directory,expected,**kwargs)
    monkeypatch.setattr(metrics_artifact_registry,'register_execution_directory',vanished)
    common,gateway=prepare(tmp_path,monkeypatch)
    planned=tmp_path/'plan'
    assert main(['prepare-research-plan',*common,'--output',str(planned)])==0
    plan=json.loads((planned/'plan.json').read_text())
    execution=tmp_path/'execution'; execution.mkdir()
    assert main(['evaluate-research',*common,'--plan',str(planned/'plan.json'),
        '--source-map',str(planned/'source-map.json'),'--output',str(execution),
        '--consent',plan['authorization_digest']])==2
    assert not list(execution.glob('report-*.html'))
    assert gateway.calls==0
    assert not list((tmp_path/'execution').rglob('result.json'))


def test_host_export_refuses_legitimate_standalone_unbound_quality_result(tmp_path,monkeypatch):
    from agc_runtime.metrics_host import load_host
    from agc_runtime.metrics_research_plan import research_plan_resolver
    from agc_runtime.metrics_runner import run_plan
    from agc_runtime.metrics_review_batch import freeze_review
    from agc_runtime.metrics_cli import main
    plan,mapping,refs=research(tmp_path,monkeypatch)
    batch=json.loads((tmp_path/'batch.json').read_text())
    cohort=json.loads((tmp_path/'cohort.json').read_text())
    context=load_host(); source=context['research_source_factory'](refs)
    resolver=research_plan_resolver(batch,cohort,plan,mapping,source=source)
    execution=tmp_path/'standalone'; execution.mkdir()
    result=run_plan(plan,directory=execution,ledger_directory=context['ledger'],
        consent_digest=plan['authorization_digest'],gateway=context['gateway'],resolve_case=resolver)
    assert result['entries'][0]['status']=='executed'
    review=freeze_review(batch,plan,execution,resolve_case=resolver,ledger_directory=context['ledger'])
    review_path=tmp_path/'standalone-review.json'; review_path.write_text(json.dumps(review))
    output=tmp_path/'standalone-export'
    args=['export-review-evidence','--review',str(review_path),'--execution-dir',str(execution),
          '--source-map',str(tmp_path/'planned'/'source-map.json'),'--output',str(output)]
    for name in ('batch','cohort','references'):
        args.extend(['--'+name,str(tmp_path/(name+'.json'))])
    assert main(args)==2
    assert not output.exists()


def test_host_export_refuses_legitimate_standalone_unbound_classification(tmp_path,monkeypatch):
    from test_metrics_classification_execution import setup
    from test_metrics_research_cohort import batch
    from agc_runtime.metrics_classification_execution import execute_classification
    from agc_runtime.metrics_cli import main
    from agc_runtime.metrics_host import load_host
    _,plan,model,args=setup(tmp_path,monkeypatch)
    args['ledger_directory']=load_host()['ledger']
    assert execute_classification(batch(),plan,**args)['status']=='completed'
    path=tmp_path/'standalone-plan.json'; path.write_text(json.dumps(plan))
    output=tmp_path/'standalone-export'
    assert main(['export-classification','--batch',str(tmp_path/'batch.json'),
                 '--references',str(tmp_path/'references.json'),'--plan',str(path),
                 '--execution-dir',str(args['directory']),'--output',str(output)])==2
    assert not output.exists() and model.calls==1
