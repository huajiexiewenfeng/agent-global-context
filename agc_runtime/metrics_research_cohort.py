"""Freeze an explicitly scoped frontend-task sample, never a Recall-derived one.

Caller classifications are not quality judgments or verified provenance. This
module performs no discovery, content reads, classification or model invocation.
"""
import json
import re
from collections import Counter

from agc_runtime.metrics_eval import _hash, _opaque
from agc_runtime.metrics_models import canonical, digest, instant, utc, validate_batch

TASK_FIELDS = {'task_ref','revision','delivered_at','decision','reason','evidence_status'}
REASONS = {
    'include': {'research_connection_request'},
    'exclude': {'not_research_connection','background_task','not_delivered'},
    'ambiguous': {'task_boundary_unclear','intent_unclear'},
}
OUTCOMES = ('selected','sample_cap','excluded','ambiguous','evidence_unavailable','outside_window')


def _classifier(value):
    if (not isinstance(value,dict) or
            set(value)!={'method','rule_version','configuration_digest','authorization_ref'}):
        raise ValueError('research_classifier_invalid')
    if (value['method'] not in ('llm','human') or not isinstance(value['rule_version'],str)
            or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,127}',value['rule_version'])):
        raise ValueError('research_classifier_invalid')
    if value['method']=='llm':
        _hash(value['configuration_digest']); _opaque(value['authorization_ref'])
    elif value['configuration_digest'] is not None or value['authorization_ref'] is not None:
        raise ValueError('research_human_classifier_fields')
    return json.loads(canonical(value))


def freeze_research_cohort(batch,tasks,*,classifier):
    checked=validate_batch(batch)
    classification=_classifier(classifier)
    if not isinstance(tasks,list) or len(tasks)>10000:
        raise ValueError('research_tasks_invalid')
    rows=[]; seen=set()
    for raw in tasks:
        if not isinstance(raw,dict) or set(raw)!=TASK_FIELDS:
            raise ValueError('research_task_fields')
        _opaque(raw['task_ref']); _hash(raw['revision'])
        if raw['task_ref'] in seen:
            # A revision is not an independent task. Resolve duplicates upstream,
            # rather than silently weighting a frequently revised task twice.
            raise ValueError('research_duplicate_task')
        seen.add(raw['task_ref'])
        if (not isinstance(raw['decision'],str) or raw['decision'] not in REASONS
                or not isinstance(raw['reason'],str) or raw['reason'] not in REASONS[raw['decision']]
                or raw['evidence_status'] not in ('available','unavailable','unknown')):
            raise ValueError('research_task_classification')
        rows.append(dict(raw,delivered_at=utc(raw['delivered_at'])))
    rows.sort(key=lambda r:(instant(r['delivered_at']),r['task_ref']))
    start=instant(checked['window']['start']); end=instant(checked['window']['end'])
    selected=[]
    for row in rows:
        if not start<=instant(row['delivered_at'])<end:
            outcome='outside_window'
        elif row['decision']=='exclude':
            outcome='excluded'
        elif row['decision']=='ambiguous':
            outcome='ambiguous'
        elif row['evidence_status']!='available':
            outcome='evidence_unavailable'
        elif len(selected)>=5:
            outcome='sample_cap'
        else:
            outcome='selected'; selected.append(row['task_ref'])
        row['selection_status']=outcome
    counts=Counter(r['selection_status'] for r in rows)
    body=dict(schema_version='agc.metrics-research-cohort.v1',batch_id=checked['batch_id'],
              window=checked['window'],classifier=classification,
              classification_provenance='caller_supplied_unverified',
              coverage='selected_frontend_tasks_not_full_population',
              sampling_rule='delivered_at_then_task_ref_first_5_v1',
              status='selected_cases' if selected else 'no_selected_cases',
              tasks=rows,selected_task_refs=selected,counts={k:counts[k] for k in OUTCOMES})
    body['cohort_id']='mrco_'+digest(body)
    return json.loads(canonical(body))


def validate_research_cohort(batch,value):
    try:
        tasks=[]
        for row in value['tasks']:
            if set(row)!=TASK_FIELDS|{'selection_status'}:
                raise ValueError('research_cohort_task_fields')
            tasks.append({k:row[k] for k in TASK_FIELDS})
        expected=freeze_research_cohort(batch,tasks,classifier=value['classifier'])
        if canonical(expected)!=canonical(value):
            raise ValueError('research_cohort_mismatch')
        return expected
    except (KeyError,TypeError,AttributeError) as error:
        raise ValueError('research_cohort_invalid') from error
