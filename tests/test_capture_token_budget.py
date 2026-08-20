from __future__ import annotations

from dataclasses import replace

import pytest

from agc_runtime.capture_budget import reservation_id_for
from agc_runtime.capture_contracts import (
    BudgetSettlement,
    CaptureKey,
    TokenReservation,
    TokenUsage,
)


def _key() -> CaptureKey:
    return CaptureKey(
        "codex",
        "a" * 64,
        "task-1",
        "turn-1",
    )


def _reservation_mapping() -> dict[str, object]:
    key = _key()
    census_id = "census-" + "b" * 32
    return {
        "schema_version": 1,
        "reservation_id": reservation_id_for("backfill", census_id, key, 1),
        "pool": "backfill",
        "census_id": census_id,
        "capture_key": key.to_mapping(),
        "attempt": 1,
        "maximum_usage": {
            "input_tokens": 700,
            "output_tokens": 300,
            "total_tokens": 1000,
        },
        "reserved_at": "2026-08-20T00:00:00Z",
    }


def _settlement_mapping() -> dict[str, object]:
    reservation = _reservation_mapping()
    return {
        "schema_version": 1,
        "reservation_id": reservation["reservation_id"],
        "capture_key": reservation["capture_key"],
        "charged_usage": {
            "input_tokens": 600,
            "output_tokens": 200,
            "total_tokens": 800,
        },
        "usage_quality": "actual",
        "settled_at": "2026-08-20T00:01:00Z",
    }


def test_token_reservation_and_settlement_round_trip_strictly() -> None:
    reservation = TokenReservation.from_mapping(_reservation_mapping())
    settlement = BudgetSettlement.from_mapping(_settlement_mapping())

    assert reservation.to_mapping() == _reservation_mapping()
    assert settlement.to_mapping() == _settlement_mapping()
    assert "task-1" not in repr(reservation)
    assert "turn-1" not in repr(settlement)


def test_reservation_id_is_deterministic_and_binds_attempt_pool_and_key() -> None:
    key = _key()
    census_id = "census-" + "b" * 32
    first = reservation_id_for("backfill", census_id, key, 1)

    assert first == reservation_id_for("backfill", census_id, key, 1)
    assert first.startswith("br_") and len(first) == 67
    assert first != reservation_id_for("backfill", census_id, key, 2)
    assert first != reservation_id_for("incremental", None, key, 1)
    assert first != reservation_id_for(
        "backfill",
        census_id,
        CaptureKey("codex", "a" * 64, "task-2", "turn-1"),
        1,
    )


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("schema_version", 2),
        ("reservation_id", "br_" + "0" * 64),
        ("pool", "unknown"),
        ("census_id", None),
        ("attempt", 0),
        ("attempt", True),
        ("reserved_at", "not-utc"),
    ),
)
def test_token_reservation_rejects_invalid_or_unbound_fields(
    field: str, value: object
) -> None:
    mapping = _reservation_mapping()
    mapping[field] = value

    with pytest.raises(ValueError, match="capture_budget_contract_invalid"):
        TokenReservation.from_mapping(mapping)


def test_token_reservation_rejects_unknown_or_missing_fields() -> None:
    unknown = {**_reservation_mapping(), "private": "do-not-leak"}
    missing = _reservation_mapping()
    del missing["maximum_usage"]

    for mapping in (unknown, missing):
        with pytest.raises(ValueError, match="capture_budget_contract_invalid"):
            TokenReservation.from_mapping(mapping)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("schema_version", 2),
        ("reservation_id", "invalid"),
        ("usage_quality", "estimated"),
        ("settled_at", "not-utc"),
    ),
)
def test_budget_settlement_rejects_invalid_or_unbound_fields(
    field: str, value: object
) -> None:
    mapping = _settlement_mapping()
    mapping[field] = value

    with pytest.raises(ValueError, match="capture_budget_contract_invalid"):
        BudgetSettlement.from_mapping(mapping)


def test_direct_dataclass_replacement_cannot_bypass_validation() -> None:
    reservation = TokenReservation.from_mapping(_reservation_mapping())
    settlement = BudgetSettlement.from_mapping(_settlement_mapping())

    with pytest.raises(ValueError, match="capture_budget_contract_invalid"):
        replace(reservation, attempt=0)
    with pytest.raises(ValueError, match="capture_budget_contract_invalid"):
        replace(settlement, usage_quality="estimated")


def test_settlement_usage_is_strict_and_additive() -> None:
    mapping = _settlement_mapping()
    mapping["charged_usage"] = {
        "input_tokens": 600,
        "output_tokens": 200,
        "total_tokens": 799,
    }

    with pytest.raises(ValueError, match="capture_budget_contract_invalid"):
        BudgetSettlement.from_mapping(mapping)


def test_incremental_reservation_requires_null_census_identity() -> None:
    mapping = _reservation_mapping()
    mapping["pool"] = "incremental"
    mapping["census_id"] = None
    mapping["reservation_id"] = reservation_id_for(
        "incremental", None, _key(), 1
    )

    assert TokenReservation.from_mapping(mapping).pool == "incremental"

    mapping["census_id"] = "census-" + "b" * 32
    with pytest.raises(ValueError, match="capture_budget_contract_invalid"):
        TokenReservation.from_mapping(mapping)


def test_token_usage_object_is_preserved_by_budget_contracts() -> None:
    reservation = TokenReservation.from_mapping(_reservation_mapping())
    settlement = BudgetSettlement.from_mapping(_settlement_mapping())

    assert reservation.maximum_usage == TokenUsage(700, 300, 1000)
    assert settlement.charged_usage == TokenUsage(600, 200, 800)
