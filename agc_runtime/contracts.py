from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Status = Literal[
    "accepted",
    "deferred",
    "rejected_policy",
    "needs_adjudication",
    "failed",
]


@dataclass(frozen=True)
class SourceKey:
    ref: str
    revision: str
    content_hash: str

    @property
    def stable_id(self) -> str:
        return f"{self.ref}\x1f{self.revision}\x1f{self.content_hash}"


@dataclass(frozen=True)
class ToolResponse:
    tool: str
    action: str
    status: Status
    data: dict[str, Any] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()
    error: dict[str, str] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["warnings"] = list(self.warnings)
        return {"schema_version": 2, **payload}


def _strict_mapping(
    value: Any,
    name: str,
    fields: set[str],
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a mapping")
    unknown = set(value) - fields
    if unknown:
        raise ValueError(f"unknown {name} field: {sorted(unknown)[0]}")
    missing = fields - set(value)
    if missing:
        raise ValueError(f"missing {name} field: {sorted(missing)[0]}")
    return value


def _string(value: Any, name: str, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _string_list(value: Any, name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item for item in value
    ):
        raise ValueError(f"{name} must be a list of non-empty strings")
    return tuple(value)


def _non_negative_int(value: Any, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


@dataclass(frozen=True)
class ObservationSource(SourceKey):
    observed_at: str


@dataclass(frozen=True)
class Assertion:
    subject: str
    mode: str
    modality: str


@dataclass(frozen=True)
class Proposal:
    disposition: str
    match_memory_id: str | None
    kind: str
    scopes: tuple[str, ...]
    temporal_type: str
    sensitivity: str
    rationale: str
    requested_confidence: str


@dataclass(frozen=True)
class EvidenceSummary:
    count: int
    distinct_sessions: int
    time_span_days: int


@dataclass(frozen=True)
class ObservationEnvelope:
    observation_id: str
    source: ObservationSource
    assertion: Assertion
    proposal: Proposal
    evidence: EvidenceSummary

    @classmethod
    def from_mapping(cls, value: Any) -> "ObservationEnvelope":
        root = _strict_mapping(
            value,
            "observation",
            {"observation_id", "source", "assertion", "proposal", "evidence"},
        )
        source = _strict_mapping(
            root["source"],
            "source",
            {"ref", "revision", "content_hash", "observed_at"},
        )
        assertion = _strict_mapping(
            root["assertion"],
            "assertion",
            {"subject", "mode", "modality"},
        )
        proposal = _strict_mapping(
            root["proposal"],
            "proposal",
            {
                "disposition",
                "match_memory_id",
                "kind",
                "scopes",
                "temporal_type",
                "sensitivity",
                "rationale",
                "requested_confidence",
            },
        )
        evidence = _strict_mapping(
            root["evidence"],
            "evidence",
            {"count", "distinct_sessions", "time_span_days"},
        )
        match_memory_id = _string(
            proposal["match_memory_id"],
            "proposal.match_memory_id",
            optional=True,
        )
        return cls(
            observation_id=_string(root["observation_id"], "observation_id"),
            source=ObservationSource(
                ref=_string(source["ref"], "source.ref"),
                revision=_string(source["revision"], "source.revision"),
                content_hash=_string(
                    source["content_hash"], "source.content_hash"
                ),
                observed_at=_string(source["observed_at"], "source.observed_at"),
            ),
            assertion=Assertion(
                subject=_string(assertion["subject"], "assertion.subject"),
                mode=_string(assertion["mode"], "assertion.mode"),
                modality=_string(assertion["modality"], "assertion.modality"),
            ),
            proposal=Proposal(
                disposition=_string(
                    proposal["disposition"], "proposal.disposition"
                ),
                match_memory_id=match_memory_id,
                kind=_string(proposal["kind"], "proposal.kind"),
                scopes=_string_list(proposal["scopes"], "proposal.scopes"),
                temporal_type=_string(
                    proposal["temporal_type"], "proposal.temporal_type"
                ),
                sensitivity=_string(
                    proposal["sensitivity"], "proposal.sensitivity"
                ),
                rationale=_string(proposal["rationale"], "proposal.rationale"),
                requested_confidence=_string(
                    proposal["requested_confidence"],
                    "proposal.requested_confidence",
                ),
            ),
            evidence=EvidenceSummary(
                count=_non_negative_int(evidence["count"], "evidence.count"),
                distinct_sessions=_non_negative_int(
                    evidence["distinct_sessions"], "evidence.distinct_sessions"
                ),
                time_span_days=_non_negative_int(
                    evidence["time_span_days"], "evidence.time_span_days"
                ),
            ),
        )

    def to_mapping(self) -> dict[str, Any]:
        return {
            "observation_id": self.observation_id,
            "source": {
                "ref": self.source.ref,
                "revision": self.source.revision,
                "content_hash": self.source.content_hash,
                "observed_at": self.source.observed_at,
            },
            "assertion": {
                "subject": self.assertion.subject,
                "mode": self.assertion.mode,
                "modality": self.assertion.modality,
            },
            "proposal": {
                "disposition": self.proposal.disposition,
                "match_memory_id": self.proposal.match_memory_id,
                "kind": self.proposal.kind,
                "scopes": list(self.proposal.scopes),
                "temporal_type": self.proposal.temporal_type,
                "sensitivity": self.proposal.sensitivity,
                "rationale": self.proposal.rationale,
                "requested_confidence": self.proposal.requested_confidence,
            },
            "evidence": {
                "count": self.evidence.count,
                "distinct_sessions": self.evidence.distinct_sessions,
                "time_span_days": self.evidence.time_span_days,
            },
        }
