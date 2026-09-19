import json

import pytest

from agc_runtime.metrics_report import render_report
from agc_runtime.metrics_cli import main
from agc_runtime.metrics_models import opaque
from agc_runtime.metrics_research_cohort import freeze_research_cohort
from test_metrics_research_cohort import batch,classifier


def cohort():
    tasks=[]
    for i,(decision,reason,status) in enumerate([
        ('include','research_connection_request','available'),
        ('exclude','not_research_connection','available'),
        ('ambiguous','intent_unclear','unknown'),
        ('include','research_connection_request','unavailable')]):
        tasks.append(dict(task_ref=opaque(str(i)),revision='a'*64,delivered_at='2026-09-02T00:00:00Z',
                          decision=decision,reason=reason,evidence_status=status))
    return freeze_research_cohort(batch(),tasks,classifier=classifier())


def test_report_preserves_selection_states_without_quality_claim():
    value=cohort()
    html=render_report(batch(),research_cohort=value)
    assert '研究任务样本覆盖' in html
    assert value['cohort_id'] in html
    assert all(token in html for token in ('not_research_connection','intent_unclear','evidence_unavailable'))
    assert '不作为 M5 质量分母' in html
    assert '不是全窗口研究任务总量' in html
    assert '内容质量与研究帮助尚未评估' in html
    assert '<script' not in html
    assert html.count('查看方法')==5


def test_tampered_cohort_rejected():
    value=cohort(); value['counts']['selected']=99
    with pytest.raises(ValueError): render_report(batch(),research_cohort=value)


def test_cli_offline_cohort_report(tmp_path,capsys):
    for name,value in [('batch',batch()),('cohort',cohort())]:
        (tmp_path/(name+'.json')).write_text(json.dumps(value),encoding='utf-8')
    output=tmp_path/'report.html'
    assert main(['render','--batch',str(tmp_path/'batch.json'),'--research-cohort',str(tmp_path/'cohort.json'),
                 '--output',str(output)])==0
    assert '研究任务样本覆盖' in output.read_text(encoding='utf-8')
    assert json.loads(capsys.readouterr().out)['model_called'] is False


def test_empty_cohort_does_not_claim_absence_of_research_tasks():
    empty=freeze_research_cohort(batch(),[],classifier=classifier())
    html=render_report(batch(),research_cohort=empty)
    assert '任务数 0' in html
    assert '不能将未入清单解释为非研究任务' in html


def test_invalid_cohort_cli_does_not_create_report(tmp_path):
    value=cohort(); value['batch_id']='wrong'
    for name,data in [('batch',batch()),('cohort',value)]:
        (tmp_path/(name+'.json')).write_text(json.dumps(data),encoding='utf-8')
    output=tmp_path/'report.html'
    assert main(['render','--batch',str(tmp_path/'batch.json'),'--research-cohort',str(tmp_path/'cohort.json'),
                 '--output',str(output)])==2
    assert not output.exists()


def test_preparation_manifest_report_needs_no_private_inputs(tmp_path,monkeypatch):
    from test_metrics_research_classification import fixture
    preparation=fixture(tmp_path,monkeypatch)
    html=render_report(batch(),research_preparation=preparation['manifest'])
    assert '研究输入准备覆盖' in html
    assert '准备就绪不等于已分类' in html
    assert 'input_budget_exceeded' in html
    assert preparation['manifest']['preparation_id'] in html
    assert 'runtime research' not in html


def test_preparation_manifest_tampering_rejected(tmp_path,monkeypatch):
    from test_metrics_research_classification import fixture
    manifest=fixture(tmp_path,monkeypatch)['manifest']
    manifest['counts']['ready']=99
    with pytest.raises(ValueError): render_report(batch(),research_preparation=manifest)


def test_cli_preparation_manifest_render(tmp_path,monkeypatch,capsys):
    from test_metrics_research_classification import fixture
    manifest=fixture(tmp_path,monkeypatch)['manifest']
    path=tmp_path/'manifest.json'; path.write_text(json.dumps(manifest),encoding='utf-8')
    output=tmp_path/'prepared-report.html'
    assert main(['render','--batch',str(tmp_path/'batch.json'),'--research-preparation',str(path),'--output',str(output)])==0
    assert json.loads(capsys.readouterr().out)['model_called'] is False
    assert '研究输入准备覆盖' in output.read_text(encoding='utf-8')


def test_metadata_validation_does_not_enable_content_free_classification(tmp_path,monkeypatch):
    from test_metrics_research_classification import fixture
    from agc_runtime.metrics_research_classification import validate_preparation_manifest,classification_request
    value=fixture(tmp_path,monkeypatch)
    assert validate_preparation_manifest(batch(),value['manifest'])==value['manifest']
    value['inputs']=[]
    with pytest.raises(ValueError): classification_request(batch(),value)
