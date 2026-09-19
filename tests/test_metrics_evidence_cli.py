import json

from agc_runtime.metrics_cli import main
from test_metrics_research_cli import prepare


def setup(tmp_path,monkeypatch):
    common,gateway=prepare(tmp_path,monkeypatch)
    planned=tmp_path/'plan'
    assert main(['prepare-research-plan',*common,'--output',str(planned)])==0
    plan=json.loads((planned/'plan.json').read_text(encoding='utf-8'))
    execution=tmp_path/'execution'; execution.mkdir()
    assert main(['evaluate-research',*common,'--plan',str(planned/'plan.json'),
                 '--source-map',str(planned/'source-map.json'),'--output',str(execution),
                 '--consent',plan['authorization_digest']])==0
    review=next(execution.glob('review-*.json'))
    output=tmp_path/'private-evidence'
    args=['export-review-evidence',*common,'--review',str(review),
          '--source-map',str(planned/'source-map.json'),'--execution-dir',str(execution),'--output',str(output)]
    return gateway,args,output


def test_explicit_evidence_export_reuses_results_without_model(tmp_path,monkeypatch,capsys):
    gateway,args,output=setup(tmp_path,monkeypatch)
    calls=gateway.calls
    assert main(args)==0
    response=json.loads(capsys.readouterr().out.splitlines()[-1])
    assert response['model_called'] is False and gateway.calls==calls
    evidence=json.loads((output/'evidence-index.json').read_text(encoding='utf-8'))
    assert evidence['cases'][0]['status']=='available'
    assert 'runtime research' not in (output/'report.html').read_text(encoding='utf-8')
    assert response['privacy']=='controlled_references_only'
    assert not (output/'evidence.json').exists()
    for path in output.iterdir():
        text=path.read_text(encoding='utf-8')
        assert 'runtime research' not in text
        assert 'Synthetic evidence has no historical background.' not in text
    assert main(args)==2
    assert gateway.calls==calls


def test_missing_source_cannot_publish_new_managed_report(tmp_path,monkeypatch):
    gateway,args,output=setup(tmp_path,monkeypatch)
    (tmp_path/'codex'/'sessions'/'research.jsonl').unlink()
    assert main(args)==2
    assert not output.exists()
    assert gateway.calls==1


def test_quality_and_evidence_exports_are_registered_for_source_cleanup(tmp_path,monkeypatch):
    from agc_runtime.metrics_host import load_host
    from agc_runtime.metrics_report_artifacts import cleanup_reports
    gateway,args,output=setup(tmp_path,monkeypatch)
    assert main(args)==0
    context=load_host()
    records=[json.loads(p.read_text()) for p in (context['ledger']/'report-registry').glob('*.json')]
    assert {r['kind'] for r in records}=={'quality_report','evidence_export'}
    binding=json.loads(next((context['ledger']/'source-bindings').glob('*.json')).read_text())
    with context['commit_guard'](): cleanup_reports(context['ledger'],binding['entries'][0]['receipt_id'])
    assert not list((tmp_path/'execution').glob('report-*.html'))
    assert not list((tmp_path/'execution').glob('review-*.json'))
    assert not list(output.iterdir()) and gateway.calls==1


def test_busy_publication_returns_controlled_error_without_output(tmp_path,monkeypatch,capsys):
    from agc_runtime.metrics_host import load_host
    gateway,args,output=setup(tmp_path,monkeypatch)
    with load_host()['commit_guard'](): assert main(args)==2
    response=json.loads(capsys.readouterr().out.splitlines()[-1])
    assert response['code']=='metrics_operation_failed' and response['model_called'] is False
    assert not output.exists() and gateway.calls==1


def test_evidence_export_rejects_protected_output(tmp_path,monkeypatch):
    gateway,args,_=setup(tmp_path,monkeypatch)
    args[-1]=str(tmp_path/'host'/'private')
    assert main(args)==2
    assert not (tmp_path/'host'/'private').exists()
    assert gateway.calls==1


def test_capture_evidence_export_uses_capture_resolver(tmp_path,monkeypatch):
    from test_metrics_host import host
    from agc_runtime.metrics_models import freeze_batch
    _,_,gateway=host(tmp_path,monkeypatch)
    batch=freeze_batch(start='2026-01-01T00:00:00Z',end='2026-01-02T00:00:00Z',cutoff='2026-01-02T00:00:00Z',data_kind='synthetic')
    refs=[dict(schema_version='eval.evidence-ref.v0.1',provider='agc',kind='capture-item',
               version='1',ref='cr_'+'a'*64,digest='sha256:'+'b'*64)]
    for name,value in [('batch',batch),('refs',refs)]:
        (tmp_path/(name+'.json')).write_text(json.dumps(value),encoding='utf-8')
    planned=tmp_path/'plan'; execution=tmp_path/'execution'; execution.mkdir()
    assert main(['prepare-capture-plan','--batch',str(tmp_path/'batch.json'),'--references',str(tmp_path/'refs.json'),
                 '--output',str(planned)])==0
    plan=json.loads((planned/'plan.json').read_text(encoding='utf-8'))
    assert main(['evaluate','--batch',str(tmp_path/'batch.json'),'--plan',str(planned/'plan.json'),
                 '--source-map',str(planned/'source-map.json'),'--consent',plan['authorization_digest'],
                 '--output',str(execution)])==0
    output=tmp_path/'private'
    assert main(['export-review-evidence','--batch',str(tmp_path/'batch.json'),
                 '--review',str(next(execution.glob('review-*.json'))),'--source-map',str(planned/'source-map.json'),
                 '--execution-dir',str(execution),'--output',str(output)])==0
    assert gateway.calls==2
    assert json.loads((output/'evidence-index.json').read_text(encoding='utf-8'))['cases'][0]['status']=='available'


def test_empty_research_plan_can_export_without_model(tmp_path,monkeypatch):
    from agc_runtime.metrics_research_cohort import freeze_research_cohort
    from test_metrics_research_cohort import batch,classifier
    common,gateway=prepare(tmp_path,monkeypatch)
    (tmp_path/'cohort.json').write_text(json.dumps(freeze_research_cohort(batch(),[],classifier=classifier())),encoding='utf-8')
    (tmp_path/'references.json').write_text('[]',encoding='utf-8')
    planned=tmp_path/'plan'; execution=tmp_path/'execution'; execution.mkdir()
    assert main(['prepare-research-plan',*common,'--output',str(planned)])==0
    plan=json.loads((planned/'plan.json').read_text(encoding='utf-8'))
    assert main(['evaluate-research',*common,'--plan',str(planned/'plan.json'),
                 '--source-map',str(planned/'source-map.json'),'--output',str(execution),
                 '--consent',plan['authorization_digest']])==0
    output=tmp_path/'empty-export'
    assert main(['export-review-evidence',*common,'--review',str(next(execution.glob('review-*.json'))),
                 '--source-map',str(planned/'source-map.json'),'--execution-dir',str(execution),
                 '--output',str(output)])==0
    assert gateway.calls==0
    assert json.loads((output/'evidence-index.json').read_text(encoding='utf-8'))['cases']==[]


def test_export_cannot_bypass_corrupt_host_registration(tmp_path,monkeypatch):
    gateway,args,output=setup(tmp_path,monkeypatch)
    for path in (tmp_path/'host'/'send-ledger'/'artifact-registry').glob('*.json'):
        path.write_text('{}',encoding='utf-8')
    assert main(args)==0
    item=json.loads((output/'evidence-index.json').read_text(encoding='utf-8'))['cases'][0]
    assert item['status']=='unavailable'
    assert item['result_refs']==[] and item['document_refs']==[]
    assert gateway.calls==1


def test_rerun_cannot_refreeze_unregistered_result_as_usable(tmp_path,monkeypatch):
    gateway,export_args,_=setup(tmp_path,monkeypatch)
    for path in (tmp_path/'host'/'send-ledger'/'artifact-registry').glob('*.json'):
        path.write_text('{}',encoding='utf-8')
    plan=json.loads((tmp_path/'plan'/'plan.json').read_text(encoding='utf-8'))
    execution=tmp_path/'execution'
    before=set(execution.glob('review-*.json'))
    args=['evaluate-research','--plan',str(tmp_path/'plan'/'plan.json'),
          '--source-map',str(tmp_path/'plan'/'source-map.json'),'--output',str(execution),
          '--consent',plan['authorization_digest']]
    for flag in ('--batch','--references','--cohort'):
        args.extend([flag,export_args[export_args.index(flag)+1]])
    assert main(args)==0
    after=set(execution.glob('review-*.json'))-before
    assert len(after)==1
    review=json.loads(after.pop().read_text(encoding='utf-8'))
    assert review['rows'][0]['status']=='evaluation_error'
    assert review['rows'][0]['research'] is None
    assert gateway.calls==1
