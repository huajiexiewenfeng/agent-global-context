import json

import pytest

from agc_runtime.metrics_cli import main
from agc_runtime.metrics_report import render_report
from agc_runtime.metrics_review_batch import freeze_review
from agc_runtime.metrics_review_evidence import freeze_evidence
from test_metrics_review_batch import setup


def fixture(tmp_path):
    batch,plan,resolver=setup(tmp_path)
    review=freeze_review(batch,plan,tmp_path,resolve_case=resolver)
    evidence=freeze_evidence(batch,review,tmp_path,resolve_case=resolver)
    return batch,review,evidence


def test_private_evidence_only_when_explicitly_supplied(tmp_path):
    batch,review,evidence=fixture(tmp_path)
    assert 'CANDIDATE_SECRET' not in render_report(batch,review=review)
    html=render_report(batch,review=review,evidence=evidence)
    assert 'CANDIDATE_SECRET' not in html
    assert '私有证据明细' in html
    assert '原始 LLM 初评' in html
    assert evidence['evidence_id'] in html
    assert '不会自动更新撤销状态' in html
    assert html.count('查看方法')==5


def test_evidence_requires_matching_review(tmp_path):
    batch,review,evidence=fixture(tmp_path)
    with pytest.raises(ValueError): render_report(batch,evidence=evidence)
    evidence['review_id']='wrong'
    with pytest.raises(ValueError): render_report(batch,review=review,evidence=evidence)


def test_cli_private_evidence_render(tmp_path,capsys):
    batch,review,evidence=fixture(tmp_path)
    for name,value in [('batch',batch),('review',review),('evidence',evidence)]:
        (tmp_path/(name+'.json')).write_text(json.dumps(value),encoding='utf-8')
    output=tmp_path/'private.html'
    assert main(['render','--batch',str(tmp_path/'batch.json'),'--review',str(tmp_path/'review.json'),
                 '--evidence',str(tmp_path/'evidence.json'),'--output',str(output)])==0
    assert json.loads(capsys.readouterr().out)['model_called'] is False
    assert 'CANDIDATE_SECRET' not in output.read_text(encoding='utf-8')


def test_renderer_escapes_source_and_model_text(tmp_path,monkeypatch):
    from agc_runtime import metrics_review_evidence
    batch,review,evidence=fixture(tmp_path)
    attack='<img src=x onerror=alert(1)><script>alert(2)</script>'
    evidence['cases'][0]['documents'][0]['content']=attack
    evidence['cases'][0]['results'][0]['assessment']['reason']=attack
    # Isolate output escaping; separate tests cover real digest validation.
    monkeypatch.setattr(metrics_review_evidence,'validate_evidence',lambda *args:evidence)
    html=render_report(batch,review=review,evidence=evidence)
    assert '<script' not in html and '<img' not in html
    assert 'alert(1)' not in html and 'alert(2)' not in html


def test_unavailable_evidence_renders_without_old_body(tmp_path):
    batch,plan,resolver=setup(tmp_path)
    review=freeze_review(batch,plan,tmp_path,resolve_case=resolver)
    def missing(case): raise ValueError('unavailable')
    evidence=freeze_evidence(batch,review,tmp_path,resolve_case=missing)
    html=render_report(batch,review=review,evidence=evidence)
    assert '证据不可用' in html
    assert 'CANDIDATE_SECRET' not in html
