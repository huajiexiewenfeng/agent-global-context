"""Capture metrics plans with re-resolvable references, never persisted Capsules."""
import json

from agc_runtime.capture_eval_adapter import _valid_reference
from agc_runtime.metrics_eval import prepare_plan, validate_plan
from agc_runtime.metrics_judge_input import rule_identities
from agc_runtime.metrics_models import canonical, digest, validate_batch


def prepare_capture_plan(batch, references, *, source, judge):
    batch=validate_batch(batch)
    if not isinstance(references,list) or not 1 <= len(references) <= 10:
        raise ValueError('capture_reference_count_invalid')
    if any(not _valid_reference(ref) for ref in references):
        raise ValueError('capture_reference_invalid')
    if len({canonical(ref) for ref in references}) != len(references):
        raise ValueError('duplicate_capture_reference')
    bundles=[source.prepare(ref) for ref in references]
    plan=prepare_plan(batch_id=batch['batch_id'],cases=[b['case'] for b in bundles],
                      judge=judge,rules=rule_identities())
    entries=sorted([dict(case_id=b['case']['case_id'],reference=ref)
                    for b,ref in zip(bundles,references)],key=lambda r:r['case_id'])
    body=dict(schema_version='agc.metrics-capture-source-map.v1',plan_id=plan['plan_id'],entries=entries)
    body['map_id']='mcsm_'+digest(body)
    return json.loads(canonical(dict(plan=plan,source_map=body)))


def capture_plan_resolver(plan, source_map, *, source):
    checked=validate_plan(plan)
    try:
        if set(source_map) != {'schema_version','plan_id','entries','map_id'}:
            raise ValueError('capture_source_map_fields')
        if (source_map['schema_version']!='agc.metrics-capture-source-map.v1'
                or source_map['plan_id']!=checked['plan_id']
                or source_map['map_id']!='mcsm_'+digest({k:v for k,v in source_map.items() if k!='map_id'})):
            raise ValueError('capture_source_map_identity')
        entries=source_map['entries']
        if not isinstance(entries,list) or len(entries)!=len(checked['cases']):
            raise ValueError('capture_source_map_cases')
        if any(set(e)!={'case_id','reference'} or not _valid_reference(e['reference']) for e in entries):
            raise ValueError('capture_source_map_reference')
        mapped={e['case_id']:e['reference'] for e in entries}
        cases={c['case_id']:c for c in checked['cases']}
        if len(mapped)!=len(entries) or set(mapped)!=set(cases) or any(c['scenario']=='research' for c in cases.values()):
            raise ValueError('capture_source_map_membership')
        mapped=json.loads(canonical(mapped))
    except (KeyError,TypeError,AttributeError) as error:
        raise ValueError('capture_source_map_invalid') from error

    def resolve(case_id):
        if case_id not in mapped:
            raise ValueError('capture_case_unknown')
        bundle=source.prepare(mapped[case_id])
        if canonical(bundle['case'])!=canonical(cases[case_id]):
            raise ValueError('capture_case_changed')
        return dict(subject=bundle['subject'],documents=bundle['documents'],revoked_refs=[])
    return resolve
