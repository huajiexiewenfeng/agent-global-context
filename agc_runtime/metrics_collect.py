"""Read-only adapters for known local metadata stores, without store initialization."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from agc_runtime.metrics_models import freeze_batch, opaque


def _now():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def _database(path, name):
    status = dict(name=name, status='not_provided', invalid_records=0, read_at=_now())
    if path is None:
        return [], status
    path = Path(path).expanduser().resolve()
    status['source_id'] = opaque(str(path))
    if not path.is_file():
        status['status'] = 'unavailable'
        return [], status
    rows = []
    connection = None
    try:
        connection = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=2)
        connection.execute('PRAGMA query_only=ON')
        connection.execute('BEGIN')
        connection.row_factory = sqlite3.Row
        if name == 'trace':
            cursor = connection.execute('SELECT event_id, trace_id, span_id, parent_span_id, timestamp, event_type, principal_ref, payload_json FROM events')
        else:
            cursor = connection.execute('SELECT result_json FROM results')
        for record in cursor:
            try:
                if name == 'trace':
                    row = dict(record)
                    row['principal_ref'] = json.loads(row['principal_ref']) if row['principal_ref'] else None
                    row['payload'] = json.loads(row.pop('payload_json'))
                else:
                    row = json.loads(record['result_json'])
                    if not isinstance(row, dict):
                        raise ValueError
                rows.append(row)
            except (ValueError, TypeError, KeyError):
                status['invalid_records'] += 1
        status['status'] = 'partial' if status['invalid_records'] else 'available'
    except sqlite3.OperationalError as error:
        # These codes never include the database path, SQL text or row content.
        status['status'] = 'schema_mismatch' if ('no such table' in str(error) or 'no such column' in str(error)) else 'unavailable'
        rows = []
    except (sqlite3.Error, OSError):
        status['status'] = 'unavailable'
        rows = []
    finally:
        if connection is not None:
            connection.close()
    return rows, status


def _receipts(directory):
    status = dict(name='receipts', status='not_provided', invalid_records=0, read_at=_now())
    if directory is None:
        return [], status
    root = Path(directory).expanduser().resolve()
    status['source_id'] = opaque(str(root))
    if not root.is_dir():
        status['status'] = 'unavailable'
        return [], status
    rows = []
    try:
        paths = sorted(root.glob('*.json'))
        for path in paths:
            try:
                if path.is_symlink() or path.resolve().parent != root:
                    raise ValueError
                before = path.stat()
                if before.st_size > 1024 * 1024:
                    raise ValueError
                value = json.loads(path.read_text(encoding='utf-8'))
                after = path.stat()
                if (before.st_mtime_ns, before.st_size) != (after.st_mtime_ns, after.st_size):
                    raise ValueError
                if not isinstance(value, dict) or path.stem != value.get('receipt_id'):
                    raise ValueError
                rows.append(value)
            except (ValueError, OSError, UnicodeError):
                status['invalid_records'] += 1
        status['status'] = 'partial' if status['invalid_records'] else 'available'
    except OSError:
        status['status'] = 'unavailable'
        rows = []
    return rows, status


def collect_batch(*, start, end, cutoff, trace_db=None, eval_db=None, receipts_dir=None, data_kind='observed', attempts_dir=None, business_dir=None):
    # Validate the window before any source I/O.
    freeze_batch(start=start, end=end, cutoff=cutoff, data_kind=data_kind)
    events, trace = _database(trace_db, 'trace')
    results, evaluation = _database(eval_db, 'eval')
    receipts, receipt = _receipts(receipts_dir)
    sources = [trace, receipt, evaluation]
    business = None
    if business_dir is not None:
        from agc_runtime.metrics_business import read_business_records
        snapshot = read_business_records(business_dir)
        business = snapshot['records']
        sources.append(dict(name='business',status=snapshot['status'],invalid_records=snapshot['invalid_records'],
            read_at=_now(),source_id=opaque(str(Path(business_dir).resolve()))))
    operations = None
    if attempts_dir is not None:
        from agc_runtime.metrics_evidence import read_capture_attempts
        snapshot = read_capture_attempts(attempts_dir)
        operations = [row[phase] for row in snapshot['attempts'] for phase in ('started','finished') if row[phase] is not None]
        sources.append(dict(name='operations', status=snapshot['status'], invalid_records=snapshot['invalid_records'],
            read_at=_now(), source_id=opaque(str(Path(attempts_dir).resolve()))))
    return freeze_batch(start=start, end=end, cutoff=cutoff, events=events, receipts=receipts,
        evaluations=results, sources=sources, data_kind=data_kind, operations=operations, business=business)
