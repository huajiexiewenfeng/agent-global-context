"""Read-only local execution verification. File consistency is not authenticity."""
import json
import re

from agc_runtime.metrics_assessment import validate_record,validate_assessment
from agc_runtime.metrics_eval import validate_plan
from agc_runtime.metrics_eval_summary import FIELDS,summarize_evaluations
from agc_runtime.metrics_evidence import _root,_linked,_unique_fields
from agc_runtime.metrics_judge_input import build_input
from agc_runtime.metrics_models import canonical,digest,instant


class EvidenceUnavailable(ValueError):
    pass


def _read(path):
    if any(_linked(p) for p in (path,*path.parents)):
        raise ValueError('linked_execution_artifact')
    before=path.stat()
    with path.open('rb') as handle:
        raw=handle.read(2*1024*1024+1)
    after=path.stat()
    if len(raw)>2*1024*1024 or (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):
        raise ValueError('execution_artifact_changed_or_oversized')
    return json.loads(raw.decode('utf-8'),object_pairs_hook=_unique_fields)


def _attempt(plan,entry,directory):
    start=_read(directory/'started.json')
    if (not isinstance(start,dict) or set(start)!=FIELDS or start['entry_id']!=entry['entry_id']
            or start['plan_id']!=plan['plan_id'] or start['status']!='in_progress'
            or start['finished_at'] is not None or start['result_digest'] is not None
            or not isinstance(start['attempt_id'],str) or not re.fullmatch(r'mea_[a-f0-9]{64}',start['attempt_id'])):
        raise ValueError('execution_start_invalid')
    instant(start['started_at'])
    if not (directory/'finished.json').exists():
        return start
    end=_read(directory/'finished.json')
    if (not isinstance(end,dict) or set(end)!=FIELDS
            or any(start[key]!=end[key] for key in FIELDS-{'finished_at','status','result_digest'})
            or end['status'] not in ('completed','evaluation_error')
            or instant(end['finished_at'])<instant(start['started_at'])):
        raise ValueError('execution_terminal_conflict')
    return end


def verify_saved_step(plan,directory,entry_id,*,resolve_case,ledger_directory=None,require_source_binding=False):
    """Verify files/live input; host callers must bind their fixed ledger.

    Omitting the ledger is a low-level standalone check, never proof of host
    registration. Recursive dependencies inherit the same explicit binding.
    """
    checked=validate_plan(plan)
    if require_source_binding and ledger_directory is None:
        raise ValueError('source_binding_requires_host_ledger')
    root=_root(directory)
    entry=next((e for e in checked['entries'] if e['entry_id']==entry_id),None)
    if entry is None:
        raise ValueError('execution_entry_unknown')
    location=root/entry_id
    attempt=_attempt(checked,entry,location)
    if attempt['status']!='completed':
        raise ValueError('execution_not_completed')
    dependency=None
    if entry['depends_on'] is not None:
        previous=verify_saved_step(checked,root,entry['depends_on'],resolve_case=resolve_case,
                                   ledger_directory=ledger_directory,require_source_binding=require_source_binding)
        if instant(previous['attempt']['finished_at'])>instant(attempt['started_at']):
            raise ValueError('execution_dependency_time_conflict')
        dependency=previous['result']
    from agc_runtime.metrics_dependencies import evaluation_dependencies
    expected_dependencies=evaluation_dependencies(checked,entry_id,
        dependency_digest=dependency['result_digest'] if dependency is not None else None)
    try:
        registered=_read(location/'dependencies.json')
    except (OSError,ValueError):
        raise ValueError('execution_dependencies_unavailable') from None
    if canonical(registered)!=canonical(expected_dependencies):
        raise ValueError('execution_dependencies_mismatch')
    if ledger_directory is not None:
        from agc_runtime.metrics_artifact_registry import verify_registration
        verify_registration(ledger_directory,location,expected_dependencies,require_source_binding=require_source_binding)
    result=validate_record(checked,_read(location/'result.json'),dependency=dependency)
    try:
        source=resolve_case(entry['case_id'])
        payload=build_input(checked,entry_id,subject=source['subject'],documents=source['documents'],
                            revoked_refs=source['revoked_refs'],dependency=dependency)
    except Exception as error:
        raise EvidenceUnavailable('execution_evidence_unchecked') from error
    validate_assessment(entry['step'],result['assessment'],allowed_refs=[r['ref'] for r in payload['case']['evidence_refs']],
                        required=payload['case'].get('required_claims'))
    receipt=_read(location/'receipt.json')
    fields={'schema_version','attempt_id','plan_id','entry_id','execution_key','input_digest','result_digest',
            'requested_configuration','observed_configuration','usage'}
    if not isinstance(receipt,dict) or set(receipt)!=fields:
        raise ValueError('execution_receipt_invalid')
    expected=dict(schema_version='agc.metrics-execution-receipt.v1',attempt_id=attempt['attempt_id'],plan_id=checked['plan_id'],
        entry_id=entry_id,execution_key=result['execution_key'],input_digest=digest(payload),
        result_digest=result['result_digest'],requested_configuration=checked['judge'])
    if (any(receipt[key]!=value for key,value in expected.items()) or attempt['result_digest']!=result['result_digest']
            or attempt['dependency_result_digest']!=result['dependency_result_digest']):
        raise ValueError('execution_receipt_mismatch')
    usage=receipt['usage']
    if usage is not None and (not isinstance(usage,dict) or set(usage)!={'input_tokens','output_tokens','total_tokens'}
            or any(type(v) is not int or v<0 for v in usage.values())
            or usage['input_tokens']+usage['output_tokens']!=usage['total_tokens']):
        raise ValueError('execution_usage_invalid')
    observed=receipt['observed_configuration']
    if observed is not None and (not isinstance(observed,dict) or set(observed)!={'provider','model','reasoning_effort'}
            or any(observed[key]!=checked['judge'][key] for key in observed)):
        raise ValueError('execution_observed_mismatch')
    # Detect a concurrent terminal replacement rather than accepting a mixed read.
    if canonical(_attempt(checked,entry,location))!=canonical(attempt):
        raise ValueError('execution_changed_during_read')
    if canonical(_read(location/'dependencies.json'))!=canonical(expected_dependencies):
        raise ValueError('execution_dependencies_changed_during_read')
    if ledger_directory is not None:
        verify_registration(ledger_directory,location,expected_dependencies,require_source_binding=require_source_binding)
    return dict(attempt=attempt,result=result,receipt=receipt,subject=source['subject'],
        status='insufficient_evidence' if result['assessment']['status']=='insufficient_evidence' else 'usable_judgment')


def summarize_execution_directory(plan,directory,*,cutoff,resolve_case,ledger_directory=None,require_source_binding=False):
    checked=validate_plan(plan)
    root=_root(directory)
    attempts=[]
    invalid=0
    for entry in checked['entries']:
        location=root/entry['entry_id']
        if not location.exists():
            continue
        try:
            attempts.append(_attempt(checked,entry,location))
        except (OSError,ValueError,TypeError,KeyError):
            invalid+=1
    def verify(entry,row):
        try:
            checked_result=verify_saved_step(checked,root,entry['entry_id'],resolve_case=resolve_case,
                                             ledger_directory=ledger_directory,require_source_binding=require_source_binding)
            if canonical(row)!=canonical(checked_result['attempt']):
                return 'conflict'
            return checked_result['status']
        except EvidenceUnavailable:
            return 'unchecked'
        except (OSError,ValueError,TypeError,KeyError):
            return 'evaluation_error'
    summary=summarize_evaluations(checked,attempts,cutoff=cutoff,verify_result=verify)
    summary['invalid_records']+=invalid
    return summary
