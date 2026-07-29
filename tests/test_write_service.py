from pathlib import Path

import pytest

from agc_runtime.models import MemoryItem
from agc_runtime.paths import MemoryPaths
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
