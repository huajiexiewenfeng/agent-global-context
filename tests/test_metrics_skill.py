import json
from pathlib import Path
import re
import shlex

import yaml

from agc_runtime.metrics_cli import main
from agc_runtime.metrics_review_batch import freeze_review
from test_metrics_review_batch import setup

SKILL = Path(__file__).resolve().parents[1]/'skills'/'agc-metrics-review'


def test_metrics_skill_is_explicit_only():
    assert SKILL.is_dir(), 'missing explicit metrics review skill'
    front = yaml.safe_load((SKILL/'SKILL.md').read_text(encoding='utf-8').split('---',2)[1])
    assert front['name'] == 'agc-metrics-review'
    config = yaml.safe_load((SKILL/'agents'/'openai.yaml').read_text(encoding='utf-8'))
    assert config['policy']['allow_implicit_invocation'] is False


def test_documented_feedback_then_render_commands_work(tmp_path, monkeypatch):
    assert SKILL.is_dir(), 'missing runnable skill workflow'
    text = (SKILL/'references'/'commands.md').read_text(encoding='utf-8')
    commands = re.findall(r'^agc-metrics (?:review|render) .+$', text, re.M)
    assert len(commands) == 2
    batch, plan, resolver = setup(tmp_path)
    review = freeze_review(batch, plan, tmp_path, resolve_case=resolver)
    feedback = dict(case_id=review['rows'][0]['case_id'], decision='accepted', correction=None,
                    feedback_ref='id_'+'a'*64, timestamp='2099-01-02T00:00:00Z')
    for name, value in [('batch',batch), ('review',review), ('feedback',feedback)]:
        (tmp_path/f'{name}.json').write_text(json.dumps(value), encoding='utf-8')
    (tmp_path/'human').mkdir()
    monkeypatch.chdir(tmp_path)
    for command in commands:
        assert main(shlex.split(command)[1:]) == 0
    html = (tmp_path/'report-revision.html').read_text(encoding='utf-8')
    assert '人工认可' in html and '原始初评保持不变' in html
    assert (tmp_path/'review.json').read_text(encoding='utf-8') == json.dumps(review)
