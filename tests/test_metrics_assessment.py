import importlib
from copy import deepcopy

import pytest

REF='id_'+'a'*64


def api():
    return importlib.import_module('agc_runtime.metrics_assessment')


def required():
    return dict(status='completed',reason=None,claims=[
        dict(claim_id='r1',text='A conditional preference',certainty='required',evidence=[REF]),
        dict(claim_id='r2',text='An ambiguous preference',certainty='uncertain',evidence=[REF])])


def alignment():
    return dict(status='completed',reason=None,candidates=[
        dict(claim_id='c1',text='A retained assertion',verdict='unsupported',evidence=[REF],reason='Input does not support assertion'),
        dict(claim_id='c2',text='An unclear assertion',verdict='uncertain',evidence=[REF],reason='Ownership is unclear')],
        matches=[dict(required_id='r1',verdict='omitted',candidate_ids=[],reason='No matching candidate'),
                 dict(required_id='r2',verdict='uncertain_match',candidate_ids=[],reason='Reference itself uncertain')])


def validate(step,value,**kwargs):
    return api().validate_assessment(step,value,allowed_refs=[REF],**kwargs)


def test_required_is_frozen_copy_and_schema_is_strict():
    original=required()
    result=validate('required_claims',original)
    original['claims'][0]['text']='changed'
    assert result['claims'][0]['text']=='A conditional preference'
    schema=api().assessment_schema('required_claims')
    assert schema['additionalProperties'] is False


def test_m2_denominators_and_uncertain_reference_exclusion():
    ref=validate('required_claims',required())
    result=validate('align_candidates',alignment(),required=ref)
    counts=api().quality_counts(ref,result)
    assert counts['retention']==dict(total=2,determinate=1,uncertain=1,errors=1,ratio=1.0)
    assert counts['required']==dict(total=2,uncertain_reference=1,determinate_matches=1,uncertain_matches=0,omitted=1,ratio=1.0)


def test_zero_candidates_not_perfect_quality():
    value=alignment(); value['candidates']=[]
    result=validate('align_candidates',value,required=required())
    counts=api().quality_counts(required(),result)
    assert counts['retention']['ratio'] is None
    assert counts['required']['ratio']==1.0


@pytest.mark.parametrize('fault',['duplicate','foreign_ref','missing_match','foreign_candidate','uncertain_as_retained','extra_field'])
def test_alignment_rejects_inconsistent_output(fault):
    value=alignment()
    if fault=='duplicate': value['candidates'].append(deepcopy(value['candidates'][0]))
    elif fault=='foreign_ref': value['candidates'][0]['evidence']=['id_'+'b'*64]
    elif fault=='missing_match': value['matches'].pop()
    elif fault=='foreign_candidate': value['matches'][0].update(verdict='retained',candidate_ids=['c99'])
    elif fault=='uncertain_as_retained': value['matches'][1].update(verdict='retained',candidate_ids=['c1'])
    else: value['score']=100
    with pytest.raises(ValueError): validate('align_candidates',value,required=required())


def test_insufficient_is_not_empty_success():
    value=dict(status='insufficient_evidence',reason='Input unavailable',claims=[])
    assert validate('required_claims',value)==value
    with pytest.raises(ValueError): validate('required_claims',dict(value,reason=None))
    with pytest.raises(ValueError): validate('align_candidates',alignment(),required=value)


def research():
    return dict(status='completed',reason=None,relevance='specific_useful',misleading='yes',
        background_accuracy='supported',issues=['unsupported_connection'],
        evidence=dict(source=[REF],research=[REF],connection=[REF]),explanation='Specific but overstated connection')


def test_research_misleading_has_display_priority():
    result=validate('research_relevance',research())
    assert api().research_label(result)=='misleading'
    assert result['relevance']=='specific_useful'


def test_specific_useful_requires_all_three_evidence_axes():
    value=research(); value['evidence']['research']=[]
    with pytest.raises(ValueError): validate('research_relevance',value)


def test_missing_background_cannot_claim_accuracy():
    value=research(); value['relevance']='partial_or_generic'; value['evidence']['research']=[]
    with pytest.raises(ValueError): validate('research_relevance',value)
    value['background_accuracy']='unknown'
    assert validate('research_relevance',value)['background_accuracy']=='unknown'


def bound_plan():
    from test_metrics_eval import config, rules
    from agc_runtime.metrics_eval import prepare_plan
    from agc_runtime.metrics_models import digest
    definitions=rules()
    for step in definitions:
        definitions[step]['schema_digest']=digest(api().assessment_schema(step))
    case=dict(case_id='id_'+'c'*64,scenario='collected',subject_digest='d'*64,
        evidence_refs=[dict(ref=REF,digest='f'*64,version='1')])
    return prepare_plan(batch_id='agcm_'+'4'*64,cases=[case],judge=config(),rules=definitions)


def test_assessment_record_binds_plan_step_and_dependency():
    from agc_runtime.metrics_eval import execution_key
    plan=bound_plan()
    first=api().freeze_assessment(plan,plan['entries'][0]['entry_id'],required())
    second=api().freeze_assessment(plan,plan['entries'][1]['entry_id'],alignment(),dependency=first)
    assert second['execution_key']==execution_key(plan,plan['entries'][1]['entry_id'],dependency_digest=first['result_digest'])
    assert second['dependency_result_digest']==first['result_digest']
    assert second['evidence_resolution']=='unchecked'
    assert second['human_review']=='unreviewed'
    assert api().validate_record(plan,second,dependency=first)==second


@pytest.mark.parametrize('fault',['tampered','wrong_step','wrong_schema','wrong_plan'])
def test_assessment_record_rejects_mismatched_binding(fault):
    from agc_runtime.metrics_eval import prepare_plan
    plan=bound_plan()
    first=api().freeze_assessment(plan,plan['entries'][0]['entry_id'],required())
    if fault=='tampered':
        first['assessment']['claims'].clear()
    elif fault=='wrong_step':
        first['entry_id']=plan['entries'][1]['entry_id']
    elif fault=='wrong_schema':
        plan['rules']['align_candidates']['schema_digest']='0'*64
        plan=prepare_plan(batch_id=plan['batch_id'],cases=plan['cases'],judge=plan['judge'],rules=plan['rules'])
    else:
        plan=prepare_plan(batch_id='agcm_'+'0'*64,cases=plan['cases'],judge=plan['judge'],rules=plan['rules'])
    with pytest.raises(ValueError):
        api().freeze_assessment(plan,plan['entries'][1]['entry_id'],alignment(),dependency=first)


def test_jsonschema_is_declared_dependency():
    from pathlib import Path
    # Avoid relying on incidental packages in the developer virtualenv.
    assert '"jsonschema>=4.23,<5"' in (Path(__file__).parents[1]/'pyproject.toml').read_text()
