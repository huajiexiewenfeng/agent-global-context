from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

pytest.importorskip("agent_trace_runtime")
from agent_trace_runtime import EventStore, PrincipalRef, TraceService, create_event
from test_capture_eval_adapter import _item_event

from agc_runtime.capture_eval_adapter import capture_eval_cases

PROFILE = {"id": "agc.capture-quality", "version": "1"}
PRINCIPAL = PrincipalRef("agent-global-context.capture", "runtime")


def reference(n):
    return {
        "schema_version": "eval.evidence-ref.v0.1",
        "provider": "agc",
        "kind": "capture-item",
        "ref": "cr_" + f"{n:064x}",
        "digest": "sha256:" + f"{n:064x}",
        "version": "1",
    }


def emit(
    service, n, ref, *, principal=PRINCIPAL, event_type="agc.capture.item.completed"
):
    service.emit(
        create_event(
            trace_id="trace_agc",
            span_id="span_agc",
            parent_span_id=None,
            event_type=event_type,
            source="principal",
            principal_ref=principal,
            payload=_item_event("trace_agc", ref).payload,
            clock=lambda: datetime(2026, 9, 8, tzinfo=UTC),
            id_factory=lambda: f"evt_{n}",
        )
    )


class QueryReader(TraceService):
    def __init__(self, store):
        super().__init__(store)
        self.queries = []
        self.snapshot_reads = []

    def list_traces(self, limit=20):
        pytest.fail("new runtime must not enumerate Trace summaries")

    def query_events(self, **kwargs):
        self.queries.append(kwargs)
        return super().query_events(**kwargs)

    def snapshot(self, trace_id):
        self.snapshot_reads.append(trace_id)
        return super().snapshot(trace_id)


@pytest.fixture
def reader(tmp_path):
    return QueryReader(EventStore(tmp_path / "trace.sqlite3"))


def test_query_pages_deduplicate_and_load_only_selected_snapshots(reader):
    emit(reader, 0, reference(1))
    for n in range(1, 23):
        emit(reader, n, reference(2))
    emit(reader, 23, reference(3), principal=PrincipalRef("other", "runtime"))
    emit(reader, 24, reference(4), event_type="agc.capture.other")
    cases = capture_eval_cases(reader, PROFILE, "0.4.5", 2)
    assert [case["evidence_refs"][0] for case in cases] == [reference(2), reference(1)]
    assert len(reader.queries) == 2
    assert reader.queries[0]["principal_ref"] == PRINCIPAL
    assert reader.queries[0]["event_type"] == "agc.capture.item.completed"
    assert reader.snapshot_reads == ["trace_agc"]
    assert all(case["trace_snapshot"]["trace_id"] == "trace_agc" for case in cases)


def test_query_stops_at_max_items_and_preserves_case_identity(reader):
    for n in range(25):
        emit(reader, n, reference(n))
    case = capture_eval_cases(reader, PROFILE, "0.4.5", 1)[0]
    assert case["evidence_refs"] == [reference(24)]
    assert len(reader.queries) == 1
    legacy = SimpleNamespace(
        list_traces=lambda limit: [
            SimpleNamespace(trace_id="trace_agc", last_timestamp="now")
        ],
        events=lambda trace_id: [_item_event(trace_id, reference(24))],
        snapshot=reader.snapshot,
    )
    assert capture_eval_cases(legacy, PROFILE, "0.4.5", 1)[0] == case


def test_query_empty_returns_no_cases_and_no_snapshots(reader):
    assert capture_eval_cases(reader, PROFILE, "0.4.5", 1) == ()
    assert reader.snapshot_reads == []


@pytest.mark.parametrize("mode", ["error", "bad_page", "repeat_cursor", "bad_cursor"])
def test_query_failure_does_not_fall_back_or_leak_details(reader, mode):
    calls = []

    def broken_query(**kwargs):
        calls.append(kwargs)
        if mode == "error":
            raise OSError("private-query-sentinel")
        if mode == "bad_page":
            return SimpleNamespace(events="invalid", next_cursor=None)
        return SimpleNamespace(
            events=[], next_cursor="repeated" if mode == "repeat_cursor" else 9
        )

    reader.query_events = broken_query
    with pytest.raises(ValueError) as error:
        capture_eval_cases(reader, PROFILE, "0.4.5", 1)
    assert str(error.value) == "capture_eval_trace_invalid"
    assert len(calls) <= 2
    assert reader.snapshot_reads == []


def test_query_keeps_domain_payload_validation(reader):
    emit(reader, 1, {"invalid": "private-sentinel"})
    with pytest.raises(ValueError, match="^capture_eval_trace_invalid$"):
        capture_eval_cases(reader, PROFILE, "0.4.5", 1)
    assert reader.snapshot_reads == []
