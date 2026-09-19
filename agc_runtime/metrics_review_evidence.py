"""Explicit private review evidence annex; never included in default metrics.

Contains safe source content and model-derived text. Keep private and apply the
same retention/forget controls as its sources. Offline hashes prove consistency,
not authenticity, current access or accuracy of the model's judgment.
"""
import json

from agc_runtime.metrics_assessment import validate_record
from agc_runtime.metrics_execution import _now
from agc_runtime.metrics_judge_input import build_input
from agc_runtime.metrics_models import canonical,digest,instant
from agc_runtime.metrics_result_reader import verify_saved_step
from agc_runtime.metrics_review_batch import validate_review


def _case(review,row,item):
    if (not isinstance(item,dict) or set(item)!={'case_id','status','subject','documents','results'}
            or item['case_id']!=row['case_id'] or item['status'] not in ('available','unavailable')):
        raise ValueError('review_evidence_case_invalid')
    if item['status']=='unavailable':
        if item['subject'] is not None or item['documents']!=[] or item['results']!=[]:
            raise ValueError('review_evidence_unavailable_content')
        return
    if row['status']!='usable_judgment': raise ValueError('review_evidence_unassessed')
    plan=review['plan']; entries=[e for e in plan['entries'] if e['case_id']==row['case_id']]
    if not isinstance(item['results'],list) or len(item['results'])!=len(entries):
        raise ValueError('review_evidence_results_missing')
    dependency=None
    for entry,result in zip(entries,item['results']):
        checked=validate_record(plan,result,dependency=dependency)
        if checked['entry_id']!=entry['entry_id']: raise ValueError('review_evidence_entry_mismatch')
        build_input(plan,entry['entry_id'],subject=item['subject'],documents=item['documents'],
                    revoked_refs=[],dependency=dependency)
        dependency=checked
    if ([r['result_digest'] for r in item['results']]!=row['result_digests']
            or item['subject']['stage']!=row['stage']):
        raise ValueError('review_evidence_review_mismatch')


def validate_evidence(batch,review,value):
    review=validate_review(review,batch)
    try:
        if (not isinstance(value,dict) or set(value)!={'schema_version','review_id','created_at','privacy','validity','cases','evidence_id'}
                or value['schema_version']!='agc.review-evidence.v1' or value['review_id']!=review['review_id']
                or value['privacy']!='private_source_and_model_content'
                or value['validity']!='point_in_time_not_live_authorization'):
            raise ValueError('review_evidence_identity')
        instant(value['created_at'])
        if not isinstance(value['cases'],list) or len(value['cases'])!=len(review['rows']):
            raise ValueError('review_evidence_cases')
        for row,item in zip(review['rows'],value['cases']): _case(review,row,item)
        if value['evidence_id']!='mev_'+digest({k:v for k,v in value.items() if k!='evidence_id'}):
            raise ValueError('review_evidence_digest')
        if len(canonical(value).encode('utf-8'))>16*1024*1024:
            raise ValueError('review_evidence_too_large')
        return json.loads(canonical(value))
    except (KeyError,TypeError,AttributeError) as error:
        raise ValueError('review_evidence_invalid') from error


def freeze_evidence(batch,review,directory,*,resolve_case,ledger_directory=None,require_source_binding=False):
    review=validate_review(review,batch)
    if not callable(resolve_case): raise ValueError('live_case_resolver_required')
    cases=[]
    for row in review['rows']:
        item=dict(case_id=row['case_id'],status='unavailable',subject=None,documents=[],results=[])
        if row['status']=='usable_judgment':
            try:
                plan=review['plan']; entries=[e for e in plan['entries'] if e['case_id']==row['case_id']]
                verified=[verify_saved_step(plan,directory,e['entry_id'],resolve_case=resolve_case,
                                            ledger_directory=ledger_directory,require_source_binding=require_source_binding) for e in entries]
                if any(v['status']!='usable_judgment' for v in verified):
                    raise ValueError('review_evidence_step_unavailable')
                source=resolve_case(row['case_id'])
                candidate=dict(case_id=row['case_id'],status='available',subject=source['subject'],
                               documents=source['documents'],results=[v['result'] for v in verified])
                _case(review,row,candidate)
                # Validate live revocations as well as bound document identity;
                # the offline validator's empty list must not replace this gate.
                dependency=None
                for entry,result in zip(entries,candidate['results']):
                    current=resolve_case(row['case_id'])
                    build_input(plan,entry['entry_id'],subject=current['subject'],documents=current['documents'],
                                revoked_refs=current['revoked_refs'],dependency=dependency)
                    dependency=result
                # Later resolver calls above may have changed host inventory.
                # Recheck after the final source read before exposing this case.
                if ledger_directory is not None:
                    from pathlib import Path
                    from agc_runtime.metrics_artifact_registry import verify_registration
                    from agc_runtime.metrics_dependencies import evaluation_dependencies
                    dependency=None
                    for entry,result in zip(entries,candidate['results']):
                        verify_registration(ledger_directory,Path(directory)/entry['entry_id'],
                            evaluation_dependencies(plan,entry['entry_id'],
                                dependency_digest=dependency['result_digest'] if dependency else None),
                            require_source_binding=require_source_binding)
                        dependency=result
                item=candidate
            except (OSError,ValueError,TypeError,KeyError,AttributeError):
                pass  # Preserve the unavailable case, never exception/source text.
        cases.append(item)
    body=dict(schema_version='agc.review-evidence.v1',review_id=review['review_id'],created_at=_now(),
              privacy='private_source_and_model_content',validity='point_in_time_not_live_authorization',cases=cases)
    body['evidence_id']='mev_'+digest(body)
    return validate_evidence(batch,review,body)


def evidence_index(batch,review,evidence):
    """Only this content-free projection is eligible for first-version export."""
    checked=validate_evidence(batch,review,evidence)
    cases=[]
    for item in checked['cases']:
        cases.append(dict(case_id=item['case_id'],status=item['status'],
            result_refs=[dict(entry_id=r['entry_id'],step=r['step'],result_digest=r['result_digest']) for r in item['results']],
            document_refs=[dict(ref=d['ref'],role=d['role'],version_digest=digest(d['version']),document_digest=digest(d)) for d in item['documents']]))
    body=dict(schema_version='agc.review-evidence-index.v1',review_id=checked['review_id'],
              evidence_id=checked['evidence_id'],created_at=checked['created_at'],
              privacy='controlled_references_only',validity=checked['validity'],cases=cases)
    body['index_id']='mevi_'+digest(body)
    return json.loads(canonical(body))
