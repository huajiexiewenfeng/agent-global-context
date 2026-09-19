"""Human review selection changes presentation, never metric denominators."""
import re

import pytest

from agc_runtime.metrics_eval import prepare_plan
from agc_runtime.metrics_models import canonical, digest, freeze_batch
from agc_runtime.metrics_report import render_report
from agc_runtime.metrics_review_batch import validate_review
from test_metrics_judge_input import fixture
from test_metrics_review import append


def report_fixture(specs):
    batch = freeze_batch(start='2026-09-11T00:00:00Z', end='2026-09-12T00:00:00Z',
                         cutoff='2099-01-01T00:00:00Z', data_kind='synthetic')
    original, _, _ = fixture()
    cases, rows = [], []
    for index, changes in enumerate(specs):
        scenario = changes.get('scenario', 'collected')
        case = dict(original['cases'][0], case_id='id_'+f'{index:064x}', scenario=scenario)
        cases.append(case)
        research = dict(relevance='specific_useful', misleading='no',
                        background_accuracy='supported', issues=[])
        row = dict(case_id=case['case_id'], scenario=scenario, status='usable_judgment',
                   subject_digest=case['subject_digest'], stage='research_task' if scenario=='research' else 'observation',
                   result_digests=['a'*64]*(1 if scenario=='research' else 2), human_review='unreviewed',
                   candidate_verdicts=None if scenario=='research' else ['supported'],
                   required_matches=None if scenario=='research' else [dict(certainty='required', verdict='retained')],
                   research=research if scenario=='research' else None)
        row.update(changes)
        if row['status'] != 'usable_judgment':
            row.update(stage='unknown', result_digests=[], candidate_verdicts=None, required_matches=None, research=None)
        rows.append(row)
    plan = prepare_plan(batch_id=batch['batch_id'], cases=cases, judge=original['judge'], rules=original['rules'])
    by_id = {r['case_id']:r for r in rows}
    review = dict(schema_version='agc.metrics-review.v1', batch_id=batch['batch_id'], plan=plan,
                  cutoff=batch['window']['cutoff'], rows=[by_id[c['case_id']] for c in plan['cases']], invalid_records=0)
    review['review_id'] = 'mr_'+digest(review)
    return batch, validate_review(review, batch)


def queue(html):
    match = re.search(r'<section[^>]*id="review-queue".*?</section>', html, re.S)
    assert match, 'report must contain the human review queue'
    return match.group()


def selected(html):
    return re.findall(r'data-review-case="(id_[a-f0-9]{64})"', queue(html))


def test_normal_spotchecks_are_capped_across_scenarios_without_changing_denominators():
    batch, review = report_fixture([{}, {}, {'scenario':'zero'}, {'scenario':'research'}])
    before = canonical(review)
    html = render_report(batch, review=review)
    assert selected(html) == ['id_'+f'{i:064x}' for i in (0, 1)]
    assert '正常抽查 2 / 4' in queue(html)
    assert '另有 2 项未列入抽查' in queue(html)
    assert '不是随机抽样' in queue(html)
    assert '计划案例 4' in html
    assert canonical(review) == before


@pytest.mark.parametrize('changes', [
    {'candidate_verdicts':['unsupported']},
    {'candidate_verdicts':['unsuitable_durable']},
    {'candidate_verdicts':['uncertain']},
    {'required_matches':[dict(certainty='required',verdict='omitted')]},
    {'required_matches':[dict(certainty='uncertain',verdict='retained')]},
    {'required_matches':[dict(certainty='required',verdict='uncertain_match')]},
    *[{'status':status} for status in ('not_run','in_progress','evaluation_error','insufficient_evidence','unchecked')],
    *[{'scenario':'research','research':dict(relevance='specific_useful',misleading='no',
        background_accuracy='supported',issues=[]) | change} for change in (
        {'misleading':'yes'}, {'misleading':'unknown'}, {'background_accuracy':'inaccurate'},
        {'background_accuracy':'unknown'}, {'issues':['unsupported_connection']},
        {'relevance':'partial_or_generic'}, {'relevance':'no_supported_link'}, {'relevance':'insufficient_evidence'})],
])
def test_flagged_or_unknown_case_precedes_normal_and_is_never_lost_to_cap(changes):
    batch, review = report_fixture([{}, {}, {}, changes])
    ids = selected(render_report(batch, review=review))
    assert ids == ['id_'+f'{i:064x}' for i in (3, 0, 1)]


@pytest.mark.parametrize('decision', ['disputed', 'corrected'])
def test_human_feedback_promotes_case_without_rewriting_judge(tmp_path, decision):
    batch, review = report_fixture([{}, {}, {}, {}])
    before = canonical(review)
    correction = dict(candidate_verdicts=['unsupported'],required_matches=[],research=None) if decision=='corrected' else None
    append(batch,review,tmp_path,case_id=review['rows'][3]['case_id'],decision=decision,correction=correction)
    html = render_report(batch,review=review,revisions_dir=tmp_path)
    assert selected(html)[0] == review['rows'][3]['case_id']
    assert ('有争议' if decision=='disputed' else '人工修正') in queue(html)
    assert '原始 LLM 初评' in queue(html)
    assert canonical(review) == before


def test_empty_review_has_no_invented_normal_cases():
    batch, review = report_fixture([])
    html = render_report(batch,review=review)
    assert selected(html) == []
    assert '没有计划案例' in queue(html)
