from copy import deepcopy
from dataclasses import replace
import hashlib
import json
import math
import unicodedata

import pytest

from agc_runtime.capture_contracts import (
    CAPTURE_SCHEMA_VERSION,
    CaptureKey,
    CaptureLease,
    RevisionRef,
    CaptureReceipt,
    CollectedObservation,
    CaptureSuppressionTombstone,
    LedgerEntry,
    SanitizedError,
    SourceQuarantine,
    TokenUsage,
    observation_fingerprint_for,
    observation_id_for,
    receipt_id_for,
    tombstone_id_for,
    validate_capture_transition,
)


UTC = "2026-08-13T12:00:00Z"
SOURCE_ROOT = "1" * 64
VECTOR_ROOT = "0" * 64


def independent_digest(prefix: str, payload: dict) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return prefix + hashlib.sha256(canonical).hexdigest()


def receipt_mapping(*, status: str = "complete") -> dict:
    complete = status == "complete"
    key = CaptureKey(
        adapter_id="synthetic_adapter",
        source_root_id=SOURCE_ROOT,
        task_id="synthetic_task",
        revision_id="synthetic_revision",
    )
    return {
        "schema_version": CAPTURE_SCHEMA_VERSION,
        "receipt_id": receipt_id_for(key),
        "adapter_id": "synthetic_adapter",
        "adapter_version": "1",
        "source_schema_version": "1",
        "source_root_id": SOURCE_ROOT,
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
            "source_root_id": SOURCE_ROOT,
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
    with pytest.raises(ValueError, match="unknown field.*CaptureReceipt"):
        value = receipt_mapping()
        value["extra"] = "not allowed"
        CaptureReceipt.from_mapping(value)


def test_schema_version_and_enums_reject_bool_and_container_types_with_value_error():
    invalid_schema = receipt_mapping()
    invalid_schema["schema_version"] = True
    with pytest.raises(ValueError, match="schema_version"):
        CaptureReceipt.from_mapping(invalid_schema)

    for field, value in (
        ("status", []),
        ("identity_quality", {}),
        ("usage_quality", ("actual",)),
    ):
        invalid = receipt_mapping()
        invalid[field] = value
        with pytest.raises(ValueError, match=field):
            CaptureReceipt.from_mapping(invalid)


@pytest.mark.parametrize("non_finite", [math.nan, math.inf, -math.inf])
def test_public_id_and_fingerprint_helpers_reject_non_finite_values(
    non_finite: float,
):
    with pytest.raises(ValueError):
        receipt_id_for(CaptureKey(non_finite, "root", "task", "revision"))
    with pytest.raises(ValueError):
        observation_id_for("cr_" + "a" * 64, non_finite)
    with pytest.raises(ValueError):
        tombstone_id_for(CaptureKey("adapter", SOURCE_ROOT, non_finite, "revision"))

    observation = observation_mapping()
    observation["project_scope"] = non_finite
    with pytest.raises(ValueError):
        observation_fingerprint_for(observation)

    observation = observation_mapping()
    observation["scopes"] = [non_finite]
    with pytest.raises(ValueError):
        observation_fingerprint_for(observation)


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
                "zero_reason": "user_forget",
        }
    )
    assert CaptureReceipt.from_mapping(redacted).redacted_by_forget is True

    invalid = receipt_mapping()
    invalid["redacted_by_forget"] = True
    invalid["forgotten_observation_count"] = 1
    with pytest.raises(ValueError, match="redacted receipt"):
        CaptureReceipt.from_mapping(invalid)


def test_quarantined_receipt_accepts_only_consistent_pre_or_post_extraction_shapes():
    pre_extraction = receipt_mapping(status="quarantined")
    pre_extraction["sanitized_error"] = {
        "stage": "source_probe",
        "code": "unknown_identity",
        "retryable": False,
    }
    assert CaptureReceipt.from_mapping(pre_extraction).extractor_id is None

    extraction_stage = deepcopy(pre_extraction)
    extraction_stage.update(
        {
            "extractor_id": "synthetic_extractor",
            "extractor_version": "1",
            "extractor_schema_version": "1",
            "taxonomy_version": "taxonomy-v1",
            "source_fingerprint": "b" * 64,
            "source_hash_schema_version": "source-v1",
            "capsule_hash": "c" * 64,
            "capsule_schema_version": "capsule-v1",
        }
    )
    assert CaptureReceipt.from_mapping(extraction_stage).extractor_id == "synthetic_extractor"

    partial = deepcopy(extraction_stage)
    partial["taxonomy_version"] = None
    with pytest.raises(ValueError, match="extractor.*taxonomy"):
        CaptureReceipt.from_mapping(partial)


@pytest.mark.parametrize(
    "status",
    ["extracting", "complete", "retryable", "failed", "quarantined"],
)
@pytest.mark.parametrize(
    "missing_fields",
    [
        ("source_fingerprint", "source_hash_schema_version"),
        ("capsule_hash", "capsule_schema_version"),
    ],
    ids=["source-hash-pair", "capsule-hash-pair"],
)
def test_post_extraction_receipts_require_both_hash_pairs(
    status: str, missing_fields: tuple[str, str]
):
    value = receipt_mapping(status=status)
    value.update(
        {
            "source_fingerprint": "b" * 64,
            "source_hash_schema_version": "source-v1",
            "capsule_hash": "c" * 64,
            "capsule_schema_version": "capsule-v1",
            "extractor_id": "synthetic_extractor",
            "extractor_version": "1",
            "extractor_schema_version": "1",
            "taxonomy_version": "taxonomy-v1",
        }
    )
    if status in {"retryable", "failed", "quarantined"}:
        value["sanitized_error"] = {
            "stage": "extract",
            "code": "synthetic_failure",
            "retryable": status == "retryable",
        }
    if status == "retryable":
        value["next_retry_at"] = UTC
    for field in missing_fields:
        value[field] = None

    with pytest.raises(ValueError, match="source and capsule hash fields"):
        CaptureReceipt.from_mapping(value)


def test_hard_forget_fields_form_one_consistent_receipt_state():
    forgotten_but_not_redacted = receipt_mapping()
    forgotten_but_not_redacted["forgotten_observation_count"] = 1
    with pytest.raises(ValueError, match="redacted_by_forget"):
        CaptureReceipt.from_mapping(forgotten_but_not_redacted)

    redacted_without_forgotten = receipt_mapping()
    redacted_without_forgotten.update(
        {
            "redacted_by_forget": True,
            "source_fingerprint": None,
            "source_hash_schema_version": None,
            "capsule_hash": None,
            "capsule_schema_version": None,
            "forgotten_observation_count": 0,
            "zero_reason": "user_forget",
        }
    )
    with pytest.raises(ValueError, match="redacted_by_forget"):
        CaptureReceipt.from_mapping(redacted_without_forgotten)

    unredacted_user_forget = receipt_mapping()
    unredacted_user_forget["zero_reason"] = "user_forget"
    with pytest.raises(ValueError, match="user_forget"):
        CaptureReceipt.from_mapping(unredacted_user_forget)

    redacted_zero = receipt_mapping()
    redacted_zero.update(
        {
            "redacted_by_forget": True,
            "source_fingerprint": None,
            "source_hash_schema_version": None,
            "capsule_hash": None,
            "capsule_schema_version": None,
            "forgotten_observation_count": 1,
            "zero_reason": "extractor_empty",
        }
    )
    with pytest.raises(ValueError, match="user_forget"):
        CaptureReceipt.from_mapping(redacted_zero)

    redacted_zero["zero_reason"] = "user_forget"
    assert CaptureReceipt.from_mapping(redacted_zero).zero_reason == "user_forget"

    redacted_nonzero = deepcopy(redacted_zero)
    redacted_nonzero.update({"observation_count": 1, "zero_reason": None})
    assert CaptureReceipt.from_mapping(redacted_nonzero).observation_count == 1


def test_coalesced_receipt_cannot_reference_itself():
    value = receipt_mapping(status="coalesced")
    value["coalesced_to"] = value["receipt_id"]

    with pytest.raises(ValueError, match="coalesced_to.*self"):
        CaptureReceipt.from_mapping(value)


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
    retryable["source_fingerprint"] = "b" * 64
    retryable["source_hash_schema_version"] = "source-v1"
    retryable["capsule_hash"] = "c" * 64
    retryable["capsule_schema_version"] = "capsule-v1"
    assert CaptureReceipt.from_mapping(retryable).sanitized_error.code == "synthetic_failure"

    excluded = receipt_mapping(status="excluded")
    excluded["exclusion_reason"] = "configured_task_exclusion"
    assert CaptureReceipt.from_mapping(excluded).exclusion_reason == "configured_task_exclusion"

    invalid = receipt_mapping()
    invalid["sanitized_error"] = {"stage": "extract", "code": "x", "retryable": True}
    with pytest.raises(ValueError, match="sanitized_error"):
        CaptureReceipt.from_mapping(invalid)


@pytest.mark.parametrize(
    "field,value",
    [
        ("stage", "Traceback from extractor"),
        ("stage", "extract\nsecret"),
        ("code", "contains private prose"),
        ("code", "x" * 65),
        ("code", ["not", "a", "slug"]),
    ],
)
def test_sanitized_error_accepts_only_bounded_machine_code_slugs(field, value):
    payload = {"stage": "extract", "code": "synthetic_failure", "retryable": True}
    payload[field] = value

    with pytest.raises(ValueError, match=field):
        SanitizedError.from_mapping(payload)


def test_receipt_error_retryability_matches_terminal_status():
    retryable = receipt_mapping(status="retryable")
    retryable.update(
        {
            "next_retry_at": UTC,
            "extractor_id": "synthetic_extractor",
            "extractor_version": "1",
            "extractor_schema_version": "1",
            "taxonomy_version": "taxonomy-v1",
            "source_fingerprint": "b" * 64,
            "source_hash_schema_version": "source-v1",
            "capsule_hash": "c" * 64,
            "capsule_schema_version": "capsule-v1",
            "sanitized_error": {
                "stage": "extract",
                "code": "synthetic_failure",
                "retryable": False,
            },
        }
    )
    with pytest.raises(ValueError, match="retryable"):
        CaptureReceipt.from_mapping(retryable)

    failed = deepcopy(retryable)
    failed.update(
        {
            "status": "failed",
            "next_retry_at": None,
            "sanitized_error": {
                "stage": "extract",
                "code": "attempts_exhausted",
                "retryable": True,
            },
        }
    )
    with pytest.raises(ValueError, match="retryable"):
        CaptureReceipt.from_mapping(failed)


def test_receipt_control_metadata_rejects_prose_and_noncanonical_references():
    excluded = receipt_mapping(status="excluded")
    excluded["exclusion_reason"] = "User asked us to exclude this private task."
    with pytest.raises(ValueError, match="exclusion_reason"):
        CaptureReceipt.from_mapping(excluded)

    coalesced = receipt_mapping(status="coalesced")
    coalesced["coalesced_to"] = "another receipt"
    with pytest.raises(ValueError, match="coalesced_to"):
        CaptureReceipt.from_mapping(coalesced)

    coalesced["coalesced_to"] = "cr_" + "a" * 64
    assert CaptureReceipt.from_mapping(coalesced).coalesced_to.startswith("cr_")


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
    ],
)
def test_capture_status_graph_accepts_every_legal_transition(source: str, target: str):
    validate_capture_transition(source, target)


@pytest.mark.parametrize("source", ["failed", "quarantined"])
@pytest.mark.parametrize(
    "reopen_reason", ["explicit_retry", "compatible_version_upgrade"]
)
def test_parked_status_reopens_only_with_an_explicit_reason(
    source: str, reopen_reason: str
):
    validate_capture_transition(source, "queued", reopen_reason=reopen_reason)


@pytest.mark.parametrize("source", ["failed", "quarantined"])
@pytest.mark.parametrize("reopen_reason", [None, "automatic_retry", ""])
def test_parked_status_rejects_missing_or_invalid_reopen_reason(
    source: str, reopen_reason: str | None
):
    with pytest.raises(ValueError, match="reopen_reason"):
        validate_capture_transition(source, "queued", reopen_reason=reopen_reason)


def test_non_reopen_transition_rejects_pseudo_authorization():
    with pytest.raises(ValueError, match="reopen_reason"):
        validate_capture_transition(
            "discovered", "queued", reopen_reason="explicit_retry"
        )


@pytest.mark.parametrize(
    "source,target,reopen_reason",
    [([], "queued", None), ("failed", {}, None), ("failed", "queued", [])],
)
def test_transition_validation_rejects_container_enum_values_with_value_error(
    source, target, reopen_reason
):
    with pytest.raises(ValueError):
        validate_capture_transition(
            source, target, reopen_reason=reopen_reason
        )


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


def test_observation_persists_statement_and_scopes_in_nfc():
    value = observation_mapping()
    value["statement"] = "Cafe\u0301 preference"
    value["scopes"] = ["re\u0301sume\u0301"]
    value["observation_fingerprint"] = observation_fingerprint_for(value)
    value["observation_id"] = observation_id_for(
        value["receipt_id"], value["observation_fingerprint"]
    )

    observation = CollectedObservation.from_mapping(value)

    assert observation.statement == "Café preference"
    assert observation.scopes == ("résumé",)
    assert unicodedata.is_normalized("NFC", observation.to_mapping()["statement"])


def test_observation_rejects_scopes_that_duplicate_after_nfc_normalization():
    value = observation_mapping()
    value["scopes"] = ["café", "cafe\u0301"]
    with pytest.raises(ValueError, match="unique.*NFC"):
        observation_fingerprint_for(value)


def test_capture_ids_are_full_sha256_and_stable_across_mapping_order_and_exact_replay():
    key = CaptureKey(
        adapter_id="synthetic_adapter",
        source_root_id=SOURCE_ROOT,
        task_id="synthetic_task",
        revision_id="synthetic_revision",
    )
    first = receipt_id_for(key)
    reordered = CaptureKey.from_mapping(
        {
            "revision_id": "synthetic_revision",
            "task_id": "synthetic_task",
            "source_root_id": SOURCE_ROOT,
            "adapter_id": "synthetic_adapter",
        }
    )
    assert first == receipt_id_for(reordered)
    assert first.startswith("cr_") and len(first) == 67


def test_canonical_ids_and_fingerprint_match_independent_known_vectors():
    key = CaptureKey(
        "codex",
        VECTOR_ROOT,
        "123e4567-e89b-12d3-a456-426614174000",
        "123e4567-e89b-12d3-a456-426614174001",
    )
    receipt = receipt_id_for(key)
    tombstone = tombstone_id_for(key)
    fingerprint_payload = {
        "schema_version": CAPTURE_SCHEMA_VERSION,
        "statement": "Use synthetic fixtures.",
        "assertion": {
            "subject": "user",
            "mode": "direct",
            "modality": "asserted",
        },
        "primary_category": "project",
        "kind": "preference",
        "scopes": ["project:alpha", "testing"],
        "project_scope": "project-alpha",
        "signal_type": "decision_or_constraint",
    }
    fingerprint = observation_fingerprint_for(fingerprint_payload)

    assert receipt == "cr_e82a4d2719c4d620a105e790e9da9f3e245b00112911b12b1fe8916e7afb0b56"
    assert tombstone == "ct_e82a4d2719c4d620a105e790e9da9f3e245b00112911b12b1fe8916e7afb0b56"
    assert fingerprint == "5ea37c433c02454c39b50d329cc80102775e3c661e2fff9fa64a41a756f6f6ec"
    assert observation_id_for(receipt, fingerprint) == (
        "co_09304d9d2f3aa4c159f2453012ae041c022a720105e5d9c2cf6a3994c7806253"
    )
    assert receipt == independent_digest(
        "cr_",
        {
            "schema_version": 1,
            "capture_key": {
                "adapter_id": "codex",
                "source_root_id": VECTOR_ROOT,
                "task_id": "123e4567-e89b-12d3-a456-426614174000",
                "revision_id": "123e4567-e89b-12d3-a456-426614174001",
            },
        },
    )


def test_observation_fingerprint_includes_exact_semantic_fields_and_excludes_metadata():
    base = observation_mapping()
    base_fingerprint = observation_fingerprint_for(base)
    included_changes = {
        "statement": "A different atomic statement.",
        "assertion": {"subject": "user", "mode": "behavior_observed", "modality": "asserted"},
        "primary_category": "learning",
        "kind": "principle",
        "scopes": ["another-scope"],
        "project_scope": "project-alpha",
        "signal_type": "learning_change",
    }
    for field, changed in included_changes.items():
        candidate = deepcopy(base)
        candidate[field] = changed
        assert observation_fingerprint_for(candidate) != base_fingerprint

    excluded_changes = {
        "ordinal": 7,
        "observed_at": "2026-08-14T12:00:00Z",
        "captured_at": "2026-08-14T13:00:00Z",
        "receipt_id": "cr_" + "f" * 64,
        "observation_id": "co_" + "f" * 64,
        "observation_fingerprint": "f" * 64,
        "taxonomy_version": "taxonomy-v2",
        "extractor_version": "2",
        "processing_state": "ignored-by-fingerprint",
    }
    for field, changed in excluded_changes.items():
        candidate = deepcopy(base)
        candidate[field] = changed
        assert observation_fingerprint_for(candidate) == base_fingerprint
    source_changes = {
        "adapter_id": "other-adapter",
        "source_root_id": "f" * 64,
        "task_id": "another-task",
        "revision_id": "another-turn",
        "locator": "archive/another-token",
        "source_fingerprint": "f" * 64,
        "source_hash": "e" * 64,
    }
    for field, changed in source_changes.items():
        candidate = deepcopy(base)
        candidate["source"][field] = changed
        assert observation_fingerprint_for(candidate) == base_fingerprint


@pytest.mark.parametrize(
    "helper,args",
    [
        (receipt_id_for, (CaptureKey("bad adapter prose", SOURCE_ROOT, "task", "turn"),)),
        (tombstone_id_for, (CaptureKey("adapter", "not-a-hash", "task", "turn"),)),
        (observation_id_for, ("not-a-receipt", "a" * 64)),
        (observation_id_for, ("cr_" + "a" * 64, "not-a-fingerprint")),
    ],
)
def test_public_id_helpers_reject_invalid_components(helper, args):
    with pytest.raises(ValueError):
        helper(*args)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value.pop("assertion"),
        lambda value: value.__setitem__("assertion", []),
        lambda value: value["assertion"].__setitem__("mode", "hypothetical"),
        lambda value: value.__setitem__("primary_category", {}),
        lambda value: value.__setitem__("kind", "unknown-kind"),
        lambda value: value.__setitem__("signal_type", "unknown-signal"),
        lambda value: value.__setitem__("statement", "\ud800"),
    ],
)
def test_observation_fingerprint_rejects_invalid_canonical_fields(mutation):
    value = observation_mapping()
    mutation(value)
    with pytest.raises(ValueError):
        observation_fingerprint_for(value)


def test_strict_mapping_errors_do_not_echo_unknown_keys_and_reject_mixed_keys():
    unknown = receipt_mapping()
    unknown["private sentence\ntraceback"] = "synthetic"
    with pytest.raises(ValueError) as captured:
        CaptureReceipt.from_mapping(unknown)
    assert "private sentence" not in str(captured.value)
    assert "unknown field" in str(captured.value)

    mixed = receipt_mapping()
    mixed[7] = "synthetic"
    with pytest.raises(ValueError):
        CaptureReceipt.from_mapping(mixed)


def test_receipt_observation_count_accepts_eight_and_rejects_nine():
    accepted = receipt_mapping(status="complete")
    accepted.update({"observation_count": 8, "zero_reason": None})
    assert CaptureReceipt.from_mapping(accepted).observation_count == 8

    rejected = deepcopy(accepted)
    rejected["observation_count"] = 9
    with pytest.raises(ValueError, match="between 0 and 8"):
        CaptureReceipt.from_mapping(rejected)


def test_observation_statement_counts_unicode_code_points_at_300_boundary():
    accepted = observation_mapping()
    accepted["statement"] = "é" * 300
    accepted["observation_fingerprint"] = observation_fingerprint_for(accepted)
    accepted["observation_id"] = observation_id_for(
        accepted["receipt_id"], accepted["observation_fingerprint"]
    )
    assert len(CollectedObservation.from_mapping(accepted).statement) == 300

    rejected = deepcopy(accepted)
    rejected["statement"] += "é"
    with pytest.raises(ValueError):
        observation_fingerprint_for(rejected)


@pytest.mark.parametrize(
    "timestamp",
    ["not-a-time", "2026-08-13T12:00:00", "2026-08-13T20:00:00+08:00"],
)
def test_capture_timestamps_require_valid_zulu_utc(timestamp: str):
    value = receipt_mapping()
    value["settled_at"] = timestamp
    with pytest.raises(ValueError, match="UTC|timestamp"):
        CaptureReceipt.from_mapping(value)


@pytest.mark.parametrize(
    "locator",
    [
        "file:///private/session.jsonl",
        "https://example.invalid/session",
        "\\\\server\\share\\session.jsonl",
        "sessions\\opaque-token",
        "sessions/../private",
        "sessions//private",
        "sessions/private\ntraceback",
    ],
)
def test_revision_locator_rejects_uri_absolute_escaping_and_control_forms(locator: str):
    value = {
        "schema_version": CAPTURE_SCHEMA_VERSION,
        "capture_key": CaptureKey("adapter", SOURCE_ROOT, "task", "revision").to_mapping(),
        "rollout_anchor_id": "turn-anchor",
        "completed_at": UTC,
        "locator": locator,
        "identity_quality": "session_id",
        "adapter_version": "1.0+legacy",
        "source_schema_version": "1",
    }
    with pytest.raises(ValueError, match="locator"):
        RevisionRef.from_mapping(value)


def test_strict_objects_reject_ids_that_do_not_match_their_canonical_inputs():
    receipt = receipt_mapping()
    receipt["receipt_id"] = "cr_" + "a" * 64
    with pytest.raises(ValueError, match="receipt_id does not match"):
        CaptureReceipt.from_mapping(receipt)

    observation = observation_mapping()
    observation["observation_id"] = "co_" + "d" * 64
    with pytest.raises(ValueError, match="observation_id does not match"):
        CollectedObservation.from_mapping(observation)

    cross_key = observation_mapping()
    cross_key["source"]["task_id"] = "another-task"
    cross_key["observation_fingerprint"] = observation_fingerprint_for(cross_key)
    cross_key["observation_id"] = observation_id_for(
        cross_key["receipt_id"], cross_key["observation_fingerprint"]
    )
    with pytest.raises(ValueError, match="receipt_id does not match"):
        CollectedObservation.from_mapping(cross_key)


def test_ledger_receipt_id_is_bound_to_its_capture_key():
    key = CaptureKey("adapter", SOURCE_ROOT, "task", "revision")
    valid = {
        "schema_version": CAPTURE_SCHEMA_VERSION,
        "capture_key": key.to_mapping(),
        "receipt_id": receipt_id_for(key),
        "discovered_at": UTC,
        "processed_at": None,
        "status": "discovered",
    }
    assert LedgerEntry.from_mapping(valid).to_mapping() == valid

    invalid = deepcopy(valid)
    invalid["capture_key"]["task_id"] = "another-task"
    with pytest.raises(ValueError, match="receipt_id does not match"):
        LedgerEntry.from_mapping(invalid)


def test_control_plane_contracts_reject_content_and_absolute_paths():
    key = CaptureKey("adapter", SOURCE_ROOT, "task", "revision")
    tombstone = CaptureSuppressionTombstone.from_mapping(
        {
            "schema_version": CAPTURE_SCHEMA_VERSION,
            "tombstone_id": tombstone_id_for(key),
            "capture_key": key.to_mapping(),
            "created_at": UTC,
            "reason": "user_forget",
        }
    )
    assert tombstone.reason == "user_forget"
    assert tombstone.tombstone_id == tombstone_id_for(key)
    assert tombstone.to_mapping()["tombstone_id"].startswith("ct_")

    invalid_tombstone = tombstone.to_mapping()
    invalid_tombstone["tombstone_id"] = "ct_" + "a" * 64
    with pytest.raises(ValueError, match="tombstone_id does not match"):
        CaptureSuppressionTombstone.from_mapping(invalid_tombstone)

    with pytest.raises(ValueError, match="source_root_id"):
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
            "capture_key": CaptureKey("adapter", SOURCE_ROOT, "task", "revision").to_mapping(),
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


def test_every_public_capture_dataclass_revalidates_before_serialization():
    key = CaptureKey.from_mapping(
        {
            "adapter_id": "adapter",
            "source_root_id": SOURCE_ROOT,
            "task_id": "task-1",
            "revision_id": "turn-1",
        }
    )
    revision = RevisionRef.from_mapping(
        {
            "schema_version": CAPTURE_SCHEMA_VERSION,
            "capture_key": key.to_mapping(),
            "rollout_anchor_id": "anchor-1",
            "completed_at": UTC,
            "locator": "sessions/opaque-token",
            "identity_quality": "session_id",
            "adapter_version": "1.0",
            "source_schema_version": "1",
        }
    )
    usage = TokenUsage.from_mapping(
        {"input_tokens": 1, "output_tokens": 2, "total_tokens": 3}
    )
    error = SanitizedError.from_mapping(
        {"stage": "extract", "code": "synthetic_failure", "retryable": True}
    )
    receipt = CaptureReceipt.from_mapping(receipt_mapping())
    observation = CollectedObservation.from_mapping(observation_mapping())
    ledger = LedgerEntry.from_mapping(
        {
            "schema_version": CAPTURE_SCHEMA_VERSION,
            "capture_key": key.to_mapping(),
            "receipt_id": receipt_id_for(key),
            "discovered_at": UTC,
            "processed_at": None,
            "status": "discovered",
        }
    )
    lease = CaptureLease.from_mapping(
        {
            "schema_version": CAPTURE_SCHEMA_VERSION,
            "capture_key": key.to_mapping(),
            "owner_id": "worker-1",
            "fencing_token": 1,
            "acquired_at": UTC,
            "expires_at": "2026-08-13T12:01:00Z",
        }
    )
    quarantine = SourceQuarantine.from_mapping(
        {
            "schema_version": CAPTURE_SCHEMA_VERSION,
            "adapter_id": "adapter",
            "source_root_id": SOURCE_ROOT,
            "created_at": UTC,
            "code": "unknown_identity",
        }
    )
    tombstone = CaptureSuppressionTombstone.from_mapping(
        {
            "schema_version": CAPTURE_SCHEMA_VERSION,
            "tombstone_id": tombstone_id_for(key),
            "capture_key": key.to_mapping(),
            "created_at": UTC,
            "reason": "user_forget",
        }
    )
    invalid_objects = (
        replace(key, source_root_id="C:\\private"),
        replace(revision, completed_at="not-utc"),
        replace(usage, total_tokens=4),
        replace(error, code="private prose"),
        replace(receipt, receipt_id="cr_" + "a" * 64),
        replace(observation, sensitivity="secret"),
        replace(ledger, receipt_id="cr_" + "a" * 64),
        replace(lease, fencing_token=0),
        replace(quarantine, code="private prose"),
        replace(tombstone, tombstone_id="ct_" + "a" * 64),
    )

    for invalid in invalid_objects:
        with pytest.raises(
            ValueError, match="^Capture contract cannot be serialized$"
        ):
            invalid.to_mapping()


def test_nested_and_container_serialization_failures_use_the_public_value_error_gate():
    key = CaptureKey.from_mapping(
        {
            "adapter_id": "adapter",
            "source_root_id": SOURCE_ROOT,
            "task_id": "task-1",
            "revision_id": "turn-1",
        }
    )
    revision = RevisionRef.from_mapping(
        {
            "schema_version": CAPTURE_SCHEMA_VERSION,
            "capture_key": key.to_mapping(),
            "rollout_anchor_id": "anchor-1",
            "completed_at": UTC,
            "locator": "sessions/opaque-token",
            "identity_quality": "session_id",
            "adapter_version": "1.0",
            "source_schema_version": "1",
        }
    )
    receipt = CaptureReceipt.from_mapping(receipt_mapping())
    observation = CollectedObservation.from_mapping(observation_mapping())
    ledger = LedgerEntry.from_mapping(
        {
            "schema_version": CAPTURE_SCHEMA_VERSION,
            "capture_key": key.to_mapping(),
            "receipt_id": receipt_id_for(key),
            "discovered_at": UTC,
            "processed_at": None,
            "status": "discovered",
        }
    )
    lease = CaptureLease.from_mapping(
        {
            "schema_version": CAPTURE_SCHEMA_VERSION,
            "capture_key": key.to_mapping(),
            "owner_id": "worker-1",
            "fencing_token": 1,
            "acquired_at": UTC,
            "expires_at": "2026-08-13T12:01:00Z",
        }
    )
    tombstone = CaptureSuppressionTombstone.from_mapping(
        {
            "schema_version": CAPTURE_SCHEMA_VERSION,
            "tombstone_id": tombstone_id_for(key),
            "capture_key": key.to_mapping(),
            "created_at": UTC,
            "reason": "user_forget",
        }
    )

    invalid_objects = (
        replace(revision, key=object()),
        replace(receipt, token_usage=object()),
        replace(observation, source=object()),
        replace(ledger, capture_key=object()),
        replace(lease, capture_key=object()),
        replace(tombstone, capture_key=object()),
    )
    for invalid in invalid_objects:
        with pytest.raises(
            ValueError, match="^Capture contract cannot be serialized$"
        ):
            invalid.to_mapping()


def test_public_serialization_gate_normalizes_unicode_failures_without_input_text():
    class UnicodeFailingMapping:
        def keys(self):
            raise UnicodeError("private-user-text")

    observation = CollectedObservation.from_mapping(observation_mapping())
    invalid = replace(observation, source=UnicodeFailingMapping())

    with pytest.raises(
        ValueError, match="^Capture contract cannot be serialized$"
    ) as caught:
        invalid.to_mapping()
    assert "private-user-text" not in str(caught.value)


def test_directly_constructed_observation_cannot_serialize_secret_or_absolute_locator():
    valid = CollectedObservation.from_mapping(observation_mapping())
    secret = CollectedObservation(**{**valid.__dict__, "sensitivity": "secret"})
    absolute = CollectedObservation(
        **{
            **valid.__dict__,
            "source": {**valid.source, "locator": "C:\\private\\turn.jsonl"},
        }
    )

    with pytest.raises(ValueError, match="^Capture contract cannot be serialized$"):
        secret.to_mapping()
    with pytest.raises(ValueError, match="^Capture contract cannot be serialized$"):
        absolute.to_mapping()
