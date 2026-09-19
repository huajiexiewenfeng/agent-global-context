"""Single authorized metrics step with exclusive, append-only local artifacts.

Gateway configuration is a trusted host contract, not self-authenticating proof.
Production host binding and safe evidence resolution must precede this API.
"""
from datetime import datetime, timezone
from contextlib import nullcontext
import json
import os
from uuid import uuid4

from agc_runtime.metrics_assessment import freeze_assessment, validate_assessment
from agc_runtime.metrics_eval import check_authorization, validate_plan, judge_configuration, execution_key
from agc_runtime.metrics_evidence import _root
from agc_runtime.metrics_judge_input import build_input
from agc_runtime.metrics_models import canonical, digest


def _now():
    return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')


def _write(path,value):
    with path.open('x',encoding='utf-8',newline='\n') as handle:
        handle.write(canonical(value))
        handle.flush()
        os.fsync(handle.fileno())


def execute_entry(plan,entry_id,*,directory,consent_digest,subject,documents,
                  revoked_refs,gateway,dependency=None,commit_guard=nullcontext,commit_check=None):
    checked=validate_plan(plan)
    if not callable(commit_guard):
        raise ValueError('commit_guard_factory_required')
    if commit_check is not None and not callable(commit_check):
        raise ValueError('commit_check_callback_required')
    if not callable(revoked_refs):
        raise ValueError('live_revocation_callback_required')
    check_authorization(checked,consent_digest,revoked_refs=revoked_refs())
    if judge_configuration(gateway.configuration)!=checked['judge']:
        raise ValueError('execution_configuration_mismatch')
    payload=build_input(checked,entry_id,subject=subject,documents=documents,
                        revoked_refs=revoked_refs(),dependency=dependency)
    entry=next(e for e in checked['entries'] if e['entry_id']==entry_id)
    dependency_digest=dependency['result_digest'] if dependency is not None else None
    key=execution_key(checked,entry_id,dependency_digest=dependency_digest)
    root=_root(directory)
    destination=root/entry_id
    try:
        destination.mkdir(exist_ok=False)
    except FileExistsError as error:
        raise ValueError('entry_already_reserved') from error
    from agc_runtime.metrics_attempt_lock import attempt_lock
    with attempt_lock(destination,create=True):
        started=dict(attempt_id='mea_'+uuid4().hex+uuid4().hex,entry_id=entry_id,plan_id=checked['plan_id'],
            started_at=_now(),finished_at=None,status='in_progress',result_digest=None,
            dependency_result_digest=dependency_digest)
        _write(destination/'started.json',started)
        result=None
        error_code=None
        try:
            from agc_runtime.metrics_dependencies import evaluation_dependencies
            _write(destination/'dependencies.json',evaluation_dependencies(checked,entry_id,
                   dependency_digest=dependency_digest))
            # Recheck immediately before sending; no implicit retry on any failure.
            check_authorization(checked,consent_digest,revoked_refs=revoked_refs())
            if judge_configuration(gateway.configuration)!=checked['judge']:
                raise ValueError('execution_configuration_changed')
            outcome=gateway.evaluate(json.loads(canonical(payload)))
            assessment=validate_assessment(entry['step'],outcome.output,
                allowed_refs=[r['ref'] for r in payload['case']['evidence_refs']],
                required=payload['case'].get('required_claims'))
            result=freeze_assessment(checked,entry_id,assessment,dependency=dependency)
            usage=outcome.usage
            if usage is not None and (not isinstance(usage,dict) or set(usage)!={'input_tokens','output_tokens','total_tokens'}
                    or any(type(v) is not int or v<0 for v in usage.values())
                    or usage['total_tokens']!=usage['input_tokens']+usage['output_tokens']):
                raise ValueError('usage_invalid')
            observed=outcome.observed_configuration
            if observed is not None and (not isinstance(observed,dict) or set(observed)!={'provider','model','reasoning_effort'}
                    or any(observed[k]!=checked['judge'][k] for k in observed)):
                raise ValueError('observed_configuration_mismatch')
            receipt=dict(schema_version='agc.metrics-execution-receipt.v1',attempt_id=started['attempt_id'],
                plan_id=checked['plan_id'],entry_id=entry_id,execution_key=key,
                input_digest=digest(payload),result_digest=result['result_digest'],
                requested_configuration=checked['judge'],observed_configuration=observed,usage=usage)
            # Network/model work is outside the host's shared write lock. Source
            # invalidation and content persistence must share one final critical section.
            with commit_guard():
                check_authorization(checked,consent_digest,revoked_refs=revoked_refs())
                if judge_configuration(gateway.configuration)!=checked['judge']:
                    raise ValueError('execution_configuration_changed')
                if commit_check is not None:
                    commit_check()
                _write(destination/'result.json',result)
                _write(destination/'receipt.json',receipt)
        except Exception:
            # Never persist arbitrary exception messages, stdout or private source text.
            result=None
            error_code='metrics_evaluation_failed'
        finished=dict(started,finished_at=_now(),status='completed' if result is not None else 'evaluation_error',
                      result_digest=result['result_digest'] if result is not None else None)
        _write(destination/'finished.json',finished)
        if error_code:
            _write(destination/'error.json',dict(code=error_code))
        return finished
