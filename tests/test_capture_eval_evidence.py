from __future__ import annotations

from dataclasses import replace

import pytest

from agc_runtime.capture_capsule import TaskCapsule
from agc_runtime.capture_contracts import (
    CaptureKey,
    CaptureReceipt,
    CollectedObservation,
    TokenUsage,
    observation_fingerprint_for,
    observation_id_for,
    receipt_id_for,
)
from agc_runtime.capture_eval_evidence import (
    canonical_sha256,
    capture_eval_evidence_content,
    capture_item_trace_report,
)

NOW = "2026-08-30T08:00:00Z"
ROOT_ID = "1" * 64


def completed_capture_fixture(
    *, sentinel: str = "The user prefers concise durable context."
) -> tuple[TaskCapsule, CaptureReceipt, tuple[CollectedObservation, ...]]:
    key = CaptureKey("synthetic", ROOT_ID, "task-one", "revision-one")
    receipt_id = receipt_id_for(key)
    capsule = TaskCapsule(
        adapter_id=key.adapter_id,
        adapter_version="1",
        source_schema_version="1",
        source_root_id=key.source_root_id,
        task_id=key.task_id,
        revision_id=key.revision_id,
        rollout_anchor_id="rollout-one",
        identity_quality="session_id",
        completed_at=NOW,
        project_scope="project:agc",
        task_title=sentinel,
        user_signals=(sentinel,),
    )
    base = {
        "schema_version": 1,
        "receipt_id": receipt_id,
        **key.to_mapping(),
        "adapter_version": "1",
        "source_schema_version": "1",
        "identity_quality": "session_id",
        "source_fingerprint": "a" * 64,
        "source_hash_schema_version": "source-v1",
        "capsule_hash": "b" * 64,
        "capsule_schema_version": "capsule-v1",
        "settled_at": NOW,
        "discovered_at": NOW,
        "updated_at": NOW,
        "status": "complete",
        "attempt_count": 1,
        "next_retry_at": None,
        "extractor_id": "codex",
        "extractor_version": "0.4.3",
        "extractor_schema_version": "1",
        "taxonomy_version": "taxonomy-v1",
        "observation_count": 1,
        "filtered_counts": {"safety": 0, "policy": 0, "over_limit": 0},
        "duplicate_suppression_count": 0,
        "token_usage": TokenUsage(100, 50, 150).to_mapping(),
        "usage_quality": "actual",
        "redacted_by_forget": False,
        "forgotten_observation_count": 0,
        "zero_reason": None,
        "sanitized_error": None,
        "coalesced_to": None,
        "exclusion_reason": None,
    }
    observation_value = {
        "schema_version": 1,
        "observation_id": "co_" + "0" * 64,
        "receipt_id": receipt_id,
        "source": {**key.to_mapping(), "locator": "opaque/one"},
        "ordinal": 0,
        "observation_fingerprint": "0" * 64,
        "statement": sentinel,
        "assertion": {"subject": "user", "mode": "direct", "modality": "asserted"},
        "primary_category": "work",
        "taxonomy_version": "taxonomy-v1",
        "kind": "preference",
        "scopes": ["global"],
        "project_scope": "project:agc",
        "confidence": "confirmed",
        "sensitivity": "normal",
        "signal_type": "explicit_user_state",
        "observed_at": NOW,
        "captured_at": NOW,
        "extractor_version": "0.4.3",
        "processing_state": "collected",
    }
    observation_value["observation_fingerprint"] = observation_fingerprint_for(
        observation_value
    )
    observation_value["observation_id"] = observation_id_for(
        receipt_id, observation_value["observation_fingerprint"]
    )
    return (
        capsule,
        CaptureReceipt.from_mapping(base),
        (CollectedObservation.from_mapping(observation_value),),
    )


def test_capture_evidence_ref_binds_capsule_decision_and_observations() -> None:
    capsule, receipt, observations = completed_capture_fixture()
    content = capture_eval_evidence_content(capsule, receipt, observations)
    report = capture_item_trace_report(
        capsule=capsule,
        receipt=receipt,
        observations=observations,
        occurred_at=NOW,
    )

    assert report.payload == {
        "schema_version": "agc.capture.item-trace.v1",
        "outcome": "collected",
        "reason_code": "observations_collected",
        "observation_count": 1,
        "filtered_counts": {"safety": 0, "policy": 0, "over_limit": 0},
        "duplicate_suppression_count": 0,
        "token_usage": {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
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


def test_zero_result_has_empty_observation_evidence() -> None:
    capsule, receipt, _ = completed_capture_fixture()
    zero = replace(receipt, observation_count=0, zero_reason="no_durable_signal")
    content = capture_eval_evidence_content(capsule, zero, ())
    report = capture_item_trace_report(
        capsule=capsule, receipt=zero, observations=(), occurred_at=NOW
    )
    assert report.payload["outcome"] == "zero"
    assert report.payload["reason_code"] == "no_durable_signal"
    assert content["decision"]["observations"] == []


@pytest.mark.parametrize(
    "mutate",
    (
        lambda receipt, observations: (replace(receipt, status="failed"), observations),
        lambda receipt, observations: (replace(receipt, observation_count=0), observations),
        lambda receipt, observations: (
            receipt,
            (replace(observations[0], receipt_id="cr_" + "f" * 64),),
        ),
        lambda receipt, observations: (replace(receipt, extractor_version=None), observations),
        lambda receipt, observations: (replace(receipt, taxonomy_version=None), observations),
        lambda receipt, observations: (replace(receipt, capsule_hash=None), observations),
        lambda receipt, observations: (
            replace(receipt, observation_count=9),
            observations * 9,
        ),
    ),
)
def test_invalid_evidence_boundaries_are_rejected(mutate) -> None:
    capsule, receipt, observations = completed_capture_fixture()
    changed_receipt, changed_observations = mutate(receipt, observations)
    with pytest.raises(ValueError, match="capture_eval_evidence_invalid"):
        capture_eval_evidence_content(capsule, changed_receipt, changed_observations)


def test_non_utc_occurrence_time_is_rejected() -> None:
    capsule, receipt, observations = completed_capture_fixture()
    with pytest.raises(ValueError, match="capture_eval_evidence_invalid"):
        capture_item_trace_report(
            capsule=capsule,
            receipt=receipt,
            observations=observations,
            occurred_at="2026-08-30T08:00:00+08:00",
        )


def test_trace_report_contains_no_capsule_or_observation_text() -> None:
    sentinel = "private-capture-evidence-must-not-enter-trace"
    capsule, receipt, observations = completed_capture_fixture(sentinel=sentinel)
    report = capture_item_trace_report(
        capsule=capsule,
        receipt=receipt,
        observations=observations,
        occurred_at=NOW,
    )
    assert sentinel not in repr(report)
    assert "task_id" not in repr(report)
    assert "revision_id" not in repr(report)
