import pytest
from agc_runtime.metrics_models import digest
from agc_runtime.metrics_review_batch import freeze_review,validate_review
from agc_runtime.metrics_report import render_report
from test_metrics_review_batch import setup


def test_frozen_history_shows_first_latest_and_unfinished(tmp_path):
    batch,plan,resolver=setup(tmp_path)
    review=freeze_review(batch,plan,tmp_path,resolve_case=resolver)
    assert len(review['execution_history'])==2
    step=review['execution_history'][0]
    assert step['first']==step['last_finished']
    assert step['unfinished_count']==0
    html=render_report(batch,review=review)
    assert '首次尝试' in html and '最近已结束尝试' in html


def test_history_private_fields_rejected_even_after_rehash(tmp_path):
    batch,plan,resolver=setup(tmp_path)
    review=freeze_review(batch,plan,tmp_path,resolve_case=resolver)
    review['execution_history'][0]['raw_output']='private'
    review['review_id']='mr_'+digest({k:v for k,v in review.items() if k!='review_id'})
    with pytest.raises(ValueError): validate_review(review,batch)
