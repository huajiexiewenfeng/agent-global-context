import importlib
import json

import pytest

from agc_runtime.codex_source_adapter import CodexSourceAdapter
from agc_runtime.capture_source import TimeWindow
from agc_runtime.capture_capsule import CapsulePolicy


def setup(tmp_path):
    root=tmp_path/'codex'; (root/'sessions').mkdir(parents=True)
    path=root/'sessions'/'research.jsonl'
    records=[
        dict(type='session_meta',payload=dict(id='rollout-research',session_id='task-research',source='vscode')),
        dict(type='event_msg',payload=dict(type='task_started',turn_id='turn-research')),
        dict(type='response_item',payload=dict(type='message',role='user',content='How does this paper help my runtime research?')),
        dict(type='response_item',payload=dict(type='reasoning',content='HIDDEN_REASONING')),
        dict(type='response_item',payload=dict(type='function_call_output',output='PRIVATE_TOOL_OUTPUT')),
        dict(type='response_item',payload=dict(type='message',role='assistant',phase='analysis',content='PRIVATE_ANALYSIS')),
        dict(type='response_item',payload=dict(type='message',role='assistant',phase='final',content='The paper gives a useful trace comparison method.')),
        dict(type='event_msg',payload=dict(type='task_complete',turn_id='turn-research')),
    ]
    for i,row in enumerate(records): row['timestamp']=f'2026-09-04T12:00:{i:02d}Z'
    def write(): path.write_text(''.join(json.dumps(r)+'\n' for r in records),encoding='utf-8')
    write()
    adapter=CodexSourceAdapter(root)
    refs=adapter.discover(None,TimeWindow.from_mapping(dict(schema_version=1,
        start_at='2026-09-01T00:00:00Z',end_at='2026-09-08T00:00:00Z'))).revisions
    api=importlib.import_module('agc_runtime.metrics_research_source')
    from agc_runtime.metrics_research_access import CaptureResearchAccess
    from agc_runtime.capture_store import CaptureStore
    from test_capture_eval_adapter import _write_config
    paths=_write_config(tmp_path/'memory'); CaptureStore(paths).ensure_layout()
    source=api.CodexResearchSource(adapter,refs,policy=CapsulePolicy(),access=CaptureResearchAccess(paths))
    return source,refs[0],records,write


def test_native_completed_turn_produces_only_input_and_final(tmp_path):
    source,ref,_,_=setup(tmp_path)
    metadata=source.describe_task(ref)
    result=source.prepare({k:metadata[k] for k in ('task_ref','revision')})
    assert {d['role'] for d in result['documents']}=={'task_input','task_output'}
    serialized=json.dumps(result)
    assert 'trace comparison' in serialized
    assert 'HIDDEN_REASONING' not in serialized
    assert 'PRIVATE_' not in serialized
    assert 'research_background' not in serialized


def test_changed_historical_output_invalidates_bound_revision(tmp_path):
    source,ref,records,write=setup(tmp_path)
    metadata=source.describe_task(ref)
    records[6]['payload']['content']='Changed final answer'; write()
    with pytest.raises(ValueError): source.prepare({k:metadata[k] for k in ('task_ref','revision')})


@pytest.mark.parametrize('fault',['no-final','secret','oversized'])
def test_unusable_task_content_is_not_silently_evaluated(tmp_path,fault):
    source,ref,records,write=setup(tmp_path)
    if fault=='no-final': records[6]['payload']['phase']='commentary'
    if fault=='secret': records[6]['payload']['content']='password=private-password-value'
    if fault=='oversized': records[6]['payload']['content']='z'*300000
    write()
    with pytest.raises(ValueError): source.describe_task(ref)


def test_reference_outside_explicit_binding_is_rejected(tmp_path):
    source,_,_,_=setup(tmp_path)
    with pytest.raises(ValueError): source.prepare(dict(task_ref='id_'+'f'*64,revision='a'*64))


def test_live_exclusion_denies_before_reading_content(tmp_path,monkeypatch):
    import yaml
    from agc_runtime.runtime_config import _Yaml12SafeLoader
    source,ref,_,_=setup(tmp_path)
    metadata=source.describe_task(ref)
    path=tmp_path/'memory'/'config.yaml'
    config=yaml.load(path.read_text(encoding='utf-8'),Loader=_Yaml12SafeLoader)
    config['capture']['exclude']['task_ids']=[ref.key.task_id]
    path.write_text(yaml.safe_dump(config),encoding='utf-8')
    def forbidden(*args): raise AssertionError('excluded source must not be read')
    monkeypatch.setattr(source._adapter,'_iter_target_turn_records',forbidden)
    with pytest.raises(ValueError): source.prepare({k:metadata[k] for k in ('task_ref','revision')})


def test_exclusion_added_during_read_prevents_return(tmp_path,monkeypatch):
    import yaml
    from agc_runtime.runtime_config import _Yaml12SafeLoader
    source,ref,_,_=setup(tmp_path)
    original=source._adapter._iter_target_turn_records
    def change_during_read(reference):
        yield from original(reference)
        path=tmp_path/'memory'/'config.yaml'
        config=yaml.load(path.read_text(encoding='utf-8'),Loader=_Yaml12SafeLoader)
        config['capture']['exclude']['task_ids']=[reference.key.task_id]
        path.write_text(yaml.safe_dump(config),encoding='utf-8')
    monkeypatch.setattr(source._adapter,'_iter_target_turn_records',change_during_read)
    with pytest.raises(ValueError): source.describe_task(ref)


def test_native_source_connects_to_frozen_research_plan(tmp_path):
    from agc_runtime.metrics_research_cohort import freeze_research_cohort
    from agc_runtime.metrics_research_plan import prepare_research_plan,research_plan_resolver
    from test_metrics_research_cohort import batch,classifier
    from test_metrics_eval import config
    source,ref,_,_=setup(tmp_path)
    metadata=source.describe_task(ref)
    cohort=freeze_research_cohort(batch(),[dict(metadata,decision='include',reason='research_connection_request')],
                                   classifier=classifier())
    prepared=prepare_research_plan(batch(),cohort,source=source,judge=config())
    resolve=research_plan_resolver(batch(),cohort,prepared['plan'],prepared['source_map'],source=source)
    evidence=resolve(prepared['plan']['cases'][0]['case_id'])
    assert len(evidence['documents'])==2
    assert 'trace comparison' not in json.dumps(prepared)


@pytest.mark.parametrize('fault',['future-final','subagent-final','analysis-channel','duplicate-final',
                                 'foreign-turn','conflicting-phase','unsupported-input'])
def test_ambiguous_or_wrong_provenance_final_is_unavailable(tmp_path,fault):
    source,ref,records,write=setup(tmp_path)
    if fault=='future-final': records[6]['timestamp']='2026-09-09T12:00:00Z'
    if fault=='subagent-final': records[6]['payload']['source']={'subagent':'worker'}
    if fault=='analysis-channel': records[6]['payload']['channel']='analysis'
    if fault=='foreign-turn': records[6]['payload']['turn_id']='different-turn'
    if fault=='conflicting-phase': records[6]['payload'].update(phase='analysis',is_final=True)
    if fault=='unsupported-input':
        records.insert(3,dict(timestamp='2026-09-04T12:00:02Z',type='response_item',
                             payload=dict(type='message',role='user',content=[
                                 dict(type='input_text',text='Critical additional context'),
                                 dict(type='input_image',image_url='synthetic-image')])) )
    if fault=='duplicate-final':
        records.insert(6,dict(timestamp='2026-09-04T12:00:05Z',type='response_item',
                             payload=dict(type='message',role='assistant',phase='final',content='Conflicting final answer.')))
    write()
    with pytest.raises(ValueError): source.describe_task(ref)
