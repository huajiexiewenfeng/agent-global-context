"""Deterministic P1 metrics; no model client, memory writes or live source reads."""
from collections import Counter, defaultdict

from agc_runtime.metrics_models import canonical, instant, validate_batch

TITLES = {'M1':'运行健康', 'M2':'记忆质量', 'M3':'Trace 可追溯性', 'M4':'Eval 可用与覆盖', 'M5':'研究任务帮助'}
IDS = {'M1':'agc.health.stage_status', 'M2':'agc.quality.judge_claims',
       'M3':'agc.trace.evidence_coverage', 'M4':'agc.eval.usability_coverage', 'M5':'agc.value.research_relevance'}
LIMITS = {
    'M1':'仅统计可见 Capture 根运行。Trace 会省略无活动周期，且开始事件在周期结束时补发；缺独立请求总体，不计算全量成功率。终态未观测不代表仍运行。审查、保存、Recall 尚缺对应读取适配。',
    'M2':'P1 不读取原始输入或调用 Judge。正常 zero 不等于质量好；尚无错误保留或遗漏的确定分母。',
    'M3':'按当前 receipt 更新时间选取至多 10 项；这是快照线索，不是历史完整业务总体。只匹配标识，没有解析源证据或核验 digest/实现版本，全部仍为 unchecked。',
    'M4':'只统计属于 AGC Capture 的已存结果元数据。没有冻结计划、证据或输出全文核验，stored pass/fail 不代表判断技术可用，更不代表准确率。',
    'M5':'尚无独立研究任务样本和当时背景证据，未运行 Judge。无新旧/有无 AGC 对照，不作增量收益或满意度结论。',
}


def _base(key, batch):
    return dict(metric_id=IDS[key], title=TITLES[key], status='not_measured', counts={},
        sample_count=0, numerator=None, denominator=None, unknown_count=0, rows=[],
        method=dict(version='1.1', layer='程序事实' if key in ('M1','M3','M4') else 'Judge 初评（尚未运行）',
            window=batch['window'], source={'M1':'Trace events','M2':'安全输入/被评版本（未读取）',
                'M3':'Capture receipt 当前快照 + Trace','M4':'Eval results 元数据','M5':'独立研究任务证据（未读取）'}[key],
            population={'M1':'窗口内开始的可见 Capture 根运行', 'M2':'未建立内容初评样本',
                'M3':'读取时更新时间在窗口内的 receipt', 'M4':'窗口内结束的已存 AGC Capture Eval 结果',
                'M5':'未建立独立研究任务样本'}[key],
            formula='按状态计数；当前无可信比例分母，不显示百分比。',
            sampling='M3 按更新时间与不透明 ID 排序取前 10 项；其余读取记录按窗口过滤。',
            deduplication='事件按 event_id；运行按 trace_id + span_id；Eval 按 result_id。冲突不任取最后结果。',
            missing='缺失、未检查、不可计算、未评估分别显示；无用户反馈不视为认可。',
            exclusions='批次 excluded 保存被排除记录的摘要与原因；来源解析错误数量另列。',
            reproduction='使用冻结 batch.json 和相同转换版本复算；不重新读取源数据库。',
            limitations=LIMITS[key]))


def compute_metrics(value):
    batch = validate_batch(value)
    lower, upper = map(instant, (batch['window']['start'], batch['window']['end']))
    in_window = lambda row: lower <= instant(row['timestamp']) < upper
    metrics = {key: _base(key, batch) for key in TITLES}
    for key, source_name, collection in (('M1','trace','events'),('M3','receipts','receipts'),('M4','eval','evaluations')):
        source = next(s for s in batch['sources'] if s['name'] == source_name)
        metrics[key]['invalid_records'] = source['invalid_records'] + sum(
            r['source'] == collection and r['reason'] == 'invalid_record' for r in batch['excluded'])
    events_by_id = defaultdict(list)
    for row in batch['events']:
        events_by_id[row['event_id']].append(row)
    unique, conflict_ids = [], set()
    for identifier, rows in events_by_id.items():
        variants = {canonical(row): row for row in rows}
        unique.extend(variants.values())
        if len(variants) > 1:
            conflict_ids.add(identifier)
    groups = defaultdict(list)
    items = []
    for row in unique:
        if row['event_type'] == 'agc.capture.item.completed':
            if in_window(row):
                items.append(row)
        else:
            groups[(row['trace_id'], row['span_id'])].append(row)
    m1 = metrics['M1']
    m1.update(status='partial', duplicate_events=len(batch['events'])-len(unique),
        conflicting_event_ids=len(conflict_ids), incomplete_records=0,
        terminal_events_in_window=0, completed_item_events=len(items),
        item_outcomes=dict(sorted(Counter(r['outcome'] for r in items).items())))
    failure_codes = Counter()
    for (trace, span), rows in sorted(groups.items()):
        starts = [r for r in rows if r['event_type'] == 'trace.root.started']
        ends = [r for r in rows if r['event_type'] != 'trace.root.started']
        m1['terminal_events_in_window'] += sum(in_window(r) for r in ends)
        if not starts:
            m1['incomplete_records'] += int(any(in_window(r) for r in ends))
            continue
        first = min(starts, key=lambda r: instant(r['timestamp']))
        if not in_window(first):
            continue
        states = {r['event_type'] for r in ends}
        conflict = (len(states) > 1 or any(r['event_id'] in conflict_ids for r in rows)
                    or len({r['timestamp'] for r in starts}) > 1
                    or any(instant(r['timestamp']) < instant(first['timestamp']) for r in ends))
        status = 'state_conflict' if conflict else ('terminal_unobserved' if not ends else
            ('failed' if 'trace.root.failed' in states else 'completed'))
        m1['rows'].append(dict(trace_id=trace, span_id=span, status=status))
        if status == 'failed':
            failure_codes.update({r['error_code'] for r in ends})
    m1['failure_codes'] = dict(sorted(failure_codes.items()))
    m1['counts'] = dict(sorted(Counter(r['status'] for r in m1['rows']).items()))
    m1['sample_count'] = len(m1['rows'])
    m1['unknown_count'] = sum(m1['counts'].get(k, 0) for k in ('terminal_unobserved', 'state_conflict')) + m1['incomplete_records']
    trace_source = next(s for s in batch['sources'] if s['name'] == 'trace')
    if trace_source['status'] not in ('available','provided','partial'):
        m1['status'] = 'unavailable'
    elif not batch['events'] and trace_source['status'] != 'partial' and not m1['invalid_records']:
        m1['status'] = 'empty'

    # Independent but explicitly limited *current* receipt frame, not a claim
    # that an event-store-only denominator measures missing trace coverage.
    m3 = metrics['M3']
    receipts = defaultdict(list)
    for row in batch['receipts']:
        receipts[row['receipt_id']].append(row)
    sample = sorted(receipts.values(), key=lambda rows: (min(instant(r['timestamp']) for r in rows), rows[0]['receipt_id']))[:10]
    traces = set()
    for variants in sample:
        receipt = variants[0]
        conflict = len({canonical(r) for r in variants}) > 1
        matches = [r for r in items if r['receipt_id'] == receipt['receipt_id']]
        traces.update(r['trace_id'] for r in matches)
        m3['rows'].append(dict(receipt_id=receipt['receipt_id'], linkage='matched' if matches else 'not_observed',
            verification='conflict' if conflict else 'unchecked', linked_events=len(matches)))
    m3.update(status='partial' if sample else 'unavailable', sample_count=len(sample),
        counts=dict(sorted(Counter(r['verification'] for r in m3['rows']).items())), unknown_count=len(sample),
        linked_items=sum(r['linkage']=='matched' for r in m3['rows']), linked_traces=len(traces))
    receipt_source = next(s for s in batch['sources'] if s['name'] == 'receipts')
    if not sample and receipt_source['status'] in ('available','provided','partial'):
        m3['status'] = 'partial' if m3['invalid_records'] else 'empty'

    m4 = metrics['M4']
    results = defaultdict(list)
    for row in batch['evaluations']:
        results[row['result_id']].append(row)
    for identifier, rows in sorted(results.items()):
        status = 'conflict' if len({canonical(r) for r in rows}) > 1 else 'stored_' + rows[0]['status'] + '_unchecked'
        m4['rows'].append(dict(result_id=identifier, status=status))
    m4.update(status='partial' if results else 'unavailable', sample_count=len(results),
        unknown_count=len(results), counts=dict(sorted(Counter(r['status'] for r in m4['rows']).items())))
    eval_source = next(s for s in batch['sources'] if s['name'] == 'eval')
    if not results and eval_source['status'] in ('available','provided','partial'):
        m4['status'] = 'partial' if m4['invalid_records'] else 'empty'
    if 'operations' in batch:
        _apply_operations(batch, metrics, unique, conflict_ids)
    if 'business' in batch:
        _apply_business(batch,metrics)
    return metrics


def _apply_business(batch,metrics):
    source=next(s for s in batch['sources'] if s['name']=='business')
    lower,upper=map(instant,(batch['window']['start'],batch['window']['end']))
    groups=defaultdict(list)
    for row in batch['business']:
        groups[row['attempt_id']].append(row)
    stages=defaultdict(Counter)
    rows=[]
    orphan=0
    for identity,raw in sorted(groups.items()):
        unique=list({canonical(r):r for r in raw}.values())
        starts=sorted((r for r in unique if r['phase']=='started'),key=lambda r:instant(r['timestamp']))
        ends=[r for r in unique if r['phase']=='finished']
        if not starts:
            orphan+=int(any(lower<=instant(r['timestamp'])<upper for r in ends))
            continue
        start=starts[0]
        if not lower<=instant(start['timestamp'])<upper:
            continue
        conflict=len(starts)>1 or len(ends)>1 or any(
            any(r[k]!=start[k] for k in ('tool','action','stage','implementation_version','observation_refs','batch_ref','request_object_ref'))
            or instant(r['timestamp'])<instant(start['timestamp']) or r['start_status']!='recorded' for r in ends)
        status='state_conflict' if conflict else 'terminal_unobserved' if not ends else ends[0]['response_status']
        stages[start['stage']][status]+=1
        end=ends[0] if len(ends)==1 else None
        rows.append(dict(attempt_id=identity,stage=start['stage'],status=status,
            write_status=end['write_status'] if end and not conflict else 'unknown',
            review_receipt_status=end['review_receipt_status'] if end and not conflict else 'unknown',
            returned_objects=len(end['objects']) if end and not conflict else None,
            actual_use='unknown',preview_delivery='unknown'))
    m1=metrics['M1']
    m1.update(stage_health={k:dict(sorted(v.items())) for k,v in sorted(stages.items())},
        business_rows=rows,business_orphan_terminals=orphan,business_source_status=source['status'],
        business_invalid_records=source['invalid_records']+sum(r['source']=='business' and r['reason']=='invalid_record' for r in batch['excluded']))
    m1['method']['source']+='；独立 read/write/notice 服务边界记录（分组展示，不混加）'
    m1['method']['limitations']+=' 服务分组 accepted 仅是响应状态，不证明发生新写入、实际使用或预览交付；版本摘要仅标识返回表示。'


def _apply_operations(batch, metrics, events, conflict_ids):
    """Use the independent start cohort, never infer it from surviving Trace."""
    lower, upper = map(instant, (batch['window']['start'], batch['window']['end']))
    source = next(s for s in batch['sources'] if s['name'] == 'operations')
    trace_source = next(s for s in batch['sources'] if s['name'] == 'trace')
    groups = defaultdict(list)
    for row in batch['operations']:
        groups[row['attempt_id']].append(row)
    cohort, orphan_count, duplicates = [], 0, 0
    failures = Counter()
    for identity, raw in sorted(groups.items()):
        rows = list({canonical(r):r for r in raw}.values())
        duplicates += len(raw) - len(rows)
        starts = sorted((r for r in rows if r['phase'] == 'started'), key=lambda r: instant(r['timestamp']))
        ends = [r for r in rows if r['phase'] == 'finished']
        if not starts:
            orphan_count += int(any(lower <= instant(r['timestamp']) < upper for r in ends))
            continue
        start = starts[0]
        if not lower <= instant(start['timestamp']) < upper:
            continue
        comparable = ('trace_id','span_id','action','implementation_version')
        conflict = len(starts) > 1 or len(ends) > 1 or any(
            any(r[k] != start[k] for k in comparable)
            or instant(r['timestamp']) < instant(start['timestamp'])
            or r['start_status'] != 'recorded' for r in ends)
        status = 'state_conflict' if conflict else ends[0]['outcome'] if ends else 'terminal_unobserved'
        end = ends[0] if len(ends) == 1 else None
        if status == 'failed':
            failures[start['error_code'] if end is None else end['error_code']] += 1
        cohort.append(dict(attempt_id=identity, trace_id=start['trace_id'], span_id=start['span_id'],
            timestamp=start['timestamp'], status=status, started=start, finished=end))
    m1, m3 = metrics['M1'], metrics['M3']
    m1['trace_cohort'] = dict(rows=m1['rows'], counts=m1['counts'], sample_count=m1['sample_count'],
                             failure_codes=m1['failure_codes'])
    invalid = source['invalid_records'] + sum(r['source'] == 'operations' and r['reason'] == 'invalid_record' for r in batch['excluded'])
    usable = source['status'] in ('available','provided','partial')
    m1.update(rows=cohort, counts=dict(sorted(Counter(r['status'] for r in cohort).items())),
        sample_count=len(cohort), unknown_count=sum(r['status'] in ('state_conflict','terminal_unobserved') for r in cohort) + orphan_count,
        invalid_records=invalid, orphan_business_terminals=orphan_count, duplicate_operation_records=duplicates,
        failure_codes=dict(sorted(failures.items())),
        status='unavailable' if not usable else 'partial' if cohort or invalid or orphan_count or source['status'] == 'partial' else 'empty')
    m1['method'].update(source='独立 Capture CLI 尝试清单；Trace 作为单独对照',
        population='窗口内开始的独立 Capture CLI 尝试',
        deduplication='按 attempt_id + phase 分组；完全重复去重，字段或终态冲突不任取最后记录。',
        sampling='所有窗口内开始的已记录业务尝试；截止前终态用于闭合，孤立终态另列。',
        limitations='仅覆盖已启用独立记录的 CLI run/cycle 边界。业务记录失败可能漏项，不能代表所有进程。completed 表示周期返回，不代表所有 item 成功或记忆有效。审查、保存、Recall 尚未接入。')
    m3['receipt_linkage'] = dict(rows=m3['rows'], counts=m3['counts'], sample_count=m3['sample_count'])
    m3.update(rows=[], counts={}, linked_items=0, linked_traces=0, invalid_records=invalid)
    sample = sorted(cohort, key=lambda r:(instant(r['timestamp']),r['attempt_id']))[:10]
    linked = set()
    trace_usable = trace_source['status'] in ('available','provided','partial')
    trace_complete_read = trace_source['status'] in ('available','provided')
    # Source or projection parse errors prevent a strong "not observed" result.
    trace_complete_read = trace_complete_read and not trace_source['invalid_records'] and not any(
        r['source'] == 'events' and r['reason'] == 'invalid_record' for r in batch['excluded'])
    for item in sample:
        matches = [r for r in events if (r['trace_id'],r['span_id']) == (item['trace_id'],item['span_id'])]
        starts = [r for r in matches if r['event_type'] == 'trace.root.started']
        ends = [r for r in matches if r['event_type'] in ('trace.root.completed','trace.root.failed')]
        fields = dict(identity='matched' if matches else 'not_observed' if trace_complete_read else 'unchecked',
            start='matched' if len(starts) == 1 and instant(starts[0]['timestamp']) == instant(item['timestamp']) else 'unchecked',
            terminal='unchecked', implementation_version='unchecked', configuration_identity='unknown', result_reference='unchecked')
        verification = 'unchecked'
        if item['status'] == 'state_conflict' or any(r['event_id'] in conflict_ids for r in matches):
            verification = 'conflict'
        elif trace_usable and matches:
            verification = 'partial'
            linked.add(item['trace_id'])
            if len(starts)==1 and fields['start']=='matched' and starts[0].get('implementation_version') is not None:
                fields['implementation_version']=('matched' if starts[0]['implementation_version']==item['started']['implementation_version'] else 'conflict')
                if fields['implementation_version']=='conflict': verification='conflict'
            expected = {'completed':'trace.root.completed', 'failed':'trace.root.failed'}.get(item['status'])
            if expected and len(ends) == 1 and ends[0]['event_type'] == expected:
                finish = item['finished']
                if instant(item['timestamp']) <= instant(ends[0]['timestamp']) <= instant(finish['timestamp']):
                    fields['terminal'] = 'matched'
                else:
                    verification = 'conflict'
            elif ends and expected:
                verification = 'conflict'
            if len(starts) > 1 or (starts and fields['start'] != 'matched'):
                verification = 'conflict'
        elif trace_complete_read:
            verification = 'not_observed'
        m3['rows'].append(dict(attempt_id=item['attempt_id'], verification=verification, fields=fields,
            linked_events=len(matches), trace_id=item['trace_id']))
    m3.update(sample_count=len(sample), unknown_count=len(sample),
        status='unavailable' if not usable else 'partial' if sample or invalid or orphan_count or source['status'] == 'partial' else 'empty',
        counts=dict(sorted(Counter(r['verification'] for r in m3['rows']).items())),
        linked_items=sum(r['linked_events'] > 0 for r in m3['rows']), linked_traces=len(linked))
    m3['method'].update(source='独立 Capture CLI 尝试清单 + Trace 根事件',
        population='窗口内开始的独立 Capture CLI 尝试（至多 10 项）',
        sampling='按业务开始时间及不透明 attempt_id 排序取前 10 项；不是从 Trace 抽取样本。',
        deduplication=m1['method']['deduplication'],
        formula='按关联核验状态计数；字段矩阵区分已匹配/冲突/未知。实现版本比较独立开始记录与同时间 Trace 开始事件的版本标签；不是代码真实性验证。配置及结果引用未完整核验，不给完整覆盖率。',
        limitations='缺 Trace 来源或存在解析缺口时，无匹配保持 unchecked。not_observed 仅表示已读 Trace 快照中未找到。Trace suppressed/disabled 也可能导致无事件，不据此推断故障。独立记录本身并非完整进程总体；未核验配置与内容引用。')
