"""M4 plan/attempt arithmetic, with explicit external result verification.

The verifier must check result identity, schema, dependency, execution receipt
and live evidence. Stored completion or a result digest alone is never usable.
"""
from collections import Counter, defaultdict
import json
import re

from agc_runtime.metrics_eval import validate_plan
from agc_runtime.metrics_models import canonical, instant

FIELDS={'attempt_id','entry_id','plan_id','started_at','finished_at','status','result_digest','dependency_result_digest'}
PRIORITY=('conflict','evaluation_error','insufficient_evidence','in_progress','unchecked','not_run','usable_judgment')


def summarize_evaluations(plan,attempts,*,cutoff,verify_result=None):
    checked=validate_plan(plan)
    deadline=instant(cutoff)
    entries={e['entry_id']:e for e in checked['entries']}
    groups=defaultdict(list)
    invalid=future=duplicates=0
    for row in attempts:
        try:
            if not isinstance(row,dict) or set(row)!=FIELDS:
                raise ValueError('invalid_attempt')
            if (not re.fullmatch(r'mea_[a-f0-9]{64}',row['attempt_id'])
                    or row['plan_id']!=checked['plan_id'] or row['entry_id'] not in entries):
                raise ValueError('foreign_attempt')
            start=instant(row['started_at'])
            finish=instant(row['finished_at']) if row['finished_at'] is not None else None
            if row['status'] not in ('in_progress','completed','evaluation_error'):
                raise ValueError('invalid_status')
            if (row['status']=='in_progress') != (finish is None) or (finish and finish<start):
                raise ValueError('invalid_attempt_times')
            if row['status']=='completed':
                if not isinstance(row['result_digest'],str) or not re.fullmatch(r'[a-f0-9]{64}',row['result_digest']):
                    raise ValueError('result_identity_missing')
            elif row['result_digest'] is not None:
                raise ValueError('unexpected_result')
            dependency=row['dependency_result_digest']
            if dependency is not None and (not isinstance(dependency,str) or not re.fullmatch(r'[a-f0-9]{64}',dependency)):
                raise ValueError('invalid_dependency')
            if entries[row['entry_id']]['depends_on'] is None and dependency is not None:
                raise ValueError('unexpected_dependency')
            if start>deadline:
                future+=1
                continue
            groups[row['attempt_id']].append(json.loads(canonical(row)))
        except (ValueError,TypeError,KeyError):
            invalid+=1
    by_entry=defaultdict(list)
    conflicts=set()
    for rows in groups.values():
        unique=list({canonical(row):row for row in rows}.values())
        duplicates+=len(rows)-len(unique)
        if len(unique)>1:
            conflicts.update(row['entry_id'] for row in unique)
        for row in unique:
            by_entry[row['entry_id']].append(row)

    def observation(entry,row):
        unfinished=row['finished_at'] is None or instant(row['finished_at'])>deadline
        status='in_progress' if unfinished else 'evaluation_error'
        if not unfinished and row['status']=='completed':
            status='unchecked'
            if verify_result is not None:
                # Detached inputs prevent a verifier mutating frozen metadata.
                try:
                    status=verify_result(json.loads(canonical(entry)),json.loads(canonical(row)))
                except Exception:
                    status='unchecked'
                if status not in ('usable_judgment','insufficient_evidence','evaluation_error','unchecked','conflict'):
                    status='unchecked'
        return dict(attempt_id=row['attempt_id'],started_at=row['started_at'],
            finished_at=None if unfinished else row['finished_at'],status=status,
            result_digest=None if unfinished else row['result_digest'],
            dependency_result_digest=row['dependency_result_digest'])

    steps=[]
    for entry in checked['entries']:
        raw=sorted(by_entry[entry['entry_id']],key=lambda r:(instant(r['started_at']),r['attempt_id']))
        observed=[observation(entry,row) for row in raw] if entry['entry_id'] not in conflicts else []
        ended=[row for row in observed if row['status']!='in_progress']
        unfinished=sum(row['status']=='in_progress' for row in observed)
        status=('conflict' if entry['entry_id'] in conflicts else 'in_progress' if unfinished
                else ended[-1]['status'] if ended else 'not_run')
        steps.append(dict(entry_id=entry['entry_id'],case_id=entry['case_id'],scenario=entry['scenario'],step=entry['step'],
            status=status,attempt_count=len({r['attempt_id'] for r in raw}),unfinished_count=unfinished,
            first=observed[0] if observed else None,last_finished=ended[-1] if ended else None,
            attempts=observed))
    cases=[]
    for case in checked['cases']:
        case_steps=[row for row in steps if row['case_id']==case['case_id']]
        statuses={row['status'] for row in case_steps}
        status=next(s for s in PRIORITY if s in statuses)
        if status=='usable_judgment':
            selected={row['entry_id']:row['last_finished'] for row in case_steps}
            for row in case_steps:
                dependency=entries[row['entry_id']]['depends_on']
                if dependency is not None and (selected[row['entry_id']]['dependency_result_digest']
                                               != selected[dependency]['result_digest']):
                    status='conflict'
        cases.append(dict(case_id=case['case_id'],scenario=case['scenario'],status=status))
    counts=dict(Counter(row['status'] for row in cases))
    usable=counts.get('usable_judgment',0)
    matrix={scenario:dict(Counter(row['status'] for row in cases if row['scenario']==scenario))
            for scenario in sorted({c['scenario'] for c in cases})}
    return dict(plan_id=checked['plan_id'],cutoff=cutoff,planned_cases=len(cases),planned_steps=len(steps),
        usable_cases=usable,usable_ratio=usable/len(cases) if cases else None,counts=counts,
        scenario_status=matrix,steps=steps,cases=cases,invalid_records=invalid,
        future_attempts=future,duplicate_records=duplicates,
        limitation='Technical usability depends on external verification, not Judge accuracy or improvement evidence.')
