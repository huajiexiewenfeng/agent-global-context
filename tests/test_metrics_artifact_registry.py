import json

import pytest

from test_metrics_runner import run


def registrations(args):
    return list((args['ledger_directory']/'artifact-registry').glob('*.json'))


def test_runner_registers_each_directory_before_model_call(tmp_path):
    api,plan,args,gateway=run(tmp_path)
    original=gateway.evaluate
    def evaluate(payload):
        paths=registrations(args)
        assert len(paths)==gateway.calls+1
        record=json.loads(paths[-1].read_text(encoding='utf-8'))
        assert record['dependencies']['artifacts']==['result.json','receipt.json']
        assert 'CANDIDATE_SECRET' not in json.dumps(record)
        return original(payload)
    gateway.evaluate=evaluate
    outcome=api.run_plan(plan,**args)
    assert [r['status'] for r in outcome['entries']]==['executed','executed']
    assert len(registrations(args))==2


def test_registry_path_failure_consumes_slot_without_model_or_result(tmp_path):
    api,plan,args,gateway=run(tmp_path)
    (args['ledger_directory']/'artifact-registry').write_text('not a directory')
    outcome=api.run_plan(plan,**args)
    assert gateway.calls==0
    assert outcome['entries'][0]['status']=='evaluation_error'
    assert not list(args['directory'].rglob('result.json'))
    assert (args['ledger_directory']/plan['plan_id']/(plan['entries'][0]['entry_id']+'.json')).is_file()


def test_classification_registers_before_send(tmp_path,monkeypatch):
    from test_metrics_classification_execution import setup
    from test_metrics_research_cohort import batch
    from agc_runtime.metrics_classification_execution import execute_classification
    _,plan,model,args=setup(tmp_path,monkeypatch)
    original=model.evaluate
    def evaluate(payload):
        records=registrations(args)
        assert len(records)==1
        value=json.loads(records[0].read_text(encoding='utf-8'))
        assert value['dependencies']['artifacts']==['classification.json','receipt.json']
        assert 'runtime research' not in json.dumps(value)
        return original(payload)
    model.evaluate=evaluate
    result=execute_classification(batch(),plan,**args)
    assert result['status']=='completed' and model.calls==1


@pytest.mark.parametrize('fault',['dependency','moved_directory','registry_record'])
def test_registry_binding_validation_rejects_changed_objects(tmp_path,fault):
    from agc_runtime.metrics_artifact_registry import verify_registration
    api,plan,args,_=run(tmp_path)
    api.run_plan(plan,**args)
    directory=args['directory']/plan['entries'][0]['entry_id']
    expected=json.loads((directory/'dependencies.json').read_text())
    record=verify_registration(args['ledger_directory'],directory,expected)
    assert record['directory']==str(directory.resolve())
    if fault=='dependency':
        (directory/'dependencies.json').write_text('{}')
    elif fault=='moved_directory':
        # Preserve original synthetic data; replace only its now-vacant pathname.
        directory.rename(directory.with_name(directory.name+'-original'))
        directory.mkdir()
        (directory/'dependencies.json').write_text(json.dumps(expected))
    else:
        path=args['ledger_directory']/'artifact-registry'/(record['registration_id']+'.json')
        value=json.loads(path.read_text()); value['directory']='D:/unrelated'
        path.write_text(json.dumps(value))
    with pytest.raises(ValueError):
        verify_registration(args['ledger_directory'],directory,expected)


def test_runner_does_not_reuse_output_with_corrupt_host_registration(tmp_path):
    api,plan,args,gateway=run(tmp_path)
    api.run_plan(plan,**args)
    for path in registrations(args):
        path.write_text('{}')
    result=api.run_plan(plan,**args)
    assert result['entries'][0]['status']=='existing_attempt_unusable'
    assert gateway.calls==2


def test_classification_reader_requires_host_registration(tmp_path,monkeypatch):
    from test_metrics_classification_execution import setup
    from test_metrics_research_cohort import batch
    from agc_runtime.metrics_classification_execution import execute_classification
    from agc_runtime.metrics_classification_reader import read_classification
    _,plan,model,args=setup(tmp_path,monkeypatch)
    execute_classification(batch(),plan,**args)
    registrations(args)[0].write_text('{}')
    with pytest.raises(ValueError):
        read_classification(batch(),plan,**{k:args[k] for k in ('directory','ledger_directory','resolve_preparation')})
    assert model.calls==1


@pytest.mark.parametrize('change_on_call',[4,6])
def test_evidence_rechecks_registry_after_its_final_source_reads(tmp_path,change_on_call):
    from test_metrics_review_batch import setup
    from agc_runtime.metrics_review_batch import freeze_review
    from agc_runtime.metrics_review_evidence import freeze_evidence
    from agc_runtime.metrics_artifact_registry import register_execution_directory
    batch,plan,resolve=setup(tmp_path)
    review=freeze_review(batch,plan,tmp_path,resolve_case=resolve)
    ledger=tmp_path/'ledger'; ledger.mkdir()
    for entry in plan['entries']:
        location=tmp_path/entry['entry_id']
        dependencies=json.loads((location/'dependencies.json').read_text())
        register_execution_directory(ledger,location,dependencies)
    calls=0
    def changed(case):
        nonlocal calls
        calls+=1
        if calls==change_on_call:
            for path in (ledger/'artifact-registry').glob('*.json'):
                path.write_text('{}')
        return resolve(case)
    evidence=freeze_evidence(batch,review,tmp_path,resolve_case=changed,ledger_directory=ledger)
    assert calls>=change_on_call
    assert evidence['cases'][0]['status']=='unavailable'
    assert evidence['cases'][0]['documents']==[]
