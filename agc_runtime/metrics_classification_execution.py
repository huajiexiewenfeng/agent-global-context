"""One explicitly authorized classification attempt, with no automatic retry.

The host must supply its fixed ledger and a live access-controlled preparation
resolver. Digest agreement binds scope, but does not authenticate user consent.
"""
from hmac import compare_digest
from contextlib import nullcontext
import json

from agc_runtime.metrics_eval import judge_configuration
from agc_runtime.metrics_evidence import _root
from agc_runtime.metrics_execution import _write,_now
from agc_runtime.metrics_models import canonical,digest,opaque,validate_batch
from agc_runtime.metrics_research_classification import (
    RULE_VERSION,classification_payload,freeze_classification_output)


def prepare_classification_plan(batch,preparation,*,judge):
    payload=classification_payload(batch,preparation)
    body=dict(schema_version='agc.classification-plan.v1',batch_id=validate_batch(batch)['batch_id'],
              preparation_id=preparation['manifest']['preparation_id'],payload_digest=digest(payload),
              judge=judge_configuration(judge),rule_version=RULE_VERSION,
              input_count=len(payload['evidence']),max_calls=int(bool(payload['evidence'])))
    body['authorization_digest']=digest(body)
    body['plan_id']='mcplan_'+body['authorization_digest']
    return json.loads(canonical(body))


def execute_classification(batch,plan,*,directory,ledger_directory,consent_digest,gateway,resolve_preparation,
                           native_references=None,commit_guard=nullcontext):
    if not callable(commit_guard): raise ValueError('commit_guard_factory_required')
    # Validate the frozen envelope before any source read or path construction.
    fields={'schema_version','batch_id','preparation_id','payload_digest','judge','rule_version',
            'input_count','max_calls','authorization_digest','plan_id'}
    if not isinstance(plan,dict) or set(plan)!=fields:
        raise ValueError('classification_plan_invalid')
    body={k:v for k,v in plan.items() if k not in ('authorization_digest','plan_id')}
    authorization=digest(body)
    if (plan['authorization_digest']!=authorization or plan['plan_id']!='mcplan_'+authorization
            or not isinstance(consent_digest,str) or not compare_digest(authorization,consent_digest)):
        raise ValueError('classification_consent_mismatch')
    if not callable(resolve_preparation): raise ValueError('classification_live_source_required')

    def current():
        if judge_configuration(gateway.configuration)!=plan['judge']:
            raise ValueError('classification_configuration_changed')
        value=resolve_preparation()
        if canonical(prepare_classification_plan(batch,value,judge=plan['judge']))!=canonical(plan):
            raise ValueError('classification_source_changed')
        return value

    preparation=current()
    if not plan['max_calls']:
        return dict(plan_id=plan['plan_id'],status='no_ready_inputs',model_called=False)
    root,ledger=_root(directory),_root(ledger_directory)
    # Shared, exclusive reservation arbitrates different output folders. Failure
    # and interruption consume this plan's single slot, as in metrics_runner.
    try:
        _write(ledger/(plan['plan_id']+'.json'),dict(
            schema_version='agc.classification-send-reservation.v1',plan_id=plan['plan_id'],
            authorization_digest=authorization,reserved_at=_now()))
    except FileExistsError:
        raise ValueError('classification_already_reserved') from None
    destination=root/plan['plan_id']; destination.mkdir(exist_ok=False)
    from agc_runtime.metrics_attempt_lock import attempt_lock
    with attempt_lock(destination,create=True):
        started=dict(plan_id=plan['plan_id'],started_at=_now(),status='in_progress',model_called=False)
        _write(destination/'started.json',started)
        called=False; result=None
        try:
            preparation=current()
            if native_references is not None:
                from agc_runtime.metrics_source_bindings import classification_source_bindings,register_source_bindings
                register_source_bindings(ledger,classification_source_bindings(batch,plan,preparation,native_references))
            from agc_runtime.metrics_dependencies import classification_dependencies
            from agc_runtime.metrics_artifact_registry import register_execution_directory,verify_registration
            dependencies=classification_dependencies(batch,plan,preparation)
            _write(destination/'dependencies.json',dependencies)
            register_execution_directory(ledger,destination,dependencies,
                                         require_source_binding=native_references is not None)
            payload=classification_payload(batch,preparation)
            called=True
            outcome=gateway.evaluate(payload)
            preparation=current()
            result=freeze_classification_output(batch,preparation,outcome.output,classifier=dict(
                method='llm',rule_version=RULE_VERSION,configuration_digest=digest(plan['judge']),
                authorization_ref=opaque(authorization)))
            usage=outcome.usage
            if usage is not None and (not isinstance(usage,dict) or set(usage)!={'input_tokens','output_tokens','total_tokens'}
                    or any(type(v) is not int or v<0 for v in usage.values())
                    or usage['total_tokens']!=usage['input_tokens']+usage['output_tokens']):
                raise ValueError('classification_usage_invalid')
            observed=outcome.observed_configuration
            if observed is not None and (not isinstance(observed,dict) or set(observed)!={'provider','model','reasoning_effort'}
                    or any(observed[k]!=plan['judge'][k] for k in observed)):
                raise ValueError('classification_observed_configuration_mismatch')
            receipt=dict(schema_version='agc.classification-receipt.v1',plan_id=plan['plan_id'],
                         payload_digest=plan['payload_digest'],classification_digest=digest(result),
                         requested_configuration=plan['judge'],observed_configuration=observed,usage=usage)
            with commit_guard():
                current()
                verify_registration(ledger,destination,dependencies,
                                    require_source_binding=native_references is not None)
                _write(destination/'classification.json',result)
                _write(destination/'receipt.json',receipt)
        except Exception:
            result=None
            _write(destination/'error.json',dict(code='classification_failed'))
        finished=dict(started,finished_at=_now(),model_called=called,
                      status='completed' if result is not None else 'classification_error',
                      classification_digest=digest(result) if result is not None else None)
        _write(destination/'finished.json',finished)
        return finished
