"""Optional service-boundary metadata. No replay, content cache or authority claims."""
from __future__ import annotations

import json
import os
import re
from dataclasses import replace
from datetime import datetime, timezone
from functools import wraps
from uuid import uuid4
from typing import get_args

from agc_runtime import __version__
from agc_runtime.contracts import Status
from agc_runtime.metrics_evidence import ENV, _linked, _root, _timestamp, _unique_fields
from agc_runtime.metrics_models import canonical, digest, instant, opaque

SCHEMA = 'agc.business-evidence.v2'
ACTIONS = {
    'agc.read': {'overview':'recall','search':'recall','get':'recall','history':'recall',
                 'evidence':'recall','capture_review_status':'review_status'},
    'agc.write': {'confirm':'memory_write','update':'memory_write','observe':'memory_write'},
    'agc.admin': {'capture_review_notice':'review_notice','capture_preview':'review_preview'},
}
FIELDS = {'schema','attempt_id','phase','timestamp','tool','action','stage','implementation_version',
          'response_status','error_code','objects','observation_refs','batch_ref','request_object_ref',
          'write_status','review_receipt_status','actual_use','preview_delivery','task_ref',
          'confirmation_ref','trace_ref','configuration_identity','start_status'}
ERRORS = {'invalid_request','invalid_action','id_required','not_found','read_failed','write_failed',
          'capture_read_busy','capture_not_found','capture_integrity_degraded','admin_failed','admin_busy','unknown'}
STATUSES = set(get_args(Status))


def _id(value):
    return opaque(value) if isinstance(value,str) and value else None


def validate_business_record(row):
    fields=FIELDS | {'request_source'} if isinstance(row,dict) and row.get('schema')==SCHEMA else FIELDS
    if not isinstance(row,dict) or set(row) != fields or row['schema'] not in (SCHEMA,'agc.business-evidence.v1'):
        raise ValueError('invalid_business_record')
    provenance=row.get('request_source')
    if provenance is not None:
        if (not isinstance(provenance,dict)
                or set(provenance)!={'ref','revision','content_digest','verification'}
                or provenance['verification']!='caller_supplied_unverified'
                or any(not isinstance(provenance[k],str) or not re.fullmatch(r'id_[a-f0-9]{64}',provenance[k]) for k in ('ref','revision'))
                or not isinstance(provenance['content_digest'],str)
                or not re.fullmatch(r'[a-f0-9]{64}',provenance['content_digest'])):
            raise ValueError('invalid_request_provenance')
    if not isinstance(row['attempt_id'],str) or not re.fullmatch(r'biz_[a-f0-9]{32}',row['attempt_id']):
        raise ValueError('invalid_identity')
    if row['tool'] not in ACTIONS or ACTIONS[row['tool']].get(row['action']) != row['stage']:
        raise ValueError('invalid_operation')
    instant(row['timestamp'])
    if not isinstance(row['implementation_version'],str) or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+',row['implementation_version']):
        raise ValueError('invalid_version')
    if row['phase'] not in ('started','finished'):
        raise ValueError('invalid_phase')
    for key in ('task_ref','confirmation_ref','trace_ref','configuration_identity'):
        if row[key] is not None:
            raise ValueError('unverified_context')
    for key in ('batch_ref','request_object_ref'):
        if row[key] is not None and (not isinstance(row[key],str) or not re.fullmatch(r'id_[a-f0-9]{64}',row[key])):
            raise ValueError('invalid_reference')
    if (row['actual_use'] != 'unknown' or row['preview_delivery'] not in ('unknown','runtime_returned')
            or (row['preview_delivery']=='runtime_returned' and
                (row['stage']!='review_preview' or row['phase']!='finished' or row['response_status']!='accepted'))):
        raise ValueError('unsupported_claim')
    if row['write_status'] not in ('unknown','accepted','not_applicable') or row['review_receipt_status'] not in ('unknown','recorded','failed','not_applicable'):
        raise ValueError('invalid_status')
    if row['response_status'] not in STATUSES | {None} or row['error_code'] not in ERRORS | {None}:
        raise ValueError('invalid_status')
    if row['start_status'] not in ('recorded','unavailable',None):
        raise ValueError('invalid_status')
    if not isinstance(row['objects'],list) or len(row['objects']) > 100:
        raise ValueError('invalid_objects')
    for obj in row['objects']:
        if not isinstance(obj,dict) or set(obj) != {'id','version','version_kind'}:
            raise ValueError('invalid_object')
        if not isinstance(obj['id'],str) or not re.fullmatch(r'id_[a-f0-9]{64}',obj['id']):
            raise ValueError('invalid_object')
        if obj['version_kind'] in ('returned_representation','written_content'):
            if not isinstance(obj['version'],str) or not re.fullmatch(r'[a-f0-9]{64}',obj['version']):
                raise ValueError('invalid_object_version')
        elif obj['version_kind'] != 'unknown' or obj['version'] is not None:
            raise ValueError('invalid_object_version')
    if (not isinstance(row['observation_refs'],list) or len(row['observation_refs']) > 100
            or any(not isinstance(v,str) or not re.fullmatch(r'id_[a-f0-9]{64}',v) for v in row['observation_refs'])):
        raise ValueError('invalid_observation_refs')
    if row['phase'] == 'started' and (row['response_status'] is not None or row['error_code'] is not None
            or row['objects'] or row['start_status'] is not None):
        raise ValueError('invalid_start')
    if row['phase'] == 'finished' and (row['response_status'] is None or row['start_status'] is None):
        raise ValueError('invalid_finish')
    return json.loads(canonical(row))


def _append(directory,row):
    validate_business_record(row)
    serialized = canonical(row)
    if len(serialized.encode('utf-8')) > 65536:
        raise ValueError('record_too_large')
    root = _root(directory)
    with (root / (row['attempt_id']+'.'+row['phase']+'.json')).open('x',encoding='utf-8',newline='\n') as stream:
        stream.write(serialized)
        stream.flush()
        os.fsync(stream.fileno())


def _begin(tool,request):
    root = _root(os.environ[ENV])
    directory = root / 'business'
    directory.mkdir(exist_ok=True)
    _root(directory)
    ids = request.get('capture_observation_ids',[])
    if not isinstance(ids,list) or len(ids)>100:
        ids=[]
    source=None
    observation=request.get('observation')
    candidate=observation.get('source') if isinstance(observation,dict) else None
    if (isinstance(candidate,dict) and all(isinstance(candidate.get(k),str) and candidate[k] for k in ('ref','revision','content_hash'))
            and re.fullmatch(r'[a-f0-9]{64}',candidate['content_hash'])):
        source=dict(ref=opaque(candidate['ref']),revision=opaque(candidate['revision']),
                    content_digest=candidate['content_hash'],verification='caller_supplied_unverified')
    row = dict(schema=SCHEMA, attempt_id='biz_'+uuid4().hex, phase='started',request_source=source,
        timestamp=_timestamp(datetime.now(timezone.utc)), tool=tool,action=request['action'],
        stage=ACTIONS[tool][request['action']],implementation_version=__version__,response_status=None,
        error_code=None,objects=[],observation_refs=sorted({_id(v) for v in ids if isinstance(v,str) and v}),
        batch_ref=_id(request.get('batch_digest')),request_object_ref=_id(request.get('id')),
        write_status='unknown',review_receipt_status='unknown',actual_use='unknown',preview_delivery='unknown',
        task_ref=None,confirmation_ref=None,trace_ref=None,configuration_identity=None,start_status=None)
    try:
        _append(directory,row)
        status='recorded'
    except Exception:
        status='unavailable'
    return directory,row,status


def _finish(directory,start,start_status,response):
    row=dict(start,phase='finished',timestamp=_timestamp(datetime.now(timezone.utc)),
             response_status=response.status,start_status=start_status)
    if response.error:
        code=response.error.get('code')
        row['error_code']=code if code in ERRORS else 'unknown'
    data=response.data
    if row['stage']=='recall' and response.status=='accepted':
        objects = [data['item']] if isinstance(data.get('item'),dict) else data.get('results',data.get('cards',[]))
        if not isinstance(objects,list) or len(objects)>100:
            raise ValueError('invalid_objects')
        row['objects']=[dict(id=opaque(obj['id']),version=digest(obj),version_kind='returned_representation')
                        for obj in objects if isinstance(obj,dict) and isinstance(obj.get('id'),str) and obj['id']]
    elif row['stage']=='review_preview' and response.status=='accepted':
        preview=data.get('preview')
        if not isinstance(preview,dict) or not isinstance(preview.get('memory_id'),str):
            raise ValueError('invalid_preview_response')
        row['preview_delivery']='runtime_returned'
        row['objects']=[dict(id=opaque(preview['memory_id']),version=preview['version'],version_kind='returned_representation')]
    elif row['stage']=='memory_write':
        row['write_status']='not_applicable'
        if response.status=='accepted' and isinstance(data.get('memory_id'),str) and data['memory_id']:
            row['write_status']='accepted'
            row['objects']=[dict(id=opaque(data['memory_id']),version=None,version_kind='unknown')]
            version=data.get('memory_version')
            if isinstance(version,str) and re.fullmatch(r'[a-f0-9]{64}',version):
                row['objects'][0].update(version=version,version_kind='written_content')
        row['review_receipt_status']='not_applicable' if not row['observation_refs'] else 'unknown'
        if 'capture_review_receipt_failed' in response.warnings:
            row['review_receipt_status']='failed'
        elif type(data.get('capture_reviewed_count')) is int and data['capture_reviewed_count'] == len(row['observation_refs']):
            row['review_receipt_status']='recorded'
    _append(directory,row)


def measured_dispatch(tool):
    """Keep the original response and exception behavior; record only fixed actions."""
    def decorate(function):
        @wraps(function)
        def wrapped(paths,request):
            if (ENV not in os.environ or not isinstance(request,dict)
                    or not isinstance(request.get('action'),str) or request['action'] not in ACTIONS[tool]):
                return function(paths,request)
            attempt=None
            try:
                attempt=_begin(tool,request)
            except Exception:
                pass
            response=function(paths,request)
            recorded=False
            if attempt is not None:
                try:
                    _finish(*attempt,response)
                    recorded=attempt[2]=='recorded'
                except Exception:
                    pass
            if not recorded:
                return replace(response,warnings=(*response.warnings,'metrics_evidence_unavailable'))
            return response
        return wrapped
    return decorate


def read_business_records(directory):
    result=dict(status='unavailable',records=[],invalid_records=0)
    try:
        root=_root(directory)
        for path in sorted(root.glob('*.json')):
            try:
                if _linked(path) or path.stat().st_size>65536:
                    raise ValueError('invalid_file')
                before=path.stat()
                row=validate_business_record(json.loads(path.read_text(encoding='utf-8'),object_pairs_hook=_unique_fields))
                after=path.stat()
                if (before.st_mtime_ns,before.st_size)!=(after.st_mtime_ns,after.st_size):
                    raise ValueError('changed_file')
                if path.name != row['attempt_id']+'.'+row['phase']+'.json':
                    raise ValueError('wrong_file')
                result['records'].append(row)
            except (OSError,ValueError,TypeError,KeyError):
                result['invalid_records']+=1
        result['status']='partial' if result['invalid_records'] else 'available'
    except (OSError,ValueError,TypeError):
        pass
    return result
