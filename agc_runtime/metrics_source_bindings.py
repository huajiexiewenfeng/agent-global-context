"""Controlled source joins for managed invalidation, never deletion authority.

These builders verify metadata joins. Host source resolvers must separately prove
the referenced native revision produced the frozen metrics evidence before an
execution can be accepted. No source text is read or inverted from metric hashes.
"""
import json
import re
from collections import Counter

from agc_runtime.capture_contracts import RevisionRef, receipt_id_for
from agc_runtime.metrics_eval import validate_plan, _opaque, _hash
from agc_runtime.metrics_models import canonical, digest
from agc_runtime.metrics_research_source import _task_ref


def _native(references,*,allow_duplicates=False):
    if not isinstance(references,list) or len(references)>100:
        raise ValueError('source_native_references_invalid')
    refs=[RevisionRef.from_mapping(r) for r in references]
    by_digest={digest(r.to_mapping()):r for r in refs}
    if not allow_duplicates and len(by_digest)!=len(refs):
        raise ValueError('source_native_reference_duplicate')
    return by_digest


def _body(plan_id, binding, entries):
    value=dict(schema_version='agc.metrics-source-bindings.v1',plan_id=plan_id,
               input_binding_digest=binding,entries=sorted(entries,key=lambda r:r['subject_ref']))
    value['binding_id']='msb_'+digest(value)
    return json.loads(canonical(value))


def evaluation_source_bindings(plan,source_map,*,native_references=None):
    checked=validate_plan(plan)
    if not isinstance(source_map,dict):
        raise ValueError('source_map_invalid')
    schema=source_map.get('schema_version')
    entries=[]
    if schema=='agc.metrics-capture-source-map.v1':
        from agc_runtime.metrics_capture_plan import capture_plan_resolver
        # Constructor checks the exact map without resolving private content.
        capture_plan_resolver(checked,source_map,source=None)
        if native_references is not None:
            raise ValueError('capture_native_references_unexpected')
        entries=[dict(subject_ref=e['case_id'],receipt_id=e['reference']['ref'],
                      native_reference_digest=None) for e in source_map['entries']]
    elif schema=='agc.metrics-research-source-map.v1':
        if (set(source_map)!={'schema_version','plan_id','cohort_id','entries','map_id'}
                or source_map['plan_id']!=checked['plan_id']
                or source_map['map_id']!='mrsm_'+digest({k:v for k,v in source_map.items() if k!='map_id'})):
            raise ValueError('research_source_map_invalid')
        native=_native(native_references)
        tasks={_task_ref(r):r for r in native.values()}
        if len(tasks)!=len(native):
            raise ValueError('source_task_revision_ambiguous')
        mapped=source_map['entries']
        if not isinstance(mapped,list) or len(mapped)!=len(checked['cases']):
            raise ValueError('source_case_membership_invalid')
        seen=set(); used=set()
        for entry in mapped:
            if not isinstance(entry,dict) or set(entry)!={'case_id','reference'}:
                raise ValueError('source_case_invalid')
            reference=entry['reference']
            if not isinstance(reference,dict) or set(reference)!={'task_ref','revision'}:
                raise ValueError('source_research_reference_invalid')
            _opaque(reference['task_ref']); _hash(reference['revision'])
            if (entry['case_id']!='id_'+digest(dict(reference=reference,stage='research_task'))
                    or entry['case_id'] in seen or reference['task_ref'] not in tasks):
                raise ValueError('source_research_join_invalid')
            seen.add(entry['case_id']); used.add(reference['task_ref'])
            ref=tasks[reference['task_ref']]
            entries.append(dict(subject_ref=entry['case_id'],receipt_id=receipt_id_for(ref.key),
                                native_reference_digest=digest(ref.to_mapping())))
        if (seen!={c['case_id'] for c in checked['cases']} or used!=set(tasks)
                or any(c['scenario']!='research' for c in checked['cases'])):
            raise ValueError('source_research_membership_invalid')
    else:
        raise ValueError('source_map_kind_invalid')
    return _body(checked['plan_id'],digest(source_map),entries)


def classification_source_bindings(batch,plan,preparation,native_references):
    from agc_runtime.metrics_classification_execution import prepare_classification_plan
    if canonical(prepare_classification_plan(batch,preparation,judge=plan['judge']))!=canonical(plan):
        raise ValueError('source_classification_plan_mismatch')
    native=_native(native_references,allow_duplicates=True)
    supplied=Counter(digest(RevisionRef.from_mapping(r).to_mapping()) for r in native_references)
    manifested=Counter(r['native_reference_digest'] for r in preparation['manifest']['entries'])
    if supplied!=manifested:
        raise ValueError('source_classification_native_membership')
    entries=[]
    for row in preparation['manifest']['entries']:
        ref=native.get(row['native_reference_digest'])
        if ref is None or _task_ref(ref)!=row['task_ref']:
            raise ValueError('source_classification_native_mismatch')
        if row['status']=='ready':
            entries.append(dict(subject_ref=row['task_ref'],receipt_id=receipt_id_for(ref.key),
                                native_reference_digest=row['native_reference_digest']))
    return _body(plan['plan_id'],digest(preparation['manifest']),entries)


def _plan_id(value):
    if not isinstance(value,str) or not re.fullmatch(r'(?:mplan|mcplan)_[a-f0-9]{64}',value):
        raise ValueError('source_binding_plan_invalid')
    return value


def _validate(value):
    if (not isinstance(value,dict) or set(value)!={'schema_version','plan_id','input_binding_digest','entries','binding_id'}
            or value['schema_version']!='agc.metrics-source-bindings.v1'):
        raise ValueError('source_binding_fields_invalid')
    _plan_id(value['plan_id']); _hash(value['input_binding_digest'])
    if not isinstance(value['entries'],list) or len(value['entries'])>100:
        raise ValueError('source_binding_entries_invalid')
    seen=set()
    for row in value['entries']:
        if not isinstance(row,dict) or set(row)!={'subject_ref','receipt_id','native_reference_digest'}:
            raise ValueError('source_binding_entry_invalid')
        _opaque(row['subject_ref'])
        if row['subject_ref'] in seen or not isinstance(row['receipt_id'],str) or not re.fullmatch(r'cr_[a-f0-9]{64}',row['receipt_id']):
            raise ValueError('source_binding_entry_identity_invalid')
        seen.add(row['subject_ref'])
        if row['native_reference_digest'] is not None: _hash(row['native_reference_digest'])
    expected=_body(value['plan_id'],value['input_binding_digest'],value['entries'])
    if canonical(expected)!=canonical(value):
        raise ValueError('source_binding_digest_invalid')
    return expected


def register_source_bindings(ledger,value):
    from agc_runtime.metrics_evidence import _root
    from agc_runtime.metrics_execution import _write
    checked=_validate(value)
    root=_root(ledger)/'source-bindings'
    root.mkdir(exist_ok=True)
    root=_root(root)
    try:
        _write(root/(checked['plan_id']+'.json'),checked)
    except FileExistsError:
        pass  # Exact reuse only; never overwrite another source association.
    if canonical(read_source_bindings(ledger,checked['plan_id']))!=canonical(checked):
        raise ValueError('source_binding_conflict')
    return checked


def read_source_bindings(ledger,plan_id):
    from agc_runtime.metrics_evidence import _root
    from agc_runtime.metrics_result_reader import _read
    identifier=_plan_id(plan_id)
    value=_validate(_read(_root(_root(ledger)/'source-bindings')/(identifier+'.json')))
    if value['plan_id']!=identifier:
        raise ValueError('source_binding_plan_mismatch')
    return value
