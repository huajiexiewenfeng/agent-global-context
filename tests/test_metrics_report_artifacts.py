import json
from contextlib import nullcontext
from pathlib import Path

import pytest

from agc_runtime.metrics_models import digest
from agc_runtime.metrics_source_bindings import register_source_bindings


def setup(tmp_path):
    ledger=tmp_path/'ledger'; ledger.mkdir()
    binding=dict(schema_version='agc.metrics-source-bindings.v1',plan_id='mplan_'+'a'*64,
        input_binding_digest='b'*64,entries=[dict(subject_ref='id_'+'c'*64,
        receipt_id='cr_'+'d'*64,native_reference_digest=None)])
    binding['binding_id']='msb_'+digest(binding)
    register_source_bindings(ledger,binding)
    context=dict(ledger=ledger,commit_guard=nullcontext)
    return context,binding


def publish(context,binding,directory,**kwargs):
    from agc_runtime.metrics_report_artifacts import publish_bundle
    return publish_bundle(context=context,plan_id=binding['plan_id'],directory=directory,
        kind='evidence_export',build=lambda:{'evidence-index.json':'{}','report.html':'<p>synthetic</p>'},**kwargs)


def test_registered_bundle_cleanup_only_removes_matching_fixed_files(tmp_path):
    from agc_runtime.metrics_report_artifacts import cleanup_reports
    context,binding=setup(tmp_path); output=tmp_path/'report'
    publish(context,binding,output)
    note=output/'keep.txt'; note.write_text('user owned')
    record=next((context['ledger']/'report-registry').glob('*.json'))
    assert '<p>synthetic' not in record.read_text()
    cleanup_reports(context['ledger'],'cr_'+'e'*64)
    assert (output/'report.html').exists()
    cleanup_reports(context['ledger'],'cr_'+'d'*64)
    assert sorted(p.name for p in output.iterdir())==['keep.txt']
    assert record.exists()  # Retain content-free audit metadata.
    cleanup_reports(context['ledger'],'cr_'+'d'*64)  # Idempotent recovery.


def test_build_and_publication_share_commit_guard_and_register_before_write(tmp_path,monkeypatch):
    from contextlib import contextmanager
    from agc_runtime.metrics_report_artifacts import publish_bundle
    context,binding=setup(tmp_path); output=tmp_path/'report'; held=[]
    @contextmanager
    def guard():
        held.append(True)
        try: yield
        finally: held.pop()
    context['commit_guard']=guard
    def build():
        assert held
        return {'evidence-index.json':'{}','report.html':'test'}
    original=Path.open
    def opening(path,*args,**kwargs):
        if path.parent==output and args and 'x' in args[0]:
            assert held and list((context['ledger']/'report-registry').glob('*.json'))
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'open',opening)
    publish_bundle(context=context,plan_id=binding['plan_id'],directory=output,kind='evidence_export',build=build)
    assert not held


@pytest.mark.parametrize('fault',['content','directory','binding'])
def test_changed_artifacts_fail_closed_without_deletion(tmp_path,fault):
    from agc_runtime.metrics_report_artifacts import cleanup_reports
    context,binding=setup(tmp_path); output=tmp_path/'report'
    publish(context,binding,output)
    if fault=='content': (output/'report.html').write_text('user edit')
    elif fault=='directory':
        output.rename(tmp_path/'original'); output.mkdir()
        (output/'report.html').write_text('<p>synthetic</p>')
    else: (context['ledger']/'source-bindings'/(binding['plan_id']+'.json')).write_text('{}')
    with pytest.raises((ValueError,OSError)): cleanup_reports(context['ledger'],'cr_'+'d'*64)
    assert (output/'report.html').exists()


def test_partial_publication_is_registered_and_can_be_cleaned(tmp_path,monkeypatch):
    from agc_runtime.metrics_report_artifacts import cleanup_reports
    context,binding=setup(tmp_path); output=tmp_path/'report'
    original=Path.open
    def opening(path,*args,**kwargs):
        if path==output/'.report.html.agc-pending' and args and 'x' in args[0]: raise OSError('synthetic')
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'open',opening)
    with pytest.raises(OSError): publish(context,binding,output)
    assert (output/'evidence-index.json').exists()
    cleanup_reports(context['ledger'],'cr_'+'d'*64)
    assert not list(output.iterdir())


def test_partial_write_leaves_only_registered_staging_file_for_cleanup(tmp_path,monkeypatch):
    from agc_runtime.metrics_report_artifacts import cleanup_reports
    context,binding=setup(tmp_path); output=tmp_path/'report'
    original=Path.open
    class Partial:
        def __init__(self,handle): self.handle=handle
        def __enter__(self): return self
        def __exit__(self,*args): self.handle.close()
        def write(self,data):
            self.handle.write(data[:3]); self.handle.flush()
            raise OSError('synthetic disk full after prefix')
    def opening(path,*args,**kwargs):
        handle=original(path,*args,**kwargs)
        if path.name=='.report.html.agc-pending' and args and 'x' in args[0]: return Partial(handle)
        return handle
    monkeypatch.setattr(Path,'open',opening)
    with pytest.raises(OSError): publish(context,binding,output)
    assert not (output/'report.html').exists()
    assert (output/'.report.html.agc-pending').read_bytes()==b'<p>'
    cleanup_reports(context['ledger'],'cr_'+'d'*64)
    assert not list(output.iterdir())


def test_capture_forget_cleans_reports_with_existing_durable_intent(tmp_path,monkeypatch):
    from test_metrics_forget_integration import setup as integrated_setup
    from agc_runtime import capture_forget_service as service
    from test_capture_forget import _request
    from agc_runtime.metrics_report_artifacts import publish_bundle
    paths,_,receipt,observations,args,model=integrated_setup(tmp_path,monkeypatch)
    binding=json.loads(next((args['ledger_directory']/'source-bindings').glob('*.json')).read_text())
    output=tmp_path/'report'
    publish_bundle(context=dict(ledger=args['ledger_directory'],commit_guard=nullcontext),
        plan_id=binding['plan_id'],directory=output,kind='evidence_export',
        build=lambda:{'evidence-index.json':'{}','report.html':'test'})
    original=Path.unlink
    def unlink(path,*values,**options):
        if path==output/'report.html': raise OSError('synthetic')
        return original(path,*values,**options)
    monkeypatch.setattr(Path,'unlink',unlink)
    request=_request({'type':'observation','observation_id':observations[0].observation_id})
    assert service.capture_forget(paths,request).status=='deferred'
    assert list((paths.capture.root/'metrics-cleanup').glob('*.json'))
    monkeypatch.setattr(Path,'unlink',original)
    assert service.capture_forget(paths,request).status=='accepted'
    assert not list(output.iterdir()) and model.calls==2
