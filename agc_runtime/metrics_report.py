"""Accessible, self-contained HTML generated solely from a frozen metadata batch."""
from html import escape
import json
from collections import Counter

from agc_runtime.metrics_compute import compute_metrics
from agc_runtime.metrics_models import canonical, digest, validate_batch
from agc_runtime.metrics_review import review_state
from agc_runtime.metrics_review_batch import review_metrics, validate_review

LABELS = {
    'matched':'已匹配',
    'completed':'已完成', 'failed':'失败', 'state_conflict':'状态冲突',
    'terminal_unobserved':'终态未观测', 'unchecked':'尚未核验',
    'stored_pass_unchecked':'已存 pass · 未核验', 'stored_fail_unchecked':'已存 fail · 未核验',
    'stored_error_unchecked':'已存执行错误', 'stored_insufficient_evidence_unchecked':'已存证据不足',
    'conflict':'冲突', 'partial':'有限可测', 'unavailable':'不可计算', 'not_measured':'尚未评估',
    'available':'已读取', 'provided':'显式输入', 'not_provided':'未提供来源', 'schema_mismatch':'存储结构不兼容',
    'empty':'窗口内无可见记录',
    'not_observed':'未找到关联 Trace',
    'usable_judgment':'可用初评', 'not_run':'尚未运行', 'in_progress':'运行中',
    'evaluation_error':'评估错误', 'insufficient_evidence':'证据不足',
    'specific_useful':'具体且有帮助', 'partial_or_generic':'部分相关或泛化',
    'no_supported_link':'未建立有依据的联系', 'yes':'有误导', 'no':'未发现误导',
    'unknown':'未知', 'unreviewed':'未经人类复核',
    'accepted':'人工认可', 'corrected':'人工修正', 'disputed':'有争议',
}
CSS = '''
:root{--ink:#17243b;--muted:#475569;--line:#dce3ec;--blue:#254f9e;--surface:#fff;--bg:#f3f5f8}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.65 "Segoe UI","Microsoft YaHei",sans-serif}
main{max-width:1180px;margin:auto;padding:40px 24px 64px}header{border-top:5px solid var(--blue);padding:24px 0}
h1{font-size:34px;line-height:1.3;margin:10px 0}h2{font-size:23px;margin:8px 0}h3{font-size:17px}
p{margin:10px 0}.muted{color:var(--muted)}.eyebrow{font-size:13px;letter-spacing:.12em;font-weight:700;color:var(--blue)}
.notice{border-left:4px solid #a46515;background:#fff7e6;padding:12px 16px;margin:16px 0}
.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px}.card{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:24px;min-width:0}
.wide{grid-column:1/-1}.badge{display:inline-block;border:1px solid var(--line);border-radius:20px;padding:3px 12px;font-size:13px}
nav{display:flex;flex-wrap:wrap;gap:12px;margin:20px 0}a{color:var(--blue)}nav a{padding:8px 12px;background:white;border:1px solid var(--line);border-radius:6px}
summary{cursor:pointer;padding:10px 0;font-weight:600}details{border-top:1px solid var(--line);margin-top:16px}
:focus-visible{outline:3px solid #c47a18;outline-offset:3px}table{border-collapse:collapse;width:100%;font-size:14px}th,td{text-align:left;border-bottom:1px solid var(--line);padding:8px;overflow-wrap:anywhere}
th{font-weight:600}meter{width:100%;height:18px;accent-color:var(--blue)}.chart{display:grid;grid-template-columns:160px 1fr 40px;align-items:center;gap:10px;margin:12px 0;font-size:14px}
dl{font-size:14px}dt{font-weight:700;margin-top:10px}dd{margin:0;color:var(--muted);overflow-wrap:anywhere}
pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}code{overflow-wrap:anywhere}footer{margin-top:24px;font-size:14px;color:var(--muted)}
@media(max-width:700px){main{padding:20px 12px}.grid{grid-template-columns:1fr}.card{padding:18px}h1{font-size:27px}.chart{grid-template-columns:125px 1fr 28px}}
@media print{body{background:white}.grid{display:block}.card{break-inside:avoid;margin:12px 0}nav{display:none}}
'''


def _e(value):
    return escape(str(value), quote=True)


def _methods(metric):
    labels = {'version':'定义版本', 'layer':'结论层级', 'window':'窗口与截止（UTC）', 'source':'来源',
        'population':'对象与总体', 'formula':'计算口径', 'sampling':'抽样', 'deduplication':'去重',
        'missing':'缺失处理', 'exclusions':'排除', 'reproduction':'复算', 'limitations':'局限'}
    entries = ''.join('<dt>'+_e(labels[k])+'</dt><dd>'+_e(canonical(v) if isinstance(v, dict) else v)+'</dd>'
                      for k,v in metric['method'].items())
    return '<details><summary>查看方法</summary><dl>'+entries+'</dl></details>'


def _trace_matrix(metric):
    columns={'identity':'关联身份','start':'开始时间','terminal':'终态','implementation_version':'实现版本',
             'configuration_identity':'配置身份','result_reference':'结果引用'}
    rows=[r for r in metric['rows'] if 'fields' in r]
    html='<h3>Trace 字段核验矩阵</h3><p>匹配只表示所读记录一致，不代表完整可追溯率。旧记录没有版本时保持未核验；配置身份和结果引用尚缺验证依据。</p>'
    if not rows: return html+'<p>没有独立业务尝试的字段样本；不能从 Trace 数量反推覆盖。</p>'
    html+='<div style="overflow-x:auto"><table><caption>最多 10 个独立业务尝试</caption><thead><tr><th scope="col">业务尝试</th>'
    html+=''.join('<th scope="col">'+label+'</th>' for label in columns.values())+'</tr></thead><tbody>'
    for row in rows:
        html+='<tr><th scope="row"><code>'+_e(row['attempt_id'])+'</code></th>'
        html+=''.join('<td>'+_e(LABELS.get(row['fields'].get(k,'unknown'),row['fields'].get(k,'unknown')))+'</td>' for k in columns)+'</tr>'
    return html+'</tbody></table></div>'


def _chart(counts):
    if not counts:
        return '<p class="muted">没有可展示的测量值；不是零分，也不是默认通过。</p>'
    maximum = max(max(counts.values()), 1)
    bars = ''.join('<div class="chart"><span>'+_e(LABELS.get(k,k))+'</span><meter min="0" max="'+str(maximum)+'" value="'+str(v)+'" aria-label="'+_e(LABELS.get(k,k))+'">'+str(v)+'</meter><strong>'+str(v)+'</strong></div>' for k,v in counts.items())
    rows = ''.join('<tr><th scope="row">'+_e(LABELS.get(k,k))+'</th><td>'+str(v)+'</td></tr>' for k,v in counts.items())
    return bars+'<details><summary>查看数据表（数量，非百分比）</summary><table><thead><tr><th>状态</th><th>数量</th></tr></thead><tbody>'+rows+'</tbody></table></details>'


def _ratio(numerator, denominator):
    if not denominator:
        return '0 / 0 · 分母为零，不可计算'
    return f'{numerator} / {denominator} · {numerator / denominator:.1%}'


def _review_cards(metrics, review, batch):
    """Overlay domain projections without changing metadata health/trace measures."""
    values = review_metrics(review, batch)
    extras = {}
    for key in ('M2', 'M4', 'M5'):
        metric = metrics[key]
        rows = [r for r in review['rows'] if (key == 'M4' or
                (r['scenario'] == 'research') == (key == 'M5'))]
        unknown = sum(r['status'] != 'usable_judgment' for r in rows)
        metric.update(sample_count=len(rows), unknown_count=unknown, rows=rows,
                      status='partial' if len(rows) > unknown else 'not_measured', counts={})
        metric['method'].update(
            version=review['schema_version'], layer='LLM 初评，未经人类复核',
            window=dict(source_window=batch['window'], evaluation_cutoff=review.get('evaluation_cutoff',review['cutoff'])),
            source='同批 review.json 的冻结投影；保存时核验执行收据与来源，渲染不读取实时来源。',
            population='冻结计划中的案例，不代表全部 Capture 或全部研究任务。',
            sampling='沿用冻结计划；collected、zero、research 分开，每层最多 5 个案例。',
            deduplication='按计划 case_id；M2 再按阶段与 subject_digest 分组，不合并不同版本。',
            missing='未运行、运行中、失败、证据不足、未核验保留在计划分母；不作为质量零分。',
            reproduction='使用同批 batch.json 与 review.json 离线复算；不重新调用 Judge。',
            limitations='小样本 LLM 初评不是人类认可、因果收益或改动有效性的证明；冻结来源状态不代表当前有效。')
    m2 = values['M2']
    metrics['M2']['method']['formula'] = '保留错误率 = unsupported 与 unsuitable_durable / 确定候选；遗漏率 = omitted / 确定匹配的必留项。uncertain 单列，零分母不计算。'
    parts = []
    for scenario, data in m2.items():
        parts.append(f'<h3>{scenario} 分层</h3><p>计划样本 {data["sample_count"]} · 未评估 {data["unassessed_cases"]}</p>')
        for group in data['groups']:
            retention, required = group['retention'], group['required']
            parts.append('<p>阶段 '+_e(group['stage'])+' · 对象版本 <code>'+_e(group['subject_digest'])+'</code></p>')
            parts.append('<table><thead><tr><th>指标</th><th>分子 / 分母 · 比率</th><th>不确定项</th></tr></thead><tbody>')
            parts.append('<tr><th scope="row">保留错误率</th><td>'+_ratio(retention['errors'],retention['determinate'])+'</td><td>'+str(retention['uncertain'])+'</td></tr>')
            parts.append('<tr><th scope="row">必留项遗漏率</th><td>'+_ratio(required['omitted'],required['determinate_matches'])+'</td><td>参考 '+str(required['uncertain_reference'])+' · 匹配 '+str(required['uncertain_matches'])+'</td></tr></tbody></table>')
            parts.append(_chart({'保留错误项':retention['errors'], '保留判断不确定':retention['uncertain'],
                                 '遗漏项':required['omitted'], '匹配不确定':required['uncertain_matches']}))
    extras['M2'] = ''.join(parts)
    m4 = values['M4']
    metrics['M4'].update(counts=m4['counts'], invalid_records=m4['invalid_records'])
    metrics['M4']['method']['layer'] = '评估运行与可用性；不是质量得分'
    metrics['M4']['method']['formula'] = '可用初评案例 / 所有计划案例；案例要求全部步骤可用且依赖一致。计划步骤数单列，不作为案例分母。'
    extras['M4'] = f'<p>计划案例 {m4["planned_cases"]} · 计划步骤 {m4["planned_steps"]}</p><p>可用初评覆盖：'+_ratio(m4['usable_cases'],m4['planned_cases'])+'</p>'
    if 'execution_history' in review:
        extras['M4'] += '<details><summary>逐步骤尝试历史</summary><table><thead><tr><th>案例 / 步骤</th><th>首次尝试</th><th>最近已结束尝试</th><th>未完成 / 总尝试</th></tr></thead><tbody>'
        def attempt_label(attempt):
            if attempt is None:
                return '未观测'
            return _e(LABELS.get(attempt['status'],attempt['status']))+'<br>'+_e(attempt['started_at'])+'<br><code>'+_e(attempt['attempt_id'])+'</code>'
        for step in review['execution_history']:
            extras['M4'] += '<tr><th scope="row"><code>'+_e(step['case_id'])+'</code><br>'+_e(step['step'])+'</th><td>'+attempt_label(step['first'])+'</td><td>'+attempt_label(step['last_finished'])+'</td><td>'+str(step['unfinished_count'])+' / '+str(step['attempt_count'])+'</td></tr>'
        extras['M4'] += '</tbody></table><p>按开始时间与尝试 ID 排序；最近已结束不取最高评分。历史仅覆盖本次提供的执行目录，未实现的重试流程不构造记录。</p></details>'
        metrics['M4']['method']['sampling'] += ' 尝试历史来自本次执行目录；首次及最近已结束项按开始时间/ID 排序选择，未完成项另列。'
    m5 = values['M5']
    metrics['M5']['method']['formula'] = '按研究案例分别计数联系质量与误导标签；两轴不相减。有具体联系但存在误导仍须优先审查。未评估单列。'
    extras['M5'] = '<h3>误导风险（优先审查）</h3>'+_chart(m5['misleading'])+'<h3>联系质量</h3>'+_chart(m5['relevance'])+'<h3>人类复核状态</h3>'+_chart(m5['human_review'])
    return extras


def _human_section(batch, review, state):
    projected = json.loads(canonical(review))
    corrected = False
    for feedback in state['rows']:
        if feedback['human_review'] == 'corrected':
            corrected = True
            row = next(r for r in projected['rows'] if r['case_id'] == feedback['case_id'])
            row.update(feedback['correction'])
    report_revision = 'mreport_'+digest({'review_id':review['review_id'],
        'human_revisions':[r['revision_id'] for r in state['revisions']]})
    html = '<section class="card wide" id="human-review"><h2>人工复核与修订</h2><p>原始初评保持不变；此处单列最新人工反馈。未回应不视为认可，争议不计作同意。</p><p>报告修订 <code>'+_e(report_revision)+'</code></p>'
    html += _chart(dict(Counter(r['human_review'] for r in state['rows'])))
    html += '<details><summary>案例与追加修订记录</summary><pre>'+_e(canonical(state))+'</pre></details>'
    if corrected:
        projected['review_id'] = 'mr_'+digest({k:v for k,v in projected.items() if k != 'review_id'})
        extras = _review_cards(compute_metrics(batch), projected, batch)
        html += '<h3>人工修正后重算（不是新的 Judge 初评）</h3><p>使用最新 corrected 标签替换对应投影，其余保留原初评；这是混合来源的复算视图，不改变原始结果或评估可用性。计算公式沿用 M2/M5，不能当成全体样本人工认可。</p>'
        html += '<h3>M2 记忆质量</h3>'+extras['M2']
        # The projection deliberately preserves frozen Judge human flags. Do not
        # reuse its M5 "unreviewed" chart as the actual human state.
        m5 = review_metrics(projected, batch)['M5']
        html += '<h3>M5 误导风险</h3>'+_chart(m5['misleading'])+'<h3>M5 联系质量</h3>'+_chart(m5['relevance'])
    return html+'</section>'


def _review_queue(review, state):
    """Presentation-only triage from validated, content-minimized projections."""
    feedback = {r['case_id']:r['human_review'] for r in state['rows']} if state else {}
    flagged, normal = [], []
    for row in review['rows']:
        human = feedback.get(row['case_id'], 'unreviewed')
        reasons = []
        if human in ('disputed', 'corrected'):
            reasons.append('人工反馈：'+LABELS[human])
        if row['status'] != 'usable_judgment':
            reasons.append('程序状态：'+LABELS.get(row['status'], row['status']))
        elif row['research'] is not None:
            research = row['research']
            if research['misleading'] == 'yes':
                reasons.append('LLM 初评：有误导')
            elif research['misleading'] == 'unknown':
                reasons.append('LLM 初评：误导风险未知')
            if research['background_accuracy'] != 'supported':
                reasons.append('LLM 初评：背景不准确或未知')
            if research['issues']:
                reasons.append('LLM 初评：存在无依据联系或其他问题标签')
            if research['relevance'] != 'specific_useful':
                reasons.append('LLM 初评：'+LABELS[research['relevance']])
        else:
            verdicts = row['candidate_verdicts']
            matches = row['required_matches']
            if any(v in ('unsupported', 'unsuitable_durable') for v in verdicts):
                reasons.append('LLM 初评：候选无依据或不适合长期保存')
            if any(m['verdict'] == 'omitted' for m in matches):
                reasons.append('LLM 初评：存在遗漏标签')
            if ('uncertain' in verdicts or any(m['certainty'] == 'uncertain' or
                    m['verdict'] == 'uncertain_match' for m in matches)):
                reasons.append('LLM 初评：存在不确定判断')
        (flagged if reasons else normal).append((row, human, reasons))
    # Stable ID order is reproducible, not a random or representative sample.
    flagged.sort(key=lambda item:item[0]['case_id'])
    normal.sort(key=lambda item:item[0]['case_id'])
    sampled = normal[:2]
    html = '<section class="card wide" id="review-queue"><h2>人工 Review 案例队列</h2>'
    html += '<p>优先审查 '+str(len(flagged))+' 项 · 正常抽查 '+str(len(sampled))+' / '+str(len(normal))+'；另有 '+str(len(normal)-len(sampled))+' 项未列入抽查。</p>'
    html += '<p>“正常”仅指原始初评未标记问题，不代表事实正确或人工认可。选择仅影响此列表，不改变五组指标的全量计划分母，也不隐藏完整元数据。</p>'
    html += '<details><summary>审查选择方法</summary><p>优先组包含问题标签、不确定判断、非可用初评状态，以及最新人工争议或修正。组内按 case_id 排序；其余初评跨场景合计最多取前两项。不是随机抽样，不能用所选案例的分歧率推断 Judge 总体准确率。人工认可不抹去原始问题标签；原始 LLM 初评与人工反馈分列。</p></details>'
    if not review['rows']:
        return html+'<p>没有计划案例；不生成正常样例或质量结论。</p></section>'
    html += '<table><thead><tr><th>案例 / 场景</th><th>选择依据（非事实裁定）</th><th>人工状态</th></tr></thead><tbody>'
    for row, human, reasons in flagged+sampled:
        html += '<tr data-review-case="'+_e(row['case_id'])+'"><th scope="row"><code>'+_e(row['case_id'])+'</code><br>'+_e(row['scenario'])+'</th><td>'+_e('；'.join(reasons) if reasons else '正常初评抽查')+'<details><summary>原始 LLM 初评与程序元数据（无正文）</summary><pre>'+_e(canonical(row))+'</pre></details></td><td>'+_e(LABELS[human])+'</td></tr>'
    return html+'</tbody></table></section>'


def _research_coverage(batch, cohort):
    from agc_runtime.metrics_research_cohort import validate_research_cohort
    value=validate_research_cohort(batch,cohort)
    html='<section class="card wide" id="research-coverage"><h2>研究任务样本覆盖</h2>'
    html+='<p>独立分类清单，不作为 M5 质量分母；不是全窗口研究任务总量。分类不是质量判断，也不是机制收益。</p>'
    html+='<p>清单 <code>'+_e(value['cohort_id'])+'</code> · 任务数 '+str(len(value['tasks']))+'</p>'
    html+=_chart(value['counts'])
    html+='<details><summary>样本选择与分类方法</summary><p>窗口左闭右开；先保留排除、歧义和证据不可用状态，再按交付时间及任务标识排序，取前 5 个可用研究任务。不是随机抽样。</p>'
    html+='<p>分类方式 '+_e(value['classifier']['method'])+' · 规则 '+_e(value['classifier']['rule_version'])+'</p>'
    html+='<p>来源标记 '+_e(value['classification_provenance'])+'；摘要一致不证明分类正确或授权真实。渲染只检查冻结文件，不读取当前来源。</p>'
    html+='<p>准备阶段尚未分类、超限或缺失输入不在此清单内，应另看 preparation manifest；不能将未入清单解释为非研究任务。与本页质量评估案例的逐项对应关系未在此自动核验。</p></details>'
    html+='<details><summary>任务选择明细（无正文）</summary><table><thead><tr><th>任务 / 版本</th><th>交付时间 UTC</th><th>分类 / 原因</th><th>证据 / 选择状态</th></tr></thead><tbody>'
    for row in value['tasks']:
        html+='<tr><td><code>'+_e(row['task_ref'])+'</code><br><code>'+_e(row['revision'])+'</code></td><td>'+_e(row['delivered_at'])+'</td><td>'+_e(row['decision'])+' / '+_e(row['reason'])+'</td><td>'+_e(row['evidence_status'])+' / '+_e(row['selection_status'])+'</td></tr>'
    return html+'</tbody></table></details></section>'


def _preparation_coverage(batch, manifest):
    from agc_runtime.metrics_research_classification import validate_preparation_manifest
    value=validate_preparation_manifest(batch,manifest)
    html='<section class="card wide" id="research-preparation"><h2>研究输入准备覆盖</h2>'
    html+='<p>准备就绪不等于已分类，更不等于已评估。以下分母是显式提供的原生引用条目，不是独立任务数或全窗口任务总量。</p>'
    html+='<p>准备清单 <code>'+_e(value['preparation_id'])+'</code> · 引用条目 '+str(len(value['entries']))+'</p>'
    html+=_chart(value['counts'])
    html+='<details><summary>输入准备方法与限制</summary><p>最多 100 条显式引用，窗口左闭右开。窗口外不读正文；同一任务多个窗口内修订保留 ambiguous_revision。按完成时间、任务和引用排序，返回输入累计不超过 2 MiB，不截断正文；放不下的条目保留 input_budget_exceeded，后续较小输入仍可能返回。</p>'
    html+='<p>evidence_unavailable 表示当时不能提供输入，不代表该任务没有价值。ready 仅表示当时安全输入可准备；清单固定标记 not_classified，不因后来运行分类而改写。渲染只核对无正文清单，不能验证输入内容或当前权限，不据此推导分类成功率或收益。</p></details>'
    html+='<details><summary>逐引用准备状态（无正文）</summary><table><thead><tr><th>任务 / 原生引用摘要</th><th>交付时间 UTC</th><th>准备状态</th></tr></thead><tbody>'
    for entry in value['entries']:
        html+='<tr><td><code>'+_e(entry['task_ref'])+'</code><br><code>'+_e(entry['native_reference_digest'])+'</code></td><td>'+_e(entry['delivered_at'])+'</td><td>'+_e(entry['status'])+'</td></tr>'
    return html+'</tbody></table></details></section>'


def _evidence_section(batch,review,evidence):
    from agc_runtime.metrics_review_evidence import validate_evidence
    value=validate_evidence(batch,review,evidence)
    html='<section class="card wide" id="private-evidence"><h2>私有证据明细</h2>'
    html+='<p>仅显示受控引用，不包含来源正文或未经检查的模型理由。原始 LLM 初评未经人工复核，不是已证实事实。敏感正文须按需通过本地解析器查看；清理机制接通前不批量导出。</p>'
    html+='<p>附录 <code>'+_e(value['evidence_id'])+'</code><br>生成时间 '+_e(value['created_at'])+'。本页离线渲染，不会自动更新撤销状态，也不能证明当前访问权限。</p>'
    for item in value['cases']:
        html+='<details><summary>案例 '+_e(item['case_id'])+' · '+('证据可用（生成时）' if item['status']=='available' else '证据不可用')+'</summary>'
        if item['status']=='unavailable':
            html+='<p>附录生成时无法提供经过核验的完整证据；不据此推断原始初评正确或错误。</p>'
        else:
            html+='<p>对象阶段 '+_e(item['subject']['stage'])+' · 版本摘要 <code>'+_e(digest(item['subject']['version']))+'</code></p>'
            for result in item['results']:
                html+='<h3>原始 LLM 初评引用 · '+_e(result['step'])+'</h3><p>步骤 <code>'+_e(result['entry_id'])+'</code><br>结果摘要 <code>'+_e(result['result_digest'])+'</code></p>'
            html+='<h3>对应安全文档引用</h3><p>仅列当时绑定的引用；不复制正文，也不证明当前实时来源有效。</p>'
            for document in item['documents']:
                html+='<p>'+_e(document['role'])+' · <code>'+_e(document['ref'])+'</code><br>版本摘要 <code>'+_e(digest(document['version']))+'</code></p>'
        html+='</details>'
    return html+'</section>'


def render_report(value, *, title='AGC 指标 Review', review=None, revisions_dir=None, research_cohort=None, research_preparation=None,evidence=None):
    batch = validate_batch(value)
    if batch['data_kind'] == 'synthetic':
        title = '合成数据演示 · ' + title
    metrics = compute_metrics(batch)
    review = validate_review(review, batch) if review is not None else None
    review_extras = _review_cards(metrics, review, batch) if review is not None else {}
    if revisions_dir is not None and review is None:
        raise ValueError('human_review_requires_frozen_review')
    human_state = review_state(batch, review, revisions_dir) if revisions_dir is not None else None
    human_html = _human_section(batch, review, human_state) if human_state is not None else ''
    if evidence is not None and review is None:
        raise ValueError('private_evidence_requires_review')
    evidence_html=_evidence_section(batch,review,evidence) if evidence is not None else ''
    cards = []
    for key, metric in metrics.items():
        extras = review_extras.get(key, '')
        if 'invalid_records' in metric:
            extras += '<p class="muted">无法解析或无效记录 '+str(metric['invalid_records'])+' 条（不计作正常空结果）。</p>'
        if key == 'M1':
            if 'stage_health' in metric:
                extras += '<h3>服务边界状态（与 Capture 分开）</h3><p>accepted 不等于新增写入、实际使用或预览交付。</p>'
                extras += '<p class="muted">来源 '+_e(metric['business_source_status'])+' · 无效记录 '+str(metric['business_invalid_records'])+' · 孤立终态 '+str(metric['business_orphan_terminals'])+'</p>'
                for stage,counts in metric['stage_health'].items():
                    extras += '<h3>'+_e(stage)+'</h3>'+_chart(counts)
                extras += '<details><summary>服务结果与审查收据（元数据）</summary><pre>'+_e(canonical(metric['business_rows']))+'</pre></details>'
            if 'operations' in batch:
                extras += '<p>新版独立 Capture CLI 尝试清单：业务开始样本与 Trace 事件分别计数。</p>'
                extras += '<details><summary>Trace 自身的开始队列（不作为业务分母）</summary>'+_chart(metric['trace_cohort']['counts'])+'</details>'
                extras += '<p class="muted">孤立业务终态 '+str(metric['orphan_business_terminals'])+' · 重复业务记录 '+str(metric['duplicate_operation_records'])+'</p>'
            extras += f'<p class="muted">窗口内终态事件 {metric["terminal_events_in_window"]} · 完成项事件 {metric["completed_item_events"]} · 缺开始记录 {metric["incomplete_records"]} · 重复事件 {metric["duplicate_events"]} · 冲突 ID {metric["conflicting_event_ids"]}</p>'
            if metric['failure_codes']:
                extras += '<details><summary>失败运行错误码标签（不是根因判断）</summary>'+_chart(metric['failure_codes'])+'</details>'
        if key == 'M3':
            extras += _trace_matrix(metric)
            extras += f'<p class="muted">标识匹配项 {metric["linked_items"]} · 涉及 Trace {metric["linked_traces"]}。这不是完整可追溯率。</p>'
        rows = '<details><summary>查看元数据证据（不含正文）</summary><pre>'+_e(canonical(metric['rows']))+'</pre></details>' if metric['rows'] else ''
        cards.append('<section id="'+key+'" class="card'+(' wide' if key=='M1' else '')+'"><span class="eyebrow">'+key+'</span><h2>'+_e(metric['title'])+'</h2><span class="badge">'+_e(LABELS[metric['status']])+'</span><p class="muted">'+_e(metric['method']['layer'])+' · 样本 '+str(metric['sample_count'])+' · 未知/未核验 '+str(metric['unknown_count'])+'</p>'+_chart(metric['counts'])+extras+'<p>'+_e(metric['method']['limitations'])+'</p>'+_methods(metric)+rows+'</section>')
    if review is not None:
        cards.append(_review_queue(review, human_state))
    if human_html:
        cards.append(human_html)
    if research_cohort is not None:
        cards.append(_research_coverage(batch,research_cohort))
    if research_preparation is not None:
        cards.append(_preparation_coverage(batch,research_preparation))
    if evidence_html:
        cards.append(evidence_html)
    sources = ''.join('<tr><th scope="row">'+_e(s['name'])+'</th><td>'+_e(LABELS.get(s['status'],s['status']))+'</td><td>'+str(s['invalid_records'])+'</td><td>'+_e(s['read_at'] or '未记录')+'</td></tr>' for s in batch['sources'])
    nav = ''.join('<a href="#'+k+'">'+k+' '+_e(v['title'])+'</a>' for k,v in metrics.items())
    if review is not None:
        nav += '<a href="#review-queue">人工 Review 案例</a>'
    notice = ('冻结 LLM 初评报告；本次渲染不调用 Judge。未复核不代表用户认可。评估批次 <code>'+_e(review['review_id'])+'</code>') if review is not None else 'P1 只读元数据报告。没有调用 Judge；内容质量与研究帮助尚未评估。不能用活动量证明效果，未复核不代表用户认可。'
    return '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; base-uri \'none\'; form-action \'none\'"><title>'+_e(title)+'</title><style>'+CSS+'</style></head><body><main><header><div class="eyebrow">AGC / EVIDENCE REVIEW</div><h1>'+_e(title)+'</h1><p>先看证据是否足够，再看机制是否有用。</p><p class="muted">窗口（UTC）：'+_e(batch['window']['start'])+' → '+_e(batch['window']['end'])+'（左闭右开）<br>观测截止：'+_e(batch['window']['cutoff'])+' · 报告时区：Asia/Shanghai</p><p class="muted">批次 <code>'+_e(batch['batch_id'])+'</code></p></header><div class="notice">'+notice+'</div><nav aria-label="指标导航">'+nav+'</nav><div class="grid">'+''.join(cards)+'</div><section class="card wide" style="margin-top:20px"><h2>来源与复算边界</h2><table><thead><tr><th>来源</th><th>读取状态</th><th>解析错误</th><th>读取时间</th></tr></thead><tbody>'+sources+'</tbody></table><p>各来源独立读取，不是跨数据库全局事务。Receipt 为读取时快照，不能倒推历史队列。</p><details><summary>纳入与排除清单</summary><p>纳入记录保存在同批 batch.json 的 events / receipts / evaluations；被排除记录 '+str(len(batch['excluded']))+' 条。</p><pre>'+_e(canonical(batch['excluded']))+'</pre></details></section><footer>定义 v1.1 · 转换 '+_e(batch['transform_version'])+' · 本地离线，无远程资源。冻结报告不自动刷新撤销状态，身份摘要不是匿名化；请作为私有材料管理。复算只读取同批文件，不调用模型。</footer></main></body></html>'
