import importlib
from types import SimpleNamespace

from test_metrics_execution import Gateway
from test_metrics_judge_input import fixture


def run(tmp_path, *, handler=None):
    plan, subject, docs = fixture()
    output=tmp_path/'run'; output.mkdir()
    ledger=tmp_path/'ledger'; ledger.mkdir()
    def default(payload):
        data = dict(status='completed', reason=None)
        if 'required_claims' in payload['case']: data.update(candidates=[],matches=[])
        else: data.update(claims=[])
        return SimpleNamespace(output=data, usage=None, observed_configuration=None)
    gateway=Gateway(plan['judge'], handler or default)
    args=dict(directory=output, ledger_directory=ledger, consent_digest=plan['authorization_digest'],
              gateway=gateway, resolve_case=lambda c:dict(subject=subject,documents=docs,revoked_refs=[]))
    api=importlib.import_module('agc_runtime.metrics_runner')
    return api,plan,args,gateway


def test_runner_executes_two_steps_then_reuses_verified_results(tmp_path):
    api,plan,args,gateway=run(tmp_path)
    first=api.run_plan(plan,**args)
    assert [r['status'] for r in first['entries']]==['executed','executed']
    assert gateway.calls==2
    second=api.run_plan(plan,**args)
    assert [r['status'] for r in second['entries']]==['reused','reused']
    assert gateway.calls==2


def test_shared_ledger_prevents_new_directory_replaying_plan(tmp_path):
    api,plan,args,gateway=run(tmp_path)
    api.run_plan(plan,**args)
    other=tmp_path/'other'; other.mkdir(); args['directory']=other
    result=api.run_plan(plan,**args)
    assert gateway.calls==2
    assert result['entries'][0]['status']=='evaluation_error'
    assert result['entries'][1]['status']=='dependency_unavailable'


def test_error_counts_as_consumed_and_is_not_retried(tmp_path):
    def failure(payload): raise RuntimeError('PRIVATE ERROR')
    api,plan,args,gateway=run(tmp_path,handler=failure)
    result=api.run_plan(plan,**args)
    assert gateway.calls==1
    assert result['entries'][1]['status']=='dependency_unavailable'
    api.run_plan(plan,**args)
    assert gateway.calls==1


def test_revoked_input_never_calls_gateway(tmp_path):
    api,plan,args,gateway=run(tmp_path)
    resolve=args['resolve_case']
    def revoked(case):
        value=resolve(case); value['revoked_refs']=[value['documents'][0]['ref']]; return value
    args['resolve_case']=revoked
    result=api.run_plan(plan,**args)
    assert gateway.calls==0
    assert result['entries'][0]['status']=='evidence_unavailable'


def test_concurrent_output_directories_share_send_reservations(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    api,plan,args,gateway=run(tmp_path)
    other=tmp_path/'other'; other.mkdir()
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(api.run_plan,plan,**args),
                 pool.submit(api.run_plan,plan,**dict(args,directory=other))]
        results=[f.result() for f in futures]
    assert gateway.calls==2
    assert sum(r['status']=='executed' for result in results for r in result['entries'])==2


def test_changed_source_blocks_cached_results_without_new_calls(tmp_path):
    api,plan,args,gateway=run(tmp_path)
    api.run_plan(plan,**args)
    resolve=args['resolve_case']
    def changed(case):
        import copy
        value=copy.deepcopy(resolve(case))
        value['documents'][0]['content']='changed source'
        return value
    result=api.run_plan(plan,**dict(args,resolve_case=changed))
    assert result['entries'][0]['status']=='evidence_unavailable'
    assert gateway.calls==2
