"""Review readiness and content-free notification cache contracts."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from agc_runtime.capture_contracts import (
    CAPTURE_SCHEMA_VERSION,
    CaptureKey,
    CaptureReceipt,
    CollectedObservation,
    TokenUsage,
    observation_fingerprint_for,
    observation_id_for,
    receipt_id_for,
)
from agc_runtime.capture_review_notification import (
    REVIEW_NOTICE_POLICY,
    capture_review_status,
    record_capture_review_notice,
)
from agc_runtime.capture_store import CaptureStore
from agc_runtime.paths import MemoryPaths


NOW = "2026-08-31T12:00:00Z"


def _timestamp(hours_ago: int, ordinal: int = 0) -> str:
    value = datetime(2026, 8, 31, 12, tzinfo=timezone.utc) - timedelta(
        hours=hours_ago, minutes=ordinal
    )
    return value.isoformat().replace("+00:00", "Z")


def _key(index: int) -> CaptureKey:
    return CaptureKey("synthetic_adapter", "1" * 64, f"task-{index}", f"revision-{index}")


def _receipt(key: CaptureKey, timestamp: str) -> CaptureReceipt:
    return CaptureReceipt.from_mapping(
        {
            "schema_version": CAPTURE_SCHEMA_VERSION,
            "receipt_id": receipt_id_for(key),
            **key.to_mapping(),
            "adapter_version": "1",
            "source_schema_version": "1",
            "identity_quality": "session_id",
            "source_fingerprint": "b" * 64,
            "source_hash_schema_version": "source-v1",
            "capsule_hash": "c" * 64,
            "capsule_schema_version": "capsule-v1",
            "settled_at": timestamp,
            "discovered_at": timestamp,
            "updated_at": timestamp,
            "status": "extracting",
            "attempt_count": 1,
            "next_retry_at": None,
            "extractor_id": "synthetic",
            "extractor_version": "1",
            "extractor_schema_version": "1",
            "taxonomy_version": "taxonomy-v1",
            "observation_count": None,
            "filtered_counts": None,
            "duplicate_suppression_count": None,
            "token_usage": TokenUsage(1, 2, 3).to_mapping(),
            "usage_quality": "actual",
            "redacted_by_forget": False,
            "forgotten_observation_count": 0,
            "zero_reason": None,
            "sanitized_error": None,
            "coalesced_to": None,
            "exclusion_reason": None,
        }
    )


def _observation(
    receipt: CaptureReceipt,
    index: int,
    timestamp: str,
    *,
    category: str = "project",
    kind: str = "goal",
) -> CollectedObservation:
    mapping = {
        "schema_version": CAPTURE_SCHEMA_VERSION,
        "observation_id": "co_" + "0" * 64,
        "receipt_id": receipt.receipt_id,
        "source": {**receipt.key.to_mapping(), "locator": "synthetic/only"},
        "ordinal": 0,
        "observation_fingerprint": "0" * 64,
        "statement": f"private statement {index}",
        "assertion": {"subject": "user", "mode": "direct", "modality": "asserted"},
        "primary_category": category,
        "taxonomy_version": "taxonomy-v1",
        "kind": kind,
        "scopes": ["testing"],
        "project_scope": "project-1",
        "confidence": "observed",
        "sensitivity": "normal",
        "signal_type": "decision_or_constraint",
        "observed_at": timestamp,
        "captured_at": timestamp,
        "extractor_version": "1",
        "processing_state": "collected",
    }
    mapping["observation_fingerprint"] = observation_fingerprint_for(mapping)
    mapping["observation_id"] = observation_id_for(
        receipt.receipt_id, mapping["observation_fingerprint"]
    )
    return CollectedObservation.from_mapping(mapping)


def _seed(
    paths: MemoryPaths,
    count: int,
    *,
    oldest_hours: int = 1,
) -> list[CollectedObservation]:
    store = CaptureStore(paths, clock=lambda: NOW)
    observations: list[CollectedObservation] = []
    for index in range(count):
        timestamp = _timestamp(max(0, oldest_hours - index), index)
        key = _key(index)
        receipt = _receipt(key, timestamp)
        observation = _observation(
            receipt,
            index,
            timestamp,
            category="project" if index % 2 == 0 else "work",
            kind="goal" if index % 2 == 0 else "preference",
        )
        store.register_extraction(receipt)
        lease = store.acquire_lease(key, owner_id="synthetic", now=NOW, ttl_seconds=60)
        assert lease is not None
        complete = CaptureReceipt.from_mapping(
            {
                **receipt.to_mapping(),
                "status": "complete",
                "observation_count": 1,
                "filtered_counts": {"safety": 0, "policy": 0, "over_limit": 0},
                "duplicate_suppression_count": 0,
            }
        )
        store.commit_extraction(lease, (observation,), complete)
        observations.append(observation)
    return observations


def test_review_status_becomes_ready_at_count_threshold_and_is_content_safe(tmp_path: Path):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    observations = _seed(paths, 10)

    status = capture_review_status(paths, now=NOW)

    expected = [item.observation_id for item in sorted(observations, key=lambda item: (item.captured_at, item.observation_id))]
    assert status["policy"] == REVIEW_NOTICE_POLICY
    assert status["ready"] is True
    assert status["should_notify"] is True
    assert status["ready_reason"] == "count_threshold"
    assert status["unreviewed_count"] == 10
    assert status["batch_observation_ids"] == expected
    assert status["category_counts"] == {"project": 5, "work": 5}
    assert status["kind_counts"] == {"goal": 5, "preference": 5}
    assert len(status["batch_digest"]) == 64
    rendered = repr(status)
    assert "private statement" not in rendered
    assert "synthetic/only" not in rendered


def test_review_status_uses_age_threshold_but_keeps_fresh_small_queue_quiet(tmp_path: Path):
    fresh = MemoryPaths.from_root(tmp_path / "fresh")
    old = MemoryPaths.from_root(tmp_path / "old")
    _seed(fresh, 9, oldest_hours=1)
    _seed(old, 1, oldest_hours=24)

    fresh_status = capture_review_status(fresh, now=NOW)
    old_status = capture_review_status(old, now=NOW)

    assert fresh_status["ready"] is False
    assert fresh_status["should_notify"] is False
    assert fresh_status["ready_reason"] == "not_ready"
    assert old_status["ready"] is True
    assert old_status["should_notify"] is True
    assert old_status["ready_reason"] == "age_threshold"


def test_review_status_excludes_terminal_reviews_and_empty_queue_is_not_ready(tmp_path: Path):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    observations = _seed(paths, 1, oldest_hours=48)
    CaptureStore(paths, clock=lambda: NOW).record_reviews(
        [observations[0].observation_id],
        outcome="discard",
        target_memory_id=None,
        reviewed_at=NOW,
    )

    status = capture_review_status(paths, now=NOW)

    assert status["unreviewed_count"] == 0
    assert status["batch_observation_ids"] == []
    assert status["batch_digest"] is None
    assert status["oldest_unreviewed_at"] is None
    assert status["ready"] is False
    assert status["should_notify"] is False
    assert status["ready_reason"] == "empty"


def test_review_status_fails_closed_when_capture_integrity_is_degraded(tmp_path: Path):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    _seed(paths, 10)
    paths.capture.reviews.mkdir(parents=True, exist_ok=True)
    (paths.capture.reviews / "invalid.json").write_text("{}", encoding="utf-8")

    status = capture_review_status(paths, now=NOW)

    assert status["integrity_state"] == "degraded"
    assert status["ready"] is False
    assert status["should_notify"] is False
    assert status["ready_reason"] == "integrity_degraded"


def test_notice_cache_suppresses_same_batch_for_24_hours_then_allows_reminder(tmp_path: Path):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    _seed(paths, 10)
    first = capture_review_status(paths, now=NOW)

    receipt = record_capture_review_notice(paths, first["batch_digest"], now=NOW)
    one_hour_later = capture_review_status(paths, now="2026-08-31T13:00:00Z")
    next_day = capture_review_status(paths, now="2026-09-01T12:00:00Z")

    assert receipt == {
        "policy": REVIEW_NOTICE_POLICY,
        "batch_digest": first["batch_digest"],
        "notified_at": NOW,
    }
    assert one_hour_later["should_notify"] is False
    assert one_hour_later["notification_state"] == "cooldown"
    assert next_day["should_notify"] is True
    assert next_day["notification_state"] == "reminder_due"


def test_invalid_notice_cache_is_non_authoritative_and_digest_is_strict(tmp_path: Path):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    _seed(paths, 10)
    paths.cache.mkdir(parents=True, exist_ok=True)
    (paths.cache / "capture-review-notice.json").write_text("{", encoding="utf-8")

    status = capture_review_status(paths, now=NOW)

    assert status["should_notify"] is True
    assert status["notification_state"] == "cache_invalid"

    for invalid in ("", "A" * 64, "f" * 63, "g" * 64):
        try:
            record_capture_review_notice(paths, invalid, now=NOW)
        except ValueError as error:
            assert str(error) == "batch_digest must be a lowercase SHA-256 digest"
        else:
            raise AssertionError("invalid digest was accepted")
