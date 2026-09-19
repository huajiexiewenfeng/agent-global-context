import importlib
import json

import pytest

from agc_runtime.metrics_models import digest


def api():
    return importlib.import_module('agc_runtime.metrics_cleanup_candidates')


def setup(tmp_path):
    from test_metrics_runner import run
    from agc_runtime.metrics_eval import prepare_plan
    from agc_runtime.metrics_source_bindings import register_source_bindings
    runner,old,args,gateway=run(tmp_path)
    other=dict(old['cases'][0],case_id='id_'+'d'*64)
    plan=prepare_plan(batch_id=old['batch_id'],cases=[*old['cases'],other],judge=old['judge'],rules=old['rules'])
    bindings=dict(schema_version='agc.metrics-source-bindings.v1',plan_id=plan['plan_id'],
                  input_binding_digest='e'*64,entries=[dict(subject_ref=case['case_id'],
                  receipt_id='cr_'+letter*64,native_reference_digest=None)
                  for case,letter in zip(plan['cases'],('a','b'))])
    bindings['binding_id']='msb_'+digest(bindings)
    register_source_bindings(args['ledger_directory'],bindings)
    args['consent_digest']=plan['authorization_digest']
    assert all(r['status']=='executed' for r in runner.run_plan(plan,**args)['entries'])
    return plan,args


def test_selects_only_target_case_in_same_plan_without_writes_or_content(tmp_path):
    plan,args=setup(tmp_path)
    before={p:p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    value=api().cleanup_candidates(args['ledger_directory'],'cr_'+'a'*64)
    expected={e['entry_id'] for e in plan['entries'] if e['case_id']==plan['cases'][0]['case_id']}
    assert {r['entry_id'] for r in value['candidates']}==expected
    assert value['pending']==[] and value['unbound']==[]
    assert all({f['name'] for f in r['files']}=={'result.json','receipt.json'} for r in value['candidates'])
    assert 'CANDIDATE_SECRET' not in json.dumps(value)
    assert before=={p:p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}


def test_missing_terminal_is_pending_not_deletion_candidate(tmp_path):
    plan,args=setup(tmp_path)
    entry=plan['entries'][0]
    (args['directory']/entry['entry_id']/'finished.json').unlink()
    (args['directory']/entry['entry_id']/'.attempt.lock').unlink()
    result=api().cleanup_candidates(args['ledger_directory'],'cr_'+'a'*64)
    assert len(result['pending'])==1
    assert all(r['entry_id']!=entry['entry_id'] for r in result['candidates'])


@pytest.mark.parametrize('fault',['source_binding','directory','artifact_names','terminal'])
def test_changed_or_invalid_inventory_never_produces_candidate_list(tmp_path,fault):
    plan,args=setup(tmp_path)
    directory=args['directory']/plan['entries'][0]['entry_id']
    if fault=='source_binding':
        next((args['ledger_directory']/'source-bindings').glob('*.json')).write_text('{}')
    elif fault=='directory':
        directory.rename(directory.with_name(directory.name+'-original'))
        directory.mkdir()
    elif fault=='artifact_names':
        path=directory/'dependencies.json'
        data=json.loads(path.read_text()); data['artifacts']=['../../user-file']
        path.write_text(json.dumps(data))
    else:
        path=directory/'finished.json'; data=json.loads(path.read_text())
        data['plan_id']='mplan_'+'f'*64; path.write_text(json.dumps(data))
    with pytest.raises(ValueError): api().cleanup_candidates(args['ledger_directory'],'cr_'+'a'*64)


def test_unbound_inventory_is_reported_not_silently_treated_as_empty(tmp_path):
    from test_metrics_runner import run
    runner,plan,args,_=run(tmp_path)
    runner.run_plan(plan,**args)
    result=api().cleanup_candidates(args['ledger_directory'],'cr_'+'a'*64)
    assert result['candidates']==[] and len(result['unbound'])==2


def test_no_related_receipt_is_distinct_from_unbound(tmp_path):
    _,args=setup(tmp_path)
    result=api().cleanup_candidates(args['ledger_directory'],'cr_'+'f'*64)
    assert result['candidates']==result['pending']==result['unbound']==[]


@pytest.mark.parametrize('mode',['completed','failed','pending'])
def test_classification_candidates_keep_batch_boundary_and_terminal_state(tmp_path,monkeypatch,mode):
    from test_metrics_classification_cli import setup as classification_setup
    from agc_runtime.metrics_cli import main
    from agc_runtime.capture_contracts import RevisionRef,receipt_id_for
    gateway,_,command,execution=classification_setup(tmp_path,monkeypatch)
    if mode=='failed':
        def fail(payload): raise RuntimeError('synthetic failure')
        gateway.handler=fail
    assert main(command)==0
    if mode=='pending':
        next(execution.rglob('finished.json')).unlink()
        next(execution.rglob('.attempt.lock')).unlink()
    ref=RevisionRef.from_mapping(json.loads((tmp_path/'references.json').read_text())[0])
    result=api().cleanup_candidates(tmp_path/'host'/'send-ledger',receipt_id_for(ref.key))
    if mode=='pending':
        assert result['candidates']==[] and len(result['pending'])==1
    else:
        assert len(result['candidates'])==1 and result['pending']==[]
        item=result['candidates'][0]
        assert item['entry_id'] is None
        if mode=='completed':
            assert {f['name'] for f in item['files']}=={'classification.json','receipt.json'}
        else:
            assert item['terminal_status']=='classification_error'
            assert item['files']==[]
            assert item['absent_files']==['classification.json','receipt.json']
