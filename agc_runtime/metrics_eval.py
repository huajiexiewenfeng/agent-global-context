"""Deterministic metrics evaluation plans and exact identities; no model execution.

Authorization digests bind a consent scope, not proof that a human consented.
Callers must supply explicit consent and live revocation checks at execution.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from hmac import compare_digest

from agc_runtime.metrics_models import canonical, digest

STEPS = ('required_claims','align_candidates','research_relevance')
SCENARIOS = ('collected','zero','research')
CONFIG_FIELDS = {'provider','model','reasoning_effort','timeout_seconds','executable_identity','adapter_identity'}


def _hash(value):
    if not isinstance(value,str) or not re.fullmatch(r'[a-f0-9]{64}',value):
        raise ValueError('invalid_digest')
    return value


def _opaque(value):
    if not isinstance(value,str) or not re.fullmatch(r'id_[a-f0-9]{64}',value):
        raise ValueError('invalid_reference')
    return value


def judge_configuration(value):
    if not isinstance(value,dict) or set(value)!=CONFIG_FIELDS:
        raise ValueError('invalid_judge_configuration')
    if (value['provider']!='openai' or not isinstance(value['model'],str)
            or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,127}',value['model'])
            or value['reasoning_effort'] not in ('low','medium')
            or type(value['timeout_seconds']) is not int or not 1<=value['timeout_seconds']<=300):
        raise ValueError('invalid_judge_configuration')
    for key in ('executable_identity','adapter_identity'):
        _hash(value[key])
    return json.loads(canonical(value))


def _case(value):
    if not isinstance(value,dict) or set(value)!={'case_id','scenario','subject_digest','evidence_refs'}:
        raise ValueError('invalid_case')
    _opaque(value['case_id']); _hash(value['subject_digest'])
    if value['scenario'] not in SCENARIOS:
        raise ValueError('invalid_scenario')
    refs=value['evidence_refs']
    if not isinstance(refs,list) or not 1<=len(refs)<=16:
        raise ValueError('invalid_evidence_refs')
    seen=set()
    for ref in refs:
        if not isinstance(ref,dict) or set(ref)!={'ref','digest','version'}:
            raise ValueError('invalid_evidence_ref')
        _opaque(ref['ref']); _hash(ref['digest'])
        if not isinstance(ref['version'],str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,127}',ref['version']):
            raise ValueError('invalid_evidence_version')
        if ref['ref'] in seen:
            raise ValueError('duplicate_evidence_ref')
        seen.add(ref['ref'])
    return dict(value,evidence_refs=sorted(json.loads(canonical(refs)),key=canonical))


def prepare_plan(*,batch_id,cases,judge,rules):
    """Freeze a pilot plan, explicitly counting both steps of each M2 case."""
    if not isinstance(batch_id,str) or not re.fullmatch(r'agcm_[a-f0-9]{64}',batch_id):
        raise ValueError('invalid_batch_identity')
    checked_judge=judge_configuration(judge)
    if not isinstance(rules,dict) or set(rules)!=set(STEPS):
        raise ValueError('invalid_rules')
    for rule in rules.values():
        if not isinstance(rule,dict) or set(rule)!={'profile_digest','prompt_digest','schema_digest'}:
            raise ValueError('invalid_rule_identity')
        for value in rule.values():
            _hash(value)
    if not isinstance(cases,list) or len(cases)>15:
        raise ValueError('invalid_cases')
    checked_cases=sorted((_case(c) for c in cases),key=lambda c:(SCENARIOS.index(c['scenario']),c['case_id']))
    if len({c['case_id'] for c in checked_cases})!=len(checked_cases):
        raise ValueError('duplicate_case')
    if any(count>5 for count in Counter(c['scenario'] for c in checked_cases).values()):
        raise ValueError('pilot_sample_cap_exceeded')
    entries=[]
    for case in checked_cases:
        previous=None
        for step in (('research_relevance',) if case['scenario']=='research' else ('required_claims','align_candidates')):
            identity=dict(case=case,step=step,judge=checked_judge,rule=rules[step],protocol='agc.metrics-execution.v1')
            entry_id='mep_'+digest(identity)
            entries.append(dict(entry_id=entry_id,case_id=case['case_id'],scenario=case['scenario'],step=step,
                input_identity=digest(identity),depends_on=previous,status='not_run'))
            previous=entry_id
    body=dict(schema_version='agc.metrics-eval-plan.v1',batch_id=batch_id,
        judge=checked_judge,observed_judge=None,cases=checked_cases,rules=json.loads(canonical(rules)),
        entries=entries,max_calls=len(entries))
    body['plan_id']='mplan_'+digest(body)
    body['authorization_digest']=digest(dict(purpose='agc.metrics-judge-consent.v1',plan=body))
    return json.loads(canonical(body))


def validate_plan(value):
    try:
        expected=prepare_plan(batch_id=value['batch_id'],cases=value['cases'],judge=value['judge'],rules=value['rules'])
        if canonical(expected)!=canonical(value):
            raise ValueError('plan_mismatch')
        return expected
    except (KeyError,TypeError,AttributeError,ValueError) as error:
        raise ValueError('metrics_eval_plan_invalid') from error


def check_authorization(plan,authorization_digest,*,revoked_refs):
    checked=validate_plan(plan)
    _hash(authorization_digest)
    if not compare_digest(checked['authorization_digest'],authorization_digest):
        raise ValueError('metrics_eval_authorization_mismatch')
    if not isinstance(revoked_refs,(list,tuple,set)):
        raise ValueError('revocation_check_required')
    for ref in revoked_refs:
        _opaque(ref)
    if any(ref['ref'] in revoked_refs for c in checked['cases'] for ref in c['evidence_refs']):
        raise ValueError('metrics_eval_evidence_revoked')


def execution_key(plan,entry_id,*,dependency_digest=None):
    checked=validate_plan(plan)
    entries=[e for e in checked['entries'] if e['entry_id']==entry_id]
    if len(entries)!=1:
        raise ValueError('unknown_eval_entry')
    entry=entries[0]
    if entry['depends_on'] is not None:
        _hash(dependency_digest)
    elif dependency_digest is not None:
        raise ValueError('unexpected_dependency')
    return digest(dict(input_identity=entry['input_identity'],dependency_digest=dependency_digest,
                       protocol='agc.metrics-execution.v1'))


def reusable_result(record,key):
    """Identity filter only; the caller must validate result content and live refs."""
    if not isinstance(record,dict) or set(record)!={'execution_key','status','result_digest'}:
        return False
    try:
        _hash(key); _hash(record['execution_key']); _hash(record['result_digest'])
    except ValueError:
        return False
    return record['status']=='completed' and compare_digest(record['execution_key'],key)
