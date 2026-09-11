from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path

import pytest

from agc_runtime.capture_experiment import compare_runs, round_receipt, run_batch
from agc_runtime.capture_experiment import _digest


def test_integration_api_exists():
    assert importlib.util.find_spec('agc_runtime.capture_experiment_integration') is not None


@pytest.fixture
def providers(tmp_path):
    trace = pytest.importorskip('agent_trace_runtime')
    eval_runtime = pytest.importorskip('agent_eval_runtime')
    wiki = pytest.importorskip('llm_wiki_runtime.runtime')
    api = importlib.import_module('agc_runtime.capture_experiment_integration')
    return api, trace.TraceService(trace.EventStore(tmp_path / 'trace.db')), eval_runtime.EvalService(), eval_runtime.EvalStore(tmp_path / 'eval.db'), eval_runtime, wiki


@pytest.fixture
def cases():
    return [dict(case_id='fixture-1', family_id='fixture-family', split='development', synthetic=True, input='SYNTHETIC-PRIVATE-INPUT', required_claims=['secret-answer-label'])]


@pytest.fixture
def runs(cases):
    identity = dict(model='fixture', model_config='fixed', schema='v1', profile='frozen', agc_version='0.4.5', prompt='baseline')
    return tuple(run_batch(cases, split='development', identity={**identity, 'prompt': name}, extractor=lambda _: {'observations': ['SYNTHETIC-OUTPUT']}) for name in ('baseline', 'candidate'))


@pytest.fixture
def profile():
    return dict(schema_version='eval.profile.v0.1', profile_id='agc.experiment-fixture', profile_version='1', judge_mode='llm',
        dimensions=[dict(id='supported', description='Fixture transport check only', rubric='Fixture transport only, not quality', weight=1, minimum_score=3)],
        pass_threshold=0.75, evidence_requirements=[dict(provider='agc', kind='experiment-item', min_count=1)], max_attempts=1)


def judge(runtime, *, bad=False):
    class FixtureJudge:
        judge_id = 'offline-fixture'
        judge_version = '1'
        def evaluate(self, *, case, profile, evidence):
            assert 'secret-answer-label' not in str(evidence)
            ref = 'opaque:NOT-IN-CASE' if bad else case['evidence_refs'][0]['ref']
            return runtime.JudgeOutcome(dimensions=({'dimension_id': 'supported', 'score': 4, 'explanation': 'Synthetic transport check', 'evidence': [ref]},))
    return FixtureJudge()


def evaluate(providers, run, cases, profile, *, bad=False):
    api, trace, service, store, runtime, _ = providers
    return api.evaluate_batch(run, cases, profile=profile, judge=judge(runtime, bad=bad), eval_service=service, eval_store=store, trace_service=trace)


def test_actual_stores_record_evaluation_not_raw_content(providers, runs, cases, profile):
    _, trace, _, store, _, _ = providers
    batch = evaluate(providers, runs[0], cases, profile)
    result = store.get(batch['result_ids'][0])
    assert result['status'] == 'pass'
    events = trace.events(batch['trace_id'])
    assert {e.event_type for e in events} >= {'trace.root.started', 'trace.root.completed', 'agc.experiment.item.evaluated'}
    assert 'SYNTHETIC-PRIVATE-INPUT' not in str(events) + str(result)
    assert 'SYNTHETIC-OUTPUT' not in str(events) + str(result)
    assert batch['run_id'] == runs[0]['run_id']


def test_invalid_judge_citation_is_not_persisted_as_pass(providers, runs, cases, profile):
    batch = evaluate(providers, runs[0], cases, profile, bad=True)
    result = providers[3].get(batch['result_ids'][0])
    assert result['status'] == 'evaluation_error'
    assert result['overall_score'] is None
    assert providers[1].snapshot(batch['trace_id'])['status'] == 'failed'


def test_input_mismatch_rejected_before_writes(providers, runs, cases, profile):
    cases[0]['input'] += ' changed'
    with pytest.raises(ValueError):
        evaluate(providers, runs[0], cases, profile)
    assert providers[1].list_traces() == []
    assert providers[3].list_results() == []


def test_wiki_round_readback_and_idempotency(providers, runs, cases, profile, tmp_path):
    api, trace, _, store, _, wiki = providers
    batches = [evaluate(providers, run, cases, profile) for run in runs]
    assessments = [dict(run_id=run['run_id'], case_id='fixture-1', evidence_refs=[run['items'][0]['output_ref']], reviewer='fixture-human', rationale='Transport fixture',
        metrics=dict(long_term_errors=1 if i == 0 else 0, durable_omissions=0, unsupported_claims=0, classification_errors=0)) for i, run in enumerate(runs)]
    report = compare_runs(*runs, assessments)
    receipt = round_receipt(report, proposal_ref='candidate:1', lesson='Synthetic lesson, not established knowledge')
    scope = tmp_path / 'isolated-wiki'
    scope.mkdir()
    profile_path = Path(__file__).parents[1] / 'templates/agc-experiment-profile.yml'
    assert wiki.init_profile(scope, profile_path, 'local', 'agc-offline-test')['status'] == 'ok'
    kwargs = dict(evaluation_batches=batches, eval_store=store, trace_service=trace, scope_root=scope, profile_path=profile_path)
    first = api.save_round(receipt, report, **kwargs)
    second = api.save_round(receipt, report, **kwargs)
    assert first['status'] == 'ok'
    assert second['status'] == 'already_exists'
    pack = wiki.load_context_pack(scope / '.llm-wiki', ['domains/agc-improvement/rounds/**'], ['.meta/**'], 10, 40000, policy='data_only')
    assert pack['included_count'] == 1
    assert receipt['receipt_id'] in pack['items'][0]['content']
    assert all(result_id in pack['items'][0]['content'] for b in batches for result_id in b['result_ids'])
    assert pack['items'][0]['instruction_policy'] == 'data_only'
    assert 'SYNTHETIC-PRIVATE-INPUT' not in pack['items'][0]['content']
    original_batch = batches[0]
    batches[0] = {**original_batch, 'items': [], 'result_ids': []}
    batches[0]['batch_id'] = _digest({k: v for k, v in batches[0].items() if k != 'batch_id'})
    with pytest.raises(ValueError, match='coverage'):
        api.save_round(receipt, report, **kwargs)
    batches[0] = original_batch
    unsafe_profile = tmp_path / 'unsafe-profile.yml'
    unsafe_profile.write_text(profile_path.read_text(encoding='utf-8').replace('create_only', 'update_allowed'), encoding='utf-8')
    with pytest.raises(ValueError):
        api.save_round(receipt, report, **{**kwargs, 'profile_path': unsafe_profile})
    batches[0]['result_ids'] = ['evr_' + 'f' * 64]
    with pytest.raises(ValueError):
        api.save_round(receipt, report, **kwargs)
