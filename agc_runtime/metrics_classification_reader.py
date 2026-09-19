"""Verify local classification consistency and live evidence, not authenticity."""
from agc_runtime.metrics_classification_execution import prepare_classification_plan
from agc_runtime.metrics_evidence import _root
from agc_runtime.metrics_models import canonical,digest,instant,opaque
from agc_runtime.metrics_research_classification import RULE_VERSION,freeze_classification_output
from agc_runtime.metrics_result_reader import _read


def read_classification(batch,plan,*,directory,ledger_directory,resolve_preparation,require_source_binding=False):
    try:
        if not callable(resolve_preparation): raise ValueError('live_resolver_required')
        preparation=resolve_preparation()
        expected=prepare_classification_plan(batch,preparation,judge=plan['judge'])
        if canonical(expected)!=canonical(plan) or plan['max_calls']!=1:
            raise ValueError('classification_plan_mismatch')
        root,ledger=_root(directory),_root(ledger_directory)
        location=_root(root/expected['plan_id'])
        paths={name:location/(name+'.json') for name in ('started','finished','receipt','classification','dependencies')}
        paths['ledger']=ledger/(expected['plan_id']+'.json')
        values={name:_read(path) for name,path in paths.items()}
        from agc_runtime.metrics_dependencies import classification_dependencies
        from agc_runtime.metrics_artifact_registry import verify_registration
        dependencies=classification_dependencies(batch,plan,preparation)
        if canonical(values['dependencies'])!=canonical(dependencies):
            raise ValueError('classification_dependencies_mismatch')
        verify_registration(ledger,location,dependencies,require_source_binding=require_source_binding)
        start,end,receipt,result,reservation=(values[k] for k in ('started','finished','receipt','classification','ledger'))
        if (set(start)!={'plan_id','started_at','status','model_called'} or start['plan_id']!=plan['plan_id']
                or start['status']!='in_progress' or start['model_called'] is not False):
            raise ValueError('classification_start_invalid')
        expected_end=dict(start,finished_at=end['finished_at'],model_called=True,status='completed',
                          classification_digest=digest(result))
        if canonical(end)!=canonical(expected_end): raise ValueError('classification_terminal_invalid')
        expected_reservation=dict(schema_version='agc.classification-send-reservation.v1',plan_id=plan['plan_id'],
                                 authorization_digest=plan['authorization_digest'],reserved_at=reservation['reserved_at'])
        if canonical(reservation)!=canonical(expected_reservation): raise ValueError('classification_reservation_invalid')
        if not instant(reservation['reserved_at'])<=instant(start['started_at'])<=instant(end['finished_at']):
            raise ValueError('classification_time_invalid')
        if (location/'error.json').exists(): raise ValueError('classification_error_present')
        expected_result=freeze_classification_output(batch,preparation,dict(labels=result['labels']),classifier=dict(
            method='llm',rule_version=RULE_VERSION,configuration_digest=digest(plan['judge']),
            authorization_ref=opaque(plan['authorization_digest'])))
        if canonical(expected_result)!=canonical(result): raise ValueError('classification_result_invalid')
        expected_receipt=dict(schema_version='agc.classification-receipt.v1',plan_id=plan['plan_id'],
                              payload_digest=plan['payload_digest'],classification_digest=digest(result),
                              requested_configuration=plan['judge'],observed_configuration=receipt['observed_configuration'],
                              usage=receipt['usage'])
        if canonical(expected_receipt)!=canonical(receipt): raise ValueError('classification_receipt_invalid')
        usage=receipt['usage']
        if usage is not None and (not isinstance(usage,dict) or set(usage)!={'input_tokens','output_tokens','total_tokens'}
                or any(type(v) is not int or v<0 for v in usage.values())
                or usage['total_tokens']!=usage['input_tokens']+usage['output_tokens']):
            raise ValueError('classification_usage_invalid')
        observed=receipt['observed_configuration']
        if observed is not None and (not isinstance(observed,dict) or set(observed)!={'provider','model','reasoning_effort'}
                or any(observed[k]!=plan['judge'][k] for k in observed)):
            raise ValueError('classification_observed_configuration_invalid')
        # Do not return a result if source access or any artifact changed during
        # this verification. This is a bounded check, not an atomic snapshot.
        if canonical(prepare_classification_plan(batch,resolve_preparation(),judge=plan['judge']))!=canonical(plan):
            raise ValueError('classification_source_changed')
        if any(canonical(_read(paths[k]))!=canonical(v) for k,v in values.items()):
            raise ValueError('classification_artifact_changed')
        if (location/'error.json').exists(): raise ValueError('classification_error_present')
        verify_registration(ledger,location,dependencies,require_source_binding=require_source_binding)
        return dict(status='verified_classification',verification='local_consistency_and_live_source_not_authenticity',
                    classification=result,receipt=receipt,attempt=end)
    except (OSError,ValueError,TypeError,KeyError,AttributeError):
        raise ValueError('classification_unavailable_or_unverified') from None
