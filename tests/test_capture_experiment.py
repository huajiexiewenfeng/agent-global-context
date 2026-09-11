from __future__ import annotations

import copy
import importlib
import importlib.util
import json
from pathlib import Path

import pytest


def test_offline_api_exists():
    assert importlib.util.find_spec('agc_runtime.capture_experiment') is not None


@pytest.fixture
def api():
    assert importlib.util.find_spec('agc_runtime.capture_experiment') is not None
    return importlib.import_module('agc_runtime.capture_experiment')


@pytest.fixture
def cases():
    return json.loads((Path(__file__).parent / 'fixtures/capture_experiment/development.json').read_text(encoding='utf-8'))


@pytest.fixture
def identity():
    return dict(model='fixture', model_config='fixed', schema='v1', profile='frozen-v1', agc_version='0.4.5', prompt='baseline')


def batches(api, cases, identity):
    left = api.run_batch(cases, split='development', identity=identity, extractor=lambda item: {'observations': []})
    right = api.run_batch(cases, split='development', identity={**identity, 'prompt': 'candidate'}, extractor=lambda item: {'observations': ['fixture output']})
    return left, right


def assessments(left, right, *, baseline_errors=1, omissions=0):
    result = []
    for side, run in [('baseline', left), ('candidate', right)]:
        for index, item in enumerate(run['items']):
            result.append(dict(run_id=run['run_id'], case_id=item['case_id'], evidence_refs=[item['output_ref']],
                metrics=dict(long_term_errors=baseline_errors if side == 'baseline' and index == 0 else 0,
                    durable_omissions=omissions if side == 'candidate' and index == 0 else 0,
                    unsupported_claims=0, classification_errors=0), reviewer='fixture-human', rationale='Synthetic adjudication, not a model evaluation'))
    return result


def test_suite_has_24_exposed_synthetic_cases(api, cases):
    api.validate_suite(cases)
    assert len(cases) == 24
    assert {c['split'] for c in cases} == {'development'}
    assert all(c['synthetic'] and c['access'] == 'exposed' for c in cases)


@pytest.mark.parametrize('mutation', ['duplicate', 'family', 'content', 'invalid_split'])
def test_suite_rejects_leakage_and_invalid_ids(api, cases, mutation):
    if mutation == 'duplicate':
        cases[1]['case_id'] = cases[0]['case_id']
    elif mutation == 'family':
        cases[1]['family_id'] = cases[0]['family_id']
        cases[1]['split'] = 'validation'
    elif mutation == 'content':
        cases[1]['input'] = cases[0]['input']
        cases[1]['split'] = 'validation'
    else:
        cases[0]['split'] = 'unknown'
    with pytest.raises(ValueError):
        api.validate_suite(cases)


def test_extractor_sees_no_labels_and_cannot_mutate_inputs(api, cases, identity):
    original = copy.deepcopy(cases)
    seen = []
    def extractor(item):
        seen.append(copy.deepcopy(item))
        assert set(item) == {'case_id', 'input'}
        item['input'] = 'mutated'
        return {'observations': []}
    result = api.run_batch(cases, split='development', identity=identity, extractor=extractor)
    assert cases == original
    assert len(seen) == 24
    assert all(i['status'] == 'completed' for i in result['items'])
    assert result['claim'] == 'offline-record-only'


def test_no_holdout_execution_in_development_harness(api, cases, identity):
    cases[0]['split'] = 'holdout'
    with pytest.raises(ValueError):
        api.run_batch(cases, split='holdout', identity=identity, extractor=lambda _: pytest.fail('must not execute'))


def test_failure_is_not_successful_zero_and_hides_exception(api, cases, identity):
    def unavailable(_):
        raise RuntimeError('private-text-must-not-appear')
    run = api.run_batch(cases, split='development', identity=identity, extractor=unavailable)
    assert all(i['status'] == 'execution_error' for i in run['items'])
    assert 'private-text' not in json.dumps(run)
    assert all(i['output'] is None for i in run['items'])
    report = api.compare_runs(run, run, [])
    assert report['recommendation'] == 'inconclusive'
    assert report['reason'] == 'execution_error'


def test_improved_result_only_recommends_rerun_not_release(api, cases, identity):
    left, right = batches(api, cases, identity)
    report = api.compare_runs(left, right, assessments(left, right))
    assert report['recommendation'] == 'rerun_required'
    assert report['production_authorized'] is False
    assert report['totals']['baseline']['long_term_errors'] == 1
    assert report['totals']['candidate']['long_term_errors'] == 0
    assert len(report['case_deltas']) == 24


def test_target_improvement_cannot_hide_omissions(api, cases, identity):
    left, right = batches(api, cases, identity)
    report = api.compare_runs(left, right, assessments(left, right, omissions=1))
    assert report['recommendation'] == 'reject'
    assert report['totals']['candidate']['durable_omissions'] == 1


def test_equal_quality_is_inconclusive(api, cases, identity):
    left, right = batches(api, cases, identity)
    assert api.compare_runs(left, right, assessments(left, right, baseline_errors=0))['recommendation'] == 'inconclusive'


@pytest.mark.parametrize('change', ['model', 'profile', 'input', 'output_tamper', 'run_id'])
def test_noncomparable_or_tampered_runs_are_rejected(api, cases, identity, change):
    left, right = batches(api, cases, identity)
    if change in ('model', 'profile'):
        right = api.run_batch(cases, split='development', identity={**identity, change: 'other'}, extractor=lambda _: {})
    elif change == 'input':
        cases[0]['input'] += ' changed'
        right = api.run_batch(cases, split='development', identity=identity, extractor=lambda _: {})
    elif change == 'output_tamper':
        right['items'][0]['output'] = {'changed': True}
    else:
        right['run_id'] = 'invented'
    with pytest.raises(ValueError):
        api.compare_runs(left, right, assessments(left, right))


@pytest.mark.parametrize('change', ['missing', 'extra', 'ref', 'negative', 'bool', 'no_reason'])
def test_assessment_requires_complete_bound_evidence(api, cases, identity, change):
    left, right = batches(api, cases, identity)
    rows = assessments(left, right)
    if change == 'missing':
        rows.pop()
    elif change == 'extra':
        rows.append(rows[0])
    elif change == 'ref':
        rows[0]['evidence_refs'] = ['opaque:NOT-IN-CASE']
    elif change in ('negative', 'bool'):
        rows[0]['metrics']['durable_omissions'] = -1 if change == 'negative' else True
    else:
        rows[0]['rationale'] = ''
    with pytest.raises(ValueError):
        api.compare_runs(left, right, rows)


def test_two_round_receipts_preserve_rejection_and_are_repeatable(api, cases, identity):
    left, right = batches(api, cases, identity)
    rejected = api.compare_runs(left, right, assessments(left, right, omissions=1))
    first = api.round_receipt(rejected, proposal_ref='candidate:1', lesson='Overfiltering lost a durable goal')
    improved = api.compare_runs(left, right, assessments(left, right))
    second = api.round_receipt(improved, proposal_ref='candidate:2', lesson='Narrow the change to avoid the first rejected overfilter', previous=first)
    assert second['previous_receipt_id'] == first['receipt_id']
    assert first['recommendation'] == 'reject'
    assert second == api.round_receipt(improved, proposal_ref='candidate:2', lesson=second['lesson'], previous=first)
    with pytest.raises(ValueError):
        api.round_receipt(improved, proposal_ref='candidate:2', lesson='', previous=first)


def test_round_cannot_inherit_experience_as_same_experiment_after_conditions_change(api, cases, identity):
    left, right = batches(api, cases, identity)
    first_report = api.compare_runs(left, right, assessments(left, right))
    first = api.round_receipt(first_report, proposal_ref='candidate:1', lesson='First experiment')
    cases[0]['input'] += ' changed input'
    left, right = batches(api, cases, identity)
    different = api.compare_runs(left, right, assessments(left, right))
    with pytest.raises(ValueError, match='context'):
        api.round_receipt(different, proposal_ref='candidate:2', lesson='Different experiment', previous=first)


def test_identity_must_be_frozen_before_callback(api, cases, identity):
    original = copy.deepcopy(identity)
    def extractor(_):
        identity['model'] = 'changed-by-callback'
        return {}
    result = api.run_batch(cases, split='development', identity=identity, extractor=extractor)
    assert result['identity'] == original
