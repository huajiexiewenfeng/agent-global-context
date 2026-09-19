"""Research plans over a scoped source adapter; source content stays in memory.

The adapter must resolve authorized historical evidence and current invalidation
state. Structural validation and hashes here do not establish source authenticity.
"""
import json

from agc_runtime.metrics_eval import _case, prepare_plan, validate_plan
from agc_runtime.metrics_judge_input import build_input, rule_identities
from agc_runtime.metrics_models import canonical, digest, validate_batch
from agc_runtime.metrics_research_cohort import validate_research_cohort


def _selected(cohort):
    return [dict(task_ref=row['task_ref'],revision=row['revision'])
            for row in cohort['tasks'] if row['selection_status']=='selected']


def _bundle(reference,source):
    value=source.prepare(json.loads(canonical(reference)))
    if (not isinstance(value,dict) or set(value)!={'task_ref','revision','documents'}
            or any(value[k]!=reference[k] for k in reference)):
        raise ValueError('research_source_identity_mismatch')
    documents=value['documents']
    if not isinstance(documents,list) or not 2<=len(documents)<=16:
        raise ValueError('research_source_documents_invalid')
    for doc in documents:
        if not isinstance(doc,dict) or set(doc)!={'ref','version','role','content'}:
            raise ValueError('research_source_document_invalid')
    refs=[dict(ref=d['ref'],version=d['version'],digest=digest(d)) for d in documents]
    version=digest(dict(reference=reference,evidence_refs=sorted(refs,key=canonical)))
    subject=dict(stage='research_task',version=version,
                 evidence_roles={d['ref']:d['role'] for d in documents})
    case=_case(dict(case_id='id_'+digest(dict(reference=reference,stage='research_task')),
                    scenario='research',subject_digest=digest(subject),evidence_refs=refs))
    return dict(case=case,subject=subject,documents=documents)


def _mapping(plan,cohort):
    entries=[dict(case_id='id_'+digest(dict(reference=ref,stage='research_task')),reference=ref)
             for ref in _selected(cohort)]
    body=dict(schema_version='agc.metrics-research-source-map.v1',plan_id=plan['plan_id'],
              cohort_id=cohort['cohort_id'],entries=sorted(entries,key=lambda e:e['case_id']))
    body['map_id']='mrsm_'+digest(body)
    return body


def prepare_research_plan(batch,cohort,*,source,judge):
    batch=validate_batch(batch)
    cohort=validate_research_cohort(batch,cohort)
    bundles=[_bundle(reference,source) for reference in _selected(cohort)]
    plan=prepare_plan(batch_id=batch['batch_id'],cases=[b['case'] for b in bundles],
                      judge=judge,rules=rule_identities())
    by_id={b['case']['case_id']:b for b in bundles}
    for entry in plan['entries']:
        bundle=by_id[entry['case_id']]
        # Enforce historical role allowlist, complete delivered input/output,
        # document bounds and digests before freezing a sendable plan.
        build_input(plan,entry['entry_id'],subject=bundle['subject'],
                    documents=bundle['documents'],revoked_refs=[])
    return json.loads(canonical(dict(plan=plan,source_map=_mapping(plan,cohort))))


def research_plan_resolver(batch,cohort,plan,source_map,*,source):
    batch=validate_batch(batch)
    cohort=validate_research_cohort(batch,cohort)
    checked=validate_plan(plan)
    expected=_mapping(checked,cohort)
    cases={c['case_id']:c for c in checked['cases']}
    if (checked['batch_id']!=batch['batch_id'] or canonical(source_map)!=canonical(expected)
            or set(cases)!={e['case_id'] for e in expected['entries']}
            or any(c['scenario']!='research' for c in cases.values())):
        raise ValueError('research_source_map_mismatch')
    mapped={e['case_id']:e['reference'] for e in expected['entries']}

    def resolve(case_id):
        if case_id not in mapped:
            raise ValueError('research_case_unknown')
        bundle=_bundle(mapped[case_id],source)
        if canonical(bundle['case'])!=canonical(cases[case_id]):
            raise ValueError('research_case_changed')
        entry=next(e for e in checked['entries'] if e['case_id']==case_id)
        build_input(checked,entry['entry_id'],subject=bundle['subject'],
                    documents=bundle['documents'],revoked_refs=[])
        return json.loads(canonical(dict(subject=bundle['subject'],documents=bundle['documents'],revoked_refs=[])))
    return resolve
