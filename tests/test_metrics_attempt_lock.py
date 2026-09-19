import importlib

import pytest


def api():
    return importlib.import_module('agc_runtime.metrics_attempt_lock')


def test_active_and_released_lock_are_distinguished(tmp_path):
    assert api().attempt_state(tmp_path)=='unknown'
    with api().attempt_lock(tmp_path,create=True):
        assert api().attempt_state(tmp_path)=='active'
        with pytest.raises(api().AttemptActive):
            with api().attempt_lock(tmp_path): pass
    assert api().attempt_state(tmp_path)=='inactive'


def test_exception_releases_lock_without_terminal_fabrication(tmp_path):
    with pytest.raises(KeyboardInterrupt):
        with api().attempt_lock(tmp_path,create=True): raise KeyboardInterrupt()
    assert api().attempt_state(tmp_path)=='inactive'
    assert not (tmp_path/'finished.json').exists()


def test_invalid_lock_remains_unknown(tmp_path):
    (tmp_path/'.attempt.lock').write_bytes(b'invalid')
    assert api().attempt_state(tmp_path)=='unknown'


def test_operating_system_releases_lock_after_abrupt_child_exit(tmp_path):
    import subprocess
    import sys
    import time
    script=('import os,sys; from pathlib import Path; '
            'from agc_runtime.metrics_attempt_lock import attempt_lock; '
            'guard=attempt_lock(Path(sys.argv[1]),create=True); guard.__enter__(); '
            'sys.stdin.readline(); os._exit(0)')
    process=subprocess.Popen([sys.executable,'-B','-c',script,str(tmp_path)],
        stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    try:
        deadline=time.monotonic()+10
        while api().attempt_state(tmp_path)!='active' and time.monotonic()<deadline:
            if process.poll() is not None: break
            time.sleep(.02)
        assert api().attempt_state(tmp_path)=='active'
        process.communicate(input=b'\n',timeout=10)
        assert process.returncode==0 and api().attempt_state(tmp_path)=='inactive'
        assert not (tmp_path/'finished.json').exists()
    finally:
        if process.poll() is None:
            process.kill(); process.communicate(timeout=10)


def test_abandoned_execution_can_be_forgotten_without_fake_terminal(tmp_path,monkeypatch):
    from test_metrics_forget_integration import setup,_request,service
    paths,_,_,observations,args,_=setup(tmp_path,monkeypatch)
    finished=next(args['directory'].rglob('finished.json')); finished.unlink()
    assert api().attempt_state(finished.parent)=='inactive'
    response=service.capture_forget(paths,_request({'type':'observation','observation_id':observations[0].observation_id}))
    assert response.status=='accepted'
    assert not list(args['directory'].rglob('result.json'))
    assert not finished.exists()


def test_live_execution_defers_until_lock_is_released(tmp_path,monkeypatch):
    from test_metrics_forget_integration import setup,_request,service
    paths,_,_,observations,args,_=setup(tmp_path,monkeypatch)
    finished=next(args['directory'].rglob('finished.json')); finished.unlink()
    request=_request({'type':'observation','observation_id':observations[0].observation_id})
    with api().attempt_lock(finished.parent):
        response=service.capture_forget(paths,request)
        assert response.status=='deferred'
        assert (finished.parent/'result.json').exists()
    assert service.capture_forget(paths,request).status=='accepted'
    assert not list(args['directory'].rglob('result.json'))
