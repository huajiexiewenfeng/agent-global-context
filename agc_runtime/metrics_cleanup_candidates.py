"""Read-only managed artifact selection; not a delete grant or atomic snapshot.

Only the host inventory is enumerated. Files are considered exclusively through
bound registrations and fixed artifact names. A missing terminal is unknown, not
proof of a live or dead process. Apply-time writer coordination remains required.
"""
import hashlib
import os
import re
from itertools import islice
from pathlib import Path

from agc_runtime.metrics_artifact_registry import verify_registration
from agc_runtime.metrics_evidence import _root, _linked
from agc_runtime.metrics_models import canonical, digest, instant
from agc_runtime.metrics_result_reader import _read, _attempt
from agc_runtime.metrics_source_bindings import read_source_bindings


def _inventory(root):
    paths=list(islice(root.iterdir(),10001))
    if len(paths)>10000 or any(not re.fullmatch(r'mart_[a-f0-9]{64}\.json',p.name) for p in paths):
        raise ValueError('cleanup_inventory_invalid_or_oversized')
    return sorted(paths,key=lambda p:p.name)


def _terminal(directory,dependency):
    if dependency['schema_version']=='agc.metrics-artifact-dependencies.v1':
        return _attempt({'plan_id':dependency['plan_id']},{'entry_id':dependency['entry_id']},directory)
    start=_read(directory/'started.json')
    if (set(start)!={'plan_id','started_at','status','model_called'}
            or start['plan_id']!=dependency['plan_id'] or start['status']!='in_progress'
            or start['model_called'] is not False):
        raise ValueError('cleanup_classification_start_invalid')
    instant(start['started_at'])
    if not (directory/'finished.json').exists(): return start
    end=_read(directory/'finished.json')
    if (set(end)!=set(start)|{'finished_at','classification_digest'}
            or end['plan_id']!=start['plan_id'] or end['started_at']!=start['started_at']
            or end['status'] not in ('completed','classification_error')
            or type(end['model_called']) is not bool
            or instant(end['finished_at'])<instant(start['started_at'])):
        raise ValueError('cleanup_classification_terminal_invalid')
    return end


def _file_snapshot(path):
    if any(_linked(p) for p in (path,*path.parents)):
        raise ValueError('cleanup_linked_artifact')
    with path.open('rb') as handle:
        before=os.fstat(handle.fileno())
        raw=handle.read(2*1024*1024+1)
        after=os.fstat(handle.fileno())
    current=path.stat()
    identity=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns)
    if len(raw)>2*1024*1024 or identity(before)!=identity(after) or identity(after)!=identity(current):
        raise ValueError('cleanup_artifact_changed_or_oversized')
    return dict(name=path.name,sha256=hashlib.sha256(raw).hexdigest(),size=len(raw),
                identity=dict(device=current.st_dev,inode=current.st_ino,mtime_ns=current.st_mtime_ns))


def cleanup_candidates(ledger,receipt_id):
    if not isinstance(receipt_id,str) or not re.fullmatch(r'cr_[a-f0-9]{64}',receipt_id):
        raise ValueError('cleanup_receipt_invalid')
    try:
        ledger=_root(ledger); inventory=_root(ledger/'artifact-registry')
        paths=_inventory(inventory)
        candidates=[]; pending=[]; unbound=[]
        observed=[]
        for path in paths:
            record=_read(path)
            fields={'schema_version','directory','directory_identity','dependencies','source_binding_id','registration_id'}
            if (not isinstance(record,dict) or set(record)!=fields
                    or record['schema_version']!='agc.metrics-artifact-registration.v2'
                    or path.name!=record['registration_id']+'.json'):
                raise ValueError('cleanup_registration_invalid')
            observed.append((path,record))
            if record['source_binding_id'] is None:
                unbound.append(record['registration_id'])
                continue  # Cannot infer ownership of standalone artifacts.
            dependency=record['dependencies']
            binding=read_source_bindings(ledger,dependency['plan_id'])
            if binding['binding_id']!=record['source_binding_id']:
                raise ValueError('cleanup_source_binding_changed')
            subjects=({dependency['case_id']} if dependency['schema_version']=='agc.metrics-artifact-dependencies.v1'
                      else {r['task_ref'] for r in dependency['inputs']})
            if not any(r['receipt_id']==receipt_id and r['subject_ref'] in subjects for r in binding['entries']):
                continue
            directory=_root(record['directory'])
            verified=verify_registration(ledger,directory,dependency,require_source_binding=True)
            if canonical(verified)!=canonical(record):
                raise ValueError('cleanup_registration_changed')
            terminal=_terminal(directory,dependency)
            if terminal['status']=='in_progress':
                from agc_runtime.metrics_attempt_lock import attempt_state
                if attempt_state(directory)!='inactive':
                    pending.append(record['registration_id'])
                    continue
            files=[]; absent=[]
            for name in dependency['artifacts']:
                target=directory/name
                if not target.exists() and not target.is_symlink(): absent.append(name)
                else: files.append(_file_snapshot(target))
            if canonical(_terminal(directory,dependency))!=canonical(terminal):
                raise ValueError('cleanup_terminal_changed')
            verify_registration(ledger,directory,dependency,require_source_binding=True)
            candidates.append(dict(registration_id=record['registration_id'],entry_id=dependency.get('entry_id'),
                plan_id=dependency['plan_id'],directory=str(directory),directory_identity=record['directory_identity'],
                source_binding_id=record['source_binding_id'],dependency_digest=digest(dependency),
                terminal_status=terminal['status'],terminal_digest=digest(terminal),files=files,absent_files=absent))
        if _inventory(inventory)!=paths or any(canonical(_read(p))!=canonical(v) for p,v in observed):
            raise ValueError('cleanup_inventory_changed')
        return dict(schema_version='agc.metrics-cleanup-candidates.v1',receipt_id=receipt_id,
                    mode='read_only_not_delete_authorization',candidates=candidates,pending=pending,unbound=unbound)
    except (OSError,KeyError,TypeError,AttributeError) as error:
        raise ValueError('cleanup_inventory_unavailable_or_invalid') from error
