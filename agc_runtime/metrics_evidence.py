"""Opt-in, content-free Capture attempt receipts, independent of Trace delivery.

Only the instrumented CLI boundary is observed, not every process or Capture item.
Records are local metadata, not proof of completeness, authenticity or quality.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from agc_runtime import __version__
from agc_runtime.metrics_models import canonical, instant

ENV = 'AGC_METRICS_EVIDENCE_DIR'
SCHEMA = 'agc.capture-attempt.v1'
COUNTS = {'attempted_count', 'completed_count', 'failed_count', 'observation_count'}
ERRORS = {'capture_disabled', 'capture_mode_unsupported', 'capture_sources_unconfigured',
          'capture_busy', 'capture_extractor_unavailable', 'capture_source_failed',
          'capture_integrity_failed', 'unknown'}
BASE = {'schema', 'attempt_id', 'trace_id', 'span_id', 'action', 'phase', 'timestamp',
        'implementation_version', 'recorder_version', 'configuration_identity'}
TERMINAL = {'outcome', 'trace_status', 'error_code', 'counts', 'start_status'}


def _timestamp(value):
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('timezone_required')
    return value.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


def _root(value):
    path = Path(value)
    if not path.is_absolute() or not path.is_dir():
        raise ValueError('invalid_evidence_root')
    if any(_linked(p) for p in (path, *path.parents)):
        raise ValueError('linked_evidence_root')
    return path.resolve()


def _linked(path):
    # Windows reparse points include junctions; this API also works on Python 3.10.
    return path.is_symlink() or bool(getattr(path.lstat(), 'st_file_attributes', 0) & 0x400)


def _unique_fields(pairs):
    row = {}
    for key, value in pairs:
        if key in row:
            raise ValueError('duplicate_field')
        row[key] = value
    return row


def _validate(row):
    if not isinstance(row, dict) or row.get('phase') not in ('started', 'finished'):
        raise ValueError('invalid_record')
    if set(row) != BASE | (TERMINAL if row['phase'] == 'finished' else set()):
        raise ValueError('invalid_fields')
    if row['schema'] != SCHEMA or row['action'] not in ('cycle', 'run'):
        raise ValueError('invalid_record')
    for key, prefix in (('attempt_id', 'cap_'), ('trace_id', 'trc_agc_'), ('span_id', 'spn_agc_')):
        if not isinstance(row[key], str) or not re.fullmatch(prefix + '[a-f0-9]{32}', row[key]):
            raise ValueError('invalid_identity')
    instant(row['timestamp'])
    if (not isinstance(row['implementation_version'], str)
            or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', row['implementation_version'])
            or row['recorder_version'] != 'p2.1' or row['configuration_identity'] is not None):
        raise ValueError('invalid_version')
    if row['phase'] == 'finished':
        if (row['outcome'] not in ('completed', 'failed')
                or row['trace_status'] not in ('disabled', 'suppressed', 'unavailable', 'recorded')
                or row['start_status'] not in ('recorded', 'unavailable')
                or row['error_code'] not in ERRORS | {None}
                or (row['outcome'] == 'completed' and row['error_code'] is not None)
                or (row['outcome'] == 'failed' and row['error_code'] is None)):
            raise ValueError('invalid_terminal')
        counts = row['counts']
        if (not isinstance(counts, dict) or not set(counts) <= COUNTS
                or any(type(v) is not int or v < 0 for v in counts.values())):
            raise ValueError('invalid_counts')
    return row


def _append(directory, row):
    _validate(row)
    root = _root(directory)
    path = root / (row['attempt_id'] + '.' + row['phase'] + '.json')
    # Exclusive creation: retries cannot overwrite a prior outcome. A crash may
    # leave an invalid partial file; the reader exposes it rather than repairing it.
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(canonical(row))
        stream.flush()
        os.fsync(stream.fileno())


@dataclass
class CaptureAttempt:
    enabled: bool
    directory: str | None = None
    base: dict = field(default_factory=dict)
    start_status: str = 'unavailable'

    @property
    def attempt_id(self):
        return self.base.get('attempt_id')

    @property
    def trace_kwargs(self):
        return {key: self.base[key] for key in ('trace_id', 'span_id')} if self.base else {}

    @classmethod
    def start(cls, *, action, started_at):
        if ENV not in os.environ:
            return cls(enabled=False)
        attempt = cls(enabled=True, directory=os.environ[ENV])
        try:
            attempt.base = dict(schema=SCHEMA, attempt_id='cap_' + uuid4().hex,
                trace_id='trc_agc_' + uuid4().hex, span_id='spn_agc_' + uuid4().hex,
                action=action, phase='started', timestamp=_timestamp(started_at),
                implementation_version=__version__, recorder_version='p2.1',
                configuration_identity=None)
            _append(attempt.directory, attempt.base)
            attempt.start_status = 'recorded'
        except Exception:  # Optional evidence must not break business execution.
            pass
        return attempt

    def finish(self, *, outcome, trace_status, finished_at=None, error_code=None, report=None):
        if not self.enabled:
            return {}
        status = 'unavailable'
        try:
            timestamp = _timestamp(finished_at or datetime.now(timezone.utc))
            if instant(timestamp) < instant(self.base['timestamp']):
                raise ValueError('terminal_before_start')
            row = dict(self.base, phase='finished', timestamp=timestamp,
                outcome=outcome, trace_status=trace_status,
                error_code=None if outcome == 'completed' else error_code if error_code in ERRORS else 'unknown',
                start_status=self.start_status,
                counts={k:v for k,v in (report or {}).items() if k in COUNTS and type(v) is int and v >= 0})
            _append(self.directory, row)
            status = 'recorded'
        except Exception:  # Do not expose exceptions, paths, or business payloads.
            pass
        return {'metrics_evidence': {'attempt_id': self.attempt_id,
                'start_status': self.start_status, 'finish_status': status}}


def read_capture_attempts(directory):
    """Read one explicit metadata directory; never repair or initialize it."""
    result = dict(status='unavailable', invalid_records=0, attempts=[])
    groups = {}
    try:
        root = _root(directory)
        for path in sorted(root.glob('*.json')):
            try:
                if _linked(path):
                    raise ValueError('linked_record')
                before = path.stat()
                if before.st_size > 8192:
                    raise ValueError('oversized_record')
                row = _validate(json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=_unique_fields))
                after = path.stat()
                if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                    raise ValueError('changed_record')
                if path.name != row['attempt_id'] + '.' + row['phase'] + '.json':
                    raise ValueError('wrong_record_name')
                groups.setdefault(row['attempt_id'], {})[row['phase']] = row
            except (OSError, ValueError, TypeError, KeyError):
                result['invalid_records'] += 1
        for identity, pair in sorted(groups.items()):
            start, end = pair.get('started'), pair.get('finished')
            state = 'terminal_unobserved' if start else 'orphan_terminal'
            if start and end:
                same = all(start[k] == end[k] for k in BASE - {'timestamp', 'phase'})
                valid = instant(end['timestamp']) >= instant(start['timestamp']) and end['start_status'] == 'recorded'
                state = end['outcome'] if same and valid else 'state_conflict'
            result['attempts'].append(dict(attempt_id=identity, state=state, started=start, finished=end))
        result['status'] = 'partial' if result['invalid_records'] else 'available'
    except (OSError, ValueError, TypeError):
        pass
    return result
