"""Host-ledger inventory of exact execution directories, not deletion authority.

Callers must reconstruct expected dependencies from the validated plan/source.
Records locate managed output without scanning user directories. They contain no
source body and do not implement forget, authenticate consent, or authorize an
arbitrary path to be deleted. Directory identity changes fail verification.
"""
from pathlib import Path

from agc_runtime.metrics_evidence import _root
from agc_runtime.metrics_models import canonical, digest
from agc_runtime.metrics_result_reader import _read


def _source_binding_id(ledger, expected):
    from agc_runtime.metrics_source_bindings import read_source_bindings, _plan_id
    path=_root(ledger)/'source-bindings'/(_plan_id(expected['plan_id'])+'.json')
    if not path.parent.exists() and not path.parent.is_symlink():
        return None
    parent=_root(path.parent)
    path=parent/path.name
    if not path.exists() and not path.is_symlink():
        return None
    binding=read_source_bindings(ledger,expected['plan_id'])
    subjects={r['subject_ref'] for r in binding['entries']}
    if expected['schema_version']=='agc.metrics-artifact-dependencies.v1':
        if expected['case_id'] not in subjects:
            raise ValueError('artifact_source_case_missing')
    elif subjects!={r['task_ref'] for r in expected['inputs']}:
        raise ValueError('artifact_source_inputs_mismatch')
    return binding['binding_id']


def _record(ledger, directory, expected):
    root = _root(directory)
    kinds = {
        'agc.metrics-artifact-dependencies.v1': ('entry_id', ['result.json', 'receipt.json']),
        'agc.classification-artifact-dependencies.v1': ('plan_id', ['classification.json', 'receipt.json']),
    }
    if not isinstance(expected, dict) or expected.get('schema_version') not in kinds:
        raise ValueError('artifact_dependency_kind_invalid')
    identity_field, artifacts = kinds[expected['schema_version']]
    if (root.name != expected.get(identity_field) or expected.get('artifacts') != artifacts
            or expected.get('dependency_id') != 'mdep_'+digest({k:v for k,v in expected.items() if k!='dependency_id'})):
        raise ValueError('artifact_dependency_identity_invalid')
    if canonical(_read(root/'dependencies.json')) != canonical(expected):
        raise ValueError('artifact_local_dependencies_changed')
    info = root.stat()
    if not info.st_ino:
        raise ValueError('artifact_directory_identity_unavailable')
    body = dict(schema_version='agc.metrics-artifact-registration.v2', directory=str(root),
                directory_identity=dict(device=info.st_dev, inode=info.st_ino),
                dependencies=expected,source_binding_id=_source_binding_id(ledger,expected))
    body['registration_id'] = 'mart_'+digest(dict(directory=str(root),dependency_id=expected['dependency_id']))
    return body


def register_execution_directory(ledger, directory, expected, *, require_source_binding=False):
    from agc_runtime.metrics_execution import _write
    root = _root(ledger)
    record = _record(root, directory, expected)
    if require_source_binding and record['source_binding_id'] is None:
        raise ValueError('artifact_source_binding_required')
    if Path(record['directory']).is_relative_to(root):
        raise ValueError('artifact_directory_inside_ledger')
    registry = root/'artifact-registry'
    registry.mkdir(exist_ok=True)
    registry = _root(registry)
    _write(registry/(record['registration_id']+'.json'), record)
    # Recheck both ends before the caller may send content to its model.
    return verify_registration(root, directory, expected,require_source_binding=require_source_binding)


def verify_registration(ledger, directory, expected, *, require_source_binding=False):
    registry = _root(_root(ledger)/'artifact-registry')
    record = _record(ledger, directory, expected)
    if require_source_binding and record['source_binding_id'] is None:
        raise ValueError('artifact_source_binding_required')
    saved = _read(registry/(record['registration_id']+'.json'))
    if canonical(saved) != canonical(record):
        raise ValueError('artifact_registration_changed')
    return record
