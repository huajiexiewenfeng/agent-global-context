"""Synthetic commit/forget serialization: no model or production root access."""
from contextlib import contextmanager

import pytest

from agc_runtime.locking import root_write_lock
from agc_runtime.paths import MemoryPaths


@pytest.mark.parametrize('kind',['quality','classification'])
@pytest.mark.parametrize('mode',['success','busy','revoked'])
def test_result_commit_is_guarded_but_model_call_is_not(tmp_path,monkeypatch,kind,mode):
    paths=MemoryPaths.from_root(tmp_path/'memory-lock')
    lock_file=paths.locks/'write.lock'
    entered=[]; writes=[]; revoked=[False]; held=[]
    if kind=='quality':
        from test_metrics_runner import run
        from agc_runtime import metrics_execution as writer
        runner,plan,args,model=run(tmp_path)
        source_key='resolve_case'
        execute=lambda:runner.run_plan(plan,**args)
        success=lambda value:all(row['status']=='executed' for row in value['entries'])
        failure=lambda value:value['entries'][0]['status']=='evaluation_error'
    else:
        from test_metrics_classification_execution import setup
        from test_metrics_research_cohort import batch
        from agc_runtime import metrics_classification_execution as writer
        _,plan,model,args=setup(tmp_path,monkeypatch)
        source_key='resolve_preparation'
        execute=lambda:writer.execute_classification(batch(),plan,**args)
        success=lambda value:value['status']=='completed'
        failure=lambda value:value['status']=='classification_error'
    original_source=args[source_key]
    def source(*values):
        if revoked[0]: raise ValueError('synthetic revoked source')
        if lock_file.exists(): entered.append('source')
        return original_source(*values)
    args[source_key]=source

    @contextmanager
    def guard():
        with root_write_lock(paths):
            if mode=='revoked': revoked[0]=True
            yield
    args['commit_guard']=guard
    original_call=model.evaluate
    def evaluate(payload):
        assert not lock_file.exists(), 'model must not hold the commit lock'
        result=original_call(payload)
        if mode=='busy':
            other=root_write_lock(paths); other.__enter__(); held.append(other)
        return result
    model.evaluate=evaluate
    original_write=writer._write
    def write(path,value):
        if path.name in ('result.json','classification.json','receipt.json'):
            assert lock_file.exists(), 'content commit must hold the shared root lock'
            writes.append(path.name)
        original_write(path,value)
    monkeypatch.setattr(writer,'_write',write)
    try:
        result=execute()
    finally:
        for other in held: other.__exit__(None,None,None)
    assert not lock_file.exists()
    if mode=='success':
        assert success(result) and entered and writes
    else:
        assert failure(result) and model.calls==1
        assert not writes
        assert not list(args['directory'].rglob('result.json'))
        assert not list(args['directory'].rglob('classification.json'))


def test_host_exposes_existing_memory_root_lock(tmp_path,monkeypatch):
    from test_metrics_host import host
    api,_,model=host(tmp_path,monkeypatch)
    context=api.load_host()
    paths=MemoryPaths.from_root(tmp_path/'memory')
    with context['commit_guard']():
        with pytest.raises(RuntimeError,match='write lock'):
            with root_write_lock(paths): pass
    assert not (paths.locks/'write.lock').exists()
    assert model.calls==0


@pytest.mark.parametrize('when',['after_model','during_final_source'])
def test_changed_registration_after_call_does_not_persist_result(tmp_path,when):
    from test_metrics_runner import run
    runner,plan,args,model=run(tmp_path)
    paths=MemoryPaths.from_root(tmp_path/'memory-lock')
    args['commit_guard']=lambda:root_write_lock(paths)
    original=model.evaluate
    def corrupt():
        record=next((args['ledger_directory']/'artifact-registry').glob('*.json'))
        record.write_text('{}',encoding='utf-8')
    def evaluate(payload):
        value=original(payload)
        if when=='after_model': corrupt()
        return value
    model.evaluate=evaluate
    source=args['resolve_case']
    def resolve(case):
        value=source(case)
        if when=='during_final_source' and (paths.locks/'write.lock').exists(): corrupt()
        return value
    args['resolve_case']=resolve
    result=runner.run_plan(plan,**args)
    assert result['entries'][0]['status']=='evaluation_error'
    assert model.calls==1 and not list(args['directory'].rglob('result.json'))
