"""Append-only human feedback sidecars; never alter Judge results or memories.

Feedback refs bind caller-provided provenance, not proof of human identity or
consent. The explicit review workflow must obtain actual user feedback first.
"""
import json
import os
import re

from agc_runtime.metrics_evidence import _root
from agc_runtime.metrics_models import canonical, digest, instant
from agc_runtime.metrics_result_reader import _read
from agc_runtime.metrics_review_batch import validate_review


def _build(review, *, case_id, decision, correction, feedback_ref, timestamp,
           revision, previous_revision_id):
    row = next((r for r in review['rows'] if r['case_id'] == case_id), None)
    if (row is None or decision not in ('accepted', 'corrected', 'disputed')
            or not isinstance(feedback_ref, str)
            or not re.fullmatch(r'id_[a-f0-9]{64}', feedback_ref)):
        raise ValueError('human_feedback_invalid')
    instant(timestamp)
    if instant(timestamp) < max(instant(review['cutoff']), instant(review.get('evaluation_cutoff',review['cutoff']))):
        raise ValueError('feedback_before_report')
    if decision == 'corrected':
        if row['status'] != 'usable_judgment' or not isinstance(correction, dict):
            raise ValueError('no_judgment_to_correct')
        if set(correction) != {'candidate_verdicts', 'required_matches', 'research'}:
            raise ValueError('correction_fields_invalid')
    elif correction is not None:
        raise ValueError('unexpected_correction')
    if decision == 'accepted' and row['status'] != 'usable_judgment':
        raise ValueError('no_judgment_to_accept')
    body = dict(schema_version='agc.metrics-human-revision.v1',
                report_id=review['review_id'], batch_id=review['batch_id'],
                case_id=case_id, result_digests=row['result_digests'], revision=revision,
                previous_revision_id=previous_revision_id, decision=decision,
                correction=correction, timestamp=timestamp, feedback_ref=feedback_ref)
    body['revision_id'] = 'mhr_'+digest(body)
    return json.loads(canonical(body))


def _validate_correction(batch, review, record):
    if record['correction'] is None:
        return
    projected = json.loads(canonical(review))
    row = next(r for r in projected['rows'] if r['case_id'] == record['case_id'])
    row.update(record['correction'])
    projected['review_id'] = 'mr_'+digest({k:v for k,v in projected.items() if k != 'review_id'})
    validate_review(projected, batch)


def read_revisions(batch, review, directory):
    review = validate_review(review, batch)
    root = _root(directory)
    paths = sorted(root.iterdir())
    if len(paths) > 10000:
        raise ValueError('human_history_too_large')
    records = []
    for number, path in enumerate(paths, 1):
        if path.name != f'{number:06d}.json':
            raise ValueError('human_history_gap_or_unexpected_file')
        value = _read(path)
        try:
            expected = _build(review, **{k:value[k] for k in
                ('case_id','decision','correction','feedback_ref','timestamp')},
                revision=number, previous_revision_id=records[-1]['revision_id'] if records else None)
            if canonical(value) != canonical(expected):
                raise ValueError('human_history_mismatch')
            if records and instant(value['timestamp']) < instant(records[-1]['timestamp']):
                raise ValueError('human_history_time_reversed')
            _validate_correction(batch, review, expected)
        except (KeyError, TypeError) as error:
            raise ValueError('human_history_invalid') from error
        records.append(expected)
    return records


def append_revision(batch, review, directory, *, case_id, decision, correction,
                    feedback_ref, timestamp):
    review = validate_review(review, batch)
    root = _root(directory)
    records = read_revisions(batch, review, root)
    if len(records) >= 10000:
        raise ValueError('human_history_too_large')
    value = _build(review, case_id=case_id, decision=decision, correction=correction,
                   feedback_ref=feedback_ref, timestamp=timestamp, revision=len(records)+1,
                   previous_revision_id=records[-1]['revision_id'] if records else None)
    _validate_correction(batch, review, value)
    if records and instant(timestamp) < instant(records[-1]['timestamp']):
        raise ValueError('human_history_time_reversed')
    # Concurrent appenders select the same next path; exclusive creation makes
    # one fail instead of silently overwriting or creating a divergent chain.
    with (root/f'{value["revision"]:06d}.json').open('x', encoding='utf-8', newline='\n') as handle:
        handle.write(canonical(value))
        handle.flush()
        os.fsync(handle.fileno())
    return value


def review_state(batch, review, directory):
    review = validate_review(review, batch)
    revisions = read_revisions(batch, review, directory)
    latest = {r['case_id']:r for r in revisions}
    rows = []
    for original in review['rows']:
        revision = latest.get(original['case_id'])
        rows.append(dict(case_id=original['case_id'],
                         human_review=revision['decision'] if revision else 'unreviewed',
                         correction=revision['correction'] if revision else None,
                         revision_id=revision['revision_id'] if revision else None))
    return dict(report_id=review['review_id'], rows=rows, revisions=revisions)
