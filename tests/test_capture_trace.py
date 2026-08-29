"""Contract tests for the optional Capture-to-Trace bridge."""

from __future__ import annotations

import builtins
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest
import tomllib

from agc_runtime.capture_trace import (
    record_capture_failure,
    record_capture_success,
)

STARTED_AT = datetime(2026, 8, 29, 8, 0, tzinfo=timezone.utc)
FINISHED_AT = STARTED_AT + timedelta(seconds=3)
SENTINEL = "private-session-content-must-not-enter-trace"


def _report(**changes: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "attempted_count": 0,
        "completed_count": 0,
        "failed_count": 0,
        "deferred_budget_count": 0,
        "lease_contention_count": 0,
        "reserved_attempt_count": 0,
        "extractor_call_count": 0,
        "observation_count": 0,
        "charged_tokens": 0,
        "silent_loss_count": 0,
        "backlog_count": 0,
        "oldest_unresolved_at": None,
        "attempt_count_delta": 0,
        "status_deltas": {},
        "run_time_ms": 3,
        "source_bytes_read": 0,
        "peak_process_count": 0,
    }
    result.update(changes)
    return result


def _install_fake_runtime(
    monkeypatch: pytest.MonkeyPatch,
    *,
    preflight_ok: bool = True,
    fail_emit_at: int | None = None,
) -> tuple[list[dict[str, Any]], list[Path]]:
    events: list[dict[str, Any]] = []
    resolved: list[Path] = []
    module = ModuleType("agent_trace_runtime")

    class PrincipalRef:
        def __init__(self, principal_id: str, kind: str) -> None:
            self.id = principal_id
            self.kind = kind

    class EventStore:
        def __init__(self, path: Path) -> None:
            self.path = path

    class TraceService:
        def __init__(self, store: EventStore) -> None:
            self.store = store

        def preflight(self, mode: str) -> SimpleNamespace:
            assert mode == "optional"
            return SimpleNamespace(ok=preflight_ok)

        def emit(self, event: dict[str, Any]) -> None:
            events.append(event)
            if fail_emit_at is not None and len(events) == fail_emit_at:
                raise OSError("private store failure")

    def create_event(**values: Any) -> dict[str, Any]:
        values = dict(values)
        values["timestamp"] = values.pop("clock")()
        return values

    def resolve_db_path(explicit: Path) -> Path:
        resolved.append(explicit)
        return explicit

    module.EventStore = EventStore
    module.PrincipalRef = PrincipalRef
    module.TraceService = TraceService
    module.create_event = create_event
    module.resolve_db_path = resolve_db_path
    monkeypatch.setitem(sys.modules, "agent_trace_runtime", module)
    return events, resolved


def test_absent_opt_in_is_disabled_without_importing_trace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AGENT_TRACE_DB", raising=False)
    real_import = builtins.__import__

    def guarded_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "agent_trace_runtime":
            raise AssertionError("Trace Runtime import must remain lazy")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    status = record_capture_success(
        action="cycle",
        started_at=STARTED_AT,
        finished_at=FINISHED_AT,
        report=_report(completed_count=1),
    )

    assert status == "disabled"


def test_empty_success_is_suppressed_before_trace_import(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENT_TRACE_DB", r"D:\tmp_test\trace.sqlite3")
    real_import = builtins.__import__

    def guarded_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "agent_trace_runtime":
            raise AssertionError("suppressed cycle must not import Trace Runtime")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    status = record_capture_success(
        action="run",
        started_at=STARTED_AT,
        finished_at=FINISHED_AT,
        report=_report(),
    )

    assert status == "suppressed"


def test_significant_success_records_one_allowlisted_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = Path(r"D:\tmp_test\agc-capture-trace\trace.sqlite3")
    monkeypatch.setenv("AGENT_TRACE_DB", str(database))
    events, resolved = _install_fake_runtime(monkeypatch)

    status = record_capture_success(
        action="cycle",
        started_at=STARTED_AT,
        finished_at=FINISHED_AT,
        report=_report(
            attempted_count=2,
            completed_count=1,
            failed_count=1,
            observation_count=3,
            charged_tokens=120,
            backlog_count=4,
            silent_loss_count=0,
            run_time_ms=3000,
            status_deltas={"complete": 1, "failed": 1, SENTINEL: 9},
            prompt=SENTINEL,
            task_id=SENTINEL,
        ),
    )

    assert status == "recorded"
    assert resolved == [database]
    assert [event["event_type"] for event in events] == [
        "trace.root.started",
        "trace.root.completed",
    ]
    assert events[0]["trace_id"] == events[1]["trace_id"]
    assert events[0]["span_id"] == events[1]["span_id"]
    assert events[0]["parent_span_id"] is None
    assert events[0]["source"] == "runtime"
    assert events[0]["principal_ref"].id == "agent-global-context.capture"
    assert events[0]["principal_ref"].kind == "runtime"
    assert events[0]["payload"] == {
        "name": "agc.capture.cycle",
        "span_kind": "workflow",
    }
    assert events[0]["timestamp"] == STARTED_AT
    assert events[1]["timestamp"] == FINISHED_AT
    assert events[1]["payload"] == {
        "action": "cycle",
        "attempted_count": 2,
        "completed_count": 1,
        "failed_count": 1,
        "deferred_budget_count": 0,
        "lease_contention_count": 0,
        "observation_count": 3,
        "charged_tokens": 120,
        "backlog_count": 4,
        "silent_loss_count": 0,
        "run_time_ms": 3000,
        "status_deltas": {"complete": 1, "failed": 1},
    }
    assert SENTINEL not in repr(events)


def test_failure_records_only_sanitized_cli_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENT_TRACE_DB", r"D:\tmp_test\trace.sqlite3")
    events, _resolved = _install_fake_runtime(monkeypatch)

    status = record_capture_failure(
        action="run",
        started_at=STARTED_AT,
        finished_at=FINISHED_AT,
        code="capture_source_failed",
        message="Capture source is unavailable",
    )

    assert status == "recorded"
    assert [event["event_type"] for event in events] == [
        "trace.root.started",
        "trace.root.failed",
    ]
    assert events[1]["payload"] == {
        "action": "run",
        "error": {
            "type": "capture_source_failed",
            "message": "Capture source is unavailable",
        },
    }


@pytest.mark.parametrize(
    ("preflight_ok", "fail_emit_at"),
    [(False, None), (True, 1), (True, 2)],
)
def test_trace_backend_failures_are_unavailable_and_never_raise(
    monkeypatch: pytest.MonkeyPatch,
    preflight_ok: bool,
    fail_emit_at: int | None,
) -> None:
    monkeypatch.setenv("AGENT_TRACE_DB", r"D:\tmp_test\trace.sqlite3")
    _install_fake_runtime(
        monkeypatch,
        preflight_ok=preflight_ok,
        fail_emit_at=fail_emit_at,
    )

    assert (
        record_capture_success(
            action="cycle",
            started_at=STARTED_AT,
            finished_at=FINISHED_AT,
            report=_report(attempted_count=1),
        )
        == "unavailable"
    )


def test_missing_trace_runtime_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_TRACE_DB", r"D:\tmp_test\trace.sqlite3")
    monkeypatch.delitem(sys.modules, "agent_trace_runtime", raising=False)
    real_import = builtins.__import__

    def missing_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "agent_trace_runtime":
            raise ModuleNotFoundError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", missing_import)

    assert (
        record_capture_success(
            action="run",
            started_at=STARTED_AT,
            finished_at=FINISHED_AT,
            report=_report(charged_tokens=1),
        )
        == "unavailable"
    )


def test_malformed_report_mapping_is_unavailable_and_never_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENT_TRACE_DB", r"D:\tmp_test\trace.sqlite3")
    _install_fake_runtime(monkeypatch)

    assert (
        record_capture_success(
            action="cycle",
            started_at=STARTED_AT,
            finished_at=FINISHED_AT,
            report=_report(
                attempted_count=1,
                status_deltas={"complete": 1, 7: 2},
            ),
        )
        == "unavailable"
    )


def test_trace_runtime_is_an_optional_bounded_dependency() -> None:
    project = tomllib.loads(
        (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(
            encoding="utf-8"
        )
    )["project"]

    assert project["optional-dependencies"]["trace"] == [
        "agent-trace-runtime>=0.1,<0.2"
    ]
    assert all("agent-trace-runtime" not in item for item in project["dependencies"])
