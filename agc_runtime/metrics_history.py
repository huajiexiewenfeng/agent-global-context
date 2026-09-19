"""Strict content-free frozen execution history projections."""
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
from agc_runtime.metrics_assessment import _object,_enum,_array
from agc_runtime.metrics_eval_summary import PRIORITY
from agc_runtime.metrics_models import instant,canonical


def validate_history(plan,history,cutoff):
    nullable=lambda schema:dict(anyOf=[schema,dict(type='null')])
    text=dict(type='string')
    sha=dict(type='string',pattern='^[a-f0-9]{64}$')
    observation=_object(attempt_id=dict(type='string',pattern='^mea_[a-f0-9]{64}$'),
        started_at=text,finished_at=nullable(text),status=_enum(*PRIORITY),
        result_digest=nullable(sha),dependency_result_digest=nullable(sha))
    schema=_object(entry_id=text,case_id=text,scenario=text,step=text,status=_enum(*PRIORITY),
        attempt_count=dict(type='integer',minimum=0),unfinished_count=dict(type='integer',minimum=0),
        first=nullable(observation),last_finished=nullable(observation),attempts=_array(observation))
    if not isinstance(history,list) or len(history)!=len(plan['entries']):
        raise ValueError('history_entries_invalid')
    try:
        for row,entry in zip(history,plan['entries']):
            Draft202012Validator(schema).validate(row)
            if any(row[k]!=entry[k] for k in ('entry_id','case_id','scenario','step')):
                raise ValueError('history_entry_mismatch')
            attempts=row['attempts']
            for attempt in attempts:
                start=instant(attempt['started_at'])
                finish=instant(attempt['finished_at']) if attempt['finished_at'] else None
                if start>instant(cutoff) or (finish and (finish<start or finish>instant(cutoff))):
                    raise ValueError('history_time_invalid')
                if (attempt['status']=='in_progress')!=(finish is None):
                    raise ValueError('history_terminal_invalid')
            if row['status']=='conflict':
                if attempts or row['first'] is not None or row['last_finished'] is not None:
                    raise ValueError('history_conflict_projection_invalid')
                continue
            ordered=sorted(attempts,key=lambda a:(instant(a['started_at']),a['attempt_id']))
            ended=[a for a in attempts if a['finished_at'] is not None]
            if (canonical(ordered)!=canonical(attempts)
                    or row['attempt_count']!=len({a['attempt_id'] for a in attempts})
                    or len(attempts)!=row['attempt_count']
                    or row['unfinished_count']!=len(attempts)-len(ended)
                    or row['first']!=(attempts[0] if attempts else None)
                    or row['last_finished']!=(ended[-1] if ended else None)):
                raise ValueError('history_summary_mismatch')
    except ValidationError as error:
        raise ValueError('history_schema_invalid') from error
