"""Content-free helpers for durable Capture census accounting."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from agc_runtime.capture_contracts import (
    CAPTURE_SCHEMA_VERSION,
    CaptureReceipt,
    RevisionRef,
    SanitizedError,
    SourceQuarantine,
    TokenUsage,
    receipt_id_for,
)
from agc_runtime.capture_transaction import atomic_write_json, read_json

if TYPE_CHECKING:
    from agc_runtime.capture_source import SourceBindingKey


def _receipt_path(census_directory: Path, revision: RevisionRef) -> Path:
    return census_directory / f"{receipt_id_for(revision.key)}.json"


def same_revision_metadata(left: RevisionRef, right: RevisionRef) -> bool:
    """Compare correctness metadata while allowing an active/archive relocation."""

    return (
        left.key == right.key
        and left.rollout_anchor_id == right.rollout_anchor_id
        and left.completed_at == right.completed_at
        and left.identity_quality == right.identity_quality
        and left.adapter_version == right.adapter_version
        and left.source_schema_version == right.source_schema_version
    )


def persist_revision(census_directory: Path, revision: RevisionRef) -> str:
    """Atomically persist one revision, returning ``created`` or ``replay``."""

    validated = RevisionRef.from_mapping(revision.to_mapping())
    path = _receipt_path(census_directory, validated)
    if path.exists():
        current = RevisionRef.from_mapping(read_json(path))
        if not same_revision_metadata(current, validated):
            raise ValueError("revision_metadata_conflict")
        if current != validated:
            atomic_write_json(path, validated.to_mapping())
        return "replay"
    atomic_write_json(path, validated.to_mapping())
    return "created"


def receipt_for_revision(
    revision: RevisionRef,
    *,
    discovered_at: str,
    status: str = "discovered",
    error_code: str | None = None,
) -> CaptureReceipt:
    """Build the truthful pre-semantic Receipt for a discovered revision."""

    revision = RevisionRef.from_mapping(revision.to_mapping())
    error = None
    if status == "quarantined":
        error = SanitizedError("source", error_code or "revision_metadata_conflict", False)
    return CaptureReceipt.from_mapping(
        {
            "schema_version": CAPTURE_SCHEMA_VERSION,
            "receipt_id": receipt_id_for(revision.key),
            **revision.key.to_mapping(),
            "adapter_version": revision.adapter_version,
            "source_schema_version": revision.source_schema_version,
            "identity_quality": revision.identity_quality,
            "source_fingerprint": None,
            "source_hash_schema_version": None,
            "capsule_hash": None,
            "capsule_schema_version": None,
            "settled_at": revision.completed_at,
            "discovered_at": discovered_at,
            "updated_at": discovered_at,
            "status": status,
            "attempt_count": 0,
            "next_retry_at": None,
            "extractor_id": None,
            "extractor_version": None,
            "extractor_schema_version": None,
            "taxonomy_version": None,
            "observation_count": None,
            "filtered_counts": None,
            "duplicate_suppression_count": None,
            "token_usage": TokenUsage(0, 0, 0).to_mapping(),
            "usage_quality": "reserved",
            "redacted_by_forget": False,
            "forgotten_observation_count": 0,
            "zero_reason": None,
            "sanitized_error": error.to_mapping() if error else None,
            "coalesced_to": None,
            "exclusion_reason": None,
        }
    )


def quarantined_receipt(current: CaptureReceipt, *, updated_at: str, code: str) -> CaptureReceipt:
    return CaptureReceipt.from_mapping(
        replace(
            current,
            status="quarantined",
            updated_at=updated_at,
            next_retry_at=None,
            sanitized_error=SanitizedError("source", code, False),
        ).to_mapping()
    )


def source_quarantine_for(
    binding: "SourceBindingKey", *, created_at: str, code: str
) -> SourceQuarantine:
    return SourceQuarantine.from_mapping(
        {
            "schema_version": CAPTURE_SCHEMA_VERSION,
            "adapter_id": binding.adapter_id,
            "source_root_id": binding.source_root_id,
            "created_at": created_at,
            "code": code,
        }
    )


def binding_digest(adapter_id: str, source_root_id: str) -> str:
    value = json.dumps(
        {"adapter_id": adapter_id, "source_root_id": source_root_id},
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")
    return hashlib.sha256(value).hexdigest()


__all__ = [
    "binding_digest",
    "persist_revision",
    "quarantined_receipt",
    "receipt_for_revision",
    "same_revision_metadata",
    "source_quarantine_for",
]
