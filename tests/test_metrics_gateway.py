import importlib
from types import SimpleNamespace

import pytest


def api():
    return importlib.import_module('agc_runtime.metrics_gateway')


class Adapter:
    instances=[]
    def __init__(self,**kwargs):
        self.kwargs=kwargs
        self.observed_configuration=None
        self.instances.append(self)
    def evaluate(self,**kwargs):
        self.payload=kwargs
        return SimpleNamespace(output={'verdict':'fixture'},usage=None)


def gateway(tmp_path,**kwargs):
    command=tmp_path/'fixture.exe'
    if not command.exists(): command.write_bytes(b'NOT EXECUTABLE: synthetic fixture')
    return api().MetricsGateway(executable=(str(command),),adapter_type=Adapter,**kwargs)


def payload():
    return dict(instruction='Synthetic rule',output_schema={'type':'object'},case={'evidence_refs':[]},profile={},evidence=[])


def test_independent_configuration_and_exact_adapter_arguments(tmp_path):
    bound=gateway(tmp_path)
    config=bound.configuration
    assert config['model']=='gpt-6-astra' and config['reasoning_effort']=='medium'
    assert len(config['executable_identity'])==64 and len(config['adapter_identity'])==64
    outcome=bound.evaluate(payload())
    instance=Adapter.instances[-1]
    assert instance.kwargs['model']=='gpt-6-astra'
    assert instance.kwargs['reasoning_effort']=='medium'
    assert instance.kwargs['instruction']=='Synthetic rule'
    assert instance.payload=={k:payload()[k] for k in ('case','profile','evidence')}
    assert outcome.output=={'verdict':'fixture'} and outcome.observed_configuration is None


def test_configuration_return_is_detached(tmp_path):
    bound=gateway(tmp_path); value=bound.configuration
    value['model']='changed'
    assert bound.configuration['model']=='gpt-6-astra'


def test_binary_change_invalidates_bound_gateway_before_call(tmp_path):
    bound=gateway(tmp_path)
    (tmp_path/'fixture.exe').write_bytes(b'new binary')
    count=len(Adapter.instances)
    with pytest.raises(ValueError): bound.evaluate(payload())
    assert len(Adapter.instances)==count
    with pytest.raises(ValueError): _=bound.configuration


def test_wrapper_script_content_is_bound(tmp_path):
    command=tmp_path/'fixture.exe'; command.write_bytes(b'fixture')
    script=tmp_path/'wrapper.py'; script.write_text('synthetic')
    bound=api().MetricsGateway(executable=(str(command),str(script)),adapter_type=Adapter)
    identity=bound.configuration['executable_identity']
    script.write_text('changed')
    changed=api().MetricsGateway(executable=(str(command),str(script)),adapter_type=Adapter)
    assert changed.configuration['executable_identity']!=identity


def test_relative_executable_not_resolved_from_path():
    with pytest.raises(ValueError): api().MetricsGateway(executable=('codex',),adapter_type=Adapter)


def test_configuration_effort_and_timeout_remain_independent(tmp_path):
    bound=gateway(tmp_path,model='gpt-6-astra',reasoning_effort='low',timeout_seconds=90)
    assert bound.configuration['reasoning_effort']=='low'
    assert bound.configuration['timeout_seconds']==90


def test_real_adapter_through_execution_with_simulated_process(tmp_path,monkeypatch):
    import json
    import subprocess
    from pathlib import Path
    pytest.importorskip('agent_eval_codex')
    from test_metrics_judge_input import fixture
    from agc_runtime.metrics_eval import prepare_plan
    from agc_runtime.metrics_execution import execute_entry
    executable=tmp_path/'fixture.exe'; executable.write_bytes(b'never executed')
    bound=api().MetricsGateway(executable=(str(executable),))
    old,subject,docs=fixture()
    plan=prepare_plan(batch_id=old['batch_id'],cases=old['cases'],judge=bound.configuration,rules=old['rules'])
    calls=[]
    def process(argv,**kwargs):
        calls.append(argv)
        assert argv[argv.index('--config')+1]=='model_reasoning_effort="medium"'
        schema=json.loads(Path(argv[argv.index('--output-schema')+1]).read_text())
        assert schema['properties']['claims']['type']=='array'
        sent=json.loads(kwargs['input'])
        assert len(sent['resolved_evidence'])==1
        assert 'CANDIDATE_SECRET' not in kwargs['input'].decode()
        events=[dict(type='thread.started',thread_id='fixture'),dict(type='item.completed',item=dict(type='agent_message',
            text=json.dumps(dict(status='completed',reason=None,claims=[])))),dict(type='turn.completed')]
        return subprocess.CompletedProcess(argv,0,stdout='\n'.join(json.dumps(e) for e in events).encode(),stderr=b'')
    monkeypatch.setattr(subprocess,'run',process)
    monkeypatch.setenv('TEMP',str(tmp_path))
    errors=[]
    evaluate=bound.evaluate
    def observed(payload):
        try: return evaluate(payload)
        except Exception as error:
            errors.append((type(error).__name__,str(error)))
            raise
    monkeypatch.setattr(bound,'evaluate',observed)
    report=tmp_path/'report'; report.mkdir()
    result=execute_entry(plan,plan['entries'][0]['entry_id'],directory=report,consent_digest=plan['authorization_digest'],
        subject=subject,documents=docs,revoked_refs=lambda:[],gateway=bound)
    assert result['status']=='completed',errors
    assert len(calls)==1
    receipt=json.loads(next(report.rglob('receipt.json')).read_text())
    assert receipt['requested_configuration']==plan['judge']
    assert receipt['observed_configuration'] is None
