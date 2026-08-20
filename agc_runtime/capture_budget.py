"""Strict identities and validation for durable Capture model-token budgets."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from agc_runtime.capture_contracts import (
    CAPTURE_SCHEMA_VERSION,
    BudgetSettlement,
    CaptureKey,
    TokenReservation,
    TokenUsage,
)


_RESERVATION_ID = re.compile(r"^br_[0-9a-f]{64}$")
_CENSUS_ID = re.compile(r"^census-[0-9a-f]{32}$")
_POOLS = frozenset({"backfill", "incremental"})
_USAGE_QUALITIES = frozenset({"actual", "reserved"})


class BudgetUnavailable(RuntimeError):
    def __init__(self) -> None:
        super().__init__("capture_budget_unavailable")


@dataclass(frozen=True)
class BudgetSnapshot:
    ceiling_tokens: int | None
    charged_tokens: int
    remaining_tokens: int | None
    active_reservations: int
    settlements: int


def _invalid() -> ValueError:
    return ValueError("capture_budget_contract_invalid")


def _canonical_json(value: dict[str, Any]) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
    except (TypeError, ValueError, UnicodeError) as error:
        raise _invalid() from error


def _valid_utc(value: object) -> bool:
    if not isinstance(value, str) or not value.endswith("Z"):
        return False
    try:
        datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return False
    return True


def _validated_key(value: object) -> CaptureKey:
    if not isinstance(value, CaptureKey):
        raise _invalid()
    try:
        return CaptureKey.from_mapping(value.to_mapping())
    except (AttributeError, TypeError, ValueError, UnicodeError) as error:
        raise _invalid() from error


def _validated_usage(value: object) -> TokenUsage:
    if not isinstance(value, TokenUsage):
        raise _invalid()
    try:
        return TokenUsage.from_mapping(value.to_mapping())
    except (AttributeError, TypeError, ValueError, UnicodeError) as error:
        raise _invalid() from error


def reservation_id_for(
    pool: str,
    census_id: str | None,
    key: CaptureKey,
    attempt: int,
) -> str:
    if (
        pool not in _POOLS
        or type(attempt) is not int
        or attempt < 1
        or (pool == "backfill" and (
            not isinstance(census_id, str)
            or _CENSUS_ID.fullmatch(census_id) is None
        ))
        or (pool == "incremental" and census_id is not None)
    ):
        raise _invalid()
    validated_key = _validated_key(key)
    payload = _canonical_json(
        {
            "attempt": attempt,
            "capture_key": validated_key.to_mapping(),
            "census_id": census_id,
            "pool": pool,
        }
    )
    return "br_" + hashlib.sha256(payload).hexdigest()


def validate_token_reservation(value: TokenReservation) -> None:
    try:
        key = _validated_key(value.capture_key)
        usage = _validated_usage(value.maximum_usage)
        valid = (
            type(value.schema_version) is int
            and value.schema_version == CAPTURE_SCHEMA_VERSION
            and isinstance(value.reservation_id, str)
            and _RESERVATION_ID.fullmatch(value.reservation_id) is not None
            and value.pool in _POOLS
            and type(value.attempt) is int
            and value.attempt >= 1
            and usage.total_tokens >= 1
            and _valid_utc(value.reserved_at)
            and value.reservation_id
            == reservation_id_for(
                value.pool,
                value.census_id,
                key,
                value.attempt,
            )
        )
    except (AttributeError, TypeError, ValueError, UnicodeError) as error:
        raise _invalid() from error
    if not valid:
        raise _invalid()


def validate_budget_settlement(value: BudgetSettlement) -> None:
    try:
        _validated_key(value.capture_key)
        _validated_usage(value.charged_usage)
        valid = (
            type(value.schema_version) is int
            and value.schema_version == CAPTURE_SCHEMA_VERSION
            and isinstance(value.reservation_id, str)
            and _RESERVATION_ID.fullmatch(value.reservation_id) is not None
            and value.usage_quality in _USAGE_QUALITIES
            and _valid_utc(value.settled_at)
        )
    except (AttributeError, TypeError, ValueError, UnicodeError) as error:
        raise _invalid() from error
    if not valid:
        raise _invalid()


class CaptureTokenBudget:
    """Durable, root-locked accounting for one Capture token pool."""

    def __init__(
        self,
        paths: object,
        *,
        pool: str,
        census_id: str | None,
        ceiling: int | None,
        clock: Callable[[], str] | None = None,
    ) -> None:
        from agc_runtime.paths import MemoryPaths

        if not isinstance(paths, MemoryPaths):
            raise _invalid()
        if (
            pool not in _POOLS
            or (pool == "backfill" and (
                not isinstance(census_id, str)
                or _CENSUS_ID.fullmatch(census_id) is None
            ))
            or (pool == "incremental" and census_id is not None)
            or (
                ceiling is not None
                and (type(ceiling) is not int or ceiling < 1)
            )
        ):
            raise _invalid()
        self.paths = paths
        self.pool = pool
        self.census_id = census_id
        self.ceiling = ceiling
        self._clock = clock or (
            lambda: datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )

    @property
    def _pool_path(self) -> Path:
        suffix = self.census_id if self.pool == "backfill" else "incremental"
        return self.paths.capture.budgets / f"pool-{self.pool}-{suffix}.json"

    def _pool_mapping(self, created_at: str) -> dict[str, object]:
        return {
            "schema_version": CAPTURE_SCHEMA_VERSION,
            "pool": self.pool,
            "census_id": self.census_id,
            "ceiling_tokens": self.ceiling,
            "created_at": created_at,
        }

    def _read_pool(self) -> dict[str, object]:
        from agc_runtime.capture_transaction import read_json

        value = read_json(self._pool_path)
        if set(value) != {
            "schema_version", "pool", "census_id", "ceiling_tokens", "created_at"
        }:
            raise ValueError("capture_budget_corrupt")
        if (
            value.get("schema_version") != CAPTURE_SCHEMA_VERSION
            or value.get("pool") != self.pool
            or value.get("census_id") != self.census_id
            or value.get("ceiling_tokens") != self.ceiling
            or not _valid_utc(value.get("created_at"))
        ):
            raise ValueError("capture_budget_conflict")
        return value

    def _ensure_pool_locked(self) -> None:
        from agc_runtime.capture_transaction import atomic_write_json

        self.paths.capture.budgets.mkdir(parents=True, exist_ok=True)
        if self._pool_path.exists():
            self._read_pool()
            return
        atomic_write_json(self._pool_path, self._pool_mapping(self._clock()))

    def _require_frozen_membership_locked(self, key: CaptureKey) -> None:
        if self.pool != "backfill":
            return
        from agc_runtime.capture_store import CaptureStore

        run = self.paths.capture.root / "census-runs" / str(self.census_id)
        try:
            _, revisions = CaptureStore(self.paths)._read_frozen_run(run)
        except (FileNotFoundError, OSError, TypeError, ValueError) as error:
            raise ValueError("capture_budget_foreign_key") from error
        if key not in {item.key for item in revisions}:
            raise ValueError("capture_budget_foreign_key")

    @staticmethod
    def _reservation_path(root: Path, reservation_id: str) -> Path:
        return root / f"reservation-{reservation_id}.json"

    @staticmethod
    def _settlement_path(root: Path, reservation_id: str) -> Path:
        return root / f"settlement-{reservation_id}.json"

    def _entries_locked(
        self,
    ) -> tuple[dict[str, TokenReservation], dict[str, BudgetSettlement]]:
        from agc_runtime.capture_transaction import read_json

        reservations: dict[str, TokenReservation] = {}
        settlements: dict[str, BudgetSettlement] = {}
        root = self.paths.capture.budgets
        for path in sorted(root.glob("reservation-*.json")):
            item = TokenReservation.from_mapping(read_json(path))
            if path.name != f"reservation-{item.reservation_id}.json":
                raise ValueError("capture_budget_corrupt")
            if item.pool == self.pool and item.census_id == self.census_id:
                reservations[item.reservation_id] = item
        for path in sorted(root.glob("settlement-*.json")):
            item = BudgetSettlement.from_mapping(read_json(path))
            if path.name != f"settlement-{item.reservation_id}.json":
                raise ValueError("capture_budget_corrupt")
            if item.reservation_id in reservations:
                settlements[item.reservation_id] = item
        return reservations, settlements

    @staticmethod
    def _charged(
        reservations: dict[str, TokenReservation],
        settlements: dict[str, BudgetSettlement],
    ) -> int:
        return sum(
            settlements[item_id].charged_usage.total_tokens
            if item_id in settlements
            else item.maximum_usage.total_tokens
            for item_id, item in reservations.items()
        )

    def reserve(
        self,
        key: CaptureKey,
        attempt: int,
        maximum: TokenUsage,
    ) -> TokenReservation:
        from agc_runtime.capture_transaction import atomic_write_json, read_json
        from agc_runtime.locking import capture_write_lock

        if self.ceiling is None:
            raise BudgetUnavailable()
        key = _validated_key(key)
        maximum = _validated_usage(maximum)
        reservation = TokenReservation(
            CAPTURE_SCHEMA_VERSION,
            reservation_id_for(self.pool, self.census_id, key, attempt),
            self.pool,
            self.census_id,
            key,
            attempt,
            maximum,
            self._clock(),
        )
        with capture_write_lock(self.paths):
            self._require_frozen_membership_locked(key)
            self._ensure_pool_locked()
            path = self._reservation_path(
                self.paths.capture.budgets, reservation.reservation_id
            )
            if path.exists():
                current = TokenReservation.from_mapping(read_json(path))
                if (
                    current.pool != reservation.pool
                    or current.census_id != reservation.census_id
                    or current.capture_key != reservation.capture_key
                    or current.attempt != reservation.attempt
                    or current.maximum_usage != reservation.maximum_usage
                ):
                    raise ValueError("capture_budget_conflict")
                return current
            reservations, settlements = self._entries_locked()
            if self._charged(reservations, settlements) + maximum.total_tokens > self.ceiling:
                raise BudgetUnavailable()
            atomic_write_json(path, reservation.to_mapping())
            return reservation

    def prepare_settlement(
        self,
        reservation: TokenReservation,
        usage: object,
    ) -> BudgetSettlement:
        reservation = TokenReservation.from_mapping(reservation.to_mapping())
        charged = reservation.maximum_usage
        quality = "reserved"
        if isinstance(usage, TokenUsage):
            try:
                actual = _validated_usage(usage)
            except ValueError:
                actual = None
            if actual is not None and all(
                getattr(actual, field) <= getattr(reservation.maximum_usage, field)
                for field in ("input_tokens", "output_tokens", "total_tokens")
            ):
                charged = actual
                quality = "actual"
        return BudgetSettlement(
            CAPTURE_SCHEMA_VERSION,
            reservation.reservation_id,
            reservation.capture_key,
            charged,
            quality,
            self._clock(),
        )

    def settle(
        self,
        reservation: TokenReservation,
        usage: object,
    ) -> BudgetSettlement:
        from agc_runtime.locking import capture_write_lock

        reservation = TokenReservation.from_mapping(reservation.to_mapping())
        desired = self.prepare_settlement(reservation, usage)
        with capture_write_lock(self.paths):
            self._ensure_pool_locked()
            return persist_settlement_locked(self.paths, reservation, desired)

    def snapshot(self) -> BudgetSnapshot:
        from agc_runtime.locking import capture_write_lock

        if self.ceiling is None:
            return BudgetSnapshot(None, 0, None, 0, 0)
        with capture_write_lock(self.paths):
            self._ensure_pool_locked()
            reservations, settlements = self._entries_locked()
            charged = self._charged(reservations, settlements)
            return BudgetSnapshot(
                self.ceiling,
                charged,
                self.ceiling - charged,
                len(reservations) - len(settlements),
                len(settlements),
            )


def persist_settlement_locked(
    paths: object,
    reservation: TokenReservation,
    settlement: BudgetSettlement,
) -> BudgetSettlement:
    """Persist one settlement while the caller holds the Capture root lock."""

    from agc_runtime.capture_transaction import atomic_write_json, read_json
    from agc_runtime.paths import MemoryPaths

    if not isinstance(paths, MemoryPaths):
        raise _invalid()
    reservation = TokenReservation.from_mapping(reservation.to_mapping())
    settlement = BudgetSettlement.from_mapping(settlement.to_mapping())
    if (
        settlement.reservation_id != reservation.reservation_id
        or settlement.capture_key != reservation.capture_key
        or any(
            getattr(settlement.charged_usage, field)
            > getattr(reservation.maximum_usage, field)
            for field in ("input_tokens", "output_tokens", "total_tokens")
        )
        or (
            settlement.usage_quality == "reserved"
            and settlement.charged_usage != reservation.maximum_usage
        )
    ):
        raise ValueError("capture_budget_conflict")
    root = paths.capture.budgets
    reservation_path = CaptureTokenBudget._reservation_path(
        root, reservation.reservation_id
    )
    if not reservation_path.exists():
        raise ValueError("capture_budget_conflict")
    current_reservation = TokenReservation.from_mapping(read_json(reservation_path))
    if current_reservation != reservation:
        raise ValueError("capture_budget_conflict")
    path = CaptureTokenBudget._settlement_path(root, reservation.reservation_id)
    if path.exists():
        current = BudgetSettlement.from_mapping(read_json(path))
        if (
            current.reservation_id != settlement.reservation_id
            or current.capture_key != settlement.capture_key
            or current.charged_usage != settlement.charged_usage
            or current.usage_quality != settlement.usage_quality
        ):
            raise ValueError("capture_budget_conflict")
        return current
    atomic_write_json(path, settlement.to_mapping())
    return settlement


__all__ = [
    "BudgetSnapshot",
    "BudgetUnavailable",
    "CaptureTokenBudget",
    "persist_settlement_locked",
    "reservation_id_for",
    "validate_budget_settlement",
    "validate_token_reservation",
]
