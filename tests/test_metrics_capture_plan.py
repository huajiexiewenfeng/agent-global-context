import importlib
import json
from copy import deepcopy

import pytest

from test_metrics_judge_input import fixture
from agc_runtime.metrics_models import freeze_batch


class Source:
    def __init__(self):
        self.calls=0
        plan,self.subject,self.docs=fixture()
        self.case=plan['cases'][0]
    def prepare(self, reference):
        self.calls+=1
        return deepcopy(dict(case=self.case,subject=self.subject,documents=self.docs,source_reference=reference))


def prepare():
    api=importlib.import_module('agc_runtime.metrics_capture_plan')
    source=Source()
    batch=freeze_batch(start='2026-09-11T00:00:00Z',end='2026-09-12T00:00:00Z',cutoff='2026-09-12T00:00:00Z')
    reference=dict(schema_version='eval.evidence-ref.v0.1',provider='agc',kind='capture-item',
                   version='1',ref='cr_'+'a'*64,digest='sha256:'+'b'*64)
    result=api.prepare_capture_plan(batch,[reference],source=source,judge=fixture()[0]['judge'])
    return api,source,result


def test_capture_plan_persists_only_reference_map_not_private_input():
    api,source,result=prepare()
    assert result['plan']['max_calls']==2
    serialized=json.dumps(result)
    assert 'CANDIDATE_SECRET' not in serialized
    assert 'A synthetic preference' not in serialized
    resolve=api.capture_plan_resolver(result['plan'],result['source_map'],source=source)
    before=source.calls
    resolve(source.case['case_id']); resolve(source.case['case_id'])
    assert source.calls==before+2


def test_wrong_source_map_rejected_before_resolution():
    api,source,result=prepare()
    result['source_map']['entries'][0]['case_id']='id_'+'f'*64
    with pytest.raises(ValueError):
        api.capture_plan_resolver(result['plan'],result['source_map'],source=source)


def test_changed_case_identity_blocks_resolution():
    api,source,result=prepare()
    resolve=api.capture_plan_resolver(result['plan'],result['source_map'],source=source)
    source.case['subject_digest']='f'*64
    with pytest.raises(ValueError): resolve(source.case['case_id'])
