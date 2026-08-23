import json
from dataclasses import replace
from pathlib import Path

import pytest

from agc_runtime.catalog import rebuild_catalog
from agc_runtime.capture_store import CaptureStore
from agc_runtime.models import MemoryItem
from agc_runtime.paths import MemoryPaths
from agc_runtime.read_service import dispatch_read
from agc_runtime.store import MemoryStore
from agc_runtime.write_service import dispatch_write


def principle() -> MemoryItem:
    fixture = Path(__file__).parent / "fixtures" / "active-principle.md"
    return MemoryItem.from_markdown(fixture.read_text(encoding="utf-8"))


def observation(
    *,
    ref: str = "codex-task:t1",
    revision: str = "r1",
    content_hash: str = "a" * 64,
    observed_at: str = "2026-07-29T00:00:00Z",
    mode: str = "direct",
    modality: str = "asserted",
    disposition: str = "new",
    match_memory_id: str | None = None,
    sensitivity: str = "normal",
    requested_confidence: str = "confirmed",
    observation_id: str = "difficult-but-correct-observation",
) -> dict:
    return {
        "observation_id": observation_id,
        "source": {
            "ref": ref,
            "revision": revision,
            "content_hash": content_hash,
            "observed_at": observed_at,
        },
        "assertion": {
            "subject": "user",
            "mode": mode,
            "modality": modality,
        },
        "proposal": {
            "disposition": disposition,
            "match_memory_id": match_memory_id,
            "kind": "principle",
            "scopes": ["work", "learning", "research", "architecture"],
            "temporal_type": "durable",
            "sensitivity": sensitivity,
            "rationale": "Changes future decision support.",
            "requested_confidence": requested_confidence,
        },
        "evidence": {
            "count": 999,
            "distinct_sessions": 999,
            "time_span_days": 999,
        },
    }


def direct_request(**changes) -> dict:
    return {
        "action": "observe",
        "observation": observation(**changes),
        "memory_markdown": principle().to_markdown(),
    }


def test_direct_normal_can_create_confirmed(tmp_path: Path):
    paths = MemoryPaths.from_root(tmp_path / "memory")

    response = dispatch_write(paths, direct_request())

    assert response.status == "accepted"
    assert response.data["lifecycle"] == "active"
    assert response.data["confidence"] == "confirmed"
    assert len(list(paths.memories.rglob("*.md"))) == 1


def test_formal_write_refreshes_existing_catalog_for_progressive_reads(
    tmp_path: Path,
):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    rebuild_catalog(paths)

    response = dispatch_write(paths, direct_request())
    overview = dispatch_read(paths, {"action": "overview"})
    search = dispatch_read(paths, {"action": "search", "limit": 20})
    catalog = json.loads(paths.catalog_json.read_text(encoding="utf-8"))

    assert response.status == "accepted"
    assert catalog["memory_count"] == 1
    assert principle().id in paths.catalog_md.read_text(encoding="utf-8")
    assert overview.data["memory_count"] == 1
    assert [item["id"] for item in search.data["items"]] == [principle().id]


def test_catalog_refresh_failure_warns_without_rejecting_saved_memory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    rebuild_catalog(paths)

    def fail_refresh(*_args, **_kwargs):
        raise OSError("catalog unavailable")

    monkeypatch.setattr(
        "agc_runtime.write_service.rebuild_catalog",
        fail_refresh,
        raising=False,
    )

    response = dispatch_write(paths, direct_request())

    assert response.status == "accepted"
    assert response.data["code"] == "memory_created"
    assert response.warnings == ("catalog_refresh_failed",)
    assert len(list(paths.memories.rglob("*.md"))) == 1


def test_sensitive_is_rejected_before_any_managed_write(tmp_path: Path):
    paths = MemoryPaths.from_root(tmp_path / "memory")

    response = dispatch_write(
        paths, direct_request(sensitivity="sensitive")
    )

    assert response.status == "rejected_policy"
    assert response.data["code"] == "sensitive_persistence_disabled"
    assert not paths.root.exists()


def test_behavior_threshold_uses_stored_sources_not_reported_counts(
    tmp_path: Path,
):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    responses = []
    for index, (task, timestamp) in enumerate(
        [
            ("t1", "2026-07-01T00:00:00Z"),
            ("t2", "2026-07-04T00:00:00Z"),
            ("t3", "2026-07-08T00:00:00Z"),
        ],
        start=1,
    ):
        responses.append(
            dispatch_write(
                paths,
                {
                    "action": "observe",
                    "observation": observation(
                        ref=f"codex-task:{task}",
                        content_hash=f"{index:x}" * 64,
                        observed_at=timestamp,
                        mode="behavior_observed",
                        disposition="need_more_evidence",
                        requested_confidence="observed",
                        observation_id="candidate-plan-first",
                    ),
                },
            )
        )

    assert responses[0].data["evidence_count"] == 1
    assert responses[0].data["candidate_status"] == "candidate"
    assert responses[-1].status == "needs_adjudication"
    assert (
        responses[-1].data["candidate_status"]
        == "eligible_for_adjudication"
    )
    assert responses[-1].data["evidence_count"] == 3
    assert not list(paths.memories.rglob("*.md"))


def test_duplicate_behavior_source_does_not_increase_evidence(tmp_path: Path):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    request = {
        "action": "observe",
        "observation": observation(
            mode="behavior_observed",
            disposition="need_more_evidence",
            requested_confidence="observed",
            observation_id="candidate-plan-first",
        ),
    }

    first = dispatch_write(paths, request)
    duplicate = dispatch_write(paths, request)

    assert first.data["evidence_count"] == 1
    assert duplicate.data["evidence_count"] == 1


def test_update_without_match_does_not_merge(tmp_path: Path):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    request = direct_request(disposition="update")

    response = dispatch_write(paths, request)

    assert response.status == "needs_adjudication"
    assert response.data["code"] == "match_memory_id_required"
    assert not list(paths.memories.rglob("*.md"))


def test_high_impact_conflict_requires_adjudication(tmp_path: Path):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    assert dispatch_write(paths, direct_request()).status == "accepted"
    conflict = direct_request(
        ref="codex-task:t2",
        content_hash="b" * 64,
        disposition="conflict",
        match_memory_id=principle().id,
    )

    response = dispatch_write(paths, conflict)

    assert response.status == "needs_adjudication"
    assert response.data["code"] == "high_impact_conflict"
    assert response.data["lifecycle"] == "active"


def test_reinforce_requires_exact_match_and_adds_evidence(tmp_path: Path):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    assert dispatch_write(paths, direct_request()).status == "accepted"

    response = dispatch_write(
        paths,
        direct_request(
            ref="codex-task:t2",
            content_hash="b" * 64,
            disposition="reinforce",
            match_memory_id=principle().id,
        ),
    )

    assert response.status == "accepted"
    assert response.data["code"] == "evidence_added"
    assert response.data["independent_evidence_count"] == 2


def test_propose_then_reject_manages_candidate_only(tmp_path: Path):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    proposed = dispatch_write(
        paths,
        {
            "action": "propose",
            "observation": observation(
                disposition="need_more_evidence",
                requested_confidence="observed",
                observation_id="candidate-plan-first",
            ),
        },
    )

    rejected = dispatch_write(
        paths,
        {
            "action": "reject",
            "candidate_id": "candidate-plan-first",
        },
    )

    assert proposed.status == "deferred"
    assert proposed.data["candidate_id"] == "candidate-plan-first"
    assert rejected.status == "accepted"
    assert rejected.data["removed"] is True
    assert not list(paths.candidates.rglob("*.json"))
    assert not list(paths.memories.rglob("*.md"))


def test_supersede_then_archive_follows_legal_transitions(tmp_path: Path):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    assert dispatch_write(paths, direct_request()).status == "accepted"
    memory_id = principle().id

    superseded = dispatch_write(
        paths,
        {
            "action": "supersede",
            "memory_id": memory_id,
            "observation": observation(
                ref="codex-task:t2",
                content_hash="b" * 64,
                disposition="update",
                match_memory_id=memory_id,
            ),
        },
    )
    archived = dispatch_write(
        paths,
        {
            "action": "archive",
            "memory_id": memory_id,
            "observation": observation(
                ref="codex-task:t3",
                content_hash="c" * 64,
                disposition="update",
                match_memory_id=memory_id,
            ),
        },
    )

    assert superseded.data["lifecycle"] == "superseded"
    assert archived.status == "accepted"
    assert archived.data["lifecycle"] == "historical"


def test_observe_batch_evaluates_each_item_independently(tmp_path: Path):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    request = {
        "action": "observe_batch",
        "items": [
            direct_request(),
            direct_request(
                ref="codex-task:t2",
                content_hash="b" * 64,
                sensitivity="secret",
            ),
        ],
    }

    response = dispatch_write(paths, request)

    assert response.status == "accepted"
    assert response.data["status_counts"] == {
        "accepted": 1,
        "rejected_policy": 1,
    }
    assert len(response.data["results"]) == 2


def test_write_failure_is_reported_without_acceptance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    paths = MemoryPaths.from_root(tmp_path / "memory")

    def fail_create(*_args, **_kwargs):
        raise OSError("disk unavailable")

    monkeypatch.setattr(
        "agc_runtime.write_service.MemoryStore.create_memory", fail_create
    )

    response = dispatch_write(paths, direct_request())

    assert response.status == "failed"
    assert response.error == {
        "code": "write_failed",
        "message": "disk unavailable",
    }


@pytest.mark.parametrize("outcome", ["needs_context", "discard"])
def test_capture_review_records_only_terminal_non_draft_outcomes(
    tmp_path, outcome, visible_capture_observations
):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    _store, (item,) = visible_capture_observations(paths, ["Reviewable preference."])
    response = dispatch_write(
        paths,
        {
            "action": "capture_review",
            "observation_ids": [item.observation_id],
            "outcome": outcome,
        },
    )
    assert response.status == "accepted"
    assert response.data == {
        "code": "capture_review_recorded",
        "outcome": outcome,
        "reviewed_count": 1,
    }


@pytest.mark.parametrize(
    "review_request",
    [
        {
            "action": "capture_review",
            "observation_ids": ["co_" + "a" * 64],
            "outcome": "draft",
        },
        {
            "action": "capture_review",
            "observation_ids": ["co_" + "a" * 64],
            "outcome": "discard",
            "reason": "free text",
        },
    ],
)
def test_capture_review_rejects_draft_and_unknown_fields_before_write(
    tmp_path, review_request
):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    response = dispatch_write(paths, review_request)
    assert response.status == "failed"
    assert response.error["code"] == "invalid_request"
    assert not paths.capture.reviews.exists()


def test_confirm_merges_two_capture_observations_into_one_draft_target(
    tmp_path, visible_capture_observations
):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    _store, observations = visible_capture_observations(
        paths,
        ["Automate publishing.", "Human confirms final publication."],
    )
    observation_ids = tuple(item.observation_id for item in observations)
    response = dispatch_write(
        paths,
        {
            "action": "confirm",
            "observation": observation(),
            "memory_markdown": principle().to_markdown(),
            "capture_observation_ids": list(observation_ids),
        },
    )
    assert response.status == "accepted"
    assert response.data["memory_id"] == principle().id
    assert response.data["capture_reviewed_count"] == 2
    reviews = CaptureStore(paths).read_snapshot().review_receipts
    assert {
        (item.observation_id, item.outcome, item.target_memory_id) for item in reviews
    } == {
        (observation_ids[0], "draft", principle().id),
        (observation_ids[1], "draft", principle().id),
    }


def test_failed_formal_write_never_records_draft_review(
    tmp_path, monkeypatch, visible_capture_observations
):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    _store, (item,) = visible_capture_observations(paths, ["Reviewable preference."])

    def fail_create(*_args, **_kwargs):
        raise OSError("disk unavailable")

    monkeypatch.setattr(MemoryStore, "create_memory", fail_create)
    response = dispatch_write(
        paths,
        {
            **direct_request(),
            "action": "confirm",
            "capture_observation_ids": [item.observation_id],
        },
    )
    assert response.status == "failed"
    assert not list(paths.capture.reviews.glob("*.json"))


def test_receipt_failure_warns_without_unsaving_memory(
    tmp_path, monkeypatch, visible_capture_observations
):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    _store, (item,) = visible_capture_observations(paths, ["Reviewable preference."])

    def fail_receipt(*_args, **_kwargs):
        raise OSError("receipt unavailable")

    monkeypatch.setattr(CaptureStore, "record_reviews", fail_receipt)
    response = dispatch_write(
        paths,
        {
            **direct_request(),
            "action": "confirm",
            "capture_observation_ids": [item.observation_id],
        },
    )
    assert response.status == "accepted"
    assert response.warnings == ("capture_review_receipt_failed",)
    assert MemoryStore(paths).get_memory(principle().id).id == principle().id


def test_formalization_rejects_dangling_reference_before_memory_write(
    tmp_path, visible_capture_observations
):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    _store, (item,) = visible_capture_observations(
        paths, ["该 skill 调用当前本地 harness。"]
    )
    invalid = replace(
        principle(), full_meaning="该 skill 调用当前本地 harness。"
    )
    response = dispatch_write(
        paths,
        {
            **direct_request(),
            "action": "confirm",
            "memory_markdown": invalid.to_markdown(),
            "capture_observation_ids": [item.observation_id],
        },
    )
    assert response.status == "failed"
    assert not list(paths.memories.rglob("*.md"))
    assert not list(paths.capture.reviews.glob("*.json"))


def test_observe_new_rejects_capture_ids_before_creating_memory(
    tmp_path, visible_capture_observations
):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    _store, (item,) = visible_capture_observations(paths, ["Reviewable preference."])
    response = dispatch_write(
        paths,
        {**direct_request(), "capture_observation_ids": [item.observation_id]},
    )
    assert response.status == "failed"
    assert response.error["code"] == "invalid_request"
    assert not list(paths.memories.rglob("*.md"))
    assert not list(paths.capture.reviews.glob("*.json"))


def test_observe_reinforce_attaches_capture_review(
    tmp_path, visible_capture_observations
):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    assert dispatch_write(paths, direct_request()).status == "accepted"
    _store, (item,) = visible_capture_observations(paths, ["Reinforces preference."])
    response = dispatch_write(
        paths,
        {
            **direct_request(
                ref="codex-task:t2",
                content_hash="b" * 64,
                disposition="reinforce",
                match_memory_id=principle().id,
            ),
            "capture_observation_ids": [item.observation_id],
        },
    )
    assert response.status == "accepted"
    assert response.data["capture_reviewed_count"] == 1
    assert CaptureStore(paths).read_snapshot().review_receipts[0].target_memory_id == principle().id


def test_update_attaches_capture_review_to_existing_memory(
    tmp_path, visible_capture_observations
):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    assert dispatch_write(paths, direct_request()).status == "accepted"
    _store, (item,) = visible_capture_observations(paths, ["Updates preference boundary."])
    updated = replace(
        principle(),
        application_boundary="用于重要决策与正式发布；低风险草稿不强制。",
    )
    response = dispatch_write(
        paths,
        {
            **direct_request(
                ref="codex-task:t2",
                content_hash="b" * 64,
                disposition="update",
                match_memory_id=principle().id,
            ),
            "action": "update",
            "memory_markdown": updated.to_markdown(),
            "capture_observation_ids": [item.observation_id],
        },
    )
    assert response.status == "accepted"
    assert response.data["capture_reviewed_count"] == 1
    review = CaptureStore(paths).read_snapshot().review_receipts[0]
    assert (review.outcome, review.target_memory_id) == ("draft", principle().id)


def test_other_write_actions_reject_capture_observation_ids_before_mutation(
    tmp_path, visible_capture_observations
):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    assert dispatch_write(paths, direct_request()).status == "accepted"
    _store, (item,) = visible_capture_observations(paths, ["Must not bind here."])
    response = dispatch_write(
        paths,
        {
            "action": "supersede",
            "memory_id": principle().id,
            "observation": observation(
                ref="codex-task:t2",
                content_hash="b" * 64,
                disposition="update",
                match_memory_id=principle().id,
            ),
            "capture_observation_ids": [item.observation_id],
        },
    )
    assert response.status == "failed"
    assert response.error["code"] == "invalid_request"
    assert MemoryStore(paths).get_memory(principle().id).lifecycle.status == "active"
    assert not list(paths.capture.reviews.glob("*.json"))
