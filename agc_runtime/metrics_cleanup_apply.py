"""Narrow, explicitly authorized removal of a verified artifact snapshot.

This library is not a production forget entry point. Its trusted host must bind
the ledger, confirmation and shared commit guard. It neither invalidates sources
nor rolls back deletions, and does not claim to handle hostile concurrent writers
which ignore the shared lock. Interrupted/partial cleanup needs a fresh snapshot.
"""
import json
from contextlib import nullcontext

from agc_runtime.metrics_artifact_registry import verify_registration
from agc_runtime.metrics_cleanup_candidates import cleanup_candidates, _file_snapshot, _terminal
from agc_runtime.metrics_evidence import _root
from agc_runtime.metrics_models import canonical, digest
from agc_runtime.metrics_result_reader import _read


def _verify_candidate(ledger,candidate):
    directory=_root(candidate['directory'])
    record=_read(_root(ledger/'artifact-registry')/(candidate['registration_id']+'.json'))
    verified=verify_registration(ledger,directory,record['dependencies'],require_source_binding=True)
    if (verified['registration_id']!=candidate['registration_id']
            or verified['directory_identity']!=candidate['directory_identity']
            or verified['source_binding_id']!=candidate['source_binding_id']
            or digest(verified['dependencies'])!=candidate['dependency_digest']
            or digest(_terminal(directory,verified['dependencies']))!=candidate['terminal_digest']):
        raise ValueError('cleanup_candidate_changed')
    return directory


def apply_cleanup(*,ledger,snapshot,authorization,commit_guard):
    if authorization!='explicit_user_request':
        raise PermissionError('artifact_cleanup_authorization_required')
    if not callable(commit_guard) or not isinstance(snapshot,dict):
        raise ValueError('artifact_cleanup_host_binding_required')
    # Freeze caller input; never construct delete targets from unverified input.
    expected=json.loads(canonical(snapshot))
    receipt=expected.get('receipt_id')
    with commit_guard():
        ledger=_root(ledger)
        current=cleanup_candidates(ledger,receipt)
        if canonical(current)!=canonical(expected):
            raise ValueError('artifact_cleanup_snapshot_changed')
        if current['pending'] or current['unbound']:
            raise ValueError('artifact_cleanup_unresolved_inventory')
        deleted=[]
        result=dict(schema_version='agc.metrics-cleanup-result.v1',receipt_id=receipt,
                    snapshot_digest=digest(current),status='selected_artifacts_removed',
                    deleted=deleted,error_code=None)
        try:
            for candidate in current['candidates']:
                for artifact in candidate['files']:
                    from agc_runtime.metrics_attempt_lock import attempt_lock
                    guard=(attempt_lock(candidate['directory'])
                           if candidate['terminal_status']=='in_progress' else nullcontext())
                    with guard:
                        directory=_verify_candidate(ledger,candidate)
                        target=directory/artifact['name']
                        # Inactive unfinished attempts stay exclusively locked
                        # during deletion. No terminal/model usage is fabricated.
                        if canonical(_file_snapshot(target))!=canonical(artifact):
                            raise ValueError('artifact_cleanup_file_changed')
                        target.unlink()
                        deleted.append(dict(registration_id=candidate['registration_id'],name=artifact['name']))
            # Confirm the selected files are absent and all other snapshot
            # metadata still agrees. This detects observed replacement, not
            # arbitrary writes after the lock has been released.
            wanted=json.loads(canonical(current))
            for candidate in wanted['candidates']:
                candidate['absent_files']=sorted(candidate['absent_files']+[f['name'] for f in candidate['files']])
                candidate['files']=[]
            final=cleanup_candidates(ledger,receipt)
            for candidate in final['candidates']:
                candidate['absent_files'].sort()
            if canonical(wanted)!=canonical(final):
                raise ValueError('artifact_cleanup_postcondition_changed')
        except (OSError,ValueError,KeyError,TypeError,RuntimeError):
            result['status']='cleanup_incomplete'
            result['error_code']='artifact_cleanup_failed'
        return result
