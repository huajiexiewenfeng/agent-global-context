import importlib
import json
from pathlib import Path

import pytest

from agc_runtime.contracts import ToolResponse
from agc_runtime.paths import MemoryPaths
from agc_runtime.read_service import dispatch_read
from agc_runtime.write_service import dispatch_write
from agc_runtime.admin_service import dispatch_admin


def setup(tmp_path, monkeypatch):
    directory = tmp_path / 'metrics'
    directory.mkdir()
    monkeypatch.setenv('AGC_METRICS_EVIDENCE_DIR', str(directory))
    return directory, MemoryPaths.from_root(tmp_path / 'memory')


def snapshot(directory):
    return importlib.import_module('agc_runtime.metrics_business').read_business_records(directory / 'business')


def test_recall_records_returned_representation_not_content(tmp_path, monkeypatch):
    directory, paths = setup(tmp_path,monkeypatch)
    response = ToolResponse(tool='agc.read',action='get',status='accepted',data={
        'item':{'id':'PRIVATE-ID','memory_card':'PRIVATE-CONTENT','full_meaning':'SECRET'}})
    def get(*args):
        before = snapshot(directory)
        assert len(before['records']) == 1
        assert before['records'][0]['phase'] == 'started'
        return response
    monkeypatch.setitem(importlib.import_module('agc_runtime.read_service')._HANDLERS,'get',get)
    returned = dispatch_read(paths, {'action':'get','id':'PRIVATE-ID'})
    assert returned.data['item'] == response.data['item']
    rows = snapshot(directory)['records']
    assert len(rows) == 2
    end = next(r for r in rows if r['phase'] == 'finished')
    assert end['stage'] == 'recall'
    assert end['objects'][0]['version_kind'] == 'returned_representation'
    assert end['actual_use'] == 'unknown'
    assert 'PRIVATE' not in json.dumps(rows)
    assert 'SECRET' not in json.dumps(rows)


def test_save_and_receipt_result_remain_separate(tmp_path, monkeypatch):
    directory, paths = setup(tmp_path,monkeypatch)
    mod = importlib.import_module('agc_runtime.write_service')
    response = ToolResponse(tool='agc.write',action='confirm',status='accepted',
        data={'memory_id':'PRIVATE-ID','code':'memory_created'}, warnings=('capture_review_receipt_failed',))
    monkeypatch.setitem(mod._HANDLERS, 'confirm', lambda *args:response)
    monkeypatch.setattr(mod,'_refresh_catalog_after_formal_memory',lambda paths,r:r)
    actual = dispatch_write(paths,{'action':'confirm','capture_observation_ids':['co_PRIVATE']})
    assert actual.status == 'accepted'
    end = next(r for r in snapshot(directory)['records'] if r['phase'] == 'finished')
    assert end['write_status'] == 'accepted'
    assert end['review_receipt_status'] == 'failed'
    assert end['confirmation_ref'] is None
    assert end['objects'][0]['version_kind'] == 'unknown'
    assert 'PRIVATE' not in json.dumps(end)


def test_notice_is_not_preview_delivery(tmp_path, monkeypatch):
    directory, paths = setup(tmp_path,monkeypatch)
    mod = importlib.import_module('agc_runtime.admin_service')
    monkeypatch.setitem(mod._HANDLERS,'capture_review_notice',lambda *args:ToolResponse(
        tool='agc.admin',action='capture_review_notice',status='accepted',data={'batch_digest':'a'*64}))
    dispatch_admin(paths,{'action':'capture_review_notice','batch_digest':'a'*64})
    end = next(r for r in snapshot(directory)['records'] if r['phase'] == 'finished')
    assert end['stage'] == 'review_notice'
    assert end['preview_delivery'] == 'unknown'


def test_disabled_keeps_response_identity(tmp_path, monkeypatch):
    monkeypatch.delenv('AGC_METRICS_EVIDENCE_DIR',raising=False)
    response=ToolResponse(tool='agc.read',action='get',status='accepted')
    monkeypatch.setitem(importlib.import_module('agc_runtime.read_service')._HANDLERS,'get',lambda *a:response)
    assert dispatch_read(MemoryPaths.from_root(tmp_path),{'action':'get','id':'any'}) is response


def test_bad_record_directory_does_not_break_recall(tmp_path, monkeypatch):
    directory, paths = setup(tmp_path,monkeypatch)
    (directory/'business').write_text('not a directory')
    response=ToolResponse(tool='agc.read',action='get',status='accepted',data={'item':{'id':'m'}})
    monkeypatch.setitem(importlib.import_module('agc_runtime.read_service')._HANDLERS,'get',lambda *a:response)
    actual=dispatch_read(paths,{'action':'get','id':'m'})
    assert actual.status == 'accepted'
    assert 'metrics_evidence_unavailable' in actual.warnings


def test_error_message_not_recorded(tmp_path,monkeypatch):
    directory,paths=setup(tmp_path,monkeypatch)
    monkeypatch.setitem(importlib.import_module('agc_runtime.read_service')._HANDLERS,'get',
                        lambda *a: (_ for _ in ()).throw(ValueError('PRIVATE')))
    actual=dispatch_read(paths,{'action':'get','id':'m'})
    assert actual.status=='failed'
    assert 'PRIVATE' not in json.dumps(snapshot(directory))


def test_returned_version_changes_when_representation_changes(tmp_path,monkeypatch):
    directory,paths=setup(tmp_path,monkeypatch)
    mod=importlib.import_module('agc_runtime.read_service')
    for content in ('first','second'):
        monkeypatch.setitem(mod._HANDLERS,'get',lambda *a:ToolResponse(tool='agc.read',action='get',status='accepted',
            data={'item':{'id':'m','memory_card':content}}))
        dispatch_read(paths,{'action':'get','id':'m'})
    ends=[r for r in snapshot(directory)['records'] if r['phase']=='finished']
    assert len({r['objects'][0]['version'] for r in ends})==2


def test_search_records_real_results_shape_once(tmp_path,monkeypatch):
    directory,paths=setup(tmp_path,monkeypatch)
    cards=[{'id':'m','memory_card':'PRIVATE'}]
    response=ToolResponse(tool='agc.read',action='search',status='accepted',data={'results':cards,'items':cards})
    monkeypatch.setitem(importlib.import_module('agc_runtime.read_service')._HANDLERS,'search',lambda *a:response)
    dispatch_read(paths,{'action':'search'})
    end=next(r for r in snapshot(directory)['records'] if r['phase']=='finished')
    assert len(end['objects'])==1


def test_non_success_status_is_recorded_not_lost(tmp_path,monkeypatch):
    directory,paths=setup(tmp_path,monkeypatch)
    response=ToolResponse(tool='agc.write',action='confirm',status='needs_adjudication',data={'memory_id':'m'})
    mod=importlib.import_module('agc_runtime.write_service')
    monkeypatch.setitem(mod._HANDLERS,'confirm',lambda *a:response)
    actual=dispatch_write(paths,{'action':'confirm'})
    assert not actual.warnings
    end=next(r for r in snapshot(directory)['records'] if r['phase']=='finished')
    assert end['response_status']=='needs_adjudication'


def test_business_reader_rejects_extra_content_and_duplicate_fields(tmp_path,monkeypatch):
    directory,paths=setup(tmp_path,monkeypatch)
    mod=importlib.import_module('agc_runtime.read_service')
    monkeypatch.setitem(mod._HANDLERS,'get',lambda *a:ToolResponse(tool='agc.read',action='get',status='accepted'))
    dispatch_read(paths,{'action':'get','id':'m'})
    start=next((directory/'business').glob('*.started.json'))
    text=start.read_text()
    start.write_text(text[:-1]+',"phase":"started"}')
    end=next((directory/'business').glob('*.finished.json'))
    raw=json.loads(end.read_text()); raw['private']='PRIVATE'; end.write_text(json.dumps(raw))
    result=snapshot(directory)
    assert result['invalid_records']==2
    assert result['records']==[]
    assert 'PRIVATE' not in json.dumps(result)


def test_real_save_and_read_with_metrics_preserves_memory(tmp_path,monkeypatch):
    from test_write_service import direct_request, principle
    directory,paths=setup(tmp_path,monkeypatch)
    assert dispatch_admin(paths,{'action':'init'}).status=='accepted'
    written=dispatch_write(paths,direct_request())
    assert written.status=='accepted'
    returned=dispatch_read(paths,{'action':'get','id':principle().id})
    assert returned.status=='accepted'
    assert returned.data['item']['full_meaning']==principle().full_meaning
    ends=[r for r in snapshot(directory)['records'] if r['phase']=='finished']
    assert {r['stage'] for r in ends}=={'recall','memory_write'}
    assert all(not response.warnings for response in (written,returned))
    assert principle().full_meaning not in json.dumps(snapshot(directory),ensure_ascii=False)
    import hashlib
    target=next(paths.memories.rglob('*.md'))
    expected=hashlib.sha256(target.read_bytes()).hexdigest()
    saved=next(r for r in ends if r['stage']=='memory_write')
    assert saved['objects'][0]['version_kind']=='written_content'
    assert saved['objects'][0]['version']==expected
    assert written.data['memory_version']==expected
    provenance=saved['request_source']
    assert provenance['verification']=='caller_supplied_unverified'
    assert provenance['content_digest']==direct_request()['observation']['source']['content_hash']
    assert provenance['ref'].startswith('id_') and provenance['revision'].startswith('id_')
    assert saved['confirmation_ref'] is None
    assert 'codex-task:t1' not in json.dumps(saved)
    duplicate=dispatch_write(paths,direct_request())
    assert duplicate.status=='accepted'
    assert 'memory_version' not in duplicate.data


def test_disabled_metrics_does_not_add_version_to_write_response(monkeypatch):
    from agc_runtime.store import MutationResult
    from agc_runtime.write_service import _mutation_response
    monkeypatch.delenv('AGC_METRICS_EVIDENCE_DIR',raising=False)
    result=MutationResult(status='accepted',code='memory_created',created=True,
                          object_id='example',independent_evidence_count=1,
                          written_content_digest='a'*64)
    assert 'memory_version' not in _mutation_response('confirm',result).data


def test_legacy_business_record_remains_readable_without_provenance(tmp_path,monkeypatch):
    directory,paths=setup(tmp_path,monkeypatch)
    response=ToolResponse(tool='agc.read',action='get',status='accepted')
    monkeypatch.setitem(importlib.import_module('agc_runtime.read_service')._HANDLERS,'get',lambda *a:response)
    dispatch_read(paths,{'action':'get','id':'m'})
    row=snapshot(directory)['records'][0]
    row['schema']='agc.business-evidence.v1'; row.pop('request_source')
    assert importlib.import_module('agc_runtime.metrics_business').validate_business_record(row)==row
