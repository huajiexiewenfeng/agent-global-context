from dataclasses import replace

import pytest

from agc_runtime.contracts import ObservationEnvelope
from agc_runtime.policy import evaluate_observation, validate_transition


def envelope(**proposal_changes) -> ObservationEnvelope:
    value = {
        "observation_id": "obs-t1-r1",
        "source": {
            "ref": "codex-task:t1",
            "revision": "r1",
            "content_hash": "a" * 64,
            "observed_at": "2026-07-29T00:00:00Z",
        },
        "assertion": {
            "subject": "user",
            "mode": "direct",
            "modality": "asserted",
        },
        "proposal": {
            "disposition": "new",
            "match_memory_id": None,
            "kind": "principle",
            "scopes": ["work"],
            "temporal_type": "durable",
            "sensitivity": "normal",
            "rationale": "Changes future decision support.",
            "requested_confidence": "confirmed",
        },
        "evidence": {
            "count": 1,
            "distinct_sessions": 1,
            "time_span_days": 0,
        },
    }
    value["proposal"].update(proposal_changes)
    return ObservationEnvelope.from_mapping(value)


def test_observation_envelope_round_trips():
    item = envelope()

    assert ObservationEnvelope.from_mapping(item.to_mapping()) == item
    assert item.source.stable_id.endswith("\x1f" + "a" * 64)


def test_sensitive_is_rejected_before_persistence():
    decision = evaluate_observation(envelope(sensitivity="sensitive"))

    assert decision.status == "rejected_policy"
    assert decision.code == "sensitive_persistence_disabled"
    assert "rationale" not in decision.persistable_metadata
    assert decision.persistable_metadata == {}


def test_secret_is_rejected_without_persistable_metadata():
    decision = evaluate_observation(envelope(sensitivity="secret"))

    assert decision.status == "rejected_policy"
    assert decision.code == "secret_persistence_forbidden"
    assert decision.persistable_metadata == {}


@pytest.mark.parametrize("disposition", ["reinforce", "update", "conflict"])
def test_existing_memory_dispositions_require_match_memory_id(disposition: str):
    decision = evaluate_observation(envelope(disposition=disposition))

    assert decision.status == "needs_adjudication"
    assert decision.code == "match_memory_id_required"


@pytest.mark.parametrize(
    ("mode", "modality"),
    [
        ("direct", "hypothetical"),
        ("direct", "question"),
        ("direct", "example"),
        ("quoted", "asserted"),
        ("agent_inferred", "asserted"),
    ],
)
def test_non_direct_assertions_cannot_auto_confirm(mode: str, modality: str):
    item = envelope()
    item = replace(
        item,
        assertion=replace(item.assertion, mode=mode, modality=modality),
    )

    decision = evaluate_observation(item)

    assert decision.status == "deferred"
    assert decision.code == "assertion_not_confirmable"
    assert decision.persistable_metadata["candidate_status"] == "candidate"


def test_behavior_observation_stays_candidate_below_threshold():
    item = envelope(requested_confidence="observed")
    item = replace(
        item,
        assertion=replace(item.assertion, mode="behavior_observed"),
    )

    decision = evaluate_observation(item)

    assert decision.status == "deferred"
    assert decision.code == "more_evidence_required"
    assert decision.persistable_metadata["candidate_status"] == "candidate"


def test_behavior_threshold_only_becomes_eligible_for_adjudication():
    item = envelope(requested_confidence="observed")
    item = replace(
        item,
        assertion=replace(item.assertion, mode="behavior_observed"),
        evidence=replace(
            item.evidence,
            count=3,
            distinct_sessions=2,
            time_span_days=7,
        ),
    )

    decision = evaluate_observation(item)

    assert decision.status == "needs_adjudication"
    assert decision.code == "eligible_for_adjudication"
    assert (
        decision.persistable_metadata["candidate_status"]
        == "eligible_for_adjudication"
    )


def test_direct_asserted_normal_observation_is_accepted():
    decision = evaluate_observation(envelope())

    assert decision.status == "accepted"
    assert decision.code == "direct_assertion_accepted"
    assert decision.persistable_metadata["rationale"]


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("active", "rejected"),
        ("superseded", "active"),
        ("historical", "active"),
    ],
)
def test_illegal_lifecycle_transitions_are_rejected(old: str, new: str):
    with pytest.raises(ValueError, match="illegal lifecycle transition"):
        validate_transition(old, new)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("candidate", "active"),
        ("active", "challenged"),
        ("active", "superseded"),
        ("dormant", "active"),
        ("superseded", "historical"),
    ],
)
def test_explicit_lifecycle_transitions_are_allowed(old: str, new: str):
    validate_transition(old, new)
