"""Content-minimized frozen Judge analysis rows and offline metric arithmetic."""
from collections import Counter,defaultdict
import json
from datetime import datetime, timezone

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from agc_runtime.metrics_assessment import _object,_enum,_array,quality_counts
from agc_runtime.metrics_eval import validate_plan
from agc_runtime.metrics_eval_summary import PRIORITY
from agc_runtime.metrics_models import canonical,digest,validate_batch,instant
from agc_runtime.metrics_result_reader import summarize_execution_directory,verify_saved_step
from agc_runtime.metrics_history import validate_history


def _row_schema():
    opaque=dict(type='string',pattern=r'^id_[a-f0-9]{64}$')
    hash_value=dict(type='string',pattern=r'^[a-f0-9]{64}$')
    nullable=lambda s:dict(anyOf=[s,dict(type='null')])
    match=_object(certainty=_enum('required','uncertain'),verdict=_enum('retained','omitted','uncertain_match'))
    research=_object(relevance=_enum('specific_useful','partial_or_generic','no_supported_link','insufficient_evidence'),
        misleading=_enum('yes','no','unknown'),background_accuracy=_enum('supported','inaccurate','unknown'),
        issues=_array(_enum('inaccurate_background','unsupported_connection','hypothesis_as_fact')))
    return _object(case_id=opaque,scenario=_enum('collected','zero','research'),status=_enum(*PRIORITY),
        subject_digest=hash_value,stage=_enum('observation','preview','formal_memory','research_task','unknown'),
        result_digests=_array(hash_value),human_review=_enum('unreviewed'),
        candidate_verdicts=nullable(_array(_enum('supported','unsupported','unsuitable_durable','uncertain'))),
        required_matches=nullable(_array(match)),research=nullable(research))


def freeze_review(batch,plan,directory,*,resolve_case,evaluation_cutoff=None,ledger_directory=None,require_source_binding=False):
    batch=validate_batch(batch); plan=validate_plan(plan)
    if batch['batch_id']!=plan['batch_id']:
        raise ValueError('review_batch_mismatch')
    evaluation_cutoff = evaluation_cutoff or datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
    instant(evaluation_cutoff)
    summary=summarize_execution_directory(plan,directory,cutoff=evaluation_cutoff,resolve_case=resolve_case,
                                          ledger_directory=ledger_directory,require_source_binding=require_source_binding)
    rows=[]
    for case,observed in zip(plan['cases'],summary['cases']):
        row=dict(case_id=case['case_id'],scenario=case['scenario'],status=observed['status'],
            subject_digest=case['subject_digest'],stage='unknown',result_digests=[],human_review='unreviewed',
            candidate_verdicts=None,required_matches=None,research=None)
        if row['status']=='usable_judgment':
            entries=[e for e in plan['entries'] if e['case_id']==case['case_id']]
            verified=[verify_saved_step(plan,directory,e['entry_id'],resolve_case=resolve_case,
                                        ledger_directory=ledger_directory,require_source_binding=require_source_binding) for e in entries]
            for e,v in zip(entries,verified):
                selected=next(s for s in summary['steps'] if s['entry_id']==e['entry_id'])['last_finished']
                if v['result']['result_digest']!=selected['result_digest'] or v['status']!='usable_judgment':
                    raise ValueError('review_result_changed')
            row['stage']=verified[-1]['subject']['stage']
            row['result_digests']=[v['result']['result_digest'] for v in verified]
            outputs=[v['result']['assessment'] for v in verified]
            if case['scenario']=='research':
                row['research']={k:outputs[0][k] for k in ('relevance','misleading','background_accuracy','issues')}
            else:
                row['candidate_verdicts']=[c['verdict'] for c in outputs[1]['candidates']]
                matches={m['required_id']:m['verdict'] for m in outputs[1]['matches']}
                row['required_matches']=[dict(certainty=c['certainty'],verdict=matches[c['claim_id']]) for c in outputs[0]['claims']]
        rows.append(row)
    body=dict(schema_version='agc.metrics-review.v3',batch_id=batch['batch_id'],plan=plan,
        cutoff=batch['window']['cutoff'],evaluation_cutoff=evaluation_cutoff,
        execution_history=summary['steps'],
        rows=rows,invalid_records=summary['invalid_records'])
    body['review_id']='mr_'+digest(body)
    return validate_review(body,batch)


def validate_review(value,batch):
    batch=validate_batch(batch)
    try:
        fields={'schema_version','batch_id','plan','cutoff','rows','invalid_records','review_id'}
        if isinstance(value,dict) and value.get('schema_version') in ('agc.metrics-review.v2','agc.metrics-review.v3'):
            fields.add('evaluation_cutoff')
            instant(value.get('evaluation_cutoff'))
        if isinstance(value,dict) and value.get('schema_version')=='agc.metrics-review.v3':
            fields.add('execution_history')
        if not isinstance(value,dict) or set(value)!=fields:
            raise ValueError('review_fields_invalid')
        plan=validate_plan(value['plan'])
        if 'execution_history' in value:
            validate_history(plan,value['execution_history'],value['evaluation_cutoff'])
        if (value['schema_version'] not in ('agc.metrics-review.v1','agc.metrics-review.v2','agc.metrics-review.v3') or value['batch_id']!=batch['batch_id']
                or plan['batch_id']!=batch['batch_id'] or value['cutoff']!=batch['window']['cutoff']
                or type(value['invalid_records']) is not int or value['invalid_records']<0):
            raise ValueError('review_identity_invalid')
        rows=value['rows']
        if not isinstance(rows,list) or len(rows)!=len(plan['cases']):
            raise ValueError('review_cases_invalid')
        for row,case in zip(rows,plan['cases']):
            Draft202012Validator(_row_schema()).validate(row)
            if any(row[k]!=case[k] for k in ('case_id','scenario','subject_digest')):
                raise ValueError('review_case_mismatch')
            usable=row['status']=='usable_judgment'
            if usable:
                if row['stage']=='unknown' or len(row['result_digests'])!=(1 if row['scenario']=='research' else 2):
                    raise ValueError('review_results_missing')
                if row['scenario']=='research':
                    if row['research'] is None or row['candidate_verdicts'] is not None or row['required_matches'] is not None:
                        raise ValueError('research_projection_invalid')
                elif row['candidate_verdicts'] is None or row['required_matches'] is None or row['research'] is not None:
                    raise ValueError('quality_projection_invalid')
            elif any(row[k] is not None for k in ('candidate_verdicts','required_matches','research')):
                raise ValueError('unassessed_projection_has_verdicts')
        body={k:v for k,v in value.items() if k!='review_id'}
        if value['review_id']!='mr_'+digest(body):
            raise ValueError('review_digest_mismatch')
        return json.loads(canonical(value))
    except (ValidationError,KeyError,TypeError) as error:
        raise ValueError('review_invalid') from error


def review_metrics(value,batch):
    review=validate_review(value,batch)
    rows=review['rows']; states=dict(Counter(r['status'] for r in rows))
    m4=dict(planned_cases=len(rows),planned_steps=len(review['plan']['entries']),counts=states,
        usable_cases=states.get('usable_judgment',0),invalid_records=review['invalid_records'])
    m4['usable_ratio']=m4['usable_cases']/len(rows) if rows else None
    m2={}
    for scenario in ('collected','zero'):
        selected=[r for r in rows if r['scenario']==scenario]
        groups=defaultdict(list)
        for row in selected:
            if row['candidate_verdicts'] is not None:
                groups[(row['stage'],row['subject_digest'])].append(row)
        summaries=[]
        for (stage,version),items in sorted(groups.items()):
            candidates=[dict(verdict=v) for r in items for v in r['candidate_verdicts']]
            matches=[m for r in items for m in r['required_matches']]
            reference=dict(status='completed',claims=[dict(claim_id=str(i),certainty=m['certainty']) for i,m in enumerate(matches)])
            alignment=dict(status='completed',candidates=candidates,matches=[dict(required_id=str(i),verdict=m['verdict']) for i,m in enumerate(matches)])
            summaries.append(dict(stage=stage,subject_digest=version,**quality_counts(reference,alignment)))
        m2[scenario]=dict(sample_count=len(selected),unassessed_cases=sum(r['candidate_verdicts'] is None for r in selected),groups=summaries)
    research=[r for r in rows if r['scenario']=='research']
    m5=dict(sample_count=len(research),unassessed_cases=sum(r['research'] is None for r in research),
        relevance=dict(Counter(r['research']['relevance'] for r in research if r['research'] is not None)),
        misleading=dict(Counter(r['research']['misleading'] for r in research if r['research'] is not None)),
        human_review=dict(Counter(r['human_review'] for r in research)))
    return dict(M2=m2,M4=m4,M5=m5)
