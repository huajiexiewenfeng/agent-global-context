"""Versioned, content-minimized inputs for explicitly requested offline metrics.

Digests provide reproducibility, not authentication or anonymization. No source
content or absolute path belongs in a frozen batch. No production paths default.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone

SCHEMA = 'agc.metrics-batch.v1'
TRANSFORM = 'agc.metrics-p1.1'
PRINCIPAL = {'id': 'agent-global-context.capture', 'kind': 'runtime'}
EVENT_TYPES = ('trace.root.started', 'trace.root.completed', 'trace.root.failed', 'agc.capture.item.completed')
ERROR_CODES = ('capture_busy', 'capture_extractor_unavailable', 'capture_source_failed',
               'extractor_unavailable', 'source_failed', 'unknown')
SOURCE_NAMES = ('trace', 'receipts', 'eval')
SOURCE_STATES = ('available', 'partial', 'unavailable', 'schema_mismatch', 'not_provided', 'provided')
OP_FIELDS = {'attempt_id','trace_id','span_id','timestamp','phase','action','implementation_version',
             'outcome','trace_status','start_status','error_code'}


def _operation(raw):
    from agc_runtime.metrics_evidence import _validate
    _validate(raw)
    return dict(attempt_id=opaque(raw['attempt_id']), trace_id=opaque(raw['trace_id']),
        span_id=opaque(raw['span_id']), timestamp=utc(raw['timestamp']), phase=raw['phase'],
        action=raw['action'], implementation_version=raw['implementation_version'],
        **{key:raw.get(key) for key in ('outcome','trace_status','start_status','error_code')})


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


def opaque(value):
    if not isinstance(value, str) or not value or len(value) > 4096:
        raise ValueError('invalid_identity')
    return 'id_' + digest(value)


def instant(value):
    if not isinstance(value, str):
        raise ValueError('invalid_timestamp')
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError('timestamp_requires_timezone')
    return parsed.astimezone(timezone.utc)


def utc(value):
    return instant(value).isoformat().replace('+00:00', 'Z')


def _event(raw):
    if raw.get('principal_ref') != PRINCIPAL or raw.get('event_type') not in EVENT_TYPES:
        raise LookupError('out_of_scope')
    payload = raw.get('payload', {})
    if not isinstance(payload, dict) or raw.get('parent_span_id') is not None:
        raise ValueError('invalid_event')
    ref = payload.get('evidence_ref')
    bound = isinstance(ref, dict) and ref.get('provider') == 'agc' and ref.get('kind') == 'capture-item'
    error = payload.get('error')
    code = error.get('type') if isinstance(error, dict) else None
    return dict(event_id=opaque(raw['event_id']), trace_id=opaque(raw['trace_id']),
        span_id=opaque(raw['span_id']), timestamp=utc(raw['timestamp']), event_type=raw['event_type'],
        outcome=payload.get('outcome') if payload.get('outcome') in ('zero', 'collected') else 'unknown',
        error_code=code if code in ERROR_CODES else 'unknown',
        receipt_id=opaque(ref['ref']) if bound else None,
        reference_present=bound, version_present=bool(payload.get('extractor_version')),
        implementation_version=payload.get('implementation_version') if isinstance(payload.get('implementation_version'),str)
            and re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+',payload['implementation_version']) else None)


def _receipt(raw):
    if raw.get('redacted_by_forget') is True:
        raise LookupError('revoked')
    if raw.get('redacted_by_forget') is not False:
        raise ValueError('forget_state_unknown')
    return dict(receipt_id=opaque(raw['receipt_id']), timestamp=utc(raw['updated_at']),
        status=raw['status'] if raw.get('status') in ('complete', 'discovered', 'failed', 'retryable', 'excluded', 'coalesced') else 'unknown')


def _evaluation(raw):
    if raw.get('subject', {}).get('principal_ref') != PRINCIPAL:
        raise LookupError('out_of_scope')
    if raw.get('schema_version') != 'eval.result.v0.1' or raw.get('status') not in ('pass', 'fail', 'error', 'insufficient_evidence'):
        raise ValueError('unsupported_result')
    if instant(raw['started_at']) > instant(raw['finished_at']):
        raise ValueError('invalid_result_time')
    return dict(result_id=opaque(raw['result_id']), case_id=opaque(raw['case_id']),
        evaluation_key=opaque(raw['evaluation_key']), timestamp=utc(raw['finished_at']),
        started_at=utc(raw['started_at']), status=raw['status'], profile_id=opaque(canonical(raw['profile_ref'])))


def freeze_batch(*, start, end, cutoff, events=None, receipts=None, evaluations=None, sources=None, data_kind='observed', operations=None, business=None):
    lower, upper, boundary = map(instant, (start, end, cutoff))
    if not lower < upper <= boundary:
        raise ValueError('invalid_window')
    if data_kind not in ('observed', 'synthetic'):
        raise ValueError('invalid_data_kind')
    excluded, collections = [], {}
    from agc_runtime.metrics_business import validate_business_record
    inputs = (events, receipts, evaluations) + ((operations,) if operations is not None else ()) + ((business,) if business is not None else ())
    names = ('events','receipts','evaluations') + (('operations',) if operations is not None else ()) + (('business',) if business is not None else ())
    source_names = SOURCE_NAMES + (('operations',) if operations is not None else ()) + (('business',) if business is not None else ())
    projections = (_event,_receipt,_evaluation) + ((_operation,) if operations is not None else ()) + ((validate_business_record,) if business is not None else ())
    for name, rows, project in zip(names, inputs, projections):
        result = []
        for raw in (() if rows is None else rows):
            identifier = digest(raw)  # discarded fields never persist, even on errors
            try:
                item = project(raw)
                observed = instant(item['timestamp'])
                if observed > boundary or (name not in ('events','operations','business') and not lower <= observed < upper):
                    raise LookupError('outside_window')
                result.append(item)
            except LookupError as error:
                reason = str(error) if str(error) in ('out_of_scope', 'revoked', 'outside_window') else 'invalid_record'
                excluded.append(dict(source=name, id=identifier, reason=reason))
            except (ValueError, TypeError, KeyError, AttributeError):
                excluded.append(dict(source=name, id=identifier, reason='invalid_record'))
        collections[name] = result
    # Retain pre-window starts only as context for a selected trace. They are not
    # members of the start cohort. Observe selected starts up to explicit cutoff.
    relevant = {e['trace_id'] for e in collections['events'] if lower <= instant(e['timestamp']) < upper}
    for name in ('operations','business'):
        if name not in collections:
            continue
        selected = {r['attempt_id'] for r in collections[name] if lower <= instant(r['timestamp']) < upper}
        kept_operations = []
        for row in collections[name]:
            if row['attempt_id'] in selected:
                kept_operations.append(row)
                if name == 'operations':
                    relevant.add(row['trace_id'])
            else:
                excluded.append(dict(source=name, id=digest(row), reason='outside_window'))
        collections[name] = kept_operations
    kept = []
    for item in collections['events']:
        if item['trace_id'] in relevant:
            kept.append(item)
        else:
            excluded.append(dict(source='events', id=digest(item), reason='outside_window'))
    collections['events'] = kept
    source_rows = sources if sources is not None else [
        dict(name=name, status='provided' if data is not None else 'not_provided', invalid_records=0)
        for name, data in zip(source_names, inputs)]
    safe_sources = []
    for name in source_names:
        matches = [s for s in source_rows if s.get('name') == name]
        if len(matches) != 1 or matches[0].get('status') not in SOURCE_STATES:
            raise ValueError('invalid_source_manifest')
        source = matches[0]
        invalid = source.get('invalid_records', 0)
        if type(invalid) is not int or invalid < 0:
            raise ValueError('invalid_source_manifest')
        safe_sources.append(dict(name=name, status=source['status'], invalid_records=invalid,
            read_at=utc(source['read_at']) if source.get('read_at') else None,
            source_id=source.get('source_id')))
    body = dict(schema_version=SCHEMA, definition_version='1.1', transform_version=TRANSFORM, data_kind=data_kind,
        window=dict(start=utc(start), end=utc(end), cutoff=utc(cutoff), timezone='Asia/Shanghai'),
        sources=safe_sources, excluded=sorted(excluded, key=canonical),
        **{name: sorted(rows, key=canonical) for name, rows in collections.items()})
    if operations is not None:
        body.update(schema_version='agc.metrics-batch.v2', transform_version='agc.metrics-p2.1')
    if business is not None:
        body.update(schema_version='agc.metrics-batch.v3', transform_version='agc.metrics-p2.2')
    body['transform_version'] += '.trace-version1'
    body['batch_id'] = 'agcm_' + digest(body)
    return body


def validate_batch(value):
    """Reject incompatible/tampered snapshots; never execute content from them."""
    try:
        keys = {'schema_version', 'definition_version', 'transform_version', 'window', 'sources',
                'excluded', 'events', 'receipts', 'evaluations', 'batch_id', 'data_kind'}
        v3 = isinstance(value,dict) and value.get('schema_version') == 'agc.metrics-batch.v3'
        v2 = isinstance(value, dict) and (value.get('schema_version') == 'agc.metrics-batch.v2' or (v3 and 'operations' in value))
        source_names = SOURCE_NAMES + (('operations',) if v2 else ()) + (('business',) if v3 else ())
        if v3:
            keys.add('business')
        if v2:
            keys.add('operations')
        if not isinstance(value, dict) or set(value) != keys:
            raise ValueError
        expected = ('agc.metrics-batch.v3','1.1','agc.metrics-p2.2') if v3 else ('agc.metrics-batch.v2','1.1','agc.metrics-p2.1') if v2 else (SCHEMA,'1.1',TRANSFORM)
        enriched=value['transform_version']==expected[2]+'.trace-version1'
        if (value['schema_version'], value['definition_version']) != expected[:2] or (value['transform_version']!=expected[2] and not enriched):
            raise ValueError
        if value['data_kind'] not in ('observed','synthetic'):
            raise ValueError
        if value['batch_id'] != 'agcm_' + digest({k: v for k, v in value.items() if k != 'batch_id'}):
            raise ValueError
        window = value['window']
        if set(window) != {'start', 'end', 'cutoff', 'timezone'} or window['timezone'] != 'Asia/Shanghai':
            raise ValueError
        if not instant(window['start']) < instant(window['end']) <= instant(window['cutoff']):
            raise ValueError
        allowed = {
            'events': {'event_id','trace_id','span_id','timestamp','event_type','outcome','error_code','receipt_id','reference_present','version_present'},
            'receipts': {'receipt_id','timestamp','status'},
            'evaluations': {'result_id','case_id','evaluation_key','timestamp','started_at','status','profile_id'},
            'sources': {'name','status','invalid_records','read_at','source_id'},
            'excluded': {'source','id','reason'},
        }
        if enriched:
            allowed['events']=allowed['events']|{'implementation_version'}
        if v2:
            allowed['operations'] = OP_FIELDS
        if v3:
            from agc_runtime.metrics_business import validate_business_record
            if not isinstance(value['business'],list):
                raise ValueError
            for row in value['business']:
                validate_business_record(row)
        for name, fields in allowed.items():
            if not isinstance(value[name], list):
                raise ValueError
            for row in value[name]:
                if not isinstance(row, dict) or set(row) != fields:
                    raise ValueError
                if any(v is not None and type(v) not in (str, bool, int) for v in row.values()):
                    raise ValueError
                if 'timestamp' in row:
                    instant(row['timestamp'])
                for key in ('event_id','trace_id','span_id','receipt_id','case_id','evaluation_key','result_id','profile_id','source_id','attempt_id'):
                    if key in row and row[key] is not None and not re.fullmatch(r'id_[0-9a-f]{64}', row[key]):
                        raise ValueError
                if name == 'events':
                    version=row.get('implementation_version')
                    if version is not None and (not isinstance(version,str) or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+',version)):
                        raise ValueError
                    if (row['event_type'] not in EVENT_TYPES or row['outcome'] not in ('zero','collected','unknown')
                        or row['error_code'] not in ERROR_CODES
                        or type(row['reference_present']) is not bool or type(row['version_present']) is not bool
                        or any(row[k] is None for k in ('event_id','trace_id','span_id'))):
                        raise ValueError
                elif name == 'receipts':
                    if row['receipt_id'] is None or row['status'] not in ('complete','discovered','failed','retryable','excluded','coalesced','unknown'):
                        raise ValueError
                elif name == 'evaluations':
                    if (row['status'] not in ('pass','fail','error','insufficient_evidence')
                        or instant(row['started_at']) > instant(row['timestamp'])
                        or any(row[k] is None for k in ('result_id','case_id','evaluation_key','profile_id'))):
                        raise ValueError
                elif name == 'sources':
                    if (row['name'] not in source_names or row['status'] not in SOURCE_STATES
                        or type(row['invalid_records']) is not int or row['invalid_records'] < 0):
                        raise ValueError
                    if row['read_at'] is not None:
                        instant(row['read_at'])
                elif name == 'excluded':
                    if (row['source'] not in ('events','receipts','evaluations') + (('operations',) if v2 else ()) + (('business',) if v3 else ())
                        or row['reason'] not in ('out_of_scope','revoked','outside_window','invalid_record')
                        or not re.fullmatch(r'[0-9a-f]{64}',row['id'])):
                        raise ValueError
                elif name == 'operations':
                    from agc_runtime.metrics_evidence import ERRORS
                    if (row['phase'] not in ('started','finished') or row['action'] not in ('cycle','run')
                        or any(row[k] is None for k in ('attempt_id','trace_id','span_id'))
                        or not isinstance(row['implementation_version'], str)
                        or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+',row['implementation_version'])):
                        raise ValueError
                    terminal = ('outcome','trace_status','start_status','error_code')
                    if row['phase'] == 'started':
                        if any(row[k] is not None for k in terminal):
                            raise ValueError
                    elif (row['outcome'] not in ('completed','failed')
                          or row['trace_status'] not in ('recorded','disabled','suppressed','unavailable')
                          or row['start_status'] not in ('recorded','unavailable')
                          or row['error_code'] not in ERRORS | {None}
                          or (row['outcome'] == 'completed') != (row['error_code'] is None)):
                        raise ValueError
        if sorted(s['name'] for s in value['sources']) != sorted(source_names):
            raise ValueError
        return json.loads(canonical(value))
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError) as error:
        raise ValueError('metrics_batch_invalid') from error
