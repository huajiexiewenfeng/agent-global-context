import json
from pathlib import Path

import pytest

from agc_runtime import capture_forget_service as service
from agc_runtime.metrics_models import digest
from test_capture_forget import _populated, _request, _key


def setup(tmp_path,monkeypatch):
    from agc_runtime import metrics_host
    from agc_runtime.metrics_source_bindings import register_source_bindings
    from test_metrics_runner import run
    paths,store,receipt,observations=_populated(tmp_path)
    base=tmp_path/'metrics-host'; base.mkdir(); ledger=base/'send-ledger'; ledger.mkdir()
    sources=tmp_path/'sessions'; sources.mkdir()
    config=dict(schema_version='agc.metrics-host.v1',memory_root=str(paths.root),
                source_roots=[str(sources)],executable=['never-call'],model='gpt-6-astra',
                reasoning_effort='medium',timeout_seconds=120)
    (base/'host.json').write_text(json.dumps(config))
    monkeypatch.setattr(metrics_host,'_host_root',lambda:base)
    work=tmp_path/'metrics-work'; work.mkdir()
    runner,plan,args,model=run(work); args['ledger_directory']=ledger
    binding=dict(schema_version='agc.metrics-source-bindings.v1',plan_id=plan['plan_id'],
                 input_binding_digest='a'*64,entries=[dict(subject_ref=plan['cases'][0]['case_id'],
                 receipt_id=receipt.receipt_id,native_reference_digest=None)])
    binding['binding_id']='msb_'+digest(binding)
    register_source_bindings(ledger,binding)
    assert all(r['status']=='executed' for r in runner.run_plan(plan,**args)['entries'])
    return paths,store,receipt,observations,args,model


@pytest.mark.parametrize('kind',['observation','revision'])
def test_forget_commits_source_invalidation_then_cleans_bound_results(tmp_path,monkeypatch,kind):
    paths,store,receipt,observations,args,model=setup(tmp_path,monkeypatch)
    target=({'type':'observation','observation_id':observations[0].observation_id}
            if kind=='observation' else {'type':'revision',**_key().to_mapping()})
    response=service.capture_forget(paths,_request(target))
    assert response.status=='accepted'
    assert not list(args['directory'].rglob('result.json'))
    assert not list(args['directory'].rglob('receipt.json'))
    assert list(args['directory'].rglob('finished.json'))
    assert not list((paths.capture.root/'metrics-cleanup').glob('*.json'))
    assert model.calls==2
    snapshot=store.read_snapshot()
    assert snapshot.integrity_state=='healthy'
    if kind=='observation': assert snapshot.receipts[0].redacted_by_forget
    else: assert snapshot.tombstones


@pytest.mark.parametrize('fault',['interrupted','partial'])
def test_postcommit_cleanup_failure_is_durable_and_resumed(tmp_path,monkeypatch,fault):
    paths,store,receipt,observations,args,model=setup(tmp_path,monkeypatch)
    from agc_runtime import metrics_cleanup_apply
    original=metrics_cleanup_apply.apply_cleanup
    def fail(**kwargs):
        assert json.loads((paths.capture.receipts/(receipt.receipt_id+'.json')).read_text())['redacted_by_forget']
        if fault=='interrupted': raise KeyboardInterrupt()
        return {'status':'cleanup_incomplete'}
    monkeypatch.setattr(metrics_cleanup_apply,'apply_cleanup',fail)
    request=_request({'type':'observation','observation_id':observations[0].observation_id})
    if fault=='interrupted':
        with pytest.raises(KeyboardInterrupt): service.capture_forget(paths,request)
    else:
        response=service.capture_forget(paths,request)
        assert response.status=='deferred' and response.data['source_forget_committed'] is True
    intents=list((paths.capture.root/'metrics-cleanup').glob('*.json'))
    assert len(intents)==1 and receipt.receipt_id in intents[0].read_text()
    assert observations[0].statement not in intents[0].read_text()
    monkeypatch.setattr(metrics_cleanup_apply,'apply_cleanup',original)
    response=service.capture_forget(paths,request)
    assert response.status=='accepted'
    assert not list(args['directory'].rglob('result.json'))
    assert not list((paths.capture.root/'metrics-cleanup').glob('*.json'))
    assert model.calls==2


def test_before_commit_failure_does_not_delete_external_results(tmp_path,monkeypatch):
    paths,store,_,observations,args,_=setup(tmp_path,monkeypatch)
    original=service.CaptureForgetTransaction
    class Failing(original):
        def commit(self): raise OSError('synthetic disk failure')
    monkeypatch.setattr(service,'CaptureForgetTransaction',Failing)
    response=service.capture_forget(paths,_request({'type':'observation','observation_id':observations[0].observation_id}))
    assert response.status=='failed'
    assert len(list(args['directory'].rglob('result.json')))==2
    assert not list((paths.capture.root/'metrics-cleanup').glob('*.json'))
    assert not store.read_snapshot().receipts[0].redacted_by_forget


def test_unfinished_attempt_is_not_reported_as_fully_forgotten(tmp_path,monkeypatch):
    paths,store,_,observations,args,_=setup(tmp_path,monkeypatch)
    unfinished=next(args['directory'].rglob('finished.json')); unfinished.unlink()
    (unfinished.parent/'.attempt.lock').unlink()  # Legacy/unknown owner, not proven inactive.
    request=_request({'type':'observation','observation_id':observations[0].observation_id})
    response=service.capture_forget(paths,request)
    assert response.status=='deferred' and response.data['source_forget_committed'] is True
    assert list((paths.capture.root/'metrics-cleanup').glob('*.json'))
    assert len(list(args['directory'].rglob('result.json')))==2


def test_missing_host_configuration_cannot_skip_existing_metrics(tmp_path,monkeypatch):
    paths,store,_,observations,args,_=setup(tmp_path,monkeypatch)
    (tmp_path/'metrics-host'/'host.json').unlink()
    response=service.capture_forget(paths,_request({'type':'observation','observation_id':observations[0].observation_id}))
    assert response.status=='failed' and response.error['code']=='metrics_cleanup_binding_unavailable'
    assert not store.read_snapshot().receipts[0].redacted_by_forget
    assert len(list(args['directory'].rglob('result.json')))==2


def test_changed_ledger_identity_blocks_recovery(tmp_path,monkeypatch):
    paths,store,_,observations,args,_=setup(tmp_path,monkeypatch)
    from agc_runtime import metrics_cleanup_apply
    original=metrics_cleanup_apply.apply_cleanup
    monkeypatch.setattr(metrics_cleanup_apply,'apply_cleanup',lambda **kw:{'status':'cleanup_incomplete'})
    request=_request({'type':'observation','observation_id':observations[0].observation_id})
    assert service.capture_forget(paths,request).status=='deferred'
    ledger=args['ledger_directory']; ledger.rename(ledger.with_name('original-ledger')); ledger.mkdir()
    monkeypatch.setattr(metrics_cleanup_apply,'apply_cleanup',original)
    response=service.capture_forget(paths,request)
    assert response.status=='deferred' and response.data['current_request_applied'] is False
    assert len(list(args['directory'].rglob('result.json')))==2
    assert list((paths.capture.root/'metrics-cleanup').glob('*.json'))


def test_interrupted_source_transaction_recovers_before_external_cleanup(tmp_path,monkeypatch):
    paths,_,_,observations,args,_=setup(tmp_path,monkeypatch)
    original=service.CaptureForgetTransaction
    class Interrupted(original):
        def write(self,path,data,*,boundary):
            super().write(path,data,boundary=boundary)
            if boundary=='metrics-cleanup-intent': raise KeyboardInterrupt()
    monkeypatch.setattr(service,'CaptureForgetTransaction',Interrupted)
    request=_request({'type':'observation','observation_id':observations[0].observation_id})
    with pytest.raises(KeyboardInterrupt): service.capture_forget(paths,request)
    assert list(paths.capture.journals.glob('capture-forget-*.json'))
    assert len(list(args['directory'].rglob('result.json')))==2
    monkeypatch.setattr(service,'CaptureForgetTransaction',original)
    assert service.capture_forget(paths,request).status=='accepted'
    assert not list(args['directory'].rglob('result.json'))
    assert not list(paths.capture.journals.glob('capture-forget-*.json'))


def test_actual_partial_unlink_recovers_without_restoring_source(tmp_path,monkeypatch):
    paths,store,_,observations,args,_=setup(tmp_path,monkeypatch)
    original=Path.unlink; deleted=[]
    def unlink(path,*values,**options):
        if path.name in ('result.json','receipt.json'):
            if deleted: raise OSError('synthetic failure')
            deleted.append(path)
        return original(path,*values,**options)
    monkeypatch.setattr(Path,'unlink',unlink)
    request=_request({'type':'observation','observation_id':observations[0].observation_id})
    response=service.capture_forget(paths,request)
    assert response.status=='deferred' and len(deleted)==1 and not deleted[0].exists()
    assert store.read_snapshot().receipts[0].redacted_by_forget
    monkeypatch.setattr(Path,'unlink',original)
    assert service.capture_forget(paths,request).status=='accepted'
    assert not list(args['directory'].rglob('result.json'))
    assert not list(args['directory'].rglob('receipt.json'))
