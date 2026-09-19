from test_metrics_batch import START, END, api, batch, event


def compute(**kwargs):
    return api('metrics_compute').compute_metrics(batch(**kwargs))


def test_cycle_cohort_dedup_conflict_and_unobserved():
    start = event()
    rows = [start, start, event('e2', kind='trace.root.completed'),
            event('e3', trace='t2'), event('e4', trace='t2', kind='trace.root.failed'),
            event('e5', trace='t2', kind='trace.root.completed'), event('e6', trace='t3')]
    metric = compute(events=rows)['M1']
    assert metric['counts'] == {'completed': 1, 'state_conflict': 1, 'terminal_unobserved': 1}
    assert metric['sample_count'] == 3
    assert metric['denominator'] is None
    assert metric['duplicate_events'] == 1


def test_cross_window_terminal_does_not_inflate_start_cohort():
    rows = [event(time='2026-09-01T00:00:00Z'), event('end', kind='trace.root.completed'),
            event('orphan', trace='orphan', kind='trace.root.failed')]
    metric = compute(events=rows)['M1']
    assert metric['sample_count'] == 0
    assert metric['incomplete_records'] == 1
    assert metric['terminal_events_in_window'] == 2


def test_cutoff_can_observe_completion_after_window_end():
    value = api('metrics_models').freeze_batch(start=START, end=END, cutoff='2026-09-11T00:00:00+08:00',
        events=[event(), event('end', kind='trace.root.completed', time='2026-09-10T01:00:00+08:00')])
    metric = api('metrics_compute').compute_metrics(value)['M1']
    assert metric['counts'] == {'completed': 1}
    assert metric['terminal_events_in_window'] == 0


def test_ten_items_nine_traces_are_not_full_coverage():
    rows = [event('i' + str(i), trace='t' + str(min(i, 8)), kind='agc.capture.item.completed',
                  outcome='zero', evidence_ref={'provider': 'agc', 'kind': 'capture-item', 'ref': 'r' + str(i), 'digest': 'sha256:' + 'a'*64}) for i in range(10)]
    receipts = [dict(receipt_id='r'+str(i), updated_at=START, status='complete', redacted_by_forget=False) for i in range(10)]
    value = compute(events=rows, receipts=receipts)['M3']
    assert value['linked_items'] == 10
    assert value['linked_traces'] == 9
    assert value['counts'] == {'unchecked': 10}
    assert value['denominator'] is None


def test_zero_is_not_quality_success_and_empty_eval_is_not_coverage():
    value = compute(events=[event(kind='agc.capture.item.completed', outcome='zero')])
    assert value['M2']['status'] == value['M5']['status'] == 'not_measured'
    assert value['M4']['denominator'] is None
    assert value['M4']['status'] == 'unavailable'
    assert all(m['method']['limitations'] for m in value.values())


def test_conflicting_duplicate_event_id_does_not_silently_win():
    value = compute(events=[event(), event(kind='trace.root.failed')])['M1']
    assert value['conflicting_event_ids'] == 1
    assert value['counts'] == {'state_conflict': 1}


def test_known_empty_sources_are_empty_not_unavailable():
    value = compute(events=[], receipts=[], evaluations=[])
    assert all(value[k]['status'] == 'empty' for k in ('M1', 'M3', 'M4'))


def test_receipt_conflict_is_reported_not_last_wins():
    receipt = dict(receipt_id='r1', updated_at=START, status='complete', redacted_by_forget=False)
    value = compute(receipts=[receipt, {**receipt, 'status':'failed'}])['M3']
    assert value['counts'] == {'conflict': 1}
    assert value['rows'][0]['verification'] == 'conflict'


def test_future_terminal_beyond_cutoff_does_not_close_cycle():
    value = compute(events=[event(), event('end',kind='trace.root.completed',time='2026-09-12T00:00:00Z')])['M1']
    assert value['counts'] == {'terminal_unobserved':1}


def test_conflicting_event_id_across_traces_is_flagged_on_both():
    value = compute(events=[event(), event(trace='another')])['M1']
    assert value['counts'] == {'state_conflict':2}


def test_failure_codes_are_categories_not_inferred_root_causes():
    value = compute(events=[event(), event('failure',kind='trace.root.failed',error={'type':'capture_busy','message':'PRIVATE'})])['M1']
    assert value['failure_codes'] == {'capture_busy':1}


def test_invalid_only_input_not_presented_as_clean_empty():
    value = compute(events=[event(time='invalid')])['M1']
    assert value['status'] == 'partial'
    assert value['invalid_records'] == 1
