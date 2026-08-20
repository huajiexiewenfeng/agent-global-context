from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest

from agc_runtime.capture_budget import (
    BudgetUnavailable,
    CaptureTokenBudget,
    reservation_id_for,
)
from agc_runtime.capture_contracts import (
    BudgetSettlement,
    CaptureKey,
    TokenReservation,
    TokenUsage,
    RevisionRef,
)
from agc_runtime.capture_store import CaptureStore
from agc_runtime.paths import MemoryPaths


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


def _frozen_budget(
    tmp_path: Path,
    *,
    ceiling: int | None = 100_000,
) -> tuple[CaptureTokenBudget, CaptureKey, str]:
    from agc_runtime.capture_source import SourceBindingKey, TimeWindow

    paths = MemoryPaths.from_root(tmp_path / "memory")
    store = CaptureStore(paths, clock=lambda: "2026-08-20T00:00:00Z")
    key = _key()
    revision = RevisionRef.from_mapping(
        {
            "schema_version": 1,
            "capture_key": key.to_mapping(),
            "rollout_anchor_id": "rollout-1",
            "completed_at": "2026-08-19T00:00:00Z",
            "locator": "sessions/active.jsonl",
            "identity_quality": "session_id",
            "adapter_version": "1",
            "source_schema_version": "1",
        }
    )
    end = datetime(2026, 8, 20, tzinfo=timezone.utc)
    start = end - timedelta(days=7)
    census = store.freeze_census(
        binding=SourceBindingKey(
            1,
            key.adapter_id,
            key.source_root_id,
        ),
        window=TimeWindow(
            1,
            start.isoformat().replace("+00:00", "Z"),
            end.isoformat().replace("+00:00", "Z"),
        ),
        started_at=end.isoformat().replace("+00:00", "Z"),
        revisions=(revision,),
    )
    return (
        CaptureTokenBudget(
            paths,
            pool="backfill",
            census_id=census.census_id,
            ceiling=ceiling,
            clock=lambda: "2026-08-20T00:01:00Z",
        ),
        key,
        census.census_id,
    )


def test_ac_15_backfill_never_exceeds_actual_or_reserved_ceiling(
    tmp_path: Path,
) -> None:
    budget, key, _ = _frozen_budget(tmp_path)

    reservation = budget.reserve(key, 1, TokenUsage(70_000, 30_000, 100_000))

    assert reservation.maximum_usage.total_tokens == 100_000
    snapshot = budget.snapshot()
    assert snapshot.charged_tokens == 100_000
    assert snapshot.remaining_tokens == 0
    with pytest.raises(BudgetUnavailable, match="capture_budget_unavailable"):
        budget.reserve(key, 2, TokenUsage(1, 0, 1))


def test_concurrent_exact_boundary_allows_only_one_winner(tmp_path: Path) -> None:
    budget, key, _ = _frozen_budget(tmp_path, ceiling=1)
    barrier = Barrier(2)

    def reserve(attempt: int) -> str:
        barrier.wait()
        try:
            return budget.reserve(key, attempt, TokenUsage(1, 0, 1)).reservation_id
        except (BudgetUnavailable, RuntimeError):
            return "unavailable"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(executor.map(reserve, (1, 2)))

    assert sum(item.startswith("br_") for item in results) == 1
    assert results.count("unavailable") == 1
    assert len(tuple(budget.paths.capture.budgets.glob("reservation-*.json"))) == 1


def test_one_token_over_is_refused_without_a_reservation_file(tmp_path: Path) -> None:
    budget, key, _ = _frozen_budget(tmp_path, ceiling=999)

    with pytest.raises(BudgetUnavailable, match="capture_budget_unavailable"):
        budget.reserve(key, 1, TokenUsage(700, 300, 1000))

    assert not tuple(budget.paths.capture.budgets.glob("reservation-*.json"))


def test_actual_usage_replaces_active_reservation_charge(tmp_path: Path) -> None:
    budget, key, _ = _frozen_budget(tmp_path, ceiling=1_500)
    reservation = budget.reserve(key, 1, TokenUsage(700, 300, 1000))

    settlement = budget.settle(reservation, TokenUsage(400, 100, 500))

    assert settlement.usage_quality == "actual"
    assert budget.snapshot().charged_tokens == 500
    assert budget.reserve(key, 2, TokenUsage(700, 300, 1000)).attempt == 2


@pytest.mark.parametrize(
    "usage",
    (None, object(), TokenUsage(800, 300, 1100)),
)
def test_absent_invalid_timeout_and_unknown_usage_charge_reserved_maximum(
    tmp_path: Path, usage: object
) -> None:
    budget, key, _ = _frozen_budget(tmp_path)
    reservation = budget.reserve(key, 1, TokenUsage(700, 300, 1000))

    settlement = budget.settle(reservation, usage)

    assert settlement.usage_quality == "reserved"
    assert settlement.charged_usage == reservation.maximum_usage


def test_retry_attempts_have_distinct_charges(tmp_path: Path) -> None:
    budget, key, _ = _frozen_budget(tmp_path)

    first = budget.reserve(key, 1, TokenUsage(700, 300, 1000))
    second = budget.reserve(key, 2, TokenUsage(700, 300, 1000))

    assert first.reservation_id != second.reservation_id
    assert budget.snapshot().charged_tokens == 2_000


def test_crash_after_reservation_survives_restart(tmp_path: Path) -> None:
    budget, key, census_id = _frozen_budget(tmp_path)
    reservation = budget.reserve(key, 1, TokenUsage(700, 300, 1000))
    restarted = CaptureTokenBudget(
        budget.paths,
        pool="backfill",
        census_id=census_id,
        ceiling=100_000,
        clock=lambda: "2026-08-20T00:02:00Z",
    )

    replay = restarted.reserve(key, 1, TokenUsage(700, 300, 1000))

    assert replay == reservation
    assert restarted.snapshot().charged_tokens == 1_000


def test_exact_double_settlement_is_idempotent_and_conflict_is_rejected(
    tmp_path: Path,
) -> None:
    budget, key, _ = _frozen_budget(tmp_path)
    reservation = budget.reserve(key, 1, TokenUsage(700, 300, 1000))
    first = budget.settle(reservation, TokenUsage(400, 100, 500))

    assert budget.settle(reservation, TokenUsage(400, 100, 500)) == first
    with pytest.raises(ValueError, match="capture_budget_conflict"):
        budget.settle(reservation, TokenUsage(300, 100, 400))


def test_incremental_pool_is_unavailable_when_configured_total_is_null(
    tmp_path: Path,
) -> None:
    paths = MemoryPaths.from_root(tmp_path / "memory")
    budget = CaptureTokenBudget(
        paths,
        pool="incremental",
        census_id=None,
        ceiling=None,
    )

    with pytest.raises(BudgetUnavailable, match="capture_budget_unavailable"):
        budget.reserve(_key(), 1, TokenUsage(1, 0, 1))


def test_foreign_key_cannot_charge_a_frozen_backfill_pool(tmp_path: Path) -> None:
    budget, _, _ = _frozen_budget(tmp_path)
    foreign = CaptureKey("codex", "a" * 64, "other-task", "turn-1")

    with pytest.raises(ValueError, match="capture_budget_foreign_key"):
        budget.reserve(foreign, 1, TokenUsage(1, 0, 1))
