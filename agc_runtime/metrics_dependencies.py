"""Local artifact dependencies; not an external-directory cleanup registry."""
import json

from agc_runtime.metrics_eval import validate_plan
from agc_runtime.metrics_models import canonical,digest


def evaluation_dependencies(plan,entry_id,*,dependency_digest=None):
    checked=validate_plan(plan)
    entry=next((e for e in checked['entries'] if e['entry_id']==entry_id),None)
    if entry is None: raise ValueError('dependency_entry_unknown')
    if (entry['depends_on'] is None)!=(dependency_digest is None):
        raise ValueError('dependency_result_required')
    if dependency_digest is not None:
        from agc_runtime.metrics_eval import _hash
        _hash(dependency_digest)
    case=next(c for c in checked['cases'] if c['case_id']==entry['case_id'])
    body=dict(schema_version='agc.metrics-artifact-dependencies.v1',plan_id=checked['plan_id'],
              entry_id=entry_id,case_id=case['case_id'],subject_digest=case['subject_digest'],
              evidence_refs=case['evidence_refs'],judge_digest=digest(checked['judge']),
              rules_digest=digest(checked['rules']),depends_on=entry['depends_on'],
              dependency_result_digest=dependency_digest,artifacts=['result.json','receipt.json'])
    body['dependency_id']='mdep_'+digest(body)
    return json.loads(canonical(body))


def classification_dependencies(batch,plan,preparation):
    from agc_runtime.metrics_classification_execution import prepare_classification_plan
    if canonical(prepare_classification_plan(batch,preparation,judge=plan['judge']))!=canonical(plan):
        raise ValueError('classification_dependency_plan_mismatch')
    body=dict(schema_version='agc.classification-artifact-dependencies.v1',plan_id=plan['plan_id'],
              preparation_id=plan['preparation_id'],payload_digest=plan['payload_digest'],
              judge_digest=digest(plan['judge']),
              inputs=[dict(task_ref=e['task_ref'],native_reference_digest=e['native_reference_digest'],
                           input_ref=e['input_ref']) for e in preparation['manifest']['entries'] if e['status']=='ready'],
              artifacts=['classification.json','receipt.json'])
    body['dependency_id']='mdep_'+digest(body)
    return json.loads(canonical(body))
