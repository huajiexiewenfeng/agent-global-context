"""Content-safe readiness and notice state for Capture formalization."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
import re
from pathlib import Path
from typing import Any

from agc_runtime.capture_store import CaptureStore
from agc_runtime.capture_transaction import atomic_write_json, canonical_json_bytes, read_json
from agc_runtime.paths import MemoryPaths
from agc_runtime.locking import capture_write_lock


REVIEW_COUNT_THRESHOLD = 10
REVIEW_MAX_AGE_SECONDS = 24 * 60 * 60
REVIEW_BATCH_LIMIT = 10
REVIEW_NOTICE_COOLDOWN_SECONDS = 24 * 60 * 60
REVIEW_NOTICE_POLICY = "capture-review-notification-v1"

_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_NOTICE_NAME = "capture-review-notice.json"
_PENDING_NAME = "capture-review-pending"
_OBSERVATION_ID = re.compile(r"^co_[0-9a-f]{64}$")


def _validate_batch_ids(value: Any, digest: str) -> list[str]:
    if (not isinstance(value, list) or not 1 <= len(value) <= REVIEW_BATCH_LIMIT
            or any(not isinstance(item, str) or not _OBSERVATION_ID.fullmatch(item) for item in value)
            or len(set(value)) != len(value) or _batch_digest(value) != digest):
        raise ValueError("capture_review_batch_binding_invalid")
    return value


def _read_pending(paths: MemoryPaths) -> list[dict[str, Any]]:
    directory = paths.cache / _PENDING_NAME
    if directory.is_symlink() or (directory.exists() and not directory.is_dir()):
        raise ValueError("capture_review_pending_state_invalid")
    if not directory.exists():
        return []
    records = []
    for path in sorted(directory.iterdir()):
        if (path.suffix != '.json' or not path.is_file() or path.is_symlink()
                or path.resolve().parent != directory.resolve()):
            raise ValueError("capture_review_pending_state_invalid")
        record = read_json(path)
        if (set(record) != {'schema_version', 'policy', 'batch_digest', 'notified_at', 'batch_observation_ids'}
                or record['schema_version'] != 1 or record['policy'] != REVIEW_NOTICE_POLICY
                or record['batch_digest'] != path.stem or not _DIGEST.fullmatch(path.stem)):
            raise ValueError("capture_review_pending_state_invalid")
        _validate_batch_ids(record['batch_observation_ids'], record['batch_digest'])
        _utc(record['notified_at'])
        records.append(record)
    return records


def _utc(value: str | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if not isinstance(value, str) or not value.endswith("Z") or value == "Z":
        raise ValueError("timestamp must be RFC 3339 UTC")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise ValueError("timestamp must be RFC 3339 UTC") from error
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise ValueError("timestamp must be RFC 3339 UTC")
    return parsed


def _utc_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _notice_path(paths: MemoryPaths) -> Path:
    return paths.cache / _NOTICE_NAME


def _batch_digest(observation_ids: list[str]) -> str:
    payload = {
        "policy": REVIEW_NOTICE_POLICY,
        "observation_ids": observation_ids,
    }
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _read_notice(paths: MemoryPaths) -> tuple[dict[str, str] | None, str]:
    path = _notice_path(paths)
    if not path.exists():
        return None, "not_notified"
    try:
        value = read_json(path)
        if set(value) != {"schema_version", "policy", "batch_digest", "notified_at"}:
            raise ValueError
        if value["schema_version"] != 1 or value["policy"] != REVIEW_NOTICE_POLICY:
            raise ValueError
        digest = value["batch_digest"]
        if not isinstance(digest, str) or _DIGEST.fullmatch(digest) is None:
            raise ValueError
        notified_at = value["notified_at"]
        if not isinstance(notified_at, str):
            raise ValueError
        _utc(notified_at)
    except (OSError, TypeError, ValueError):
        return None, "cache_invalid"
    return {"batch_digest": digest, "notified_at": notified_at}, "notified"


def capture_review_status(
    paths: MemoryPaths, *, now: str | None = None
) -> dict[str, Any]:
    current = _utc(now)
    snapshot = CaptureStore(paths).read_review_snapshot()
    reviewed = {item.observation_id for item in snapshot.review_receipts}
    unreviewed = [
        item for item in snapshot.observations if item.observation_id not in reviewed
    ]
    pending_invalid = False
    try:
        pending = _read_pending(paths)
    except (OSError, TypeError, ValueError):
        pending = []
        pending_invalid = True
    pending_ids = {identifier for record in pending for identifier in record['batch_observation_ids']}
    eligible = [item for item in unreviewed if item.observation_id not in pending_ids]
    eligible.sort(
        key=lambda item: (_utc(item.captured_at), item.observation_id)
    )
    batch = [] if pending_invalid else eligible[:REVIEW_BATCH_LIMIT]
    batch_ids = [item.observation_id for item in batch]
    digest = _batch_digest(batch_ids) if batch_ids else None
    oldest = min((item.captured_at for item in unreviewed), default=None)
    integrity_state = snapshot.integrity_state

    if pending_invalid:
        ready = False
        ready_reason = "pending_state_invalid"
    elif integrity_state != "healthy":
        ready = False
        ready_reason = "integrity_degraded"
    elif not eligible:
        ready = False
        ready_reason = "awaiting_confirmation" if unreviewed else "empty"
    elif len(eligible) >= REVIEW_COUNT_THRESHOLD:
        ready = True
        ready_reason = "count_threshold"
    elif (current - _utc(eligible[0].captured_at)).total_seconds() >= REVIEW_MAX_AGE_SECONDS:
        ready = True
        ready_reason = "age_threshold"
    else:
        ready = False
        ready_reason = "not_ready"

    notice, notification_state = _read_notice(paths)
    # Pending records are durable even if the legacy cooldown write failed.
    for record in pending:
        if notice is None or _utc(record['notified_at']) > _utc(notice['notified_at']):
            notice = record
    last_notified_at = notice["notified_at"] if notice is not None else None
    if notice is not None:
        elapsed = (current - _utc(notice["notified_at"])).total_seconds()
        if elapsed < REVIEW_NOTICE_COOLDOWN_SECONDS:
            notification_state = "cooldown"
        elif notice["batch_digest"] == digest:
            notification_state = "reminder_due"
        else:
            notification_state = "new_batch_due"
    should_notify = ready and notification_state != "cooldown"

    return {
        "policy": REVIEW_NOTICE_POLICY,
        "ready": ready,
        "should_notify": should_notify,
        "ready_reason": ready_reason,
        "unreviewed_count": len(unreviewed),
        "pending_confirmation_count": None if pending_invalid else sum(item.observation_id in pending_ids for item in unreviewed),
        "undispatched_count": None if pending_invalid else len(eligible),
        "oldest_unreviewed_at": oldest,
        "batch_size": len(batch),
        "batch_observation_ids": batch_ids,
        "batch_digest": digest,
        "category_counts": dict(sorted(Counter(item.primary_category for item in batch).items())),
        "kind_counts": dict(sorted(Counter(item.kind for item in batch).items())),
        "integrity_state": integrity_state,
        "notification_state": notification_state,
        "last_notified_at": last_notified_at,
        "notification_cooldown_seconds": REVIEW_NOTICE_COOLDOWN_SECONDS,
    }


def record_capture_review_notice(
    paths: MemoryPaths, batch_digest: str, *, now: str | None = None,
    batch_observation_ids: list[str] | None = None,
) -> dict[str, Any]:
    if not isinstance(batch_digest, str) or _DIGEST.fullmatch(batch_digest) is None:
        raise ValueError("batch_digest must be a lowercase SHA-256 digest")
    notified_at = _utc_text(_utc(now))
    if batch_observation_ids is not None:
        ids = _validate_batch_ids(batch_observation_ids, batch_digest)
        with capture_write_lock(paths):
            records = _read_pending(paths)
            existing = next((record for record in records if record['batch_digest'] == batch_digest), None)
            if existing is not None:
                return {key: existing[key] for key in ('policy', 'batch_digest', 'notified_at')}
            # This metadata reader takes no lock itself; bind selection and
            # publication under the same writer guard as reviews/Hard Forget.
            snapshot = CaptureStore(paths).read_review_snapshot()
            if snapshot.integrity_state != 'healthy':
                raise ValueError('capture_review_integrity_degraded')
            excluded = {item.observation_id for item in snapshot.review_receipts}
            excluded.update(identifier for record in records for identifier in record['batch_observation_ids'])
            eligible = sorted((item for item in snapshot.observations if item.observation_id not in excluded),
                              key=lambda item: (_utc(item.captured_at), item.observation_id))
            if ids != [item.observation_id for item in eligible[:REVIEW_BATCH_LIMIT]]:
                raise ValueError('capture_review_batch_stale')
            atomic_write_json(paths.cache / _PENDING_NAME / (batch_digest + '.json'), {
                'schema_version': 1, 'policy': REVIEW_NOTICE_POLICY,
                'batch_digest': batch_digest, 'notified_at': notified_at,
                'batch_observation_ids': ids,
            })
    atomic_write_json(
        _notice_path(paths),
        {
            "schema_version": 1,
            "policy": REVIEW_NOTICE_POLICY,
            "batch_digest": batch_digest,
            "notified_at": notified_at,
        },
    )
    return {
        "policy": REVIEW_NOTICE_POLICY,
        "batch_digest": batch_digest,
        "notified_at": notified_at,
    }


__all__ = [
    "REVIEW_BATCH_LIMIT",
    "REVIEW_COUNT_THRESHOLD",
    "REVIEW_MAX_AGE_SECONDS",
    "REVIEW_NOTICE_COOLDOWN_SECONDS",
    "REVIEW_NOTICE_POLICY",
    "capture_review_status",
    "record_capture_review_notice",
]
