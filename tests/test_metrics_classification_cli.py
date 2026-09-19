import json
from types import SimpleNamespace

from agc_runtime.metrics_cli import main
from test_metrics_research_cli import prepare


def setup(tmp_path,monkeypatch):
    _,gateway=prepare(tmp_path,monkeypatch)
    def classify(payload):
        assert all(d['role']=='task_input' for d in payload['evidence'])
        labels=[dict(ref,decision='include',reason='research_connection_request') for ref in payload['case']['references']]
        return SimpleNamespace(output={'labels':labels},usage=None,observed_configuration=None)
    gateway.handler=classify
    common=['--batch',str(tmp_path/'batch.json'),'--references',str(tmp_path/'references.json')]
    planned=tmp_path/'classification-plan'
    assert main(['prepare-classification-plan',*common,'--output',str(planned)])==0
    plan=json.loads((planned/'plan.json').read_text(encoding='utf-8'))
    execution=tmp_path/'classification-run'; execution.mkdir()
    args=['classify-research',*common,'--plan',str(planned/'plan.json'),
          '--output',str(execution),'--consent',plan['authorization_digest']]
    return gateway,plan,args,execution


def test_native_input_cli_classification_without_manual_labels(tmp_path,monkeypatch,capsys):
    gateway,plan,args,execution=setup(tmp_path,monkeypatch)
    assert gateway.calls==0
    assert main(args)==0
    response=json.loads(capsys.readouterr().out.splitlines()[-1])
    assert response['model_called'] is True
    assert response['classification_status']=='completed'
    result=json.loads(next(execution.rglob('classification.json')).read_text(encoding='utf-8'))
    assert result['cohort']['counts']['selected']==1
    assert 'runtime research' not in json.dumps(result)
    assert main(args)==2
    assert gateway.calls==1
    assert json.loads(capsys.readouterr().out)['model_called'] is False


def test_wrong_consent_does_not_resolve_content(tmp_path,monkeypatch):
    from agc_runtime.metrics_research_source import CodexResearchSource
    gateway,plan,args,_=setup(tmp_path,monkeypatch)
    def forbidden(*args): raise AssertionError('must not read')
    monkeypatch.setattr(CodexResearchSource,'classification_input',forbidden)
    args[-1]='0'*64
    assert main(args)==2
    assert gateway.calls==0


def test_source_change_after_prepare_does_not_send(tmp_path,monkeypatch):
    gateway,plan,args,_=setup(tmp_path,monkeypatch)
    (tmp_path/'codex'/'sessions'/'research.jsonl').unlink()
    assert main(args)==2
    assert gateway.calls==0


def test_output_inside_host_is_rejected(tmp_path,monkeypatch):
    _,gateway=prepare(tmp_path,monkeypatch)
    assert main(['prepare-classification-plan','--batch',str(tmp_path/'batch.json'),
                 '--references',str(tmp_path/'references.json'),'--output',str(tmp_path/'host'/'new')])==2
    assert gateway.calls==0
    assert not (tmp_path/'host'/'new').exists()


def test_model_failure_reports_actual_call_and_failure_status(tmp_path,monkeypatch,capsys):
    gateway,_,args,execution=setup(tmp_path,monkeypatch)
    def fail(payload): raise RuntimeError('private model error')
    gateway.handler=fail
    assert main(args)==0
    response=json.loads(capsys.readouterr().out.splitlines()[-1])
    assert response['classification_status']=='classification_error'
    assert response['model_called'] is True and response['model_call_attempts']==1
    assert not list(execution.rglob('classification.json'))
    assert 'private model error' not in json.dumps(response)


def test_export_verified_cohort_feeds_research_plan_without_model_call(tmp_path,monkeypatch,capsys):
    gateway,_,args,execution=setup(tmp_path,monkeypatch)
    assert main(args)==0
    exported=tmp_path/'exported'
    command=['export-classification','--batch',str(tmp_path/'batch.json'),
             '--references',str(tmp_path/'references.json'),
             '--plan',str(tmp_path/'classification-plan'/'plan.json'),
             '--execution-dir',str(execution),'--output',str(exported)]
    assert main(command)==0
    response=json.loads(capsys.readouterr().out.splitlines()[-1])
    assert response['model_called'] is False and gateway.calls==1
    assert (exported/'research-cohort.json').exists()
    assert (exported/'classification-verification.json').exists()
    planned=tmp_path/'research-eval-plan'
    assert main(['prepare-research-plan','--batch',str(tmp_path/'batch.json'),
                 '--references',str(tmp_path/'references.json'),
                 '--cohort',str(exported/'research-cohort.json'),'--output',str(planned)])==0
    assert gateway.calls==1
    assert json.loads((planned/'plan.json').read_text(encoding='utf-8'))['max_calls']==1
    assert main(command)==2  # No overwrite.
    from agc_runtime.metrics_host import load_host
    from agc_runtime.metrics_report_artifacts import cleanup_reports
    context=load_host()
    records=[json.loads(p.read_text()) for p in (context['ledger']/'report-registry').glob('*.json')]
    assert len(records)==1 and records[0]['kind']=='classification_export'
    binding=json.loads(next((context['ledger']/'source-bindings').glob('*.json')).read_text())
    with context['commit_guard'](): cleanup_reports(context['ledger'],binding['entries'][0]['receipt_id'])
    assert not list(exported.iterdir()) and gateway.calls==1


def test_export_invalid_result_does_not_create_output(tmp_path,monkeypatch):
    gateway,_,args,execution=setup(tmp_path,monkeypatch)
    assert main(args)==0
    next(execution.rglob('finished.json')).unlink()
    exported=tmp_path/'invalid-export'
    assert main(['export-classification','--batch',str(tmp_path/'batch.json'),
                 '--references',str(tmp_path/'references.json'),
                 '--plan',str(tmp_path/'classification-plan'/'plan.json'),
                 '--execution-dir',str(execution),'--output',str(exported)])==2
    assert not exported.exists()
    assert gateway.calls==1
