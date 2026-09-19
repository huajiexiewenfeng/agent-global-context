import importlib
import json

import pytest

from agc_runtime.metrics_review_batch import freeze_review
from test_metrics_review_batch import setup


def fixture(tmp_path):
    batch, plan, resolver = setup(tmp_path)
    frozen = freeze_review(batch, plan, tmp_path, resolve_case=resolver)
    folder = tmp_path/'human'; folder.mkdir()
    return batch, frozen, folder


def append(batch, review, folder, **changes):
    args = dict(case_id=review['rows'][0]['case_id'], decision='accepted', correction=None,
                feedback_ref='id_'+'a'*64, timestamp='2099-01-02T00:00:00Z')
    args.update(changes)
    return importlib.import_module('agc_runtime.metrics_review').append_revision(
        batch, review, folder, **args)


def test_append_preserves_initial_judge_and_revision_chain(tmp_path):
    batch, review, folder = fixture(tmp_path)
    before = json.dumps(review, sort_keys=True)
    first = append(batch, review, folder)
    second = append(batch, review, folder, decision='disputed')
    assert first['revision'] == 1 and second['revision'] == 2
    assert second['previous_revision_id'] == first['revision_id']
    assert first['result_digests'] == review['rows'][0]['result_digests']
    assert json.dumps(review, sort_keys=True) == before
    assert len(list(folder.glob('*.json'))) == 2


def test_corrected_projection_is_separate_and_original_unchanged(tmp_path):
    batch, review, folder = fixture(tmp_path)
    correction = dict(candidate_verdicts=['unsupported'], required_matches=[], research=None)
    append(batch, review, folder, decision='corrected', correction=correction)
    api = importlib.import_module('agc_runtime.metrics_review')
    result = api.review_state(batch, review, folder)
    assert result['rows'][0]['human_review'] == 'corrected'
    assert result['rows'][0]['correction'] == correction
    assert review['rows'][0]['candidate_verdicts'] == []


@pytest.mark.parametrize('changes', [
    dict(case_id='id_'+'b'*64), dict(decision='corrected'),
    dict(correction={'private_text':'not allowed'}),
    dict(feedback_ref='raw feedback'), dict(timestamp='not a date'),
])
def test_invalid_feedback_never_written(tmp_path, changes):
    batch, review, folder = fixture(tmp_path)
    with pytest.raises(ValueError): append(batch, review, folder, **changes)
    assert not list(folder.iterdir())


def test_existing_revision_tamper_blocks_append(tmp_path):
    batch, review, folder = fixture(tmp_path)
    append(batch, review, folder)
    path = next(folder.glob('*.json'))
    value = json.loads(path.read_text()); value['decision']='disputed'
    path.write_text(json.dumps(value), encoding='utf-8')
    with pytest.raises(ValueError): append(batch, review, folder)
    assert len(list(folder.iterdir())) == 1


def test_cli_append_explicit_feedback(tmp_path, capsys):
    from agc_runtime.metrics_cli import main
    batch, review, folder = fixture(tmp_path)
    feedback = dict(case_id=review['rows'][0]['case_id'], decision='accepted', correction=None,
                    feedback_ref='id_'+'a'*64, timestamp='2099-01-02T00:00:00Z')
    for name, value in [('batch',batch),('review',review),('feedback',feedback)]:
        (tmp_path/f'{name}.json').write_text(json.dumps(value), encoding='utf-8')
    assert main(['review', '--batch',str(tmp_path/'batch.json'), '--review',str(tmp_path/'review.json'),
                 '--feedback',str(tmp_path/'feedback.json'), '--revisions-dir',str(folder)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['model_called'] is False
    assert len(list(folder.glob('*.json'))) == 1


def test_render_shows_separate_human_recalculation(tmp_path):
    from agc_runtime.metrics_report import render_report
    batch, review, folder = fixture(tmp_path)
    append(batch, review, folder, decision='corrected', correction=dict(
        candidate_verdicts=['unsupported'], required_matches=[], research=None))
    html = render_report(batch, review=review, revisions_dir=folder)
    assert '人工复核与修订' in html
    assert '人工修正后重算（不是新的 Judge 初评）' in html
    assert '1 / 1 · 100.0%' in html
    assert '原始初评保持不变' in html
    assert html.count('查看方法') == 5
