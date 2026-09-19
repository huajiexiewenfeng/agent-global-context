import importlib
from copy import deepcopy

import pytest

from agc_runtime.capture_eval_adapter import AGCCaptureEvidenceResolver
from agc_runtime.metrics_eval import prepare_plan
from agc_runtime.metrics_judge_input import build_input,rule_identities
from test_capture_eval_adapter import completed_reference_fixture
from test_metrics_eval import config


def api():
    return importlib.import_module('agc_runtime.metrics_capture_source')


def setup(tmp_path):
    paths,adapter,reference,content=completed_reference_fixture(tmp_path)
    source=api().CaptureMetricsSource(AGCCaptureEvidenceResolver(paths=paths,adapters=[adapter]))
    return source,adapter,reference,content


def test_real_capture_resolver_produces_separate_bound_documents(tmp_path):
    source,adapter,reference,content=setup(tmp_path)
    bundle=source.prepare(reference)
    assert bundle['case']['scenario']==content['decision']['outcome']
    assert bundle['subject']['stage']=='observation'
    assert {d['role'] for d in bundle['documents']}=={'safe_input','candidate'}
    assert next(d for d in bundle['documents'] if d['role']=='safe_input')['content']==content['capsule']
    assert source.resolve(bundle)==bundle
    assert source.revoked_refs(bundle)==[]


def test_prepared_capture_case_feeds_blind_input_builder(tmp_path):
    source,_,reference,_=setup(tmp_path)
    bundle=source.prepare(reference)
    plan=prepare_plan(batch_id='agcm_'+'a'*64,cases=[bundle['case']],judge=config(),rules=rule_identities())
    payload=build_input(plan,plan['entries'][0]['entry_id'],subject=bundle['subject'],
                        documents=bundle['documents'],revoked_refs=source.revoked_refs(bundle))
    assert [d['role'] for d in payload['evidence']]==['safe_input']
    assert 'decision' not in payload['evidence'][0]['content']


def test_unavailable_source_invalidates_both_derived_refs(tmp_path):
    source,adapter,reference,_=setup(tmp_path)
    bundle=source.prepare(reference)
    adapter.fail=True
    with pytest.raises(ValueError): source.resolve(bundle)
    assert set(source.revoked_refs(bundle))=={d['ref'] for d in bundle['documents']}


def test_modified_frozen_candidate_is_not_trusted(tmp_path):
    source,_,reference,_=setup(tmp_path)
    bundle=source.prepare(reference)
    bundle['documents'][1]['content']={'observations':[]}
    with pytest.raises(ValueError): source.resolve(bundle)


def test_reference_digest_and_source_type_enforced(tmp_path):
    source,_,reference,_=setup(tmp_path)
    for change in ({'digest':'sha256:'+'0'*64},{'kind':'arbitrary-file'}):
        with pytest.raises(ValueError): source.prepare(dict(reference,**change))


def test_returned_bundle_does_not_mutate_reference(tmp_path):
    source,_,reference,_=setup(tmp_path)
    original=deepcopy(reference)
    bundle=source.prepare(reference)
    bundle['source_reference']['digest']='changed'
    assert reference==original


def test_resolved_capture_runs_through_execution_boundary(tmp_path):
    from agc_runtime.metrics_execution import execute_entry
    from test_metrics_execution import Gateway
    source,adapter,reference,_=setup(tmp_path)
    bundle=source.prepare(reference)
    plan=prepare_plan(batch_id='agcm_'+'a'*64,cases=[bundle['case']],judge=config(),rules=rule_identities())
    output=tmp_path/'report'; output.mkdir()
    gateway=Gateway(plan['judge'])
    result=execute_entry(plan,plan['entries'][0]['entry_id'],directory=output,consent_digest=plan['authorization_digest'],
        subject=bundle['subject'],documents=bundle['documents'],revoked_refs=lambda:source.revoked_refs(bundle),gateway=gateway)
    assert result['status']=='completed' and gateway.calls==1
    adapter.fail=True
    fresh=tmp_path/'other-report'; fresh.mkdir()
    with pytest.raises(ValueError):
        execute_entry(plan,plan['entries'][0]['entry_id'],directory=fresh,consent_digest=plan['authorization_digest'],
            subject=bundle['subject'],documents=bundle['documents'],revoked_refs=lambda:source.revoked_refs(bundle),gateway=gateway)
    assert gateway.calls==1 and not list(fresh.iterdir())


def test_capsule_revision_change_invalidates_frozen_case(tmp_path):
    from dataclasses import replace
    source,adapter,reference,_=setup(tmp_path)
    bundle=source.prepare(reference)
    adapter.capsule_result=replace(adapter.capsule_result,capsule_hash='e'*64)
    assert len(source.revoked_refs(bundle))==2
    with pytest.raises(ValueError): source.resolve(bundle)
