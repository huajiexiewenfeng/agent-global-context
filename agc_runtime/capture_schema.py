"""Strict mapping parsers for Capture's independent on-disk contracts."""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from typing import Any

from agc_runtime.capture_contracts import (
    CAPTURE_SCHEMA_VERSION, CAPTURE_STATUSES, BudgetSettlement, CaptureKey, CaptureLease,
    CaptureReceipt, CaptureSuppressionTombstone, CollectedObservation, LedgerEntry,
    RevisionRef, SanitizedError, SourceQuarantine, TokenReservation, TokenUsage,
    observation_fingerprint_for, observation_id_for, receipt_id_for, tombstone_id_for,
)


_HASH = re.compile(r"^[0-9a-f]{64}$")
_IDENTITY_QUALITIES = frozenset({"session_id", "legacy_rollout_id", "unknown"})
_USAGE_QUALITIES = frozenset({"actual", "reserved"})
_ZERO_REASONS = frozenset({"no_durable_signal", "extractor_empty", "all_filtered_safety", "all_filtered_policy", "all_duplicates_within_revision", "user_forget"})
_CATEGORIES = frozenset({"personal_growth", "research", "learning", "project", "work"})
_KINDS = frozenset({"identity", "principle", "preference", "interest", "capability", "goal", "pattern", "context"})
_CONFIDENCE = frozenset({"tentative", "observed", "confirmed", "disputed"})
_SIGNAL_TYPES = frozenset({"explicit_user_state", "decision_or_constraint", "verified_outcome", "reusable_method", "learning_change", "research_change", "capability_evidence", "open_commitment"})
_MACHINE_CODE = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$")
_PROJECT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
_URI_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
_OPAQUE = re.compile(r"^[A-Za-z0-9._~-]{1,512}$")


def _strict(
    value: Any,
    name: str,
    fields: set[str],
    *,
    allow_extra: bool = False,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a mapping")
    if any(not isinstance(field, str) for field in value):
        raise ValueError(f"{name} field names must be strings")
    unknown = set(value) - fields
    missing = fields - set(value)
    if unknown and not allow_extra:
        raise ValueError(f"unknown field(s) for {name}: {len(unknown)}")
    if missing:
        raise ValueError(f"missing {name} field: {sorted(missing)[0]}")
    return value


def _schema(value: Any, name: str) -> int:
    if type(value) is not int or value != CAPTURE_SCHEMA_VERSION:
        raise ValueError(f"{name}.schema_version must be {CAPTURE_SCHEMA_VERSION}")
    return value


def _nfc_string(
    value: Any, name: str, *, maximum: int, nullable: bool = False
) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    if len(value) > maximum or unicodedata.normalize("NFC", value) != value:
        raise ValueError(f"{name} must be NFC and at most {maximum} characters")
    if any(unicodedata.category(character).startswith("C") for character in value):
        raise ValueError(f"{name} must not contain control characters")
    return value


def _identifier(value: Any, name: str, *, nullable: bool = False) -> str | None:
    value = _nfc_string(value, name, maximum=128, nullable=nullable)
    if value is None:
        return None
    if not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"{name} must be an ASCII identifier")
    return value


def _version(value: Any, name: str, *, nullable: bool = False) -> str | None:
    value = _nfc_string(value, name, maximum=64, nullable=nullable)
    if value is None:
        return None
    if not _VERSION.fullmatch(value):
        raise ValueError(f"{name} must be an ASCII version identifier")
    return value


def _project_id(value: Any, name: str, *, nullable: bool = False) -> str | None:
    value = _nfc_string(value, name, maximum=128, nullable=nullable)
    if value is None:
        return None
    if not _PROJECT_ID.fullmatch(value):
        raise ValueError(f"{name} must be an ASCII project identifier")
    return value


def _opaque_project_id(value: Any, name: str) -> str:
    result = _project_id(value, name)
    assert isinstance(result, str)
    if (
        result.startswith(("/", "\\"))
        or re.match(r"^[A-Za-z]:[/\\]", result)
        or re.match(r"(?i)^file:(?:/+|[a-z]:/)", result)
    ):
        raise ValueError(f"{name} must not be an absolute path")
    return result


def _scope_id(value: Any, name: str) -> str:
    value = _nfc_string(value, name, maximum=128)
    assert isinstance(value, str)
    if (
        not value[0].isalnum()
        or any(not character.isalnum() and character not in "._:/-" for character in value)
    ):
        raise ValueError(f"{name} must be a bounded scope identifier")
    return value


def _locator(value: Any, name: str, *, nullable: bool = False) -> str | None:
    value = _nfc_string(value, name, maximum=512, nullable=nullable)
    if value is None:
        return None
    if (
        value.startswith(("/", "\\"))
        or "\\" in value
        or _URI_SCHEME.match(value)
        or any(segment in {"", ".", ".."} for segment in value.split("/"))
    ):
        raise ValueError(f"{name} must be a relative opaque locator")
    return value


def _utc(value: Any, name: str, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(f"{name} must be a UTC timestamp ending in Z")
    try:
        datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise ValueError(f"{name} must be a valid UTC timestamp") from error
    return value


def _integer(value: Any, name: str, *, minimum: int = 0) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


def _enum(value: Any, name: str, choices: frozenset[str]) -> str:
    if not isinstance(value, str) or value not in choices:
        raise ValueError(f"{name} must be one of {sorted(choices)}")
    return value


def _hash(value: Any, name: str, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or not _HASH.fullmatch(value):
        raise ValueError(f"{name} must be a lowercase SHA-256 hash")
    return value


def validate_sha256(value: Any, name: str) -> str:
    result = _hash(value, name)
    assert isinstance(result, str)
    return result


def _machine_code(value: Any, name: str, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or not _MACHINE_CODE.fullmatch(value):
        raise ValueError(f"{name} must be a 1-64 character machine-code slug")
    return value


def validate_capture_id(value: Any, name: str, prefix: str) -> str:
    if (
        not isinstance(value, str)
        or not value.startswith(prefix)
        or not _HASH.fullmatch(value[len(prefix):])
    ):
        raise ValueError(f"{name} must be a canonical {prefix} SHA-256 id")
    return value


def capture_key_from_mapping(value: Any) -> CaptureKey:
    root = _strict(value, "CaptureKey", {"adapter_id", "source_root_id", "task_id", "revision_id"})
    return CaptureKey(
        _identifier(root["adapter_id"], "CaptureKey.adapter_id"),
        validate_sha256(root["source_root_id"], "CaptureKey.source_root_id"),
        _identifier(root["task_id"], "CaptureKey.task_id"),
        _identifier(root["revision_id"], "CaptureKey.revision_id"),
    )


def revision_ref_from_mapping(value: Any) -> RevisionRef:
    root = _strict(value, "RevisionRef", {"schema_version", "capture_key", "rollout_anchor_id", "completed_at", "locator", "identity_quality", "adapter_version", "source_schema_version"})
    _schema(root["schema_version"], "RevisionRef")
    return RevisionRef(
        capture_key_from_mapping(root["capture_key"]),
        _identifier(root["rollout_anchor_id"], "RevisionRef.rollout_anchor_id"),
        _utc(root["completed_at"], "RevisionRef.completed_at"),
        _locator(root["locator"], "RevisionRef.locator", nullable=True),
        _enum(root["identity_quality"], "RevisionRef.identity_quality", _IDENTITY_QUALITIES),
        _version(root["adapter_version"], "RevisionRef.adapter_version"),
        _version(root["source_schema_version"], "RevisionRef.source_schema_version"),
    )


def token_usage_from_mapping(value: Any) -> TokenUsage:
    root = _strict(value, "TokenUsage", {"input_tokens", "output_tokens", "total_tokens"})
    input_tokens = _integer(root["input_tokens"], "TokenUsage.input_tokens")
    output_tokens = _integer(root["output_tokens"], "TokenUsage.output_tokens")
    total_tokens = _integer(root["total_tokens"], "TokenUsage.total_tokens")
    if total_tokens != input_tokens + output_tokens:
        raise ValueError("TokenUsage.total_tokens must equal input_tokens + output_tokens")
    return TokenUsage(input_tokens, output_tokens, total_tokens)


def token_reservation_from_mapping(value: Any) -> TokenReservation:
    root = _strict(
        value,
        "TokenReservation",
        {
            "schema_version",
            "reservation_id",
            "pool",
            "census_id",
            "capture_key",
            "attempt",
            "maximum_usage",
            "reserved_at",
        },
    )
    return TokenReservation(
        _schema(root["schema_version"], "TokenReservation"),
        validate_capture_id(
            root["reservation_id"], "TokenReservation.reservation_id", "br_"
        ),
        _enum(
            root["pool"],
            "TokenReservation.pool",
            frozenset({"backfill", "incremental"}),
        ),
        _nfc_string(
            root["census_id"],
            "TokenReservation.census_id",
            maximum=80,
            nullable=True,
        ),
        capture_key_from_mapping(root["capture_key"]),
        _integer(root["attempt"], "TokenReservation.attempt", minimum=1),
        token_usage_from_mapping(root["maximum_usage"]),
        _utc(root["reserved_at"], "TokenReservation.reserved_at"),
    )


def budget_settlement_from_mapping(value: Any) -> BudgetSettlement:
    root = _strict(
        value,
        "BudgetSettlement",
        {
            "schema_version",
            "reservation_id",
            "capture_key",
            "charged_usage",
            "usage_quality",
            "settled_at",
        },
    )
    return BudgetSettlement(
        _schema(root["schema_version"], "BudgetSettlement"),
        validate_capture_id(
            root["reservation_id"], "BudgetSettlement.reservation_id", "br_"
        ),
        capture_key_from_mapping(root["capture_key"]),
        token_usage_from_mapping(root["charged_usage"]),
        _enum(
            root["usage_quality"],
            "BudgetSettlement.usage_quality",
            _USAGE_QUALITIES,
        ),
        _utc(root["settled_at"], "BudgetSettlement.settled_at"),
    )


def sanitized_error_from_mapping(value: Any) -> SanitizedError:
    root = _strict(value, "SanitizedError", {"stage", "code", "retryable"})
    if not isinstance(root["retryable"], bool):
        raise ValueError("SanitizedError.retryable must be a boolean")
    return SanitizedError(_machine_code(root["stage"], "SanitizedError.stage"), _machine_code(root["code"], "SanitizedError.code"), root["retryable"])


def _optional_pair(root: dict[str, Any], left: str, right: str, name: str) -> tuple[str | None, str | None]:
    first = _hash(root[left], left, nullable=True)
    second = _version(root[right], right, nullable=True)
    if (first is None) != (second is None):
        raise ValueError(f"{name} fields must both be null or both be present")
    return first, second


def capture_receipt_from_mapping(value: Any) -> CaptureReceipt:
    fields = {"schema_version", "receipt_id", "adapter_id", "adapter_version", "source_schema_version", "source_root_id", "task_id", "revision_id", "identity_quality", "source_fingerprint", "source_hash_schema_version", "capsule_hash", "capsule_schema_version", "settled_at", "discovered_at", "updated_at", "status", "attempt_count", "next_retry_at", "extractor_id", "extractor_version", "extractor_schema_version", "taxonomy_version", "observation_count", "filtered_counts", "duplicate_suppression_count", "token_usage", "usage_quality", "redacted_by_forget", "forgotten_observation_count", "zero_reason", "sanitized_error", "coalesced_to", "exclusion_reason"}
    root = _strict(value, "CaptureReceipt", fields)
    schema_version = _schema(root["schema_version"], "CaptureReceipt")
    receipt_id = validate_capture_id(root["receipt_id"], "CaptureReceipt.receipt_id", "cr_")
    key = capture_key_from_mapping(
        {name: root[name] for name in ("adapter_id", "source_root_id", "task_id", "revision_id")}
    )
    if receipt_id != receipt_id_for(key):
        raise ValueError("CaptureReceipt.receipt_id does not match its CaptureKey")
    status = _enum(root["status"], "CaptureReceipt.status", CAPTURE_STATUSES)
    source_fingerprint, source_hash_schema_version = _optional_pair(root, "source_fingerprint", "source_hash_schema_version", "source")
    capsule_hash, capsule_schema_version = _optional_pair(root, "capsule_hash", "capsule_schema_version", "capsule")
    extractor_values = (
        _identifier(root["extractor_id"], "CaptureReceipt.extractor_id", nullable=True),
        _version(root["extractor_version"], "CaptureReceipt.extractor_version", nullable=True),
        _version(root["extractor_schema_version"], "CaptureReceipt.extractor_schema_version", nullable=True),
    )
    taxonomy_version = _version(root["taxonomy_version"], "CaptureReceipt.taxonomy_version", nullable=True)
    extraction_metadata = (*extractor_values, taxonomy_version)
    if any(item is None for item in extraction_metadata) and any(item is not None for item in extraction_metadata):
        raise ValueError("extractor fields and taxonomy must all be null or all be present")
    has_extraction_metadata = all(item is not None for item in extraction_metadata)
    post_extracting = {"extracting", "complete", "retryable", "failed"}
    if status in post_extracting and any(item is None for item in extraction_metadata):
        raise ValueError("extractor fields and taxonomy must be present after extracting")
    if status not in post_extracting | {"quarantined"} and any(item is not None for item in extraction_metadata):
        raise ValueError("extractor fields and taxonomy must be null before extracting")
    observation_count = root["observation_count"]
    filtered_counts = root["filtered_counts"]
    duplicate_suppression_count = root["duplicate_suppression_count"]
    if status == "complete":
        observation_count = _integer(observation_count, "CaptureReceipt.observation_count")
        if observation_count > 8:
            raise ValueError("CaptureReceipt.observation_count must be between 0 and 8")
        filtered_counts = _strict(filtered_counts, "CaptureReceipt.filtered_counts", {"safety", "policy", "over_limit"})
        filtered_counts = {name: _integer(amount, f"CaptureReceipt.filtered_counts.{name}") for name, amount in filtered_counts.items()}
        duplicate_suppression_count = _integer(duplicate_suppression_count, "CaptureReceipt.duplicate_suppression_count")
    elif any(item is not None for item in (observation_count, filtered_counts, duplicate_suppression_count)):
        raise ValueError("observation result fields must be null before complete")
    redacted = root["redacted_by_forget"]
    if not isinstance(redacted, bool):
        raise ValueError("CaptureReceipt.redacted_by_forget must be a boolean")
    forgotten = _integer(root["forgotten_observation_count"], "CaptureReceipt.forgotten_observation_count")
    if redacted != (forgotten > 0):
        raise ValueError(
            "redacted_by_forget must equal whether forgotten_observation_count is positive"
        )
    if redacted and (source_fingerprint is not None or capsule_hash is not None):
        raise ValueError("redacted receipt must clear source and capsule hashes")
    if has_extraction_metadata and not redacted and any(
        item is None
        for item in (
            source_fingerprint,
            source_hash_schema_version,
            capsule_hash,
            capsule_schema_version,
        )
    ):
        raise ValueError(
            "post-extraction source and capsule hash fields must be present unless redacted"
        )
    zero_reason = root["zero_reason"]
    if status == "complete" and observation_count == 0:
        zero_reason = _enum(zero_reason, "CaptureReceipt.zero_reason", _ZERO_REASONS)
        if redacted and zero_reason != "user_forget":
            raise ValueError("redacted zero-observation receipt requires zero_reason=user_forget")
        if not redacted and zero_reason == "user_forget":
            raise ValueError("zero_reason=user_forget requires redacted_by_forget")
    elif zero_reason is not None:
        raise ValueError("zero_reason is required only for complete receipts with zero observations")
    sanitized = root["sanitized_error"]
    if status in {"retryable", "failed", "quarantined"}:
        sanitized = sanitized_error_from_mapping(sanitized)
        expected_retryable = status == "retryable"
        if sanitized.retryable is not expected_retryable:
            raise ValueError(
                "sanitized_error.retryable must match the CaptureReceipt status"
            )
    elif sanitized is not None:
        raise ValueError("sanitized_error is allowed only for retryable, failed, or quarantined receipts")
    coalesced_to = root["coalesced_to"]
    if coalesced_to is not None:
        coalesced_to = validate_capture_id(coalesced_to, "CaptureReceipt.coalesced_to", "cr_")
    exclusion_reason = _machine_code(root["exclusion_reason"], "CaptureReceipt.exclusion_reason", nullable=True)
    if (status == "coalesced") != (coalesced_to is not None):
        raise ValueError("coalesced_to is required only for coalesced receipts")
    if coalesced_to == receipt_id:
        raise ValueError("CaptureReceipt.coalesced_to cannot reference self")
    if (status == "excluded") != (exclusion_reason is not None):
        raise ValueError("exclusion_reason is required only for excluded receipts")
    next_retry_at = _utc(root["next_retry_at"], "CaptureReceipt.next_retry_at", nullable=True)
    if (status == "retryable") != (next_retry_at is not None):
        raise ValueError("next_retry_at is required only for retryable receipts")
    return CaptureReceipt(schema_version, receipt_id, key.adapter_id, _version(root["adapter_version"], "CaptureReceipt.adapter_version"), _version(root["source_schema_version"], "CaptureReceipt.source_schema_version"), key.source_root_id, key.task_id, key.revision_id, _enum(root["identity_quality"], "CaptureReceipt.identity_quality", _IDENTITY_QUALITIES), source_fingerprint, source_hash_schema_version, capsule_hash, capsule_schema_version, *(_utc(root[name], f"CaptureReceipt.{name}") for name in ("settled_at", "discovered_at", "updated_at")), status, _integer(root["attempt_count"], "CaptureReceipt.attempt_count"), next_retry_at, *extractor_values, taxonomy_version, observation_count, filtered_counts, duplicate_suppression_count, token_usage_from_mapping(root["token_usage"]), _enum(root["usage_quality"], "CaptureReceipt.usage_quality", _USAGE_QUALITIES), redacted, forgotten, zero_reason, sanitized, coalesced_to, exclusion_reason)


def observation_fingerprint_payload(value: Any) -> dict[str, Any]:
    root = _strict(
        value,
        "ObservationFingerprint",
        {
            "statement", "assertion", "primary_category", "kind", "scopes",
            "project_scope", "signal_type",
        },
        allow_extra=True,
    )
    raw_statement = root["statement"]
    if not isinstance(raw_statement, str):
        raise ValueError("ObservationFingerprint.statement must be a string")
    statement = unicodedata.normalize("NFC", " ".join(raw_statement.split()))
    statement = _nfc_string(
        statement, "ObservationFingerprint.statement", maximum=300
    )
    assertion = _strict(
        root["assertion"],
        "ObservationFingerprint.assertion",
        {"subject", "mode", "modality"},
    )
    assertion_payload = {
        "subject": _identifier(assertion["subject"], "ObservationFingerprint.assertion.subject"),
        "mode": _enum(assertion["mode"], "ObservationFingerprint.assertion.mode", frozenset({"direct", "behavior_observed", "agent_inferred"})),
        "modality": _enum(assertion["modality"], "ObservationFingerprint.assertion.modality", frozenset({"asserted"})),
    }
    scopes = root["scopes"]
    if not isinstance(scopes, list) or not scopes:
        raise ValueError("ObservationFingerprint.scopes must be a non-empty list")
    normalized_scopes = []
    for scope in scopes:
        if not isinstance(scope, str):
            raise ValueError("ObservationFingerprint.scope must be a string")
        normalized_scopes.append(
            _scope_id(
                unicodedata.normalize("NFC", scope),
                "ObservationFingerprint.scope",
            )
        )
    if len(set(normalized_scopes)) != len(normalized_scopes):
        raise ValueError(
            "ObservationFingerprint.scopes must be unique after NFC normalization"
        )
    return {
        "schema_version": CAPTURE_SCHEMA_VERSION,
        "statement": statement,
        "assertion": assertion_payload,
        "primary_category": _enum(root["primary_category"], "ObservationFingerprint.primary_category", _CATEGORIES),
        "kind": _enum(root["kind"], "ObservationFingerprint.kind", _KINDS),
        "scopes": sorted(normalized_scopes),
        "project_scope": _project_id(root["project_scope"], "ObservationFingerprint.project_scope", nullable=True),
        "signal_type": _enum(root["signal_type"], "ObservationFingerprint.signal_type", _SIGNAL_TYPES),
    }


def collected_observation_from_mapping(value: Any) -> CollectedObservation:
    fields = {"schema_version", "observation_id", "receipt_id", "source", "ordinal", "observation_fingerprint", "statement", "assertion", "primary_category", "taxonomy_version", "kind", "scopes", "project_scope", "confidence", "sensitivity", "signal_type", "observed_at", "captured_at", "extractor_version", "processing_state"}
    root = _strict(value, "CollectedObservation", fields)
    source = _strict(root["source"], "CollectedObservation.source", {"adapter_id", "source_root_id", "task_id", "revision_id", "locator"})
    source_value = {
        "adapter_id": _identifier(source["adapter_id"], "CollectedObservation.source.adapter_id"),
        "source_root_id": validate_sha256(source["source_root_id"], "CollectedObservation.source.source_root_id"),
        "task_id": _identifier(source["task_id"], "CollectedObservation.source.task_id"),
        "revision_id": _identifier(source["revision_id"], "CollectedObservation.source.revision_id"),
        "locator": _locator(source["locator"], "CollectedObservation.source.locator", nullable=True),
    }
    assertion = _strict(root["assertion"], "CollectedObservation.assertion", {"subject", "mode", "modality"})
    assertion_value = {
        "subject": _identifier(assertion["subject"], "CollectedObservation.assertion.subject"),
        "mode": _enum(assertion["mode"], "CollectedObservation.assertion.mode", frozenset({"direct", "behavior_observed", "agent_inferred"})),
        "modality": _enum(assertion["modality"], "CollectedObservation.assertion.modality", frozenset({"asserted"})),
    }
    if assertion_value["mode"] not in {"direct", "behavior_observed", "agent_inferred"} or assertion_value["modality"] != "asserted":
        raise ValueError("CollectedObservation.assertion has an unsupported mode or modality")
    confidence = _enum(root["confidence"], "CollectedObservation.confidence", _CONFIDENCE)
    if assertion_value["mode"] == "agent_inferred" and confidence != "tentative":
        raise ValueError("agent_inferred observations must use tentative confidence")
    statement = root["statement"]
    if not isinstance(statement, str) or not statement.strip():
        raise ValueError("CollectedObservation.statement must be a non-empty string")
    statement = unicodedata.normalize("NFC", statement)
    if len(statement) > 300:
        raise ValueError("CollectedObservation.statement must be at most 300 Unicode code points")
    scopes = root["scopes"]
    if not isinstance(scopes, list) or not scopes:
        raise ValueError("CollectedObservation.scopes must be a non-empty unique list of strings")
    normalized_scopes = tuple(
        _scope_id(
            unicodedata.normalize("NFC", item)
            if isinstance(item, str)
            else item,
            "CollectedObservation.scope",
        )
        for item in scopes
    )
    if len(set(normalized_scopes)) != len(normalized_scopes):
        raise ValueError("CollectedObservation.scopes must be unique after NFC normalization")
    observation_id = validate_capture_id(root["observation_id"], "CollectedObservation.observation_id", "co_")
    receipt_id = validate_capture_id(root["receipt_id"], "CollectedObservation.receipt_id", "cr_")
    fingerprint = _hash(root["observation_fingerprint"], "CollectedObservation.observation_fingerprint")
    if not observation_id.startswith("co_") or not _HASH.fullmatch(observation_id[3:]) or not receipt_id.startswith("cr_") or not _HASH.fullmatch(receipt_id[3:]):
        raise ValueError("CollectedObservation IDs must be canonical capture IDs")
    source_key = CaptureKey(
        source_value["adapter_id"], source_value["source_root_id"],
        source_value["task_id"], source_value["revision_id"],
    )
    if receipt_id != receipt_id_for(source_key):
        raise ValueError("CollectedObservation.receipt_id does not match its source CaptureKey")
    if fingerprint != observation_fingerprint_for(root):
        raise ValueError("CollectedObservation.observation_fingerprint does not match its canonical fields")
    if observation_id != observation_id_for(receipt_id, fingerprint):
        raise ValueError("CollectedObservation.observation_id does not match its receipt and fingerprint")
    return CollectedObservation(_schema(root["schema_version"], "CollectedObservation"), observation_id, receipt_id, source_value, _integer(root["ordinal"], "CollectedObservation.ordinal"), fingerprint, statement, assertion_value, _enum(root["primary_category"], "CollectedObservation.primary_category", _CATEGORIES), _version(root["taxonomy_version"], "CollectedObservation.taxonomy_version"), _enum(root["kind"], "CollectedObservation.kind", _KINDS), normalized_scopes, _project_id(root["project_scope"], "CollectedObservation.project_scope", nullable=True), confidence, _enum(root["sensitivity"], "CollectedObservation.sensitivity", frozenset({"normal", "personal"})), _enum(root["signal_type"], "CollectedObservation.signal_type", _SIGNAL_TYPES), _utc(root["observed_at"], "CollectedObservation.observed_at"), _utc(root["captured_at"], "CollectedObservation.captured_at"), _version(root["extractor_version"], "CollectedObservation.extractor_version"), _enum(root["processing_state"], "CollectedObservation.processing_state", frozenset({"collected"})))


def ledger_entry_from_mapping(value: Any) -> LedgerEntry:
    root = _strict(value, "LedgerEntry", {"schema_version", "capture_key", "receipt_id", "discovered_at", "processed_at", "status"})
    key = capture_key_from_mapping(root["capture_key"])
    receipt_id = validate_capture_id(root["receipt_id"], "LedgerEntry.receipt_id", "cr_")
    if receipt_id != receipt_id_for(key):
        raise ValueError("LedgerEntry.receipt_id does not match its CaptureKey")
    return LedgerEntry(_schema(root["schema_version"], "LedgerEntry"), key, receipt_id, _utc(root["discovered_at"], "LedgerEntry.discovered_at"), _utc(root["processed_at"], "LedgerEntry.processed_at", nullable=True), _enum(root["status"], "LedgerEntry.status", CAPTURE_STATUSES))


def capture_lease_from_mapping(value: Any) -> CaptureLease:
    root = _strict(value, "CaptureLease", {"schema_version", "capture_key", "owner_id", "fencing_token", "acquired_at", "expires_at"})
    return CaptureLease(_schema(root["schema_version"], "CaptureLease"), capture_key_from_mapping(root["capture_key"]), _identifier(root["owner_id"], "CaptureLease.owner_id"), _integer(root["fencing_token"], "CaptureLease.fencing_token", minimum=1), _utc(root["acquired_at"], "CaptureLease.acquired_at"), _utc(root["expires_at"], "CaptureLease.expires_at"))


def source_quarantine_from_mapping(value: Any) -> SourceQuarantine:
    root = _strict(value, "SourceQuarantine", {"schema_version", "adapter_id", "source_root_id", "created_at", "code"})
    return SourceQuarantine(_schema(root["schema_version"], "SourceQuarantine"), _identifier(root["adapter_id"], "SourceQuarantine.adapter_id"), validate_sha256(root["source_root_id"], "SourceQuarantine.source_root_id"), _utc(root["created_at"], "SourceQuarantine.created_at"), _machine_code(root["code"], "SourceQuarantine.code"))


def capture_suppression_tombstone_from_mapping(value: Any) -> CaptureSuppressionTombstone:
    root = _strict(value, "CaptureSuppressionTombstone", {"schema_version", "tombstone_id", "capture_key", "created_at", "reason"})
    if root["reason"] != "user_forget":
        raise ValueError("CaptureSuppressionTombstone.reason must be user_forget")
    key = capture_key_from_mapping(root["capture_key"])
    tombstone_id = validate_capture_id(root["tombstone_id"], "CaptureSuppressionTombstone.tombstone_id", "ct_")
    if tombstone_id != tombstone_id_for(key):
        raise ValueError("CaptureSuppressionTombstone.tombstone_id does not match its CaptureKey")
    return CaptureSuppressionTombstone(_schema(root["schema_version"], "CaptureSuppressionTombstone"), tombstone_id, key, _utc(root["created_at"], "CaptureSuppressionTombstone.created_at"), root["reason"])


def _string_tuple(value: Any, name: str, parser: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be a list")
    parsed = tuple(parser(item, f"{name} item") for item in value)
    if len(set(parsed)) != len(parsed):
        raise ValueError(f"{name} must not contain duplicates")
    return parsed


def adapter_descriptor_from_mapping(value: Any) -> Any:
    from agc_runtime.capture_source import AdapterDescriptor

    root = _strict(value, "AdapterDescriptor", {"schema_version", "adapter_id", "adapter_version", "source_schema_version", "source_root_id", "capabilities"})
    capabilities = _string_tuple(root["capabilities"], "AdapterDescriptor.capabilities", _machine_code)
    return AdapterDescriptor(_schema(root["schema_version"], "AdapterDescriptor"), _identifier(root["adapter_id"], "AdapterDescriptor.adapter_id"), _version(root["adapter_version"], "AdapterDescriptor.adapter_version"), _version(root["source_schema_version"], "AdapterDescriptor.source_schema_version"), validate_sha256(root["source_root_id"], "AdapterDescriptor.source_root_id"), capabilities)


def source_binding_key_from_mapping(value: Any) -> Any:
    from agc_runtime.capture_source import SourceBindingKey

    root = _strict(value, "SourceBindingKey", {"schema_version", "adapter_id", "source_root_id"})
    return SourceBindingKey(_schema(root["schema_version"], "SourceBindingKey"), _identifier(root["adapter_id"], "SourceBindingKey.adapter_id"), validate_sha256(root["source_root_id"], "SourceBindingKey.source_root_id"))


_MARKER_FIELDS = {"schema_version", "adapter_id", "adapter_version", "source_schema_version", "source_root_id", "task_id", "revision_id", "locator", "observed_at", "hook_event"}


def _marker_values(value: Any, name: str) -> tuple[Any, ...]:
    root = _strict(value, name, _MARKER_FIELDS)
    if root["hook_event"] != "Stop":
        raise ValueError(f"{name}.hook_event must be Stop")
    return (_schema(root["schema_version"], name), _identifier(root["adapter_id"], f"{name}.adapter_id"), _version(root["adapter_version"], f"{name}.adapter_version"), _version(root["source_schema_version"], f"{name}.source_schema_version"), validate_sha256(root["source_root_id"], f"{name}.source_root_id"), _identifier(root["task_id"], f"{name}.task_id"), _identifier(root["revision_id"], f"{name}.revision_id"), _locator(root["locator"], f"{name}.locator", nullable=True), _utc(root["observed_at"], f"{name}.observed_at"), "Stop")


def stop_hook_envelope_from_mapping(value: Any) -> Any:
    from agc_runtime.capture_source import StopHookEnvelope

    fields = {"session_id", "turn_id", "transcript_path", "cwd", "hook_event_name", "model", "stop_hook_active", "last_assistant_message"}
    root = _strict(value, "StopHookEnvelope", fields)
    if root["hook_event_name"] != "Stop":
        raise ValueError("StopHookEnvelope.hook_event_name must be Stop")
    for field in ("transcript_path", "cwd"):
        if not isinstance(root[field], str) or not root[field] or len(root[field]) > 32768:
            raise ValueError(f"StopHookEnvelope.{field} must be a bounded non-empty string")
    if not isinstance(root["model"], str) or not root["model"] or len(root["model"]) > 256:
        raise ValueError("StopHookEnvelope.model must be a bounded non-empty string")
    if not isinstance(root["stop_hook_active"], bool):
        raise ValueError("StopHookEnvelope.stop_hook_active must be a boolean")
    if not isinstance(root["last_assistant_message"], str) or len(root["last_assistant_message"]) > 4_000_000:
        raise ValueError("StopHookEnvelope.last_assistant_message must be a bounded string")
    return StopHookEnvelope(_identifier(root["session_id"], "StopHookEnvelope.session_id"), _identifier(root["turn_id"], "StopHookEnvelope.turn_id"), root["transcript_path"], root["cwd"], "Stop", root["model"], root["stop_hook_active"], root["last_assistant_message"])


def dirty_marker_from_mapping(value: Any) -> Any:
    from agc_runtime.capture_source import DirtyMarker

    return DirtyMarker(*_marker_values(value, "DirtyMarker"))


def scan_hint_from_mapping(value: Any) -> Any:
    from agc_runtime.capture_source import ScanHint

    root = _strict(value, "ScanHint", {"schema_version", "adapter_id", "source_root_id", "hint_schema_version", "opaque_value"})
    opaque = root["opaque_value"]
    if not isinstance(opaque, str) or not _OPAQUE.fullmatch(opaque):
        raise ValueError("ScanHint.opaque_value must be an opaque ASCII token")
    return ScanHint(_schema(root["schema_version"], "ScanHint"), _identifier(root["adapter_id"], "ScanHint.adapter_id"), validate_sha256(root["source_root_id"], "ScanHint.source_root_id"), _version(root["hint_schema_version"], "ScanHint.hint_schema_version"), opaque)


def time_window_from_mapping(value: Any) -> Any:
    from agc_runtime.capture_source import TimeWindow

    root = _strict(value, "TimeWindow", {"schema_version", "start_at", "end_at"})
    start = _utc(root["start_at"], "TimeWindow.start_at")
    end = _utc(root["end_at"], "TimeWindow.end_at")
    assert isinstance(start, str) and isinstance(end, str)
    if datetime.fromisoformat(start[:-1] + "+00:00") >= datetime.fromisoformat(end[:-1] + "+00:00"):
        raise ValueError("TimeWindow must be a non-empty UTC half-open window")
    return TimeWindow(_schema(root["schema_version"], "TimeWindow"), start, end)


def _same_binding(binding: Any, adapter_id: str, source_root_id: str, name: str) -> None:
    if binding.adapter_id != adapter_id or binding.source_root_id != source_root_id:
        raise ValueError(f"{name} must match its SourceBindingKey")


def discovery_batch_from_mapping(value: Any) -> Any:
    from agc_runtime.capture_source import DiscoveryBatch

    root = _strict(value, "DiscoveryBatch", {"schema_version", "binding", "window", "revisions", "next_hint", "diagnostic_codes"})
    binding = source_binding_key_from_mapping(root["binding"])
    window = time_window_from_mapping(root["window"])
    if not isinstance(root["revisions"], list):
        raise ValueError("DiscoveryBatch.revisions must be a list")
    revisions = tuple(revision_ref_from_mapping(item) for item in root["revisions"])
    if len({(item.key.adapter_id, item.key.source_root_id, item.key.task_id, item.key.revision_id) for item in revisions}) != len(revisions):
        raise ValueError("DiscoveryBatch.revisions must not contain duplicate Capture Keys")
    for revision in revisions:
        _same_binding(binding, revision.key.adapter_id, revision.key.source_root_id, "DiscoveryBatch revision")
    hint = None if root["next_hint"] is None else scan_hint_from_mapping(root["next_hint"])
    if hint is not None:
        _same_binding(binding, hint.adapter_id, hint.source_root_id, "DiscoveryBatch.next_hint")
    diagnostics = _string_tuple(root["diagnostic_codes"], "DiscoveryBatch.diagnostic_codes", _machine_code)
    return DiscoveryBatch(_schema(root["schema_version"], "DiscoveryBatch"), binding, window, revisions, hint, diagnostics)


def source_probe_from_mapping(value: Any) -> Any:
    from agc_runtime.capture_source import SourceProbe

    root = _strict(value, "SourceProbe", {"schema_version", "revision", "source_kind", "completion_state", "diagnostic_code"})
    kind = _enum(root["source_kind"], "SourceProbe.source_kind", frozenset({"main", "subagent", "unknown"}))
    state = _enum(root["completion_state"], "SourceProbe.completion_state", frozenset({"complete", "partial", "aborted", "unreadable"}))
    diagnostic = _machine_code(root["diagnostic_code"], "SourceProbe.diagnostic_code", nullable=True)
    if state == "complete" and diagnostic is not None:
        raise ValueError("complete SourceProbe must not have a diagnostic_code")
    if state == "unreadable" and diagnostic is None:
        raise ValueError("unreadable SourceProbe requires a diagnostic_code")
    return SourceProbe(_schema(root["schema_version"], "SourceProbe"), revision_ref_from_mapping(root["revision"]), kind, state, diagnostic)


def census_run_from_mapping(value: Any) -> Any:
    from agc_runtime.capture_source import CensusRun

    root = _strict(value, "CensusRun", {"schema_version", "census_id", "binding", "window", "started_at", "frozen_at", "revision_keys", "source_quarantine_count"})
    binding = source_binding_key_from_mapping(root["binding"])
    window = time_window_from_mapping(root["window"])
    started = _utc(root["started_at"], "CensusRun.started_at")
    frozen = _utc(root["frozen_at"], "CensusRun.frozen_at")
    assert isinstance(started, str) and isinstance(frozen, str)
    if datetime.fromisoformat(frozen[:-1] + "+00:00") < datetime.fromisoformat(started[:-1] + "+00:00"):
        raise ValueError("CensusRun.frozen_at must not precede started_at")
    if not isinstance(root["revision_keys"], list):
        raise ValueError("CensusRun.revision_keys must be a list")
    keys = tuple(capture_key_from_mapping(item) for item in root["revision_keys"])
    if len({tuple(item._to_mapping_unchecked().values()) for item in keys}) != len(keys):
        raise ValueError("CensusRun.revision_keys must not contain duplicates")
    for key in keys:
        _same_binding(binding, key.adapter_id, key.source_root_id, "CensusRun revision key")
    return CensusRun(_schema(root["schema_version"], "CensusRun"), _identifier(root["census_id"], "CensusRun.census_id"), binding, window, started, frozen, keys, _integer(root["source_quarantine_count"], "CensusRun.source_quarantine_count"))


def scan_state_from_mapping(value: Any) -> Any:
    from agc_runtime.capture_source import ScanState

    root = _strict(value, "ScanState", {"schema_version", "binding", "state_version", "hint", "last_scan_at", "lookback_started_at"})
    binding = source_binding_key_from_mapping(root["binding"])
    hint = None if root["hint"] is None else scan_hint_from_mapping(root["hint"])
    if hint is not None:
        _same_binding(binding, hint.adapter_id, hint.source_root_id, "ScanState.hint")
    return ScanState(_schema(root["schema_version"], "ScanState"), binding, _integer(root["state_version"], "ScanState.state_version", minimum=1), hint, _utc(root["last_scan_at"], "ScanState.last_scan_at", nullable=True), _utc(root["lookback_started_at"], "ScanState.lookback_started_at"))


def project_identity_from_mapping(value: Any) -> Any:
    from agc_runtime.project_identity import ProjectIdentity

    root = _strict(value, "ProjectIdentity", {"schema_version", "project_id", "resolution"})
    resolution = _enum(root["resolution"], "ProjectIdentity.resolution", frozenset({"explicit_registry", "git_common_dir_registry", "generated_registry"}))
    return ProjectIdentity(_schema(root["schema_version"], "ProjectIdentity"), _opaque_project_id(root["project_id"], "ProjectIdentity.project_id"), resolution)
