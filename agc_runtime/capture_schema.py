"""Strict mapping parsers for Capture's independent on-disk contracts."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from agc_runtime.capture_contracts import (
    CAPTURE_SCHEMA_VERSION, CAPTURE_STATUSES, CaptureKey, CaptureLease,
    CaptureReceipt, CaptureSuppressionTombstone, CollectedObservation, LedgerEntry,
    RevisionRef, SanitizedError, SourceQuarantine, TokenUsage,
    observation_fingerprint_for, observation_id_for, receipt_id_for,
)


_HASH = re.compile(r"^[0-9a-f]{64}$")
_IDENTITY_QUALITIES = frozenset({"session_id", "legacy_rollout_id", "unknown"})
_USAGE_QUALITIES = frozenset({"actual", "reserved"})
_ZERO_REASONS = frozenset({"no_durable_signal", "extractor_empty", "all_filtered_safety", "all_filtered_policy", "all_duplicates_within_revision", "user_forget"})
_CATEGORIES = frozenset({"personal_growth", "research", "learning", "project", "work"})
_KINDS = frozenset({"identity", "principle", "preference", "interest", "capability", "goal", "pattern", "context"})
_CONFIDENCE = frozenset({"tentative", "observed", "confirmed", "disputed"})
_SIGNAL_TYPES = frozenset({"explicit_user_state", "decision_or_constraint", "verified_outcome", "reusable_method", "learning_change", "research_change", "capability_evidence", "open_commitment"})


def _strict(value: Any, name: str, fields: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a mapping")
    unknown = set(value) - fields
    missing = fields - set(value)
    if unknown:
        raise ValueError(f"unknown {name} field: {sorted(unknown)[0]}")
    if missing:
        raise ValueError(f"missing {name} field: {sorted(missing)[0]}")
    return value


def _schema(value: Any, name: str) -> int:
    if value != CAPTURE_SCHEMA_VERSION:
        raise ValueError(f"{name}.schema_version must be {CAPTURE_SCHEMA_VERSION}")
    return value


def _opaque(value: Any, name: str, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    if value.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:[\\/]", value) or ".." in value.replace("\\", "/").split("/"):
        raise ValueError(f"{name} must not contain an absolute path or escaping locator")
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
    if value not in choices:
        raise ValueError(f"{name} must be one of {sorted(choices)}")
    return value


def _hash(value: Any, name: str, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or not _HASH.fullmatch(value):
        raise ValueError(f"{name} must be a lowercase SHA-256 hash")
    return value


def capture_key_from_mapping(value: Any) -> CaptureKey:
    root = _strict(value, "CaptureKey", {"adapter_id", "source_root_id", "task_id", "revision_id"})
    return CaptureKey(*(_opaque(root[name], f"CaptureKey.{name}") for name in ("adapter_id", "source_root_id", "task_id", "revision_id")))


def revision_ref_from_mapping(value: Any) -> RevisionRef:
    root = _strict(value, "RevisionRef", {"schema_version", "capture_key", "rollout_anchor_id", "completed_at", "locator", "identity_quality", "adapter_version", "source_schema_version"})
    _schema(root["schema_version"], "RevisionRef")
    return RevisionRef(
        capture_key_from_mapping(root["capture_key"]),
        _opaque(root["rollout_anchor_id"], "RevisionRef.rollout_anchor_id"),
        _utc(root["completed_at"], "RevisionRef.completed_at"),
        _opaque(root["locator"], "RevisionRef.locator", nullable=True),
        _enum(root["identity_quality"], "RevisionRef.identity_quality", _IDENTITY_QUALITIES),
        _opaque(root["adapter_version"], "RevisionRef.adapter_version"),
        _opaque(root["source_schema_version"], "RevisionRef.source_schema_version"),
    )


def token_usage_from_mapping(value: Any) -> TokenUsage:
    root = _strict(value, "TokenUsage", {"input_tokens", "output_tokens", "total_tokens"})
    input_tokens = _integer(root["input_tokens"], "TokenUsage.input_tokens")
    output_tokens = _integer(root["output_tokens"], "TokenUsage.output_tokens")
    total_tokens = _integer(root["total_tokens"], "TokenUsage.total_tokens")
    if total_tokens != input_tokens + output_tokens:
        raise ValueError("TokenUsage.total_tokens must equal input_tokens + output_tokens")
    return TokenUsage(input_tokens, output_tokens, total_tokens)


def sanitized_error_from_mapping(value: Any) -> SanitizedError:
    root = _strict(value, "SanitizedError", {"stage", "code", "retryable"})
    if not isinstance(root["retryable"], bool):
        raise ValueError("SanitizedError.retryable must be a boolean")
    return SanitizedError(_opaque(root["stage"], "SanitizedError.stage"), _opaque(root["code"], "SanitizedError.code"), root["retryable"])


def _optional_pair(root: dict[str, Any], left: str, right: str, name: str) -> tuple[str | None, str | None]:
    first = _hash(root[left], left, nullable=True)
    second = _opaque(root[right], right, nullable=True)
    if (first is None) != (second is None):
        raise ValueError(f"{name} fields must both be null or both be present")
    return first, second


def capture_receipt_from_mapping(value: Any) -> CaptureReceipt:
    fields = {"schema_version", "receipt_id", "adapter_id", "adapter_version", "source_schema_version", "source_root_id", "task_id", "revision_id", "identity_quality", "source_fingerprint", "source_hash_schema_version", "capsule_hash", "capsule_schema_version", "settled_at", "discovered_at", "updated_at", "status", "attempt_count", "next_retry_at", "extractor_id", "extractor_version", "extractor_schema_version", "taxonomy_version", "observation_count", "filtered_counts", "duplicate_suppression_count", "token_usage", "usage_quality", "redacted_by_forget", "forgotten_observation_count", "zero_reason", "sanitized_error", "coalesced_to", "exclusion_reason"}
    root = _strict(value, "CaptureReceipt", fields)
    schema_version = _schema(root["schema_version"], "CaptureReceipt")
    receipt_id = _opaque(root["receipt_id"], "CaptureReceipt.receipt_id")
    if not receipt_id.startswith("cr_") or not _HASH.fullmatch(receipt_id[3:]):
        raise ValueError("CaptureReceipt.receipt_id must be a cr_ SHA-256 id")
    key = CaptureKey(
        _opaque(root["adapter_id"], "CaptureReceipt.adapter_id"),
        _opaque(root["source_root_id"], "CaptureReceipt.source_root_id"),
        _opaque(root["task_id"], "CaptureReceipt.task_id"),
        _opaque(root["revision_id"], "CaptureReceipt.revision_id"),
    )
    if receipt_id != receipt_id_for(key):
        raise ValueError("CaptureReceipt.receipt_id does not match its CaptureKey")
    status = _enum(root["status"], "CaptureReceipt.status", CAPTURE_STATUSES)
    source_fingerprint, source_hash_schema_version = _optional_pair(root, "source_fingerprint", "source_hash_schema_version", "source")
    capsule_hash, capsule_schema_version = _optional_pair(root, "capsule_hash", "capsule_schema_version", "capsule")
    extractor_values = tuple(_opaque(root[name], f"CaptureReceipt.{name}", nullable=True) for name in ("extractor_id", "extractor_version", "extractor_schema_version"))
    if any(item is None for item in extractor_values) and any(item is not None for item in extractor_values):
        raise ValueError("extractor fields must all be null or all be present")
    post_extracting = {"extracting", "complete", "retryable", "failed"}
    if status in post_extracting and any(item is None for item in extractor_values):
        raise ValueError("extractor fields must be present after extracting")
    if status not in post_extracting and any(item is not None for item in extractor_values):
        raise ValueError("extractor fields must be null before extracting")
    taxonomy_version = _opaque(root["taxonomy_version"], "CaptureReceipt.taxonomy_version", nullable=True)
    if (status in post_extracting) != (taxonomy_version is not None):
        raise ValueError("taxonomy_version must be present after extracting and null before extracting")
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
    if redacted and (source_fingerprint is not None or capsule_hash is not None):
        raise ValueError("redacted receipt must clear source and capsule hashes")
    if status == "complete" and not redacted and (source_fingerprint is None or capsule_hash is None):
        raise ValueError("complete receipt requires source and capsule hashes unless redacted")
    zero_reason = root["zero_reason"]
    if status == "complete" and observation_count == 0:
        zero_reason = _enum(zero_reason, "CaptureReceipt.zero_reason", _ZERO_REASONS)
    elif zero_reason is not None:
        raise ValueError("zero_reason is required only for complete receipts with zero observations")
    sanitized = root["sanitized_error"]
    if status in {"retryable", "failed", "quarantined"}:
        sanitized = sanitized_error_from_mapping(sanitized)
    elif sanitized is not None:
        raise ValueError("sanitized_error is allowed only for retryable, failed, or quarantined receipts")
    coalesced_to = _opaque(root["coalesced_to"], "CaptureReceipt.coalesced_to", nullable=True)
    exclusion_reason = _opaque(root["exclusion_reason"], "CaptureReceipt.exclusion_reason", nullable=True)
    if (status == "coalesced") != (coalesced_to is not None):
        raise ValueError("coalesced_to is required only for coalesced receipts")
    if (status == "excluded") != (exclusion_reason is not None):
        raise ValueError("exclusion_reason is required only for excluded receipts")
    next_retry_at = _utc(root["next_retry_at"], "CaptureReceipt.next_retry_at", nullable=True)
    if (status == "retryable") != (next_retry_at is not None):
        raise ValueError("next_retry_at is required only for retryable receipts")
    return CaptureReceipt(schema_version, receipt_id, *(_opaque(root[name], f"CaptureReceipt.{name}") for name in ("adapter_id", "adapter_version", "source_schema_version", "source_root_id", "task_id", "revision_id")), _enum(root["identity_quality"], "CaptureReceipt.identity_quality", _IDENTITY_QUALITIES), source_fingerprint, source_hash_schema_version, capsule_hash, capsule_schema_version, *(_utc(root[name], f"CaptureReceipt.{name}") for name in ("settled_at", "discovered_at", "updated_at")), status, _integer(root["attempt_count"], "CaptureReceipt.attempt_count"), next_retry_at, *extractor_values, taxonomy_version, observation_count, filtered_counts, duplicate_suppression_count, token_usage_from_mapping(root["token_usage"]), _enum(root["usage_quality"], "CaptureReceipt.usage_quality", _USAGE_QUALITIES), redacted, forgotten, zero_reason, sanitized, coalesced_to, exclusion_reason)


def collected_observation_from_mapping(value: Any) -> CollectedObservation:
    fields = {"schema_version", "observation_id", "receipt_id", "source", "ordinal", "observation_fingerprint", "statement", "assertion", "primary_category", "taxonomy_version", "kind", "scopes", "project_scope", "confidence", "sensitivity", "signal_type", "observed_at", "captured_at", "extractor_version", "processing_state"}
    root = _strict(value, "CollectedObservation", fields)
    source = _strict(root["source"], "CollectedObservation.source", {"adapter_id", "source_root_id", "task_id", "revision_id", "locator"})
    source_value = {name: _opaque(source[name], f"CollectedObservation.source.{name}", nullable=name == "locator") for name in source}
    assertion = _strict(root["assertion"], "CollectedObservation.assertion", {"subject", "mode", "modality"})
    assertion_value = {name: _opaque(assertion[name], f"CollectedObservation.assertion.{name}") for name in assertion}
    if assertion_value["mode"] not in {"direct", "behavior_observed", "agent_inferred"} or assertion_value["modality"] != "asserted":
        raise ValueError("CollectedObservation.assertion has an unsupported mode or modality")
    confidence = _enum(root["confidence"], "CollectedObservation.confidence", _CONFIDENCE)
    if assertion_value["mode"] == "agent_inferred" and confidence != "tentative":
        raise ValueError("agent_inferred observations must use tentative confidence")
    statement = root["statement"]
    if not isinstance(statement, str) or not statement.strip():
        raise ValueError("CollectedObservation.statement must be a non-empty string")
    if len(statement) > 300:
        raise ValueError("CollectedObservation.statement must be at most 300 Unicode code points")
    scopes = root["scopes"]
    if not isinstance(scopes, list) or not scopes or any(not isinstance(item, str) or not item for item in scopes) or len(set(scopes)) != len(scopes):
        raise ValueError("CollectedObservation.scopes must be a non-empty unique list of strings")
    observation_id = _opaque(root["observation_id"], "CollectedObservation.observation_id")
    receipt_id = _opaque(root["receipt_id"], "CollectedObservation.receipt_id")
    fingerprint = _hash(root["observation_fingerprint"], "CollectedObservation.observation_fingerprint")
    if not observation_id.startswith("co_") or not _HASH.fullmatch(observation_id[3:]) or not receipt_id.startswith("cr_") or not _HASH.fullmatch(receipt_id[3:]):
        raise ValueError("CollectedObservation IDs must be canonical capture IDs")
    if fingerprint != observation_fingerprint_for(root):
        raise ValueError("CollectedObservation.observation_fingerprint does not match its canonical fields")
    if observation_id != observation_id_for(receipt_id, fingerprint):
        raise ValueError("CollectedObservation.observation_id does not match its receipt and fingerprint")
    return CollectedObservation(_schema(root["schema_version"], "CollectedObservation"), observation_id, receipt_id, source_value, _integer(root["ordinal"], "CollectedObservation.ordinal"), fingerprint, statement, assertion_value, _enum(root["primary_category"], "CollectedObservation.primary_category", _CATEGORIES), _opaque(root["taxonomy_version"], "CollectedObservation.taxonomy_version"), _enum(root["kind"], "CollectedObservation.kind", _KINDS), tuple(scopes), _opaque(root["project_scope"], "CollectedObservation.project_scope", nullable=True), confidence, _enum(root["sensitivity"], "CollectedObservation.sensitivity", frozenset({"normal", "personal"})), _enum(root["signal_type"], "CollectedObservation.signal_type", _SIGNAL_TYPES), _utc(root["observed_at"], "CollectedObservation.observed_at"), _utc(root["captured_at"], "CollectedObservation.captured_at"), _opaque(root["extractor_version"], "CollectedObservation.extractor_version"), _enum(root["processing_state"], "CollectedObservation.processing_state", frozenset({"collected"})))


def ledger_entry_from_mapping(value: Any) -> LedgerEntry:
    root = _strict(value, "LedgerEntry", {"schema_version", "capture_key", "receipt_id", "discovered_at", "processed_at", "status"})
    return LedgerEntry(_schema(root["schema_version"], "LedgerEntry"), capture_key_from_mapping(root["capture_key"]), _opaque(root["receipt_id"], "LedgerEntry.receipt_id"), _utc(root["discovered_at"], "LedgerEntry.discovered_at"), _utc(root["processed_at"], "LedgerEntry.processed_at", nullable=True), _enum(root["status"], "LedgerEntry.status", CAPTURE_STATUSES))


def capture_lease_from_mapping(value: Any) -> CaptureLease:
    root = _strict(value, "CaptureLease", {"schema_version", "capture_key", "owner_id", "fencing_token", "acquired_at", "expires_at"})
    return CaptureLease(_schema(root["schema_version"], "CaptureLease"), capture_key_from_mapping(root["capture_key"]), _opaque(root["owner_id"], "CaptureLease.owner_id"), _integer(root["fencing_token"], "CaptureLease.fencing_token", minimum=1), _utc(root["acquired_at"], "CaptureLease.acquired_at"), _utc(root["expires_at"], "CaptureLease.expires_at"))


def source_quarantine_from_mapping(value: Any) -> SourceQuarantine:
    root = _strict(value, "SourceQuarantine", {"schema_version", "adapter_id", "source_root_id", "created_at", "code"})
    return SourceQuarantine(_schema(root["schema_version"], "SourceQuarantine"), _opaque(root["adapter_id"], "SourceQuarantine.adapter_id"), _opaque(root["source_root_id"], "SourceQuarantine.source_root_id"), _utc(root["created_at"], "SourceQuarantine.created_at"), _opaque(root["code"], "SourceQuarantine.code"))


def capture_suppression_tombstone_from_mapping(value: Any) -> CaptureSuppressionTombstone:
    root = _strict(value, "CaptureSuppressionTombstone", {"schema_version", "capture_key", "created_at", "reason"})
    if root["reason"] != "user_forget":
        raise ValueError("CaptureSuppressionTombstone.reason must be user_forget")
    return CaptureSuppressionTombstone(_schema(root["schema_version"], "CaptureSuppressionTombstone"), capture_key_from_mapping(root["capture_key"]), _utc(root["created_at"], "CaptureSuppressionTombstone.created_at"), root["reason"])
