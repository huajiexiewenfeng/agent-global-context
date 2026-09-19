import importlib

import pytest
import yaml
from agc_runtime.runtime_config import _Yaml12SafeLoader

from agc_runtime.capture_store import CaptureStore
from agc_runtime.write_service import dispatch_write
from test_capture_eval_adapter import _write_config
from test_capture_forget import _populated,_revision


def gate(paths):
    return importlib.import_module('agc_runtime.metrics_research_access').CaptureResearchAccess(paths)


def test_uncaptured_task_is_allowed_without_receipt(tmp_path):
    from test_capture_forget import _key
    paths=_write_config(tmp_path/'memory'); CaptureStore(paths).ensure_layout()
    check=gate(paths)
    assert check.check(_revision(_key())) is None


def test_actual_revision_forget_blocks_later_research_access(tmp_path):
    paths,_,receipt,_=_populated(tmp_path)
    check=gate(paths); ref=_revision(receipt.key)
    check.check(ref)
    result=dispatch_write(paths,dict(action='capture_forget',authorization='explicit_user_request',
                                   target=dict(type='revision',**receipt.key.to_mapping())))
    assert result.status=='accepted'
    with pytest.raises(ValueError): check.check(ref)


def test_actual_observation_forget_blocks_reconstruction_from_session(tmp_path):
    paths,_,receipt,observations=_populated(tmp_path)
    check=gate(paths); ref=_revision(receipt.key)
    check.check(ref)
    result=dispatch_write(paths,dict(action='capture_forget',authorization='explicit_user_request',
                                   target=dict(type='observation',observation_id=observations[0].observation_id)))
    assert result.status=='accepted'
    with pytest.raises(ValueError): check.check(ref)


def test_live_task_and_project_exclusions_are_reloaded(tmp_path):
    paths,_,receipt,_=_populated(tmp_path)
    check=gate(paths); ref=_revision(receipt.key)
    check.check(ref)
    config=paths.root/'config.yaml'
    value=yaml.load(config.read_text(encoding='utf-8'),Loader=_Yaml12SafeLoader)
    value['capture']['exclude']['task_ids']=[ref.key.task_id]
    config.write_text(yaml.safe_dump(value),encoding='utf-8')
    with pytest.raises(ValueError): check.check(ref)
    value['capture']['exclude']['task_ids']=[]
    value['capture']['exclude']['project_ids']=['project:example']
    config.write_text(yaml.safe_dump(value),encoding='utf-8')
    with pytest.raises(ValueError): check.check(ref,project_scope='project:example',content_loaded=True)
    with pytest.raises(ValueError): check.check(ref,project_scope=None,content_loaded=True)
    check.check(ref,project_scope='project:other',content_loaded=True)


def test_missing_config_does_not_fall_back_to_permissive_defaults(tmp_path):
    paths,_,receipt,_=_populated(tmp_path)
    check=gate(paths)
    (paths.root/'config.yaml').unlink()
    with pytest.raises(ValueError): check.check(_revision(receipt.key))


def test_config_removed_between_check_and_load_is_denied(tmp_path,monkeypatch):
    from agc_runtime import metrics_research_access
    paths,_,receipt,_=_populated(tmp_path)
    config=paths.root/'config.yaml'
    original=metrics_research_access._linked
    def remove_after_check(path):
        result=original(path)
        if path==config: path.unlink()
        return result
    monkeypatch.setattr(metrics_research_access,'_linked',remove_after_check)
    with pytest.raises(ValueError): gate(paths).check(_revision(receipt.key))
