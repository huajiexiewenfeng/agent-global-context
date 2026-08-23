from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from agc_runtime.capture_review import (
    CaptureReviewReceipt,
    parse_capture_observation_ids,
    validate_formalization_item,
)
from agc_runtime.models import MemoryItem
from agc_runtime.paths import MemoryPaths


UTC = "2026-08-23T12:00:00Z"


def test_review_receipt_is_strict_content_free_and_target_bound():
    value = {
        "schema_version": 1,
        "observation_id": "co_" + "a" * 64,
        "outcome": "draft",
        "target_memory_id": "publish-with-human-confirmation",
        "reviewed_at": UTC,
    }
    receipt = CaptureReviewReceipt.from_mapping(value)
    assert receipt.to_mapping() == value
    for extra in ("statement", "memory_markdown", "reason", "prompt"):
        with pytest.raises(ValueError):
            CaptureReviewReceipt.from_mapping({**value, extra: "forbidden"})
    for outcome, target in (("draft", None), ("discard", "memory-id"), ("needs_context", "memory-id")):
        with pytest.raises(ValueError):
            CaptureReviewReceipt.from_mapping({**value, "outcome": outcome, "target_memory_id": target})


def test_review_id_batch_is_canonical_unique_and_bounded():
    ids = [f"co_{index:064x}" for index in range(20)]
    assert parse_capture_observation_ids(ids) == tuple(ids)
    for invalid in ([], ids + ["co_" + "f" * 64], ids[:1] * 2, ["not-an-id"]):
        with pytest.raises(ValueError):
            parse_capture_observation_ids(invalid)


def test_review_store_records_visible_observations_idempotently(
    tmp_path: Path, visible_capture_observations
):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    store, observations = visible_capture_observations(paths, ["One.", "Two."])
    ids = [item.observation_id for item in observations]

    store.validate_review_batch(ids, outcome="draft", target_memory_id="merged-memory")
    assert store.record_reviews(
        ids, outcome="draft", target_memory_id="merged-memory", reviewed_at=UTC
    ) == 2
    assert store.record_reviews(
        ids, outcome="draft", target_memory_id="merged-memory", reviewed_at="2026-08-24T00:00:00Z"
    ) == 0
    assert sorted(path.stem for path in paths.capture.reviews.glob("*.json")) == sorted(ids)
    snapshot = store.read_snapshot()
    assert {item.observation_id: item.outcome for item in snapshot.review_receipts} == {
        item.observation_id: "draft" for item in observations
    }

    with pytest.raises(ValueError, match="conflicts"):
        store.record_reviews(ids, outcome="discard", target_memory_id=None)


def test_review_store_rejects_non_visible_observation(tmp_path: Path):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    from agc_runtime.capture_store import CaptureStore

    store = CaptureStore(paths, clock=lambda: UTC)
    with pytest.raises((FileNotFoundError, ValueError)):
        store.record_reviews(["co_" + "a" * 64], outcome="discard", target_memory_id=None)
    assert not list(paths.capture.reviews.glob("*.json"))


def test_snapshot_rejects_review_filename_binding(
    tmp_path: Path, visible_capture_observations
):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    store, (observation,) = visible_capture_observations(paths, ["Review me."])
    store.record_reviews(
        [observation.observation_id], outcome="discard", target_memory_id=None, reviewed_at=UTC
    )
    original = paths.capture.reviews / f"{observation.observation_id}.json"
    original.rename(paths.capture.reviews / f"{'co_' + 'f' * 64}.json")

    snapshot = store.read_snapshot()
    assert snapshot.review_receipts == ()
    assert "invalid_review_receipt" in {item.code for item in snapshot.diagnostics}


def test_formalization_item_rejects_dangling_references():
    fixture = Path(__file__).parent / "fixtures" / "active-principle.md"
    item = MemoryItem.from_markdown(fixture.read_text(encoding="utf-8"))
    validate_formalization_item(item)
    with pytest.raises(ValueError, match="dangling reference"):
        validate_formalization_item(replace(item, full_meaning="最终目标保持不变"))
