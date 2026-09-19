import importlib

from test_metrics_eval import plan

CUTOFF='2026-09-11T12:00:00Z'


def api():
    return importlib.import_module('agc_runtime.metrics_eval_summary')


def attempt(p,index=0,ident='a',status='completed',**changes):
    value=dict(attempt_id='mea_'+ident*64,entry_id=p['entries'][index]['entry_id'],
        plan_id=p['plan_id'],started_at='2026-09-11T10:00:00Z',finished_at='2026-09-11T11:00:00Z',
        status=status,result_digest='f'*64 if status=='completed' else None)
    value['dependency_result_digest']='f'*64 if index==1 and status=='completed' else None
    value.update(changes)
    return value


def summarize(p,rows,verify=lambda entry,row:'usable_judgment'):
    return api().summarize_evaluations(p,rows,cutoff=CUTOFF,verify_result=verify)


def test_planned_cases_and_steps_are_not_confused():
    p=plan()
    result=summarize(p,[])
    assert result['planned_cases']==1 and result['planned_steps']==2
    assert result['counts']=={'not_run':1}
    assert result['usable_ratio']==0


def test_two_m2_steps_required_for_case_coverage():
    p=plan()
    assert summarize(p,[attempt(p)])['usable_cases']==0
    result=summarize(p,[attempt(p),attempt(p,1,'b')])
    assert result['usable_cases']==1 and result['usable_ratio']==1.0


def test_retry_does_not_erase_first_error_and_retransmission_deduped():
    p=plan()
    first=attempt(p,status='evaluation_error')
    last=attempt(p,ident='b',started_at='2026-09-11T11:01:00Z',finished_at='2026-09-11T11:30:00Z')
    result=summarize(p,[last,first,last])
    row=result['steps'][0]
    assert row['first']['status']=='evaluation_error'
    assert row['last_finished']['status']=='usable_judgment'
    assert row['attempt_count']==2
    assert result['duplicate_records']==1


def test_conflicting_attempt_is_not_last_wins():
    p=plan(); first=attempt(p)
    conflict=dict(first,status='evaluation_error',result_digest=None)
    result=summarize(p,[first,conflict])
    assert result['steps'][0]['status']=='conflict'
    assert result['counts']=={'conflict':1}


def test_cutoff_keeps_unfinished_and_excludes_future_start():
    p=plan()
    rows=[attempt(p,finished_at='2026-09-11T13:00:00Z'),
          attempt(p,1,'b',started_at='2026-09-11T13:00:00Z',finished_at='2026-09-11T14:00:00Z')]
    result=summarize(p,rows)
    assert result['steps'][0]['status']=='in_progress'
    assert result['steps'][0]['unfinished_count']==1
    assert result['steps'][1]['status']=='not_run'
    assert result['future_attempts']==1


def test_completed_without_verification_is_not_usable():
    p=plan()
    result=summarize(p,[attempt(p),attempt(p,1,'b')],verify=None)
    assert result['counts']=={'unchecked':1}
    assert result['usable_cases']==0


def test_evidence_insufficient_separate_from_error():
    p=plan()
    result=summarize(p,[attempt(p)],verify=lambda e,r:'insufficient_evidence')
    assert result['counts']=={'insufficient_evidence':1}


def test_bad_record_visible_and_empty_plan_not_applicable():
    p=plan()
    result=summarize(p,[dict(attempt(p),started_at='bad')])
    assert result['invalid_records']==1
    assert result['counts']=={'not_run':1}
    assert summarize(plan([]),[])['usable_ratio'] is None


def test_rerun_reference_cannot_pair_with_old_alignment():
    p=plan()
    first=attempt(p,result_digest='e'*64)
    second=attempt(p,1,'b')
    result=summarize(p,[first,second])
    assert result['usable_cases']==0
    assert result['counts']=={'conflict':1}


def test_latest_unfinished_retry_keeps_previous_result_visible():
    p=plan()
    first=attempt(p)
    later=attempt(p,ident='b',status='in_progress',started_at='2026-09-11T11:30:00Z',finished_at=None)
    result=summarize(p,[first,later])
    step=result['steps'][0]
    assert step['status']=='in_progress'
    assert step['last_finished']['status']=='usable_judgment'
    assert step['unfinished_count']==1
