from copy import deepcopy

import pytest

from agc_runtime.capture_contracts import (
    CAPTURE_SCHEMA_VERSION,
    CaptureKey,
    RevisionRef,
    CaptureReceipt,
    CollectedObservation,
    CaptureSuppressionTombstone,
    SourceQuarantine,
    observation_fingerprint_for,
    observation_id_for,
    receipt_id_for,
    validate_capture_transition,
)


UTC = "2026-08-13T12:00:00Z"


def receipt_mapping(*, status: str = "complete") -> dict:
    complete = status == "complete"
    key = CaptureKey(
        adapter_id="synthetic_adapter",
        source_root_id="synthetic_root",
        task_id="synthetic_task",
        revision_id="synthetic_revision",
    )
    return {
        "schema_version": CAPTURE_SCHEMA_VERSION,
        "receipt_id": receipt_id_for(key),
        "adapter_id": "synthetic_adapter",
        "adapter_version": "1",
        "source_schema_version": "1",
        "source_root_id": "synthetic_root",
        "task_id": "synthetic_task",
        "revision_id": "synthetic_revision",
        "identity_quality": "session_id",
        "source_fingerprint": "b" * 64 if complete else None,
        "source_hash_schema_version": "source-v1" if complete else None,
        "capsule_hash": "c" * 64 if complete else None,
        "capsule_schema_version": "capsule-v1" if complete else None,
        "settled_at": UTC,
        "discovered_at": UTC,
        "updated_at": UTC,
        "status": status,
        "attempt_count": 0,
        "next_retry_at": None,
        "extractor_id": "synthetic_extractor" if complete else None,
        "extractor_version": "1" if complete else None,
        "extractor_schema_version": "1" if complete else None,
        "taxonomy_version": "taxonomy-v1" if complete else None,
        "observation_count": 0 if complete else None,
        "filtered_counts": {"safety": 0, "policy": 0, "over_limit": 0}
        if complete
        else None,
        "duplicate_suppression_count": 0 if complete else None,
        "token_usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
        "usage_quality": "actual",
        "redacted_by_forget": False,
        "forgotten_observation_count": 0,
        "zero_reason": "extractor_empty" if complete else None,
        "sanitized_error": None,
        "coalesced_to": None,
        "exclusion_reason": None,
    }


def observation_mapping(*, ordinal: int = 0) -> dict:
    value = {
        "schema_version": CAPTURE_SCHEMA_VERSION,
        "observation_id": "co_" + "d" * 64,
        "receipt_id": receipt_mapping()["receipt_id"],
        "source": {
            "adapter_id": "synthetic_adapter",
            "source_root_id": "synthetic_root",
            "task_id": "synthetic_task",
            "revision_id": "synthetic_revision",
            "locator": "sessions/opaque-turn-token",
        },
        "ordinal": ordinal,
        "observation_fingerprint": "e" * 64,
        "statement": "User prefers synthetic fixtures for contract tests.",
        "assertion": {
            "subject": "user",
            "mode": "direct",
            "modality": "asserted",
        },
        "primary_category": "work",
        "taxonomy_version": "taxonomy-v1",
        "kind": "preference",
        "scopes": ["testing"],
        "project_scope": None,
        "confidence": "observed",
        "sensitivity": "normal",
        "signal_type": "decision_or_constraint",
        "observed_at": UTC,
        "captured_at": UTC,
        "extractor_version": "1",
        "processing_state": "collected",
    }
    value["observation_fingerprint"] = observation_fingerprint_for(value)
    value["observation_id"] = observation_id_for(
        value["receipt_id"], value["observation_fingerprint"]
    )
    return value


def test_receipt_round_trip_requires_every_field_and_rejects_unknown_fields():
    receipt = CaptureReceipt.from_mapping(receipt_mapping())

    assert receipt.to_mapping() == receipt_mapping()
    with pytest.raises(ValueError, match="missing CaptureReceipt field: status"):
        value = receipt_mapping()
        del value["status"]
        CaptureReceipt.from_mapping(value)
    with pytest.raises(ValueError, match="unknown CaptureReceipt field: extra"):
        value = receipt_mapping()
        value["extra"] = "not allowed"
        CaptureReceipt.from_mapping(value)


def test_receipt_conditional_fields_follow_status_and_redaction_invariants():
    discovered = receipt_mapping(status="discovered")
    assert CaptureReceipt.from_mapping(discovered).status == "discovered"

    invalid = receipt_mapping(status="discovered")
    invalid["extractor_id"] = "must-not-exist-yet"
    with pytest.raises(ValueError, match="extractor fields"):
        CaptureReceipt.from_mapping(invalid)

    invalid = receipt_mapping()
    invalid["zero_reason"] = None
    with pytest.raises(ValueError, match="zero_reason"):
        CaptureReceipt.from_mapping(invalid)

    invalid = receipt_mapping()
    invalid["source_fingerprint"] = None
    with pytest.raises(ValueError, match="source"):
        CaptureReceipt.from_mapping(invalid)

    redacted = receipt_mapping()
    redacted.update(
        {
            "source_fingerprint": None,
            "source_hash_schema_version": None,
            "capsule_hash": None,
            "capsule_schema_version": None,
            "redacted_by_forget": True,
            "forgotten_observation_count": 1,
        }
    )
    assert CaptureReceipt.from_mapping(redacted).redacted_by_forget is True

    invalid = receipt_mapping()
    invalid["redacted_by_forget"] = True
    invalid["forgotten_observation_count"] = 1
    with pytest.raises(ValueError, match="redacted receipt"):
        CaptureReceipt.from_mapping(invalid)


def test_receipt_error_coalescing_and_exclusion_fields_are_status_conditioned():
    retryable = receipt_mapping(status="retryable")
    retryable["sanitized_error"] = {
        "stage": "extract",
        "code": "synthetic_failure",
        "retryable": True,
    }
    retryable["next_retry_at"] = UTC
    retryable["extractor_id"] = "synthetic_extractor"
    retryable["extractor_version"] = "1"
    retryable["extractor_schema_version"] = "1"
    retryable["taxonomy_version"] = "taxonomy-v1"
    assert CaptureReceipt.from_mapping(retryable).sanitized_error.code == "synthetic_failure"

    excluded = receipt_mapping(status="excluded")
    excluded["exclusion_reason"] = "configured_task_exclusion"
    assert CaptureReceipt.from_mapping(excluded).exclusion_reason == "configured_task_exclusion"

    invalid = receipt_mapping()
    invalid["sanitized_error"] = {"stage": "extract", "code": "x", "retryable": True}
    with pytest.raises(ValueError, match="sanitized_error"):
        CaptureReceipt.from_mapping(invalid)


@pytest.mark.parametrize(
    ("source", "target"),
    [
        ("discovered", "queued"), ("discovered", "excluded"),
        ("discovered", "coalesced"), ("discovered", "deferred_budget"),
        ("discovered", "quarantined"), ("queued", "extracting"),
        ("queued", "deferred_budget"), ("queued", "excluded"),
        ("extracting", "complete"), ("extracting", "retryable"),
        ("extracting", "failed"), ("extracting", "quarantined"),
        ("retryable", "queued"), ("retryable", "deferred_budget"),
        ("retryable", "failed"), ("retryable", "quarantined"),
        ("deferred_budget", "queued"), ("deferred_budget", "excluded"),
        ("failed", "queued"), ("quarantined", "queued"),
    ],
)
def test_capture_status_graph_accepts_every_legal_transition(source: str, target: str):
    validate_capture_transition(source, target)


@pytest.mark.parametrize(
    ("source", "target"),
    [
        ("complete", "queued"), ("queued", "complete"),
        ("excluded", "queued"), ("coalesced", "queued"),
        ("failed", "complete"), ("quarantined", "complete"),
    ],
)
def test_capture_status_graph_rejects_illegal_transitions(source: str, target: str):
    with pytest.raises(ValueError, match="illegal capture status transition"):
        validate_capture_transition(source, target)


def test_observation_is_strict_and_enforces_phase_one_safety_invariants():
    observation = CollectedObservation.from_mapping(observation_mapping())
    assert observation.to_mapping() == observation_mapping()

    too_long = observation_mapping()
    too_long["statement"] = "x" * 301
    with pytest.raises(ValueError, match="300 Unicode code points"):
        CollectedObservation.from_mapping(too_long)

    sensitive = observation_mapping()
    sensitive["sensitivity"] = "sensitive"
    with pytest.raises(ValueError, match="sensitivity"):
        CollectedObservation.from_mapping(sensitive)

    non_collected = observation_mapping()
    non_collected["processing_state"] = "promoted"
    with pytest.raises(ValueError, match="processing_state"):
        CollectedObservation.from_mapping(non_collected)

    inferred = observation_mapping()
    inferred["assertion"]["mode"] = "agent_inferred"
    with pytest.raises(ValueError, match="agent_inferred"):
        CollectedObservation.from_mapping(inferred)


@pytest.mark.parametrize("locator", ["/absolute/transcript.jsonl", "C:\\secret\\turn.jsonl", "../escape"])
def test_observation_rejects_absolute_or_escaping_source_locators(locator: str):
    value = observation_mapping()
    value["source"]["locator"] = locator

    with pytest.raises(ValueError, match="locator"):
        CollectedObservation.from_mapping(value)


def test_observation_fingerprint_is_canonical_and_excludes_ordinal_and_source_metadata():
    first = observation_mapping(ordinal=0)
    second = deepcopy(first)
    second["ordinal"] = 7
    second["source"]["locator"] = "archived/another-opaque-token"
    second["observed_at"] = "2026-08-14T12:00:00Z"
    second["captured_at"] = "2026-08-14T12:00:00Z"

    first_fingerprint = observation_fingerprint_for(first)
    assert first_fingerprint == observation_fingerprint_for(second)
    assert len(first_fingerprint) == 64
    assert observation_id_for(first["receipt_id"], first_fingerprint).startswith("co_")


def test_capture_ids_are_full_sha256_and_stable_across_mapping_order_and_exact_replay():
    key = CaptureKey(
        adapter_id="synthetic_adapter",
        source_root_id="synthetic_root",
        task_id="synthetic_task",
        revision_id="synthetic_revision",
    )
    first = receipt_id_for(key)
    reordered = CaptureKey.from_mapping(
        {
            "revision_id": "synthetic_revision",
            "task_id": "synthetic_task",
            "source_root_id": "synthetic_root",
            "adapter_id": "synthetic_adapter",
        }
    )
    assert first == receipt_id_for(reordered)
    assert first.startswith("cr_") and len(first) == 67


def test_strict_objects_reject_ids_that_do_not_match_their_canonical_inputs():
    receipt = receipt_mapping()
    receipt["receipt_id"] = "cr_" + "a" * 64
    with pytest.raises(ValueError, match="receipt_id does not match"):
        CaptureReceipt.from_mapping(receipt)

    observation = observation_mapping()
    observation["observation_id"] = "co_" + "d" * 64
    with pytest.raises(ValueError, match="observation_id does not match"):
        CollectedObservation.from_mapping(observation)


def test_control_plane_contracts_reject_content_and_absolute_paths():
    tombstone = CaptureSuppressionTombstone.from_mapping(
        {
            "schema_version": CAPTURE_SCHEMA_VERSION,
            "capture_key": CaptureKey("adapter", "root", "task", "revision").to_mapping(),
            "created_at": UTC,
            "reason": "user_forget",
        }
    )
    assert tombstone.reason == "user_forget"

    with pytest.raises(ValueError, match="absolute path"):
        SourceQuarantine.from_mapping(
            {
                "schema_version": CAPTURE_SCHEMA_VERSION,
                "adapter_id": "adapter",
                "source_root_id": "C:\\private",
                "created_at": UTC,
                "code": "unknown_identity",
            }
        )


def test_revision_ref_is_strict_metadata_with_only_an_opaque_locator():
    ref = RevisionRef.from_mapping(
        {
            "schema_version": CAPTURE_SCHEMA_VERSION,
            "capture_key": CaptureKey("adapter", "root", "task", "revision").to_mapping(),
            "rollout_anchor_id": "turn-anchor",
            "completed_at": UTC,
            "locator": "sessions/opaque-turn-token",
            "identity_quality": "session_id",
            "adapter_version": "1",
            "source_schema_version": "1",
        }
    )

    assert ref.key.task_id == "task"
    assert ref.locator == "sessions/opaque-turn-token"
