from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from agc_runtime.capture_capsule import CapsuleCounts, CapsuleResult, TaskCapsule
from agc_runtime.capture_contracts import (
    CaptureKey,
    CaptureReceipt,
    CollectedObservation,
    RevisionRef,
    TokenUsage,
    observation_fingerprint_for,
    observation_id_for,
    receipt_id_for,
)
from agc_runtime.capture_eval_adapter import (
    AGCCaptureEvidenceResolver,
    capture_eval_cases,
)
from agc_runtime.capture_eval_evidence import (
    canonical_sha256,
    capture_eval_evidence_content,
)
from agc_runtime.capture_source import SourceBindingKey, TimeWindow
from agc_runtime.capture_store import CaptureStore
from agc_runtime.paths import MemoryPaths

NOW = "2026-08-30T08:00:00Z"
ROOT_ID = "1" * 64
SENTINEL = "private-source-error-must-not-escape"
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class FakeAdapter:
    def __init__(self, capsule_result: CapsuleResult) -> None:
        self.capsule_result = capsule_result
        self.fail = False

    def describe(self):
        return SimpleNamespace(adapter_id="synthetic", source_root_id=ROOT_ID)

    def load_capsule(self, revision, policy):
        del revision, policy
        if self.fail:
            raise OSError(SENTINEL)
        return self.capsule_result


def _write_config(root: Path) -> MemoryPaths:
    root.mkdir(parents=True)
    config = (REPOSITORY_ROOT / "agc_runtime" / "default_config.yaml").read_text(
        encoding="utf-8"
    )
    (root / "config.yaml").write_text(config, encoding="utf-8")
    return MemoryPaths.from_root(root)


def completed_reference_fixture(
    tmp_path: Path,
) -> tuple[MemoryPaths, FakeAdapter, dict[str, str], dict[str, object]]:
    paths = _write_config(tmp_path / "memory")
    key = CaptureKey("synthetic", ROOT_ID, "task-one", "revision-one")
    revision = RevisionRef.from_mapping(
        {
            "schema_version": 1,
            "capture_key": key.to_mapping(),
            "rollout_anchor_id": "rollout-one",
            "completed_at": "2026-08-29T08:00:00Z",
            "locator": "sessions/opaque.jsonl",
            "identity_quality": "session_id",
            "adapter_version": "1",
            "source_schema_version": "1",
        }
    )
    capsule = TaskCapsule(
        adapter_id=key.adapter_id,
        adapter_version="1",
        source_schema_version="1",
        source_root_id=key.source_root_id,
        task_id=key.task_id,
        revision_id=key.revision_id,
        rollout_anchor_id="rollout-one",
        identity_quality="session_id",
        completed_at=revision.completed_at,
        project_scope="project:agc",
        user_signals=("The user prefers durable context.",),
    )
    capsule_result = CapsuleResult(
        capsule,
        "a" * 64,
        "source-v1",
        "b" * 64,
        "capsule-v1",
        ("1",),
        100,
        CapsuleCounts(1, 1, 1, 0, 0, 0, 0, 0),
    )
    adapter = FakeAdapter(capsule_result)
    store = CaptureStore(paths, clock=lambda: NOW)
    store.freeze_census(
        binding=SourceBindingKey(1, "synthetic", ROOT_ID),
        window=TimeWindow(1, "2026-08-23T08:00:00Z", NOW),
        started_at=NOW,
        revisions=(revision,),
    )
    receipt_id = receipt_id_for(key)
    extracting = CaptureReceipt.from_mapping(
        {
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
            "status": "extracting",
            "attempt_count": 1,
            "next_retry_at": None,
            "extractor_id": "codex",
            "extractor_version": "0.4.3",
            "extractor_schema_version": "1",
            "taxonomy_version": "taxonomy-v1",
            "observation_count": None,
            "filtered_counts": None,
            "duplicate_suppression_count": None,
            "token_usage": TokenUsage(100, 50, 150).to_mapping(),
            "usage_quality": "actual",
            "redacted_by_forget": False,
            "forgotten_observation_count": 0,
            "zero_reason": None,
            "sanitized_error": None,
            "coalesced_to": None,
            "exclusion_reason": None,
        }
    )
    observation_value = {
        "schema_version": 1,
        "observation_id": "co_" + "0" * 64,
        "receipt_id": receipt_id,
        "source": {**key.to_mapping(), "locator": revision.locator},
        "ordinal": 0,
        "observation_fingerprint": "0" * 64,
        "statement": "The user prefers durable context.",
        "assertion": {"subject": "user", "mode": "direct", "modality": "asserted"},
        "primary_category": "work",
        "taxonomy_version": "taxonomy-v1",
        "kind": "preference",
        "scopes": ["global"],
        "project_scope": "project:agc",
        "confidence": "confirmed",
        "sensitivity": "normal",
        "signal_type": "explicit_user_state",
        "observed_at": revision.completed_at,
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
    observation = CollectedObservation.from_mapping(observation_value)
    complete = CaptureReceipt.from_mapping(
        {
            **extracting.to_mapping(),
            "status": "complete",
            "observation_count": 1,
            "filtered_counts": {"safety": 0, "policy": 0, "over_limit": 0},
            "duplicate_suppression_count": 0,
        }
    )
    store.register_extraction(extracting)
    lease = store.acquire_lease(key, owner_id="fixture", now=NOW, ttl_seconds=60)
    assert lease is not None
    store.commit_extraction(lease, (observation,), complete)
    content = capture_eval_evidence_content(capsule, complete, (observation,))
    reference = {
        "schema_version": "eval.evidence-ref.v0.1",
        "provider": "agc",
        "kind": "capture-item",
        "ref": receipt_id,
        "digest": canonical_sha256(content),
        "version": "1",
    }
    return paths, adapter, reference, content


def test_resolver_rebuilds_exact_capture_evidence(tmp_path: Path) -> None:
    paths, adapter, reference, expected_content = completed_reference_fixture(tmp_path)
    resolver = AGCCaptureEvidenceResolver(paths=paths, adapters=(adapter,))
    resolved = resolver.resolve(reference)
    assert resolved == expected_content
    assert canonical_sha256(resolved) == reference["digest"]


@pytest.mark.parametrize(
    ("field", "value", "code"),
    (
        ("provider", "other", "capture_eval_reference_invalid"),
        ("kind", "other", "capture_eval_reference_invalid"),
        ("ref", "not-a-receipt", "capture_eval_reference_invalid"),
        ("digest", "sha256:" + "f" * 64, "capture_eval_evidence_changed"),
    ),
)
def test_resolver_maps_reference_and_digest_failures_to_fixed_codes(
    tmp_path: Path, field: str, value: str, code: str
) -> None:
    paths, adapter, reference, _ = completed_reference_fixture(tmp_path)
    reference[field] = value
    with pytest.raises(ValueError) as raised:
        AGCCaptureEvidenceResolver(paths=paths, adapters=(adapter,)).resolve(reference)
    assert str(raised.value) == code
    assert SENTINEL not in str(raised.value)


def test_resolver_maps_missing_adapter_and_source_failure_without_details(tmp_path: Path) -> None:
    paths, adapter, reference, _ = completed_reference_fixture(tmp_path)
    with pytest.raises(ValueError) as missing:
        AGCCaptureEvidenceResolver(paths=paths, adapters=()).resolve(reference)
    assert str(missing.value) == "capture_eval_evidence_unavailable"
    adapter.fail = True
    with pytest.raises(ValueError) as failed:
        AGCCaptureEvidenceResolver(paths=paths, adapters=(adapter,)).resolve(reference)
    assert str(failed.value) == "capture_eval_evidence_unavailable"
    assert SENTINEL not in str(failed.value)


def test_resolver_rejects_changed_capsule_hash(tmp_path: Path) -> None:
    paths, adapter, reference, _ = completed_reference_fixture(tmp_path)
    adapter.capsule_result = replace(adapter.capsule_result, capsule_hash="f" * 64)
    with pytest.raises(ValueError) as raised:
        AGCCaptureEvidenceResolver(paths=paths, adapters=(adapter,)).resolve(reference)
    assert str(raised.value) == "capture_eval_evidence_changed"


class FakeTraceReader:
    def __init__(self, summaries, events_by_trace, snapshots) -> None:
        self.summaries = summaries
        self.events_by_trace = events_by_trace
        self.snapshots = snapshots

    def list_traces(self, limit=20):
        del limit
        return self.summaries

    def events(self, trace_id):
        return self.events_by_trace[trace_id]

    def snapshot(self, trace_id):
        return self.snapshots[trace_id]


def _item_event(trace_id: str, reference: dict[str, str]):
    return SimpleNamespace(
        trace_id=trace_id,
        event_type="agc.capture.item.completed",
        source="principal",
        principal_ref=SimpleNamespace(id="agent-global-context.capture", kind="runtime"),
        payload={
            "schema_version": "agc.capture.item-trace.v1",
            "outcome": "collected",
            "reason_code": "observations_collected",
            "observation_count": 1,
            "filtered_counts": {"safety": 0, "policy": 0, "over_limit": 0},
            "duplicate_suppression_count": 0,
            "token_usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
            "extractor_version": "0.4.3",
            "taxonomy_version": "taxonomy-v1",
            "evidence_ref": reference,
        },
    )


def test_case_builder_is_newest_first_deduplicated_and_exact() -> None:
    first_ref = {
        "schema_version": "eval.evidence-ref.v0.1",
        "provider": "agc",
        "kind": "capture-item",
        "ref": "cr_" + "a" * 64,
        "digest": "sha256:" + "b" * 64,
        "version": "1",
    }
    second_ref = {**first_ref, "ref": "cr_" + "c" * 64, "digest": "sha256:" + "d" * 64}
    summaries = [
        SimpleNamespace(trace_id="old", last_timestamp="2026-08-29T08:00:00Z"),
        SimpleNamespace(trace_id="new", last_timestamp="2026-08-30T08:00:00Z"),
    ]
    reader = FakeTraceReader(
        summaries,
        {
            "old": [_item_event("old", first_ref)],
            "new": [_item_event("new", second_ref), _item_event("new", first_ref)],
        },
        {"old": {"trace_id": "old"}, "new": {"trace_id": "new"}},
    )
    profile_ref = {"id": "agc.capture-quality", "version": "1"}
    cases = capture_eval_cases(reader, profile_ref, "0.4.4", 100)
    subject = {
        "principal_ref": {"id": "agent-global-context.capture", "kind": "runtime"},
        "capability": "capture",
        "operation": "observation-quality",
        "implementation_version": "0.4.4",
    }
    expected_case_id = "evc_" + canonical_sha256(
        {"subject": subject, "profile_ref": profile_ref, "evidence_ref": second_ref}
    ).removeprefix("sha256:")
    assert len(cases) == 2
    assert cases[0] == {
        "schema_version": "eval.case.v0.1",
        "case_id": expected_case_id,
        "subject": subject,
        "profile_ref": profile_ref,
        "evidence_refs": [second_ref],
        "trace_snapshot": {"trace_id": "new"},
        "reference": None,
        "metadata": {"sample_reason": "latest-completed-capture-item"},
    }


def test_case_builder_ignores_unrelated_events_and_rejects_malformed_items() -> None:
    unrelated = SimpleNamespace(
        event_type="trace.root.completed",
        source="runtime",
        principal_ref=None,
        payload={},
    )
    reader = FakeTraceReader(
        [SimpleNamespace(trace_id="one", last_timestamp=NOW)],
        {"one": [unrelated]},
        {"one": {"trace_id": "one"}},
    )
    assert capture_eval_cases(reader, {"id": "agc.capture-quality", "version": "1"}, "1", 1) == ()
    malformed = _item_event("one", {"raw": SENTINEL})
    reader.events_by_trace["one"] = [malformed]
    with pytest.raises(ValueError, match="capture_eval_trace_invalid"):
        capture_eval_cases(reader, {"id": "agc.capture-quality", "version": "1"}, "1", 1)


@pytest.mark.parametrize("maximum", (0, 101, True))
def test_case_builder_rejects_out_of_range_limits(maximum) -> None:
    with pytest.raises(ValueError, match="capture_eval_case_request_invalid"):
        capture_eval_cases(
            FakeTraceReader([], {}, {}),
            {"id": "agc.capture-quality", "version": "1"},
            "1",
            maximum,
        )
