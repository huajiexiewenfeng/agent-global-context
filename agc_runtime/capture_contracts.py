"""Strict, isolated contracts for the disabled Capture data plane."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from dataclasses import dataclass
from typing import Any, Mapping


CAPTURE_SCHEMA_VERSION = 1

CAPTURE_STATUSES = frozenset(
    {
        "discovered", "queued", "extracting", "complete", "retryable",
        "deferred_budget", "failed", "quarantined", "excluded", "coalesced",
    }
)
_TRANSITIONS = {
    "discovered": frozenset({"queued", "excluded", "coalesced", "deferred_budget", "quarantined"}),
    "queued": frozenset({"extracting", "deferred_budget", "excluded"}),
    "extracting": frozenset({"complete", "retryable", "failed", "quarantined"}),
    "retryable": frozenset({"queued", "deferred_budget", "failed", "quarantined"}),
    "deferred_budget": frozenset({"queued", "excluded"}),
    "failed": frozenset({"queued"}),
    "quarantined": frozenset({"queued"}),
    "complete": frozenset(),
    "excluded": frozenset(),
    "coalesced": frozenset(),
}


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _digest(prefix: str, value: Mapping[str, Any]) -> str:
    return prefix + hashlib.sha256(_canonical_json(value)).hexdigest()


def _mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a mapping")
    return value


@dataclass(frozen=True)
class CaptureKey:
    adapter_id: str
    source_root_id: str
    task_id: str
    revision_id: str

    @classmethod
    def from_mapping(cls, value: Any) -> "CaptureKey":
        from agc_runtime.capture_schema import capture_key_from_mapping

        return capture_key_from_mapping(value)

    def to_mapping(self) -> dict[str, str]:
        return {
            "adapter_id": self.adapter_id,
            "source_root_id": self.source_root_id,
            "task_id": self.task_id,
            "revision_id": self.revision_id,
        }


@dataclass(frozen=True)
class RevisionRef:
    key: CaptureKey
    rollout_anchor_id: str
    completed_at: str
    locator: str | None
    identity_quality: str
    adapter_version: str
    source_schema_version: str

    @classmethod
    def from_mapping(cls, value: Any) -> "RevisionRef":
        from agc_runtime.capture_schema import revision_ref_from_mapping

        return revision_ref_from_mapping(value)

    def to_mapping(self) -> dict[str, Any]:
        return {
            "schema_version": CAPTURE_SCHEMA_VERSION,
            "capture_key": self.key.to_mapping(),
            "rollout_anchor_id": self.rollout_anchor_id,
            "completed_at": self.completed_at,
            "locator": self.locator,
            "identity_quality": self.identity_quality,
            "adapter_version": self.adapter_version,
            "source_schema_version": self.source_schema_version,
        }


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int
    output_tokens: int
    total_tokens: int

    @classmethod
    def from_mapping(cls, value: Any) -> "TokenUsage":
        from agc_runtime.capture_schema import token_usage_from_mapping

        return token_usage_from_mapping(value)

    def to_mapping(self) -> dict[str, int]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
        }


@dataclass(frozen=True)
class SanitizedError:
    stage: str
    code: str
    retryable: bool

    @classmethod
    def from_mapping(cls, value: Any) -> "SanitizedError":
        from agc_runtime.capture_schema import sanitized_error_from_mapping

        return sanitized_error_from_mapping(value)

    def to_mapping(self) -> dict[str, Any]:
        return {"stage": self.stage, "code": self.code, "retryable": self.retryable}


@dataclass(frozen=True)
class CaptureReceipt:
    schema_version: int
    receipt_id: str
    adapter_id: str
    adapter_version: str
    source_schema_version: str
    source_root_id: str
    task_id: str
    revision_id: str
    identity_quality: str
    source_fingerprint: str | None
    source_hash_schema_version: str | None
    capsule_hash: str | None
    capsule_schema_version: str | None
    settled_at: str
    discovered_at: str
    updated_at: str
    status: str
    attempt_count: int
    next_retry_at: str | None
    extractor_id: str | None
    extractor_version: str | None
    extractor_schema_version: str | None
    taxonomy_version: str | None
    observation_count: int | None
    filtered_counts: dict[str, int] | None
    duplicate_suppression_count: int | None
    token_usage: TokenUsage
    usage_quality: str
    redacted_by_forget: bool
    forgotten_observation_count: int
    zero_reason: str | None
    sanitized_error: SanitizedError | None
    coalesced_to: str | None
    exclusion_reason: str | None

    @classmethod
    def from_mapping(cls, value: Any) -> "CaptureReceipt":
        from agc_runtime.capture_schema import capture_receipt_from_mapping

        return capture_receipt_from_mapping(value)

    @property
    def key(self) -> CaptureKey:
        return CaptureKey(self.adapter_id, self.source_root_id, self.task_id, self.revision_id)

    def to_mapping(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version, "receipt_id": self.receipt_id,
            "adapter_id": self.adapter_id, "adapter_version": self.adapter_version,
            "source_schema_version": self.source_schema_version, "source_root_id": self.source_root_id,
            "task_id": self.task_id, "revision_id": self.revision_id,
            "identity_quality": self.identity_quality, "source_fingerprint": self.source_fingerprint,
            "source_hash_schema_version": self.source_hash_schema_version, "capsule_hash": self.capsule_hash,
            "capsule_schema_version": self.capsule_schema_version, "settled_at": self.settled_at,
            "discovered_at": self.discovered_at, "updated_at": self.updated_at, "status": self.status,
            "attempt_count": self.attempt_count, "next_retry_at": self.next_retry_at,
            "extractor_id": self.extractor_id, "extractor_version": self.extractor_version,
            "extractor_schema_version": self.extractor_schema_version, "taxonomy_version": self.taxonomy_version,
            "observation_count": self.observation_count, "filtered_counts": self.filtered_counts,
            "duplicate_suppression_count": self.duplicate_suppression_count,
            "token_usage": self.token_usage.to_mapping(), "usage_quality": self.usage_quality,
            "redacted_by_forget": self.redacted_by_forget,
            "forgotten_observation_count": self.forgotten_observation_count,
            "zero_reason": self.zero_reason,
            "sanitized_error": self.sanitized_error.to_mapping() if self.sanitized_error else None,
            "coalesced_to": self.coalesced_to, "exclusion_reason": self.exclusion_reason,
        }


@dataclass(frozen=True)
class CollectedObservation:
    schema_version: int
    observation_id: str
    receipt_id: str
    source: dict[str, str | None]
    ordinal: int
    observation_fingerprint: str
    statement: str
    assertion: dict[str, str]
    primary_category: str
    taxonomy_version: str
    kind: str
    scopes: tuple[str, ...]
    project_scope: str | None
    confidence: str
    sensitivity: str
    signal_type: str
    observed_at: str
    captured_at: str
    extractor_version: str
    processing_state: str

    @classmethod
    def from_mapping(cls, value: Any) -> "CollectedObservation":
        from agc_runtime.capture_schema import collected_observation_from_mapping

        return collected_observation_from_mapping(value)

    def to_mapping(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version, "observation_id": self.observation_id,
            "receipt_id": self.receipt_id, "source": dict(self.source), "ordinal": self.ordinal,
            "observation_fingerprint": self.observation_fingerprint, "statement": self.statement,
            "assertion": dict(self.assertion), "primary_category": self.primary_category,
            "taxonomy_version": self.taxonomy_version, "kind": self.kind, "scopes": list(self.scopes),
            "project_scope": self.project_scope, "confidence": self.confidence,
            "sensitivity": self.sensitivity, "signal_type": self.signal_type,
            "observed_at": self.observed_at, "captured_at": self.captured_at,
            "extractor_version": self.extractor_version, "processing_state": self.processing_state,
        }


@dataclass(frozen=True)
class LedgerEntry:
    schema_version: int
    capture_key: CaptureKey
    receipt_id: str
    discovered_at: str
    processed_at: str | None
    status: str

    @classmethod
    def from_mapping(cls, value: Any) -> "LedgerEntry":
        from agc_runtime.capture_schema import ledger_entry_from_mapping

        return ledger_entry_from_mapping(value)

    def to_mapping(self) -> dict[str, Any]:
        return {"schema_version": self.schema_version, "capture_key": self.capture_key.to_mapping(), "receipt_id": self.receipt_id, "discovered_at": self.discovered_at, "processed_at": self.processed_at, "status": self.status}


@dataclass(frozen=True)
class CaptureLease:
    schema_version: int
    capture_key: CaptureKey
    owner_id: str
    fencing_token: int
    acquired_at: str
    expires_at: str

    @classmethod
    def from_mapping(cls, value: Any) -> "CaptureLease":
        from agc_runtime.capture_schema import capture_lease_from_mapping

        return capture_lease_from_mapping(value)

    def to_mapping(self) -> dict[str, Any]:
        return {"schema_version": self.schema_version, "capture_key": self.capture_key.to_mapping(), "owner_id": self.owner_id, "fencing_token": self.fencing_token, "acquired_at": self.acquired_at, "expires_at": self.expires_at}


@dataclass(frozen=True)
class SourceQuarantine:
    schema_version: int
    adapter_id: str
    source_root_id: str
    created_at: str
    code: str

    @classmethod
    def from_mapping(cls, value: Any) -> "SourceQuarantine":
        from agc_runtime.capture_schema import source_quarantine_from_mapping

        return source_quarantine_from_mapping(value)

    def to_mapping(self) -> dict[str, Any]:
        return {"schema_version": self.schema_version, "adapter_id": self.adapter_id, "source_root_id": self.source_root_id, "created_at": self.created_at, "code": self.code}


@dataclass(frozen=True)
class CaptureSuppressionTombstone:
    schema_version: int
    capture_key: CaptureKey
    created_at: str
    reason: str

    @classmethod
    def from_mapping(cls, value: Any) -> "CaptureSuppressionTombstone":
        from agc_runtime.capture_schema import capture_suppression_tombstone_from_mapping

        return capture_suppression_tombstone_from_mapping(value)

    def to_mapping(self) -> dict[str, Any]:
        return {"schema_version": self.schema_version, "capture_key": self.capture_key.to_mapping(), "created_at": self.created_at, "reason": self.reason}


def receipt_id_for(key: CaptureKey) -> str:
    return _digest("cr_", {"schema_version": CAPTURE_SCHEMA_VERSION, "capture_key": key.to_mapping()})


def observation_fingerprint_for(value: Mapping[str, Any] | CollectedObservation) -> str:
    mapping = value.to_mapping() if isinstance(value, CollectedObservation) else _mapping(value, "observation")
    assertion = _mapping(mapping.get("assertion"), "observation.assertion")
    statement = mapping.get("statement")
    scopes = mapping.get("scopes")
    if not isinstance(statement, str) or not isinstance(scopes, list):
        raise ValueError("observation fingerprint requires statement and scopes")
    payload = {
        "schema_version": CAPTURE_SCHEMA_VERSION,
        "statement": unicodedata.normalize("NFC", " ".join(statement.split())),
        "assertion": {name: assertion.get(name) for name in ("subject", "mode", "modality")},
        "primary_category": mapping.get("primary_category"), "kind": mapping.get("kind"),
        "scopes": sorted({unicodedata.normalize("NFC", item) for item in scopes}),
        "project_scope": mapping.get("project_scope"), "signal_type": mapping.get("signal_type"),
    }
    return hashlib.sha256(_canonical_json(payload)).hexdigest()


def observation_id_for(receipt_id: str, observation_fingerprint: str) -> str:
    return _digest("co_", {"schema_version": CAPTURE_SCHEMA_VERSION, "receipt_id": receipt_id, "observation_fingerprint": observation_fingerprint})


def tombstone_id_for(key: CaptureKey) -> str:
    return _digest("ct_", {"schema_version": CAPTURE_SCHEMA_VERSION, "capture_key": key.to_mapping()})


def validate_capture_transition(source: str, target: str) -> None:
    if source not in CAPTURE_STATUSES or target not in CAPTURE_STATUSES:
        raise ValueError("unknown capture status")
    if target not in _TRANSITIONS[source]:
        raise ValueError(f"illegal capture status transition: {source} -> {target}")
