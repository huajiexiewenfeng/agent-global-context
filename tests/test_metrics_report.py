import json

from test_metrics_batch import api, batch, event


def test_report_offline_methods_and_no_unsupported_scores():
    html = api('metrics_report').render_report(batch(events=[event()]))
    assert html.count('查看方法') == 5
    assert '<html lang="zh-CN">' in html
    assert '<script' not in html and 'https://' not in html
    assert '尚未评估' in html
    assert '终态未观测' in html
    assert '<table' in html and '<meter' in html


def test_html_title_escaped():
    html = api('metrics_report').render_report(batch(), title='<img src=x onerror=alert(1)>')
    assert '<img' not in html
    assert '&lt;img' in html


def test_cli_freeze_and_render_without_sources_or_judge(tmp_path):
    cli = api('metrics_cli')
    folder = tmp_path / 'report'
    assert cli.main(['prepare', '--start', '2026-09-03T00:00:00+08:00', '--end', '2026-09-10T00:00:00+08:00', '--output', str(folder)]) == 0
    frozen = (folder / 'batch.json').read_bytes()
    first = (folder / 'report.html').read_bytes()
    assert cli.main(['render', '--batch', str(folder / 'batch.json'), '--output', str(tmp_path / 'again.html')]) == 0
    assert first == (tmp_path / 'again.html').read_bytes()
    assert frozen == (folder / 'batch.json').read_bytes()
    assert cli.main(['prepare', '--start', '2026-09-03T00:00:00+08:00', '--end', '2026-09-10T00:00:00+08:00', '--output', str(folder)]) == 2


def test_render_rejects_modified_batch(tmp_path):
    value = batch(); value['window']['start'] = '2020-01-01T00:00:00Z'
    path = tmp_path / 'batch.json'; path.write_text(json.dumps(value), encoding='utf-8')
    assert api('metrics_cli').main(['render', '--batch', str(path), '--output', str(tmp_path/'report.html')]) == 2
    assert not (tmp_path / 'report.html').exists()


def test_output_must_not_overwrite_batch_or_source(tmp_path):
    cli = api('metrics_cli')
    path = tmp_path/'batch.json'
    path.write_text(json.dumps(batch()), encoding='utf-8')
    before = path.read_bytes()
    assert cli.main(['render','--batch',str(path),'--output',str(path)]) == 2
    assert path.read_bytes() == before


def test_generate_synthetic_report(tmp_path):
    from test_metrics_collect import trace_db
    from test_metrics_batch import START, END
    trace_path = tmp_path/'trace.sqlite3'
    receipts = tmp_path/'receipts'; receipts.mkdir()
    rows = [event(), event('e2',kind='trace.root.completed'), event('e3',trace='t2'),
        event('e4',trace='t2',kind='trace.root.failed',error={'type':'capture_busy'}), event('e5',trace='t3'),
        event('item',kind='agc.capture.item.completed',outcome='zero',evidence_ref={'provider':'agc','kind':'capture-item','ref':'r1'})]
    trace_db(trace_path,rows)
    (receipts/'r1.json').write_text(json.dumps(dict(receipt_id='r1',updated_at=START,status='complete',redacted_by_forget=False)),encoding='utf-8')
    target = tmp_path/'synthetic-report'
    assert api('metrics_cli').main(['prepare','--start',START,'--end',END,'--trace-db',str(trace_path),'--receipts-dir',str(receipts),'--output',str(target),'--synthetic']) == 0
    html = (target/'report.html').read_text(encoding='utf-8')
    assert '合成数据演示' in html
    assert json.loads((target/'batch.json').read_text(encoding='utf-8'))['data_kind'] == 'synthetic'
