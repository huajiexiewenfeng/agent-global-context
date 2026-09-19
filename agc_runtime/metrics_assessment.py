"""AGC domain output contracts; structure and arithmetic are not semantic truth.

The caller must resolve and authorize evidence before validating its citations.
Claim text/reasons are private derived content, never Trace metadata or public data.
"""
from __future__ import annotations

import json

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from agc_runtime.metrics_models import canonical, digest
from agc_runtime.metrics_eval import execution_key, validate_plan


def _object(**properties):
    return dict(type='object',properties=properties,required=list(properties),additionalProperties=False)


def _enum(*values):
    return dict(type='string',enum=list(values))


def _array(items,minimum=0):
    return dict(type='array',items=items,minItems=minimum,maxItems=128)


def assessment_schema(step):
    text=dict(type='string',minLength=1,maxLength=1000)
    identity=dict(type='string',pattern=r'^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$')
    refs=_array(dict(type='string',pattern=r'^id_[a-f0-9]{64}$'))
    refs['uniqueItems']=True
    ids=_array(identity); ids['uniqueItems']=True
    common=dict(status=_enum('completed','insufficient_evidence'),reason=dict(anyOf=[text,dict(type='null')]))
    if step=='required_claims':
        return _object(**common,claims=_array(_object(claim_id=identity,text=text,
            certainty=_enum('required','uncertain'),evidence=refs)))
    if step=='align_candidates':
        return _object(**common,candidates=_array(_object(claim_id=identity,text=text,
            verdict=_enum('supported','unsupported','unsuitable_durable','uncertain'),evidence=refs,reason=text)),
            matches=_array(_object(required_id=identity,verdict=_enum('retained','omitted','uncertain_match'),
                candidate_ids=ids,reason=text)))
    if step=='research_relevance':
        issues=_array(_enum('inaccurate_background','unsupported_connection','hypothesis_as_fact'))
        issues['uniqueItems']=True
        return _object(**common,relevance=_enum('specific_useful','partial_or_generic','no_supported_link','insufficient_evidence'),
            misleading=_enum('yes','no','unknown'),background_accuracy=_enum('supported','inaccurate','unknown'),
            issues=issues,evidence=_object(source=refs,research=refs,connection=refs),explanation=text)
    raise ValueError('unknown_assessment_step')


def _unique(rows,key):
    result={row[key]:row for row in rows}
    if len(result)!=len(rows):
        raise ValueError('duplicate_claim_identity')
    return result


def validate_assessment(step,value,*,allowed_refs,required=None):
    """Validate schema, case citation membership and inter-step alignment.

    Membership is not resolution; success does not establish technical usability
    until the executor separately verifies source identity, digest and liveness.
    """
    try:
        Draft202012Validator(assessment_schema(step)).validate(value)
        value=json.loads(canonical(value))
        allowed=set(allowed_refs)
        if value['status']=='insufficient_evidence':
            if not value['reason']:
                raise ValueError('insufficient_reason_required')
        elif value['reason'] is not None:
            raise ValueError('unexpected_insufficient_reason')

        def citations(refs,nonempty=False):
            if (nonempty and not refs) or not set(refs)<=allowed:
                raise ValueError('invalid_assessment_citation')

        if step=='required_claims':
            _unique(value['claims'],'claim_id')
            if value['status']=='insufficient_evidence' and value['claims']:
                raise ValueError('insufficient_with_claims')
            for claim in value['claims']:
                citations(claim['evidence'],True)
        elif step=='align_candidates':
            reference=validate_assessment('required_claims',required,allowed_refs=allowed)
            if reference['status']!='completed':
                raise ValueError('required_claims_unavailable')
            candidates=_unique(value['candidates'],'claim_id')
            matches=_unique(value['matches'],'required_id')
            if value['status']=='insufficient_evidence':
                if candidates or matches:
                    raise ValueError('insufficient_with_judgments')
                return value
            if set(matches)!={r['claim_id'] for r in reference['claims']}:
                raise ValueError('required_alignment_incomplete')
            for claim in candidates.values():
                citations(claim['evidence'],True)
            for claim in reference['claims']:
                match=matches[claim['claim_id']]
                if not set(match['candidate_ids'])<=set(candidates):
                    raise ValueError('unknown_candidate')
                if match['verdict']=='retained' and not match['candidate_ids']:
                    raise ValueError('retained_without_candidate')
                if match['verdict']=='omitted' and match['candidate_ids']:
                    raise ValueError('omitted_with_candidate')
                if claim['certainty']=='uncertain' and match['verdict']!='uncertain_match':
                    raise ValueError('uncertain_reference_determined')
        else:
            for refs in value['evidence'].values():
                citations(refs)
            if (value['status']=='insufficient_evidence') != (value['relevance']=='insufficient_evidence'):
                raise ValueError('research_status_conflict')
            if value['relevance']=='specific_useful' and not all(value['evidence'].values()):
                raise ValueError('specific_link_evidence_missing')
            if not value['evidence']['research'] and value['background_accuracy']!='unknown':
                raise ValueError('background_unverified')
        return value
    except (ValidationError,TypeError,KeyError,AttributeError) as error:
        raise ValueError('assessment_invalid') from error


def quality_counts(required,alignment):
    """Count one already-validated case/stage/version, never merge sample strata."""
    if required['status']!='completed' or alignment['status']!='completed':
        return dict(status='insufficient_evidence',retention=None,required=None)
    candidates=alignment['candidates']
    unknown=sum(c['verdict']=='uncertain' for c in candidates)
    errors=sum(c['verdict'] in ('unsupported','unsuitable_durable') for c in candidates)
    determinate=len(candidates)-unknown
    matches={m['required_id']:m for m in alignment['matches']}
    uncertain_reference=sum(c['certainty']=='uncertain' for c in required['claims'])
    reference_matches=[matches[c['claim_id']]['verdict'] for c in required['claims'] if c['certainty']=='required']
    uncertain_matches=reference_matches.count('uncertain_match')
    known=len(reference_matches)-uncertain_matches
    omitted=reference_matches.count('omitted')
    return dict(status='computed',retention=dict(total=len(candidates),determinate=determinate,uncertain=unknown,
        errors=errors,ratio=errors/determinate if determinate else None),
        required=dict(total=len(required['claims']),uncertain_reference=uncertain_reference,
            determinate_matches=known,uncertain_matches=uncertain_matches,omitted=omitted,ratio=omitted/known if known else None))


def research_label(value):
    return 'misleading' if value['misleading']=='yes' else value['relevance']


def freeze_assessment(plan,entry_id,assessment,*,dependency=None):
    """Bind a private derived result, without claiming it came from a real Judge.

    Execution receipts and live evidence validation must be supplied by the
    executor before this structural result can count as a usable judgment.
    """
    checked=validate_plan(plan)
    entries=[entry for entry in checked['entries'] if entry['entry_id']==entry_id]
    if len(entries)!=1:
        raise ValueError('assessment_entry_unknown')
    entry=entries[0]
    if checked['rules'][entry['step']]['schema_digest']!=digest(assessment_schema(entry['step'])):
        raise ValueError('assessment_schema_mismatch')
    dependency_digest=None
    reference=None
    if entry['depends_on'] is not None:
        validated=validate_record(checked,dependency)
        if validated['entry_id']!=entry['depends_on']:
            raise ValueError('assessment_dependency_mismatch')
        dependency_digest=validated['result_digest']
        reference=validated['assessment']
    elif dependency is not None:
        raise ValueError('assessment_dependency_unexpected')
    case=next(c for c in checked['cases'] if c['case_id']==entry['case_id'])
    value=validate_assessment(entry['step'],assessment,
        allowed_refs=[r['ref'] for r in case['evidence_refs']],required=reference)
    body=dict(schema_version='agc.domain-assessment.v1',plan_id=checked['plan_id'],
        case_id=entry['case_id'],entry_id=entry_id,step=entry['step'],
        execution_key=execution_key(checked,entry_id,dependency_digest=dependency_digest),
        dependency_result_digest=dependency_digest,assessment=value,
        evidence_resolution='unchecked',human_review='unreviewed',execution_receipt=None)
    body['result_digest']=digest(body)
    body['result_id']='ma_'+body['result_digest']
    return json.loads(canonical(body))


def validate_record(plan,value,*,dependency=None):
    try:
        expected=freeze_assessment(plan,value['entry_id'],value['assessment'],dependency=dependency)
        if canonical(expected)!=canonical(value):
            raise ValueError('assessment_record_mismatch')
        return expected
    except (KeyError,TypeError,AttributeError) as error:
        raise ValueError('assessment_record_invalid') from error
