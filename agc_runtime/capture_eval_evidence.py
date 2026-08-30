"""AGC-owned evidence and content-free item reports for Capture evaluation."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from agc_runtime.capture_capsule import TaskCapsule
from agc_runtime.capture_contracts import CaptureReceipt, CollectedObservation


@dataclass(frozen=True)
class CaptureItemTraceReport:
    occurred_at: str
    payload: dict[str, Any] = field(repr=False)


def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _observation_value(item: CollectedObservation) -> dict[str, Any]:
    return {
        "statement": item.statement,
        "assertion": dict(item.assertion),
        "primary_category": item.primary_category,
        "kind": item.kind,
        "scopes": list(item.scopes),
        "project_scope": item.project_scope,
        "confidence": item.confidence,
        "sensitivity": item.sensitivity,
        "signal_type": item.signal_type,
    }


def capture_eval_evidence_content(
    capsule: TaskCapsule,
    receipt: CaptureReceipt,
    observations: Sequence[CollectedObservation],
) -> dict[str, Any]:
    if not isinstance(capsule, TaskCapsule) or not isinstance(receipt, CaptureReceipt):
        raise ValueError("capture_eval_evidence_invalid")
    items = tuple(observations)
    if (
        receipt.status != "complete"
        or receipt.observation_count != len(items)
        or len(items) > 8
        or any(
            not isinstance(item, CollectedObservation)
            or item.receipt_id != receipt.receipt_id
            for item in items
        )
        or not receipt.capsule_hash
        or not receipt.capsule_schema_version
        or not receipt.extractor_version
        or not receipt.taxonomy_version
        or receipt.filtered_counts is None
        or receipt.duplicate_suppression_count is None
    ):
        raise ValueError("capture_eval_evidence_invalid")
    outcome = "collected" if items else "zero"
    reason = "observations_collected" if items else receipt.zero_reason
    if not isinstance(reason, str) or not reason:
        raise ValueError("capture_eval_evidence_invalid")
    return {
        "schema_version": "agc.capture-evidence.v1",
        "capsule": capsule.to_mapping(),
        "decision": {
            "outcome": outcome,
            "reason_code": reason,
            "observations": [_observation_value(item) for item in items],
            "filtered_counts": dict(receipt.filtered_counts),
            "duplicate_suppression_count": receipt.duplicate_suppression_count,
        },
        "runtime": {
            "capsule_hash": receipt.capsule_hash,
            "capsule_schema_version": receipt.capsule_schema_version,
            "extractor_version": receipt.extractor_version,
            "taxonomy_version": receipt.taxonomy_version,
            "token_usage": receipt.token_usage.to_mapping(),
        },
    }


def capture_item_trace_report(
    *,
    capsule: TaskCapsule,
    receipt: CaptureReceipt,
    observations: Sequence[CollectedObservation],
    occurred_at: str,
) -> CaptureItemTraceReport:
    try:
        parsed = datetime.fromisoformat(occurred_at.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError) as error:
        raise ValueError("capture_eval_evidence_invalid") from error
    if not occurred_at.endswith("Z") or parsed.utcoffset() != timedelta(0):
        raise ValueError("capture_eval_evidence_invalid")
    items = tuple(observations)
    content = capture_eval_evidence_content(capsule, receipt, items)
    outcome = "collected" if items else "zero"
    reason = "observations_collected" if items else receipt.zero_reason
    payload = {
        "schema_version": "agc.capture.item-trace.v1",
        "outcome": outcome,
        "reason_code": reason,
        "observation_count": len(items),
        "filtered_counts": dict(receipt.filtered_counts or {}),
        "duplicate_suppression_count": receipt.duplicate_suppression_count,
        "token_usage": receipt.token_usage.to_mapping(),
        "extractor_version": receipt.extractor_version,
        "taxonomy_version": receipt.taxonomy_version,
        "evidence_ref": {
            "schema_version": "eval.evidence-ref.v0.1",
            "provider": "agc",
            "kind": "capture-item",
            "ref": receipt.receipt_id,
            "digest": canonical_sha256(content),
            "version": "1",
        },
    }
    return CaptureItemTraceReport(occurred_at=occurred_at, payload=payload)


__all__ = [
    "CaptureItemTraceReport",
    "canonical_sha256",
    "capture_eval_evidence_content",
    "capture_item_trace_report",
]
