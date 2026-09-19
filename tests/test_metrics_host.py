import importlib
import json
from types import SimpleNamespace

from test_metrics_capture_plan import Source
from test_metrics_judge_input import fixture
from test_metrics_execution import Gateway
from agc_runtime.metrics_models import freeze_batch
import pytest


def host(tmp_path, monkeypatch):
    api=importlib.import_module('agc_runtime.metrics_host')
    base=tmp_path/'host'; base.mkdir(); (base/'send-ledger').mkdir()
    memory=tmp_path/'memory'; memory.mkdir()
    (memory/'.runtime'/'capture').mkdir(parents=True)
    sessions=tmp_path/'sessions'; sessions.mkdir()
    config=dict(schema_version='agc.metrics-host.v1',memory_root=str(memory),source_roots=[str(sessions)],
        executable=['unused'],model='gpt-6-astra',reasoning_effort='medium',timeout_seconds=120)
    (base/'host.json').write_text(json.dumps(config),encoding='utf-8')
    monkeypatch.setattr(api,'_host_root',lambda:base)
    monkeypatch.setattr(api,'_source',lambda c:Source())
    def result(payload):
        data=dict(status='completed',reason=None)
        data.update(dict(candidates=[],matches=[]) if 'required_claims' in payload['case'] else dict(claims=[]))
        return SimpleNamespace(output=data,usage=None,observed_configuration=None)
    gateway=Gateway(fixture()[0]['judge'],result)
    monkeypatch.setattr(api,'_gateway',lambda c:gateway)
    return api,base,gateway


def test_fixed_host_ledger_not_report_relative(tmp_path,monkeypatch):
    api,base,gateway=host(tmp_path,monkeypatch)
    context=api.load_host()
    assert context['ledger']==base/'send-ledger'
    assert gateway.calls==0


def test_cli_capture_plan_evaluate_freeze_and_render(tmp_path,monkeypatch,capsys):
    api,base,gateway=host(tmp_path,monkeypatch)
    from agc_runtime.metrics_cli import main
    batch=freeze_batch(start='2026-01-01T00:00:00Z',end='2026-01-02T00:00:00Z',cutoff='2026-01-02T00:00:00Z',data_kind='synthetic')
    refs=[dict(schema_version='eval.evidence-ref.v0.1',provider='agc',kind='capture-item',
        version='1',ref='cr_'+'a'*64,digest='sha256:'+'b'*64)]
    (tmp_path/'batch.json').write_text(json.dumps(batch),encoding='utf-8')
    (tmp_path/'refs.json').write_text(json.dumps(refs),encoding='utf-8')
    output=tmp_path/'plan'
    assert main(['prepare-capture-plan','--batch',str(tmp_path/'batch.json'),'--references',str(tmp_path/'refs.json'),'--output',str(output)])==0
    assert gateway.calls==0
    plan=json.loads((output/'plan.json').read_text())
    execution=tmp_path/'execution'; execution.mkdir()
    args=['evaluate','--batch',str(tmp_path/'batch.json'),'--plan',str(output/'plan.json'),
          '--source-map',str(output/'source-map.json'),'--consent',plan['authorization_digest'],'--output',str(execution)]
    assert main(args)==0
    assert gateway.calls==2
    assert list(execution.glob('report-*.html'))
    assert main(args)==0
    assert gateway.calls==2
    assert len(list(execution.glob('report-*.html')))==2
    responses=[json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert responses[1]['model_call_attempts']==2 and responses[1]['model_called'] is True
    assert responses[2]['model_call_attempts']==0 and responses[2]['model_called'] is False
    args[args.index('--consent')+1]='0'*64
    assert main(args)==2
    assert gateway.calls==2
    assert json.loads(capsys.readouterr().out)['model_called'] is False


def test_missing_ledger_fails_without_recreating(tmp_path,monkeypatch):
    api,base,gateway=host(tmp_path,monkeypatch)
    (base/'send-ledger').rmdir()
    with pytest.raises(ValueError): api.load_host()
    assert not (base/'send-ledger').exists()
    assert gateway.calls==0


def test_output_cannot_be_within_host_or_memory(tmp_path,monkeypatch):
    api,base,_=host(tmp_path,monkeypatch)
    context=api.load_host()
    for root in context['protected_roots']:
        with pytest.raises(ValueError): api.output_directory(root/'report',context,existing=False)


def test_unknown_host_field_cannot_override_ledger(tmp_path,monkeypatch):
    api,base,_=host(tmp_path,monkeypatch)
    path=base/'host.json'
    config=json.loads(path.read_text()); config['ledger_directory']=str(tmp_path)
    path.write_text(json.dumps(config),encoding='utf-8')
    with pytest.raises(ValueError): api.load_host()


def test_executing_host_keeps_binding_when_host_directory_disappears(tmp_path,monkeypatch):
    from agc_runtime.paths import MemoryPaths
    api,base,model=host(tmp_path,monkeypatch)
    context=api.load_host()
    context['gateway'].evaluate({'case':{}})
    paths=MemoryPaths.from_root(tmp_path/'memory')
    assert (paths.capture.root/'metrics-host.json').exists()
    base.rename(base.with_name('missing-original-host'))
    with pytest.raises(ValueError): api.cleanup_ledger(paths)
    assert model.calls==1
