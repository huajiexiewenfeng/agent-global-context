import json

import pytest

from agc_runtime.metrics_cli import main
from agc_runtime.metrics_report import render_report
from agc_runtime.metrics_review_batch import freeze_review
from test_metrics_review_batch import setup


def test_review_report_uses_frozen_quality_and_plan(tmp_path):
    batch, plan, resolver = setup(tmp_path)
    review = freeze_review(batch, plan, tmp_path, resolve_case=resolver)
    html = render_report(batch, review=review)
    assert html.count('查看方法') == 5
    assert '计划案例 1 · 计划步骤 2' in html
    assert 'collected 分层' in html and 'zero 分层' in html
    assert '分母为零，不可计算' in html
    assert 'LLM 初评，未经人类复核' in html
    assert '内容质量与研究帮助尚未评估' not in html
    assert review['review_id'] in html
    assert 'CANDIDATE_SECRET' not in html
    assert '<script' not in html and 'https://' not in html


def test_review_render_rejects_tampering(tmp_path):
    batch, plan, resolver = setup(tmp_path)
    review = freeze_review(batch, plan, tmp_path, resolve_case=resolver)
    review['rows'][0]['status'] = 'not_run'
    with pytest.raises(ValueError):
        render_report(batch, review=review)


def test_cli_review_render_is_offline_and_exclusive(tmp_path, capsys):
    batch, plan, resolver = setup(tmp_path)
    review = freeze_review(batch, plan, tmp_path, resolve_case=resolver)
    for name, value in [('batch.json', batch), ('review.json', review)]:
        (tmp_path/name).write_text(json.dumps(value), encoding='utf-8')
    output = tmp_path/'report.html'
    args = ['render', '--batch', str(tmp_path/'batch.json'), '--review',
            str(tmp_path/'review.json'), '--output', str(output)]
    assert main(args) == 0
    assert json.loads(capsys.readouterr().out)['model_called'] is False
    before = output.read_bytes()
    assert main(args) == 2
    assert output.read_bytes() == before


def test_cli_rejects_duplicate_review_json_before_output(tmp_path):
    batch, plan, resolver = setup(tmp_path)
    review = freeze_review(batch, plan, tmp_path, resolve_case=resolver)
    (tmp_path/'batch.json').write_text(json.dumps(batch), encoding='utf-8')
    raw = json.dumps(review)
    (tmp_path/'review.json').write_text('{"rows":[],'+raw[1:], encoding='utf-8')
    output = tmp_path/'report.html'
    assert main(['render', '--batch', str(tmp_path/'batch.json'), '--review',
                 str(tmp_path/'review.json'), '--output', str(output)]) == 2
    assert not output.exists()
