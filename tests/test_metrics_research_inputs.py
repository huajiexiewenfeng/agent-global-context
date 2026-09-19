import importlib
import json
from copy import deepcopy

from agc_runtime.metrics_cli import main
from test_metrics_research_cli import prepare
from test_metrics_research_cohort import batch


def test_cli_returns_bound_input_for_classification_not_judge_output(tmp_path,monkeypatch,capsys):
    common,gateway=prepare(tmp_path,monkeypatch)
    assert main(['research-inputs','--batch',str(tmp_path/'batch.json'),
                 '--references',str(tmp_path/'references.json')])==0
    result=json.loads(capsys.readouterr().out)['research_preparation']
    assert result['manifest']['entries'][0]['status']=='ready'
    assert 'runtime research' in json.dumps(result['inputs'])
    assert 'trace comparison' not in json.dumps(result)
    assert 'runtime research' not in json.dumps(result['manifest'])
    assert gateway.calls==0


def test_outside_window_and_duplicate_task_do_not_read_content(tmp_path,monkeypatch):
    from agc_runtime.metrics_host import load_host
    prepare(tmp_path,monkeypatch)
    refs=json.loads((tmp_path/'references.json').read_text(encoding='utf-8'))
    outside=deepcopy(refs[0]); outside['completed_at']='2026-10-01T00:00:00Z'
    module=importlib.import_module('agc_runtime.metrics_research_inputs')
    def forbidden(refs): raise AssertionError('must not resolve outside/ambiguous tasks')
    result=module.prepare_research_inputs(batch(),[outside],source_factory=forbidden)
    assert result['manifest']['entries'][0]['status']=='outside_window'
    result=module.prepare_research_inputs(batch(),refs+refs,source_factory=forbidden)
    assert {e['status'] for e in result['manifest']['entries']}=={'ambiguous_revision'}
    assert result['inputs']==[]


def test_unavailable_source_remains_visible_without_content(tmp_path,monkeypatch):
    from agc_runtime.metrics_host import load_host
    prepare(tmp_path,monkeypatch)
    refs=json.loads((tmp_path/'references.json').read_text(encoding='utf-8'))
    (tmp_path/'codex'/'sessions'/'research.jsonl').unlink()
    module=importlib.import_module('agc_runtime.metrics_research_inputs')
    result=module.prepare_research_inputs(batch(),refs,source_factory=load_host()['research_source_factory'])
    assert result['manifest']['entries'][0]['status']=='evidence_unavailable'
    assert result['inputs']==[]


def test_preparation_is_deterministic_and_does_not_persist_private_content(tmp_path,monkeypatch):
    from agc_runtime.metrics_host import load_host
    prepare(tmp_path,monkeypatch)
    refs=json.loads((tmp_path/'references.json').read_text(encoding='utf-8'))
    module=importlib.import_module('agc_runtime.metrics_research_inputs')
    factory=load_host()['research_source_factory']
    before={p.relative_to(tmp_path):p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    first=module.prepare_research_inputs(batch(),refs,source_factory=factory)
    second=module.prepare_research_inputs(batch(),list(reversed(refs)),source_factory=factory)
    assert first==second
    after={p.relative_to(tmp_path):p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    assert before==after


def test_total_input_budget_preserves_every_manifest_entry(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from agc_runtime.capture_contracts import RevisionRef
    from agc_runtime.metrics_research_source import _task_ref
    from agc_runtime.metrics_models import canonical,opaque
    prepare(tmp_path,monkeypatch)
    native=json.loads((tmp_path/'references.json').read_text(encoding='utf-8'))[0]
    refs=[]
    for index in range(10):
        ref=deepcopy(native); ref['capture_key']['task_id']='large-task-'+str(index)
        refs.append(ref)
    def factory(values):
        def read(value):
            ref=RevisionRef.from_mapping(value); task_ref=_task_ref(ref)
            return dict(task_ref=task_ref,revision='a'*64,delivered_at=ref.completed_at,
                        document=dict(ref=opaque(task_ref),version='a'*64,role='task_input',content='q'*250000))
        return SimpleNamespace(classification_input=read)
    module=importlib.import_module('agc_runtime.metrics_research_inputs')
    result=module.prepare_research_inputs(batch(),refs,source_factory=factory)
    assert len(result['manifest']['entries'])==10
    assert result['manifest']['counts']['input_budget_exceeded']>0
    assert result['manifest']['counts']['ready']==len(result['inputs'])
    assert len(canonical(result['inputs']).encode('utf-8'))<=2*1024*1024
