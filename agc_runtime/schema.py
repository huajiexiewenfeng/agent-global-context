import re
from datetime import date

from agc_runtime.models import MemoryItem


KINDS = {
    "identity",
    "principle",
    "preference",
    "interest",
    "capability",
    "goal",
    "pattern",
    "context",
}
LIFECYCLES = {
    "candidate",
    "active",
    "challenged",
    "dormant",
    "superseded",
    "historical",
    "rejected",
}
CONFIDENCE_LEVELS = {"tentative", "observed", "confirmed", "disputed"}
TEMPORAL_TYPES = {
    "durable",
    "evolving",
    "goal_bound",
    "contextual",
    "derived",
    "episodic",
}
RECALL_PRIORS = {"low", "medium", "high"}
DECISION_IMPACTS = {"low", "medium", "high"}
EXPOSURES = {
    "core_card",
    "scoped_card",
    "discoverable_only",
    "history_only",
}
FRESHNESS_POLICIES = {"event_driven", "periodic", "goal_bound", "contextual"}
SENSITIVITIES = {"normal", "personal", "sensitive", "secret"}
INTEREST_INTENSITIES = {"emerging", "low", "medium", "high"}
INTEREST_TRENDS = {"rising", "stable", "declining", "dormant"}
CAPABILITY_POLARITIES = {"strength", "growth_area"}
BODY_BUDGETS = {
    "Memory Card": 60,
    "Full Meaning": 300,
    "Application Boundary": 150,
    "Rationale": 100,
}
_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,79}$")


def _require_enum(value: str, allowed: set[str], name: str) -> None:
    if value not in allowed:
        raise ValueError(f"invalid {name}: {value}")


def _require_iso_date(value: str | None, name: str) -> None:
    if value is None:
        return
    try:
        date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"invalid {name}: expected ISO date") from error


def _validate_budgets(item: MemoryItem) -> None:
    values = {
        "Memory Card": item.memory_card,
        "Full Meaning": item.full_meaning,
        "Application Boundary": item.application_boundary,
        "Rationale": item.rationale,
    }
    for name, maximum in BODY_BUDGETS.items():
        if len(values[name]) > maximum:
            raise ValueError(f"{name} exceeds {maximum} Unicode code points")


def _validate_kind_metadata(item: MemoryItem) -> None:
    if item.kind == "interest":
        required = {
            "topic": item.topic,
            "intensity": item.intensity,
            "trend": item.trend,
            "motivation": item.motivation,
        }
        missing = [name for name, value in required.items() if value is None]
        if missing:
            raise ValueError(f"interest requires {missing[0]}")
        _require_enum(item.intensity or "", INTEREST_INTENSITIES, "interest intensity")
        _require_enum(item.trend or "", INTEREST_TRENDS, "interest trend")

    if item.kind == "capability":
        required = {
            "domain": item.domain,
            "polarity": item.polarity,
            "current_level": item.current_level,
        }
        missing = [name for name, value in required.items() if value is None]
        if missing:
            raise ValueError(f"capability requires {missing[0]}")
        _require_enum(
            item.polarity or "", CAPABILITY_POLARITIES, "capability polarity"
        )
        if (
            item.polarity == "growth_area"
            and item.recall.exposure in {"core_card", "scoped_card"}
            and not item.goal_refs
        ):
            raise ValueError(
                "growth_area requires active goal_refs for proactive exposure"
            )


def validate_memory_item(item: MemoryItem) -> None:
    if item.schema_version != 2:
        raise ValueError("schema_version must be 2")
    if not _ID_PATTERN.fullmatch(item.id):
        raise ValueError(f"invalid memory id: {item.id}")

    _require_enum(item.kind, KINDS, "kind")
    _require_enum(item.lifecycle.status, LIFECYCLES, "lifecycle status")
    _require_enum(item.confidence.level, CONFIDENCE_LEVELS, "confidence level")
    _require_enum(item.temporal.type, TEMPORAL_TYPES, "temporal type")
    _require_enum(item.recall.prior, RECALL_PRIORS, "recall prior")
    _require_enum(
        item.recall.decision_impact, DECISION_IMPACTS, "decision impact"
    )
    _require_enum(item.recall.exposure, EXPOSURES, "recall exposure")
    _require_enum(
        item.recall.freshness_policy,
        FRESHNESS_POLICIES,
        "freshness policy",
    )
    _require_enum(item.sensitivity, SENSITIVITIES, "sensitivity")
    if item.sensitivity in {"sensitive", "secret"}:
        raise ValueError(
            f"{item.sensitivity} content cannot be a persistent MemoryItem"
        )

    _require_iso_date(item.temporal.valid_from, "temporal.valid_from")
    _require_iso_date(item.temporal.last_observed, "temporal.last_observed")
    _require_iso_date(item.temporal.review_after, "temporal.review_after")
    _require_iso_date(item.provenance.created_at, "provenance.created_at")
    _require_iso_date(item.provenance.updated_at, "provenance.updated_at")
    _require_iso_date(item.provenance.confirmed_at, "provenance.confirmed_at")

    if (
        item.kind == "identity"
        and item.sensitivity == "personal"
        and item.recall.exposure == "core_card"
        and not item.policy_reason
    ):
        raise ValueError(
            "personal identity core_card requires an explicit policy_reason"
        )

    _validate_budgets(item)
    _validate_kind_metadata(item)
