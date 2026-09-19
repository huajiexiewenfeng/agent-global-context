import json
from copy import deepcopy

import pytest

from test_metrics_review_batch import setup
from agc_runtime.metrics_review_batch import freeze_review


def test_explicit_annex_retains_bound_private_evidence(tmp_path):
    from agc_runtime.metrics_review_evidence import freeze_evidence,validate_evidence
    batch,plan,resolver=setup(tmp_path)
    review=freeze_review(batch,plan,tmp_path,resolve_case=resolver)
    value=freeze_evidence(batch,review,tmp_path,resolve_case=resolver)
    assert value['cases'][0]['status']=='available'
    assert 'CANDIDATE_SECRET' in json.dumps(value)
    assert 'CANDIDATE_SECRET' not in json.dumps(review)
    assert validate_evidence(batch,review,value)==value


def test_revoked_source_preserves_case_without_body(tmp_path):
    from agc_runtime.metrics_review_evidence import freeze_evidence
    batch,plan,resolver=setup(tmp_path)
    review=freeze_review(batch,plan,tmp_path,resolve_case=resolver)
    def revoked(case): raise ValueError('private failure')
    value=freeze_evidence(batch,review,tmp_path,resolve_case=revoked)
    assert value['cases'][0]['status']=='unavailable'
    assert value['cases'][0]['documents']==[]
    assert 'private failure' not in json.dumps(value)


@pytest.mark.parametrize('change',['document','result','case','review'])
def test_rehashed_tampered_annex_rejected(tmp_path,change):
    from agc_runtime.metrics_review_evidence import freeze_evidence,validate_evidence
    from agc_runtime.metrics_models import digest
    batch,plan,resolver=setup(tmp_path)
    review=freeze_review(batch,plan,tmp_path,resolve_case=resolver)
    value=freeze_evidence(batch,review,tmp_path,resolve_case=resolver)
    if change=='document': value['cases'][0]['documents'][0]['content']='changed'
    elif change=='result': value['cases'][0]['results'][0]['assessment']['status']='changed'
    elif change=='case': value['cases'][0]['case_id']='bad'
    else: value['review_id']='bad'
    value['evidence_id']='mev_'+digest({k:v for k,v in value.items() if k!='evidence_id'})
    with pytest.raises(ValueError): validate_evidence(batch,review,value)


def test_live_revocation_during_annex_generation_omits_content(tmp_path):
    from agc_runtime.metrics_review_evidence import freeze_evidence
    batch,plan,resolver=setup(tmp_path)
    review=freeze_review(batch,plan,tmp_path,resolve_case=resolver)
    calls=[]
    def changes(case):
        calls.append(case)
        source=deepcopy(resolver(case))
        if len(calls)>=5: source['revoked_refs']=[source['documents'][0]['ref']]
        return source
    value=freeze_evidence(batch,review,tmp_path,resolve_case=changes)
    assert len(calls)>=5
    assert value['cases'][0]['status']=='unavailable'
    assert 'CANDIDATE_SECRET' not in json.dumps(value)
