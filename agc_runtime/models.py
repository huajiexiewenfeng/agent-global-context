from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from agc_runtime.frontmatter import (
    parse_body_sections,
    parse_frontmatter,
    render_markdown,
)


TOP_LEVEL_FIELDS = {
    "schema_version",
    "id",
    "kind",
    "subkind",
    "lifecycle",
    "confidence",
    "temporal",
    "recall",
    "sensitivity",
    "provenance",
    "policy_reason",
    "topic",
    "intensity",
    "trend",
    "motivation",
    "domain",
    "polarity",
    "current_level",
    "goal_refs",
}
NESTED_FIELDS = {
    "lifecycle": {"status"},
    "confidence": {"level"},
    "temporal": {"type", "valid_from", "last_observed", "review_after"},
    "recall": {
        "prior",
        "decision_impact",
        "exposure",
        "scopes",
        "applies_when",
        "not_when",
        "freshness_policy",
    },
    "provenance": {
        "created_at",
        "updated_at",
        "confirmed_at",
        "evidence_refs",
    },
}


def _require_mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping")
    unknown = set(value) - NESTED_FIELDS[name]
    if unknown:
        raise ValueError(f"unknown {name} field: {sorted(unknown)[0]}")
    missing = NESTED_FIELDS[name] - set(value)
    if missing:
        raise ValueError(f"missing {name} field: {sorted(missing)[0]}")
    return value


def _as_string(value: Any, name: str, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _as_strings(value: Any, name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item for item in value
    ):
        raise ValueError(f"{name} must be a list of non-empty strings")
    return tuple(value)


@dataclass(frozen=True)
class Lifecycle:
    status: str


@dataclass(frozen=True)
class Confidence:
    level: str


@dataclass(frozen=True)
class Temporal:
    type: str
    valid_from: str
    last_observed: str
    review_after: str | None


@dataclass(frozen=True)
class Recall:
    prior: str
    decision_impact: str
    exposure: str
    scopes: tuple[str, ...]
    applies_when: tuple[str, ...]
    not_when: tuple[str, ...]
    freshness_policy: str


@dataclass(frozen=True)
class Provenance:
    created_at: str
    updated_at: str
    confirmed_at: str | None
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class MemoryItem:
    schema_version: int
    id: str
    kind: str
    subkind: str
    lifecycle: Lifecycle
    confidence: Confidence
    temporal: Temporal
    recall: Recall
    sensitivity: str
    provenance: Provenance
    memory_card: str
    full_meaning: str
    application_boundary: str
    rationale: str
    policy_reason: str | None = None
    topic: str | None = None
    intensity: str | None = None
    trend: str | None = None
    motivation: str | None = None
    domain: str | None = None
    polarity: str | None = None
    current_level: str | None = None
    goal_refs: tuple[str, ...] = ()

    @classmethod
    def from_markdown(cls, text: str) -> "MemoryItem":
        values, body = parse_frontmatter(text)
        unknown = set(values) - TOP_LEVEL_FIELDS
        if unknown:
            raise ValueError(f"unknown frontmatter field: {sorted(unknown)[0]}")
        required = {
            "schema_version",
            "id",
            "kind",
            "subkind",
            "lifecycle",
            "confidence",
            "temporal",
            "recall",
            "sensitivity",
            "provenance",
        }
        missing = required - set(values)
        if missing:
            raise ValueError(f"missing frontmatter field: {sorted(missing)[0]}")

        lifecycle = _require_mapping(values["lifecycle"], "lifecycle")
        confidence = _require_mapping(values["confidence"], "confidence")
        temporal = _require_mapping(values["temporal"], "temporal")
        recall = _require_mapping(values["recall"], "recall")
        provenance = _require_mapping(values["provenance"], "provenance")
        sections = parse_body_sections(body)

        schema_version = values["schema_version"]
        if not isinstance(schema_version, int) or isinstance(schema_version, bool):
            raise ValueError("schema_version must be an integer")

        goal_refs = values.get("goal_refs", [])
        return cls(
            schema_version=schema_version,
            id=_as_string(values["id"], "id"),
            kind=_as_string(values["kind"], "kind"),
            subkind=_as_string(values["subkind"], "subkind"),
            lifecycle=Lifecycle(status=_as_string(lifecycle["status"], "lifecycle.status")),
            confidence=Confidence(
                level=_as_string(confidence["level"], "confidence.level")
            ),
            temporal=Temporal(
                type=_as_string(temporal["type"], "temporal.type"),
                valid_from=_as_string(temporal["valid_from"], "temporal.valid_from"),
                last_observed=_as_string(
                    temporal["last_observed"], "temporal.last_observed"
                ),
                review_after=_as_string(
                    temporal["review_after"], "temporal.review_after", optional=True
                ),
            ),
            recall=Recall(
                prior=_as_string(recall["prior"], "recall.prior"),
                decision_impact=_as_string(
                    recall["decision_impact"], "recall.decision_impact"
                ),
                exposure=_as_string(recall["exposure"], "recall.exposure"),
                scopes=_as_strings(recall["scopes"], "recall.scopes"),
                applies_when=_as_strings(
                    recall["applies_when"], "recall.applies_when"
                ),
                not_when=_as_strings(recall["not_when"], "recall.not_when"),
                freshness_policy=_as_string(
                    recall["freshness_policy"], "recall.freshness_policy"
                ),
            ),
            sensitivity=_as_string(values["sensitivity"], "sensitivity"),
            provenance=Provenance(
                created_at=_as_string(provenance["created_at"], "provenance.created_at"),
                updated_at=_as_string(provenance["updated_at"], "provenance.updated_at"),
                confirmed_at=_as_string(
                    provenance["confirmed_at"],
                    "provenance.confirmed_at",
                    optional=True,
                ),
                evidence_refs=_as_strings(
                    provenance["evidence_refs"], "provenance.evidence_refs"
                ),
            ),
            memory_card=sections["Memory Card"],
            full_meaning=sections["Full Meaning"],
            application_boundary=sections["Application Boundary"],
            rationale=sections["Rationale"],
            policy_reason=_as_string(
                values.get("policy_reason"), "policy_reason", optional=True
            ),
            topic=_as_string(values.get("topic"), "topic", optional=True),
            intensity=_as_string(
                values.get("intensity"), "intensity", optional=True
            ),
            trend=_as_string(values.get("trend"), "trend", optional=True),
            motivation=_as_string(
                values.get("motivation"), "motivation", optional=True
            ),
            domain=_as_string(values.get("domain"), "domain", optional=True),
            polarity=_as_string(values.get("polarity"), "polarity", optional=True),
            current_level=_as_string(
                values.get("current_level"), "current_level", optional=True
            ),
            goal_refs=_as_strings(goal_refs, "goal_refs"),
        )

    def to_markdown(self) -> str:
        frontmatter: dict[str, Any] = {
            "schema_version": self.schema_version,
            "id": self.id,
            "kind": self.kind,
            "subkind": self.subkind,
            "lifecycle": {"status": self.lifecycle.status},
            "confidence": {"level": self.confidence.level},
            "temporal": {
                "type": self.temporal.type,
                "valid_from": self.temporal.valid_from,
                "last_observed": self.temporal.last_observed,
                "review_after": self.temporal.review_after,
            },
            "recall": {
                "prior": self.recall.prior,
                "decision_impact": self.recall.decision_impact,
                "exposure": self.recall.exposure,
                "scopes": list(self.recall.scopes),
                "applies_when": list(self.recall.applies_when),
                "not_when": list(self.recall.not_when),
                "freshness_policy": self.recall.freshness_policy,
            },
            "sensitivity": self.sensitivity,
            "provenance": {
                "created_at": self.provenance.created_at,
                "updated_at": self.provenance.updated_at,
                "confirmed_at": self.provenance.confirmed_at,
                "evidence_refs": list(self.provenance.evidence_refs),
            },
        }
        optional = (
            "policy_reason",
            "topic",
            "intensity",
            "trend",
            "motivation",
            "domain",
            "polarity",
            "current_level",
        )
        for name in optional:
            value = getattr(self, name)
            if value is not None:
                frontmatter[name] = value
        if self.goal_refs:
            frontmatter["goal_refs"] = list(self.goal_refs)

        return render_markdown(
            frontmatter,
            {
                "Memory Card": self.memory_card,
                "Full Meaning": self.full_meaning,
                "Application Boundary": self.application_boundary,
                "Rationale": self.rationale,
            },
        )
