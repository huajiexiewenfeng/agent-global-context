"""Strict identities and validation for durable Capture model-token budgets."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any

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


__all__ = [
    "reservation_id_for",
    "validate_budget_settlement",
    "validate_token_reservation",
]
