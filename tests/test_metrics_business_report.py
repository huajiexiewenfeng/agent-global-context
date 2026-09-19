import importlib
from datetime import datetime, timezone, timedelta

from agc_runtime.contracts import ToolResponse
from agc_runtime.paths import MemoryPaths
from agc_runtime.read_service import dispatch_read
from agc_runtime.metrics_collect import collect_batch
from agc_runtime.metrics_compute import compute_metrics
from agc_runtime.metrics_models import validate_batch
from agc_runtime.metrics_cli import main


def test_business_records_are_frozen_and_stage_counts_not_capture(tmp_path,monkeypatch):
    monkeypatch.setenv('AGC_METRICS_EVIDENCE_DIR',str(tmp_path))
    monkeypatch.setitem(importlib.import_module('agc_runtime.read_service')._HANDLERS,'get',
        lambda *a:ToolResponse(tool='agc.read',action='get',status='accepted',data={'item':{'id':'m','memory_card':'PRIVATE'}}))
    now=datetime.now(timezone.utc)
    start=(now-timedelta(days=1)).isoformat()
    end=(now+timedelta(days=1)).isoformat()
    dispatch_read(MemoryPaths.from_root(tmp_path/'memory'),{'action':'get','id':'m'})
    frozen=collect_batch(start=start,end=end,cutoff=end,business_dir=tmp_path/'business')
    assert validate_batch(frozen)==frozen
    assert len(frozen['business'])==2
    result=compute_metrics(frozen)
    assert result['M1']['stage_health']['recall']=={'accepted':1}
    assert result['M1']['sample_count']==0
    assert result['M5']['status']=='not_measured'
    for path in (tmp_path/'business').glob('*.json'):
        path.unlink()
    assert compute_metrics(frozen)==result
    assert 'PRIVATE' not in str(frozen)


def test_cli_accepts_business_source_and_blocks_output_inside_it(tmp_path,monkeypatch):
    directory=tmp_path/'business'; directory.mkdir()
    args=['prepare','--start','2026-09-11T00:00:00Z','--end','2026-09-12T00:00:00Z',
        '--business-dir',str(directory),'--output',str(tmp_path/'report')]
    assert main(args)==0
    args[-1]=str(directory/'report')
    assert main(args)==2
