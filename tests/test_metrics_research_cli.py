import json
from types import SimpleNamespace

from agc_runtime.metrics_cli import main
from agc_runtime.metrics_research_cohort import freeze_research_cohort
from test_metrics_research_cohort import batch,classifier
from test_metrics_research_source import setup
from test_metrics_eval import config
from test_metrics_execution import Gateway


def prepare(tmp_path,monkeypatch):
    from agc_runtime import metrics_host
    source,ref,_,_=setup(tmp_path)
    metadata=source.describe_task(ref)
    cohort=freeze_research_cohort(batch(),[dict(metadata,decision='include',reason='research_connection_request')],
                                   classifier=classifier())
    base=tmp_path/'host'; base.mkdir(); (base/'send-ledger').mkdir()
    value=dict(schema_version='agc.metrics-host.v1',memory_root=str(tmp_path/'memory'),
               source_roots=[str(tmp_path/'codex')],executable=['unused'],
               model='gpt-6-astra',reasoning_effort='medium',timeout_seconds=120)
    (base/'host.json').write_text(json.dumps(value),encoding='utf-8')
    monkeypatch.setattr(metrics_host,'_host_root',lambda:base)
    def judge(payload):
        assert {d['role'] for d in payload['evidence']}=={'task_input','task_output'}
        return SimpleNamespace(output=dict(status='completed',reason=None,relevance='partial_or_generic',
            misleading='unknown',background_accuracy='unknown',issues=[],
            evidence=dict(source=[],research=[],connection=[]),explanation='Synthetic evidence has no historical background.'),
            usage=None,observed_configuration=None)
    gateway=Gateway(config(),judge)
    monkeypatch.setattr(metrics_host,'_gateway',lambda c:gateway)
    for name,content in [('batch',batch()),('cohort',cohort),('references',[ref.to_mapping()])]:
        (tmp_path/(name+'.json')).write_text(json.dumps(content),encoding='utf-8')
    common=[]
    for name in ('batch','cohort','references'):
        common+=['--'+name,str(tmp_path/(name+'.json'))]
    return common,gateway


def test_research_cli_native_source_plan_execute_reuse_report(tmp_path,monkeypatch,capsys):
    common,gateway=prepare(tmp_path,monkeypatch)
    output=tmp_path/'plan'
    assert main(['prepare-research-plan',*common,'--output',str(output)])==0
    assert gateway.calls==0
    plan=json.loads((output/'plan.json').read_text(encoding='utf-8'))
    assert plan['max_calls']==1
    execution=tmp_path/'execution'; execution.mkdir()
    args=['evaluate-research',*common,'--plan',str(output/'plan.json'),
          '--source-map',str(output/'source-map.json'),'--output',str(execution),
          '--consent',plan['authorization_digest']]
    assert main(args)==0
    assert gateway.calls==1
    assert list(execution.glob('report-*.html'))
    assert main(args)==0
    assert gateway.calls==1
    responses=[json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert responses[1]['model_called'] is True
    assert responses[2]['model_called'] is False
    args[-1]='0'*64
    assert main(args)==2
    assert gateway.calls==1


def test_research_reference_outside_host_roots_fails_without_model(tmp_path,monkeypatch):
    common,gateway=prepare(tmp_path,monkeypatch)
    path=tmp_path/'references.json'
    refs=json.loads(path.read_text(encoding='utf-8'))
    refs[0]['capture_key']['source_root_id']='f'*64
    path.write_text(json.dumps(refs),encoding='utf-8')
    output=tmp_path/'plan'
    assert main(['prepare-research-plan',*common,'--output',str(output)])==2
    assert not output.exists()
    assert gateway.calls==0


def test_cohort_delivery_time_must_match_native_completion(tmp_path,monkeypatch):
    common,gateway=prepare(tmp_path,monkeypatch)
    path=tmp_path/'cohort.json'
    cohort=json.loads(path.read_text(encoding='utf-8'))
    task={k:v for k,v in cohort['tasks'][0].items() if k!='selection_status'}
    task['delivered_at']='2026-09-02T00:00:00Z'
    altered=freeze_research_cohort(batch(),[task],classifier=classifier())
    path.write_text(json.dumps(altered),encoding='utf-8')
    output=tmp_path/'plan'
    assert main(['prepare-research-plan',*common,'--output',str(output)])==2
    assert not output.exists()
    assert gateway.calls==0
