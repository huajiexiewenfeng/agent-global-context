"""Optional, metadata-only Trace bridge for Capture Runner cycles."""

from __future__ import annotations

import os
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from agc_runtime.capture_contracts import CAPTURE_STATUSES

TraceStatus = Literal["disabled", "suppressed", "recorded", "unavailable"]

_TRACE_ENV = "AGENT_TRACE_DB"
_ROOT_NAME = "agc.capture.cycle"
_PRINCIPAL_ID = "agent-global-context.capture"
_COUNT_FIELDS = (
    "attempted_count",
    "completed_count",
    "failed_count",
    "deferred_budget_count",
    "lease_contention_count",
    "observation_count",
    "charged_tokens",
    "backlog_count",
    "silent_loss_count",
    "run_time_ms",
)
_SIGNIFICANT_FIELDS = frozenset(
    {
        "attempted_count",
        "completed_count",
        "failed_count",
        "deferred_budget_count",
        "lease_contention_count",
        "observation_count",
        "charged_tokens",
    }
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _is_non_negative_integer(value: Any) -> bool:
    return type(value) is int and value >= 0


def _is_significant(report: Mapping[str, Any]) -> bool:
    return any(
        _is_non_negative_integer(report.get(name)) and report[name] > 0
        for name in _SIGNIFICANT_FIELDS
    )


def _success_payload(action: str, report: Mapping[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {"action": action}
    for name in _COUNT_FIELDS:
        value = report.get(name)
        if _is_non_negative_integer(value):
            payload[name] = value
    deltas = report.get("status_deltas")
    if isinstance(deltas, Mapping):
        delta_items = tuple(deltas.items())
        if any(not isinstance(name, str) for name, _value in delta_items):
            raise TypeError("trace_status_deltas_invalid")
        safe_deltas = dict(
            sorted(
                {
                    name: value
                    for name, value in delta_items
                    if name in CAPTURE_STATUSES
                    and _is_non_negative_integer(value)
                }.items()
            )
        )
        payload["status_deltas"] = safe_deltas
    return payload


def _emit_root(
    *,
    database_value: str,
    started_at: datetime,
    finished_at: datetime,
    terminal_event_type: str,
    terminal_payload: Mapping[str, Any],
) -> TraceStatus:
    if not database_value:
        return "unavailable"
    try:
        from agent_trace_runtime import (
            EventStore,
            PrincipalRef,
            TraceService,
            create_event,
            resolve_db_path,
        )

        database = resolve_db_path(Path(database_value))
        service = TraceService(EventStore(database))
        if not service.preflight("optional").ok:
            return "unavailable"
        principal = PrincipalRef(_PRINCIPAL_ID, "runtime")
        trace_id = "trc_agc_" + uuid4().hex
        span_id = "spn_agc_" + uuid4().hex
        service.emit(
            create_event(
                trace_id=trace_id,
                span_id=span_id,
                parent_span_id=None,
                event_type="trace.root.started",
                source="runtime",
                principal_ref=principal,
                payload={"name": _ROOT_NAME, "span_kind": "workflow"},
                clock=lambda: started_at,
            )
        )
        service.emit(
            create_event(
                trace_id=trace_id,
                span_id=span_id,
                parent_span_id=None,
                event_type=terminal_event_type,
                source="runtime",
                principal_ref=principal,
                payload=terminal_payload,
                clock=lambda: finished_at,
            )
        )
    except Exception:  # noqa: BLE001 - Trace must never affect Capture.
        return "unavailable"
    return "recorded"


def record_capture_success(
    *,
    action: str,
    started_at: datetime,
    report: Mapping[str, Any],
    finished_at: datetime | None = None,
) -> TraceStatus:
    """Record one useful successful cycle without exposing Capture content."""

    if _TRACE_ENV not in os.environ:
        return "disabled"
    try:
        if not _is_significant(report):
            return "suppressed"
        terminal_payload = _success_payload(action, report)
    except Exception:  # noqa: BLE001 - Trace must never affect Capture.
        return "unavailable"
    return _emit_root(
        database_value=os.environ[_TRACE_ENV],
        started_at=started_at,
        finished_at=finished_at or _now(),
        terminal_event_type="trace.root.completed",
        terminal_payload=terminal_payload,
    )


def record_capture_failure(
    *,
    action: str,
    started_at: datetime,
    code: str,
    message: str,
    finished_at: datetime | None = None,
) -> TraceStatus:
    """Record one sanitized failed cycle without affecting Capture failure."""

    if _TRACE_ENV not in os.environ:
        return "disabled"
    return _emit_root(
        database_value=os.environ[_TRACE_ENV],
        started_at=started_at,
        finished_at=finished_at or _now(),
        terminal_event_type="trace.root.failed",
        terminal_payload={
            "action": action,
            "error": {"type": code, "message": message},
        },
    )


__all__ = ["TraceStatus", "record_capture_failure", "record_capture_success"]
