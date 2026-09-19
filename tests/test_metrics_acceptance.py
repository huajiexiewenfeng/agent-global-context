"""Synthetic user journey; feedback below is a fixture, not user approval."""
import json

from agc_runtime.metrics_cli import main
from agc_runtime.metrics_compute import compute_metrics
from test_metrics_evidence_cli import setup


def test_prepare_judge_report_feedback_and_offline_reproduction(tmp_path,monkeypatch):
    gateway,export_args,output=setup(tmp_path,monkeypatch)
    assert gateway.calls==1
    assert main(export_args)==0
    batch=tmp_path/'batch.json'
    review=next((tmp_path/'execution').glob('review-*.json'))
    frozen=review.read_bytes()
    value=json.loads(frozen)
    revisions=tmp_path/'human'; revisions.mkdir()
    feedback=dict(case_id=value['rows'][0]['case_id'],decision='corrected',
        correction=dict(candidate_verdicts=None,required_matches=None,research=dict(
            relevance='specific_useful',misleading='no',background_accuracy='supported',issues=[])),
        feedback_ref='id_'+'f'*64,timestamp='2099-01-02T00:00:00Z')
    path=tmp_path/'synthetic-feedback.json'; path.write_text(json.dumps(feedback),encoding='utf-8')
    assert main(['review','--batch',str(batch),'--review',str(review),'--feedback',str(path),
        '--revisions-dir',str(revisions)])==0
    def forbidden(*args,**kwargs): raise AssertionError('offline render must not load model/source host')
    from agc_runtime import metrics_host
    monkeypatch.setattr(metrics_host,'load_host',forbidden)
    args=['render','--batch',str(batch),'--review',str(review),'--revisions-dir',str(revisions)]
    first=tmp_path/'reviewed.html'; second=tmp_path/'reproduced.html'
    assert main([*args,'--output',str(first)])==0
    assert main([*args,'--output',str(second)])==0
    assert first.read_bytes()==second.read_bytes()
    assert review.read_bytes()==frozen and gateway.calls==1
    html=first.read_text(encoding='utf-8')
    assert html.count('查看方法')==5
    assert '人工修正后重算' in html and '原始初评保持不变' in html
    assert 'runtime research' not in html and 'Synthetic evidence has no historical background.' not in html
    assert '<script' not in html and 'https://' not in html
    metrics=compute_metrics(json.loads(batch.read_text()))
    assert set(metrics)=={'M1','M2','M3','M4','M5'}
    print('ACCEPTANCE_HTML='+str(first))
