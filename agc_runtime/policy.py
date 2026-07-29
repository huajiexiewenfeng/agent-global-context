from dataclasses import dataclass
from typing import Any

from agc_runtime.contracts import ObservationEnvelope, Status


PERSISTABLE_SENSITIVITY = {"normal", "personal"}
NON_PERSISTABLE_SENSITIVITY = {"sensitive", "secret"}
ASSERTION_MODES = {"direct", "behavior_observed", "agent_inferred", "quoted"}
ASSERTION_MODALITIES = {"asserted", "hypothetical", "question", "example"}
DISPOSITIONS = {
    "ignore",
    "new",
    "reinforce",
    "update",
    "conflict",
    "need_more_evidence",
}
REQUESTED_CONFIDENCE = {"tentative", "observed", "confirmed", "disputed"}
CONFIRMABLE_ASSERTIONS = {("direct", "asserted")}
MATCH_REQUIRED = {"reinforce", "update", "conflict"}
EVIDENCE_THRESHOLD = {
    "minimum_evidence": 3,
    "minimum_distinct_sessions": 2,
    "minimum_time_span_days": 7,
}
LIFECYCLE_TRANSITIONS = {
    "candidate": {"active", "challenged", "dormant", "rejected"},
    "active": {"challenged", "dormant", "superseded", "historical"},
    "challenged": {"active", "dormant", "superseded", "historical", "rejected"},
    "dormant": {"active", "historical", "superseded"},
    "superseded": {"historical"},
    "historical": set(),
    "rejected": set(),
}


@dataclass(frozen=True)
class PolicyDecision:
    status: Status
    code: str
    persistable_metadata: dict[str, Any]


def _candidate_metadata(
    envelope: ObservationEnvelope, candidate_status: str
) -> dict[str, Any]:
    return {
        "observation_id": envelope.observation_id,
        "source": {
            "ref": envelope.source.ref,
            "revision": envelope.source.revision,
            "content_hash": envelope.source.content_hash,
            "observed_at": envelope.source.observed_at,
        },
        "kind": envelope.proposal.kind,
        "scopes": list(envelope.proposal.scopes),
        "temporal_type": envelope.proposal.temporal_type,
        "sensitivity": envelope.proposal.sensitivity,
        "rationale": envelope.proposal.rationale,
        "candidate_status": candidate_status,
    }


def _validate_policy_enums(envelope: ObservationEnvelope) -> None:
    if envelope.assertion.mode not in ASSERTION_MODES:
        raise ValueError(f"invalid assertion mode: {envelope.assertion.mode}")
    if envelope.assertion.modality not in ASSERTION_MODALITIES:
        raise ValueError(
            f"invalid assertion modality: {envelope.assertion.modality}"
        )
    if envelope.proposal.disposition not in DISPOSITIONS:
        raise ValueError(
            f"invalid proposal disposition: {envelope.proposal.disposition}"
        )
    if envelope.proposal.requested_confidence not in REQUESTED_CONFIDENCE:
        raise ValueError(
            "invalid proposal requested_confidence: "
            f"{envelope.proposal.requested_confidence}"
        )
    if envelope.proposal.sensitivity not in (
        PERSISTABLE_SENSITIVITY | NON_PERSISTABLE_SENSITIVITY
    ):
        raise ValueError(
            f"invalid proposal sensitivity: {envelope.proposal.sensitivity}"
        )


def _threshold_satisfied(envelope: ObservationEnvelope) -> bool:
    evidence = envelope.evidence
    return (
        evidence.count >= EVIDENCE_THRESHOLD["minimum_evidence"]
        and evidence.distinct_sessions
        >= EVIDENCE_THRESHOLD["minimum_distinct_sessions"]
        and evidence.time_span_days
        >= EVIDENCE_THRESHOLD["minimum_time_span_days"]
    )


def evaluate_observation(envelope: ObservationEnvelope) -> PolicyDecision:
    _validate_policy_enums(envelope)
    sensitivity = envelope.proposal.sensitivity
    if sensitivity == "secret":
        return PolicyDecision(
            status="rejected_policy",
            code="secret_persistence_forbidden",
            persistable_metadata={},
        )
    if sensitivity == "sensitive":
        return PolicyDecision(
            status="rejected_policy",
            code="sensitive_persistence_disabled",
            persistable_metadata={},
        )

    proposal = envelope.proposal
    if proposal.disposition in MATCH_REQUIRED and not proposal.match_memory_id:
        return PolicyDecision(
            status="needs_adjudication",
            code="match_memory_id_required",
            persistable_metadata={},
        )

    assertion_key = (envelope.assertion.mode, envelope.assertion.modality)
    confirmable = (
        envelope.assertion.subject == "user"
        and assertion_key in CONFIRMABLE_ASSERTIONS
    )
    if proposal.requested_confidence == "confirmed" and not confirmable:
        return PolicyDecision(
            status="deferred",
            code="assertion_not_confirmable",
            persistable_metadata=_candidate_metadata(envelope, "candidate"),
        )

    if envelope.assertion.mode == "behavior_observed":
        if _threshold_satisfied(envelope):
            return PolicyDecision(
                status="needs_adjudication",
                code="eligible_for_adjudication",
                persistable_metadata=_candidate_metadata(
                    envelope, "eligible_for_adjudication"
                ),
            )
        return PolicyDecision(
            status="deferred",
            code="more_evidence_required",
            persistable_metadata=_candidate_metadata(envelope, "candidate"),
        )

    if proposal.disposition == "need_more_evidence":
        return PolicyDecision(
            status="deferred",
            code="more_evidence_required",
            persistable_metadata=_candidate_metadata(envelope, "candidate"),
        )
    if proposal.disposition == "ignore":
        return PolicyDecision(
            status="accepted",
            code="ignored",
            persistable_metadata={},
        )

    return PolicyDecision(
        status="accepted",
        code="direct_assertion_accepted",
        persistable_metadata={
            **_candidate_metadata(envelope, "accepted"),
            "requested_confidence": proposal.requested_confidence,
            "match_memory_id": proposal.match_memory_id,
            "disposition": proposal.disposition,
        },
    )


def validate_transition(old: str, new: str) -> None:
    if old not in LIFECYCLE_TRANSITIONS:
        raise ValueError(f"unknown lifecycle status: {old}")
    if new not in LIFECYCLE_TRANSITIONS:
        raise ValueError(f"unknown lifecycle status: {new}")
    if old == new:
        return
    if new not in LIFECYCLE_TRANSITIONS[old]:
        raise ValueError(f"illegal lifecycle transition: {old} -> {new}")
