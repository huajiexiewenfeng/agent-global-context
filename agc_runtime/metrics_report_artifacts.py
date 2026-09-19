"""Host-managed, content-minimized report bundles and source-bound cleanup.

Publication's build callback must revalidate live sources while the shared root
guard is held. Cleanup is called only by committed Capture forget under that
same guard. User copies/offline render outputs are not enrolled retroactively.
"""
import hashlib
import os
import re
from itertools import islice
from pathlib import Path

from agc_runtime.metrics_cleanup_candidates import _file_snapshot
from agc_runtime.metrics_evidence import _root
from agc_runtime.metrics_execution import _write
from agc_runtime.metrics_models import canonical, digest
from agc_runtime.metrics_result_reader import _read
from agc_runtime.metrics_source_bindings import read_source_bindings


def _names(kind,revision):
    if kind=='quality_report' and isinstance(revision,str) and re.fullmatch(r'[a-f0-9]{32}',revision):
        return ['run-'+revision+'.json','review-'+revision+'.json','report-'+revision+'.html']
    if revision is None:
        if kind=='classification_export': return ['research-cohort.json','classification-verification.json']
        if kind=='evidence_export': return ['evidence-index.json','report.html']
    raise ValueError('report_kind_invalid')


def _identity(directory):
    info=_root(directory).stat()
    if not info.st_ino: raise ValueError('report_directory_identity_unavailable')
    return dict(device=info.st_dev,inode=info.st_ino)


def _present(path):
    try: path.lstat(); return True
    except FileNotFoundError: return False


def _staging(row):
    # Reserved internal publication files, never user-facing report outputs.
    return '.'+row['name']+'.agc-pending'


def _record(ledger,value):
    fields={'schema_version','plan_id','source_binding_id','directory','directory_identity',
            'kind','revision','files','registration_id'}
    if (not isinstance(value,dict) or set(value)!=fields
            or value['schema_version']!='agc.metrics-report-registration.v1'):
        raise ValueError('report_registration_invalid')
    binding=read_source_bindings(ledger,value['plan_id'])
    directory=_root(value['directory'])
    if (str(directory)!=value['directory'] or directory.is_relative_to(_root(ledger))
            or _identity(directory)!=value['directory_identity']
            or value['source_binding_id']!=binding['binding_id']):
        raise ValueError('report_binding_changed')
    names=_names(value['kind'],value['revision'])
    if not isinstance(value['files'],list) or len(value['files'])!=len(names):
        raise ValueError('report_files_invalid')
    for name,row in zip(names,value['files']):
        if (not isinstance(row,dict) or set(row)!={'name','sha256','size'} or row['name']!=name
                or not isinstance(row['sha256'],str) or not re.fullmatch(r'[a-f0-9]{64}',row['sha256'])
                or type(row['size']) is not int or not 0<=row['size']<=2*1024*1024):
            raise ValueError('report_file_invalid')
    if value['registration_id']!='mrart_'+digest({k:v for k,v in value.items() if k!='registration_id'}):
        raise ValueError('report_registration_digest_invalid')
    return directory,binding


def publish_bundle(*,context,plan_id,directory,kind,build,revision=None):
    """Register before exclusive writes; source validation/build is inside guard."""
    if not callable(build) or not callable(context.get('commit_guard')):
        raise ValueError('report_guard_required')
    names=_names(kind,revision)
    with context['commit_guard']():
        ledger=_root(context['ledger'])
        binding=read_source_bindings(ledger,plan_id)
        files=build()  # No model call; caller rechecks live evidence here.
        if not isinstance(files,dict) or set(files)!=set(names) or any(not isinstance(v,str) for v in files.values()):
            raise ValueError('report_output_invalid')
        encoded={name:files[name].encode('utf-8') for name in names}
        if any(len(data)>2*1024*1024 for data in encoded.values()): raise ValueError('report_output_oversized')
        if canonical(read_source_bindings(ledger,plan_id))!=canonical(binding):
            raise ValueError('report_source_binding_changed')
        directory=Path(directory).absolute()
        _root(directory.parent)
        if kind=='quality_report': directory=_root(directory)
        else: directory.mkdir(exist_ok=False); directory=_root(directory)
        if directory.is_relative_to(ledger): raise ValueError('report_inside_ledger')
        if any(_present(directory/name) or _present(directory/_staging({'name':name})) for name in names):
            raise ValueError('report_output_exists')
        value=dict(schema_version='agc.metrics-report-registration.v1',plan_id=plan_id,
            source_binding_id=binding['binding_id'],directory=str(directory),directory_identity=_identity(directory),
            kind=kind,revision=revision,files=[dict(name=n,sha256=hashlib.sha256(encoded[n]).hexdigest(),
            size=len(encoded[n])) for n in names])
        value['registration_id']='mrart_'+digest(value)
        root=ledger/'report-registry'; root.mkdir(exist_ok=True); root=_root(root)
        record=root/(value['registration_id']+'.json')
        _record(ledger,value)
        _write(record,value)
        for row in value['files']:
            _record(ledger,_read(record))
            staging=directory/_staging(row)
            with staging.open('xb') as handle:
                handle.write(encoded[row['name']]); handle.flush(); os.fsync(handle.fileno())
            _check_file(directory,dict(row,name=staging.name))
            # Same-directory hard link is atomic and refuses an existing final
            # name on Windows/POSIX. Never rename-overwrite a user's file.
            os.link(staging,directory/row['name'])
            staging.unlink()
            _check_file(directory,row)
        if canonical(_read(record))!=canonical(value): raise ValueError('report_registration_changed')
        _record(ledger,value)
        return value['registration_id']


def _check_file(directory,row):
    path=directory/row['name']
    if not _present(path): return None
    snapshot=_file_snapshot(path)
    if any(snapshot[k]!=row[k] for k in ('name','sha256','size')):
        raise ValueError('report_file_changed')
    return snapshot


def _check_staging(directory,row):
    path=directory/_staging(row)
    if not _present(path): return None
    snapshot=_file_snapshot(path)
    # An interrupted private staging write need not match the complete hash.
    # The controlled name, registered directory and bounded regular-file
    # snapshot establish scope; finalized/user-facing files remain hash-bound.
    if snapshot['size']>row['size']: raise ValueError('report_staging_oversized')
    return snapshot


def cleanup_reports(ledger,receipt_id):
    """Existing forget authorization/locks/intent own this operation and recovery."""
    if not isinstance(receipt_id,str) or not re.fullmatch(r'cr_[a-f0-9]{64}',receipt_id):
        raise ValueError('report_cleanup_receipt_invalid')
    ledger=_root(ledger); root=ledger/'report-registry'
    if not _present(root): return
    root=_root(root)
    paths=sorted(islice(root.iterdir(),10001))
    if len(paths)>10000 or any(not re.fullmatch(r'mrart_[a-f0-9]{64}\.json',p.name) for p in paths):
        raise ValueError('report_inventory_invalid')
    selected=[]
    for path in paths:
        record=_read(path)
        directory,binding=_record(ledger,record)
        if path.name!=record['registration_id']+'.json': raise ValueError('report_inventory_binding_invalid')
        if any(row['receipt_id']==receipt_id for row in binding['entries']):
            snapshots=[(_check_file(directory,row),_check_staging(directory,row)) for row in record['files']]
            selected.append((path,record,directory,snapshots))
    for path,record,directory,snapshots in selected:
        for row,(snapshot,staged) in zip(record['files'],snapshots):
            if canonical(_read(path))!=canonical(record): raise ValueError('report_registration_changed')
            _record(ledger,record)
            if _check_file(directory,row)!=snapshot: raise ValueError('report_cleanup_file_changed')
            if _check_staging(directory,row)!=staged: raise ValueError('report_cleanup_staging_changed')
            if snapshot is not None: (directory/row['name']).unlink()
            if staged is not None: (directory/_staging(row)).unlink()
    if sorted(root.iterdir())!=paths: raise ValueError('report_inventory_changed')
    for path,record,directory,_ in selected:
        if canonical(_read(path))!=canonical(record): raise ValueError('report_registration_changed')
        _record(ledger,record)
        if any(_present(directory/row['name']) or _present(directory/_staging(row)) for row in record['files']):
            raise ValueError('report_cleanup_incomplete')
