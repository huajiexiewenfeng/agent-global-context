import importlib
import json
from pathlib import Path

import pytest

from agc_runtime.locking import root_write_lock
from agc_runtime.paths import MemoryPaths
from agc_runtime.metrics_cleanup_candidates import cleanup_candidates
from test_metrics_cleanup_candidates import setup


def prepare(tmp_path):
    plan,args=setup(tmp_path)
    paths=MemoryPaths.from_root(tmp_path/'memory-lock')
    snapshot=cleanup_candidates(args['ledger_directory'],'cr_'+'a'*64)
    kwargs=dict(ledger=args['ledger_directory'],snapshot=snapshot,
                authorization='explicit_user_request',commit_guard=lambda:root_write_lock(paths))
    return plan,args,paths,kwargs


def apply(**kwargs):
    return importlib.import_module('agc_runtime.metrics_cleanup_apply').apply_cleanup(**kwargs)


def test_only_registered_selected_artifacts_are_removed(tmp_path):
    plan,args,paths,kwargs=prepare(tmp_path)
    unrelated=args['directory']/'user-note.txt'; unrelated.write_text('keep')
    before={p:p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    targets={Path(c['directory'])/f['name'] for c in kwargs['snapshot']['candidates'] for f in c['files']}
    result=apply(**kwargs)
    assert result['status']=='selected_artifacts_removed'
    assert len(result['deleted'])==4
    assert not any(p.exists() for p in targets)
    assert {p:p.read_bytes() for p in before if p not in targets}=={p:v for p,v in before.items() if p not in targets}
    assert not (paths.locks/'write.lock').exists()
    assert 'CANDIDATE_SECRET' not in json.dumps(result)
    refreshed=cleanup_candidates(args['ledger_directory'],kwargs['snapshot']['receipt_id'])
    assert all(not c['files'] for c in refreshed['candidates'])


@pytest.mark.parametrize('fault',['authorization','changed_file','pending','unbound','changed_registry','changed_terminal'])
def test_preflight_failure_deletes_nothing(tmp_path,fault):
    _,args,_,kwargs=prepare(tmp_path)
    candidate=kwargs['snapshot']['candidates'][0]
    if fault=='authorization': kwargs['authorization']='implicit'
    elif fault=='changed_file': (Path(candidate['directory'])/'result.json').write_text('changed')
    elif fault=='changed_registry':
        (args['ledger_directory']/'artifact-registry'/(candidate['registration_id']+'.json')).write_text('{}')
    elif fault=='changed_terminal':
        path=Path(candidate['directory'])/'finished.json'
        data=json.loads(path.read_text()); data['finished_at']='2099-01-01T00:00:00Z'
        path.write_text(json.dumps(data))
    elif fault=='pending':
        (Path(candidate['directory'])/'finished.json').unlink()
        (Path(candidate['directory'])/'.attempt.lock').unlink()
        kwargs['snapshot']=cleanup_candidates(args['ledger_directory'],kwargs['snapshot']['receipt_id'])
    else:
        from test_metrics_runner import run
        extra=tmp_path/'standalone'; extra.mkdir()
        runner,plan,other,_=run(extra); other['ledger_directory']=args['ledger_directory']
        # A different plan has no source bindings, so it is explicitly unbound.
        from agc_runtime.metrics_eval import prepare_plan
        plan=prepare_plan(batch_id=plan['batch_id'],cases=plan['cases'],judge=plan['judge'],rules=plan['rules'])
        other['consent_digest']=plan['authorization_digest']
        runner.run_plan(plan,**other)
        kwargs['snapshot']=cleanup_candidates(args['ledger_directory'],kwargs['snapshot']['receipt_id'])
        assert kwargs['snapshot']['unbound']
    before={p:p.read_bytes() for p in args['directory'].rglob('*') if p.is_file()}
    with pytest.raises((ValueError,PermissionError)): apply(**kwargs)
    assert before=={p:p.read_bytes() for p in args['directory'].rglob('*') if p.is_file()}


def test_busy_shared_lock_deletes_nothing(tmp_path):
    _,args,paths,kwargs=prepare(tmp_path)
    with root_write_lock(paths):
        with pytest.raises(RuntimeError): apply(**kwargs)
    assert len(list(args['directory'].rglob('result.json')))==4


def test_midway_io_failure_reports_exact_partial_progress(tmp_path,monkeypatch):
    _,args,paths,kwargs=prepare(tmp_path)
    original=Path.unlink; deleted=[]
    def unlink(path,*values,**options):
        if path.name in ('result.json','receipt.json'):
            assert (paths.locks/'write.lock').exists()
            if deleted: raise OSError('private OS error')
            deleted.append(path)
        return original(path,*values,**options)
    monkeypatch.setattr(Path,'unlink',unlink)
    result=apply(**kwargs)
    assert result['status']=='cleanup_incomplete' and len(result['deleted'])==1
    assert result['error_code']=='artifact_cleanup_failed'
    assert 'private OS error' not in json.dumps(result)
    assert not deleted[0].exists()
    assert len(list(args['directory'].rglob('result.json')))+len(list(args['directory'].rglob('receipt.json')))==7


def test_recreated_selected_file_is_not_reported_as_removed(tmp_path,monkeypatch):
    _,_,_,kwargs=prepare(tmp_path)
    original=Path.unlink; recreated=[]
    def unlink(path,*values,**options):
        result=original(path,*values,**options)
        if path.name=='result.json' and not recreated:
            path.write_text('synthetic concurrent replacement')
            recreated.append(path)
        return result
    monkeypatch.setattr(Path,'unlink',unlink)
    result=apply(**kwargs)
    assert recreated[0].exists()
    assert result['status']=='cleanup_incomplete'


def test_classification_cleanup_uses_same_verified_scope(tmp_path,monkeypatch):
    from test_metrics_classification_cli import setup as classification_setup
    from agc_runtime.metrics_cli import main
    from agc_runtime.metrics_host import load_host
    from agc_runtime.capture_contracts import RevisionRef,receipt_id_for
    _,_,command,execution=classification_setup(tmp_path,monkeypatch)
    assert main(command)==0
    context=load_host()
    ref=RevisionRef.from_mapping(json.loads((tmp_path/'references.json').read_text())[0])
    snapshot=cleanup_candidates(context['ledger'],receipt_id_for(ref.key))
    result=apply(ledger=context['ledger'],snapshot=snapshot,authorization='explicit_user_request',
                 commit_guard=context['commit_guard'])
    assert result['status']=='selected_artifacts_removed' and len(result['deleted'])==2
    assert not list(execution.rglob('classification.json'))
    assert list(execution.rglob('finished.json')) and list(execution.rglob('dependencies.json'))
