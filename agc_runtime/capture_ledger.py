"""Content-free helpers for durable Capture census accounting."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Sequence

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
    from agc_runtime.capture_source import CensusRun, SourceBindingKey, TimeWindow


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


def validate_receipt_revision_truth(
    receipt: CaptureReceipt,
    revision: RevisionRef,
    *,
    require_census_only: bool = False,
) -> CaptureReceipt:
    """Bind a Receipt to frozen Revision truth before census accounting.

    Later extractor/terminal Receipts retain their own schema invariants and
    are never projected back into a census-only shape.  Receipts that still
    claim census-only state must exactly retain the metadata-only contract.
    """

    validated_receipt = CaptureReceipt.from_mapping(receipt.to_mapping())
    validated_revision = RevisionRef.from_mapping(revision.to_mapping())
    if (
        validated_receipt.key != validated_revision.key
        or validated_receipt.settled_at != validated_revision.completed_at
        or validated_receipt.adapter_version != validated_revision.adapter_version
        or validated_receipt.source_schema_version
        != validated_revision.source_schema_version
        or validated_receipt.identity_quality != validated_revision.identity_quality
    ):
        raise ValueError("receipt_revision_truth_conflict")

    census_only = validated_receipt.status in {"discovered", "excluded"} or (
        validated_receipt.status == "quarantined"
        and validated_receipt.sanitized_error is not None
        and validated_receipt.sanitized_error.code == "revision_metadata_conflict"
    )
    if require_census_only and not census_only:
        raise ValueError("receipt_is_not_census_only")
    if not census_only:
        return validated_receipt

    empty_fields = (
        "source_fingerprint",
        "source_hash_schema_version",
        "capsule_hash",
        "capsule_schema_version",
        "next_retry_at",
        "extractor_id",
        "extractor_version",
        "extractor_schema_version",
        "taxonomy_version",
        "observation_count",
        "filtered_counts",
        "duplicate_suppression_count",
        "zero_reason",
        "coalesced_to",
    )
    if (
        any(getattr(validated_receipt, field) is not None for field in empty_fields)
        or validated_receipt.attempt_count != 0
        or validated_receipt.token_usage != TokenUsage(0, 0, 0)
        or validated_receipt.usage_quality != "reserved"
        or validated_receipt.redacted_by_forget
        or validated_receipt.forgotten_observation_count != 0
    ):
        raise ValueError("untruthful_census_receipt")
    if validated_receipt.status == "discovered":
        if (
            validated_receipt.sanitized_error is not None
            or validated_receipt.exclusion_reason is not None
        ):
            raise ValueError("untruthful_census_receipt")
    elif validated_receipt.status == "excluded":
        if (
            validated_receipt.sanitized_error is not None
            or validated_receipt.exclusion_reason != "configured_task_exclusion"
        ):
            raise ValueError("untruthful_census_receipt")
    else:
        error = validated_receipt.sanitized_error
        if (
            error is None
            or error.stage != "source"
            or error.code != "revision_metadata_conflict"
            or error.retryable
            or validated_receipt.exclusion_reason is not None
        ):
            raise ValueError("untruthful_census_receipt")
    return validated_receipt


def canonical_census_id(
    binding: "SourceBindingKey", window: "TimeWindow", started_at: str
) -> str:
    """Return the deterministic identity of a frozen Census run."""

    digest = hashlib.sha256(
        json.dumps(
            {
                "binding": binding.to_mapping(),
                "started_at": started_at,
                "window": window.to_mapping(),
            },
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
    ).hexdigest()[:32]
    return f"census-{digest}"


def validate_frozen_census_run(
    census: "CensusRun", revisions: Sequence[RevisionRef], *, run_id: str
) -> None:
    """Validate identity, window, membership, and binding for live or archived runs."""

    run_start = datetime.fromisoformat(census.started_at.replace("Z", "+00:00"))
    window_start = datetime.fromisoformat(census.window.start_at.replace("Z", "+00:00"))
    window_end = datetime.fromisoformat(census.window.end_at.replace("Z", "+00:00"))
    frozen_at = datetime.fromisoformat(census.frozen_at.replace("Z", "+00:00"))
    if (
        census.census_id != run_id
        or canonical_census_id(census.binding, census.window, census.started_at)
        != run_id
        or window_end != run_start
        or window_start != run_start - timedelta(days=7)
        or frozen_at < run_start
    ):
        raise ValueError("frozen Census run identity or window is invalid")
    ordered = tuple(
        sorted(
            revisions,
            key=lambda item: (
                item.key.adapter_id,
                item.key.source_root_id,
                item.key.task_id,
                item.key.revision_id,
            ),
        )
    )
    if tuple(item.key for item in ordered) != census.revision_keys:
        raise ValueError("frozen Census membership does not match run")
    if any(
        item.key.adapter_id != census.binding.adapter_id
        or item.key.source_root_id != census.binding.source_root_id
        for item in ordered
    ):
        raise ValueError("frozen Census member binding does not match run")


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
    exclusion_reason: str | None = None,
) -> CaptureReceipt:
    """Build the truthful pre-semantic Receipt for a discovered revision."""

    revision = RevisionRef.from_mapping(revision.to_mapping())
    error = None
    if status == "quarantined":
        error = SanitizedError("source", error_code or "revision_metadata_conflict", False)
    if status == "excluded":
        exclusion_reason = exclusion_reason or "configured_task_exclusion"
    elif exclusion_reason is not None:
        raise ValueError("exclusion_reason is valid only for excluded receipts")
    receipt = CaptureReceipt.from_mapping(
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
            "exclusion_reason": exclusion_reason,
        }
    )
    return validate_receipt_revision_truth(
        receipt, revision, require_census_only=True
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
    "canonical_census_id",
    "persist_revision",
    "quarantined_receipt",
    "receipt_for_revision",
    "same_revision_metadata",
    "source_quarantine_for",
    "validate_receipt_revision_truth",
    "validate_frozen_census_run",
]
