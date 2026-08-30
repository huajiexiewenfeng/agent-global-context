"""Read-only AGC evidence resolution and Trace-to-EvalCase adaptation."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from agc_runtime.capture_capsule import CapsulePolicy
from agc_runtime.capture_eval_evidence import (
    canonical_sha256,
    capture_eval_evidence_content,
)
from agc_runtime.capture_store import CaptureStore
from agc_runtime.paths import MemoryPaths
from agc_runtime.runtime_config import load_runtime_config

_RECEIPT_ID = re.compile(r"^cr_[0-9a-f]{64}$")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_REFERENCE_FIELDS = frozenset(
    {"schema_version", "provider", "kind", "ref", "digest", "version"}
)
_ITEM_FIELDS = frozenset(
    {
        "schema_version",
        "outcome",
        "reason_code",
        "observation_count",
        "filtered_counts",
        "duplicate_suppression_count",
        "token_usage",
        "extractor_version",
        "taxonomy_version",
        "evidence_ref",
    }
)


class TraceReader(Protocol):
    def list_traces(self, limit: int = 20) -> Sequence[object]: ...

    def events(self, trace_id: str) -> Sequence[object]: ...

    def snapshot(self, trace_id: str) -> Mapping[str, Any]: ...


def _valid_reference(value: object) -> bool:
    return (
        isinstance(value, Mapping)
        and frozenset(value) == _REFERENCE_FIELDS
        and value.get("schema_version") == "eval.evidence-ref.v0.1"
        and value.get("provider") == "agc"
        and value.get("kind") == "capture-item"
        and value.get("version") == "1"
        and isinstance(value.get("ref"), str)
        and _RECEIPT_ID.fullmatch(value["ref"]) is not None
        and isinstance(value.get("digest"), str)
        and _DIGEST.fullmatch(value["digest"]) is not None
    )


class AGCCaptureEvidenceResolver:
    def __init__(self, *, paths: MemoryPaths, adapters: Sequence[object]) -> None:
        if not isinstance(paths, MemoryPaths):
            raise ValueError("capture_eval_evidence_unavailable")
        self.paths = paths
        try:
            self.adapters = {
                (descriptor.adapter_id, descriptor.source_root_id): adapter
                for adapter in adapters
                for descriptor in (adapter.describe(),)
            }
            capsule = load_runtime_config(paths).capture.capsule
            self.policy = CapsulePolicy(
                target_token_limit=capsule.target_tokens,
                hard_token_limit=capsule.max_tokens,
            )
        except Exception as error:
            raise ValueError("capture_eval_evidence_unavailable") from error

    def resolve(self, reference: Mapping[str, Any]) -> Mapping[str, Any]:
        if not _valid_reference(reference):
            raise ValueError("capture_eval_reference_invalid")
        try:
            snapshot = CaptureStore(self.paths).read_snapshot()
            if snapshot.integrity_state != "healthy":
                raise ValueError
            receipts = tuple(
                item for item in snapshot.receipts if item.receipt_id == reference["ref"]
            )
            if len(receipts) != 1 or receipts[0].status != "complete":
                raise ValueError
            receipt = receipts[0]
            revisions = tuple(item for item in snapshot.census if item.key == receipt.key)
            if len(revisions) != 1:
                raise ValueError
            observations = tuple(
                sorted(
                    (
                        item
                        for item in snapshot.observations
                        if item.receipt_id == receipt.receipt_id
                    ),
                    key=lambda item: item.ordinal,
                )
            )
            adapter = self.adapters.get((receipt.adapter_id, receipt.source_root_id))
            if adapter is None:
                raise ValueError
            capsule_result = adapter.load_capsule(revisions[0], self.policy)
        except Exception as error:
            raise ValueError("capture_eval_evidence_unavailable") from error
        try:
            changed = (
                capsule_result.capsule_hash != receipt.capsule_hash
                or capsule_result.capsule_schema_version != receipt.capsule_schema_version
            )
        except Exception as error:
            raise ValueError("capture_eval_evidence_unavailable") from error
        if changed:
            raise ValueError("capture_eval_evidence_changed")
        try:
            content = capture_eval_evidence_content(
                capsule_result.capsule,
                receipt,
                observations,
            )
        except Exception as error:
            raise ValueError("capture_eval_evidence_unavailable") from error
        if canonical_sha256(content) != reference["digest"]:
            raise ValueError("capture_eval_evidence_changed")
        return content


def _attribute(value: object, name: str) -> Any:
    if isinstance(value, Mapping):
        return value.get(name)
    return getattr(value, name, None)


def _event_reference(event: object) -> Mapping[str, Any] | None:
    if _attribute(event, "event_type") != "agc.capture.item.completed":
        return None
    if _attribute(event, "source") != "principal":
        return None
    principal = _attribute(event, "principal_ref")
    if (
        _attribute(principal, "id") != "agent-global-context.capture"
        or _attribute(principal, "kind") != "runtime"
    ):
        return None
    payload = _attribute(event, "payload")
    if (
        not isinstance(payload, Mapping)
        or frozenset(payload) != _ITEM_FIELDS
        or payload.get("schema_version") != "agc.capture.item-trace.v1"
    ):
        raise ValueError("capture_eval_trace_invalid")
    reference = payload.get("evidence_ref")
    if not _valid_reference(reference):
        raise ValueError("capture_eval_trace_invalid")
    return dict(reference)


def capture_eval_cases(
    trace_reader: TraceReader,
    profile_ref: Mapping[str, str],
    implementation_version: str,
    max_items: int,
) -> tuple[dict[str, Any], ...]:
    if (
        type(max_items) is not int
        or not 1 <= max_items <= 100
        or not isinstance(profile_ref, Mapping)
        or set(profile_ref) != {"id", "version"}
        or any(not isinstance(profile_ref.get(name), str) or not profile_ref[name] for name in profile_ref)
        or not isinstance(implementation_version, str)
        or not implementation_version
    ):
        raise ValueError("capture_eval_case_request_invalid")
    subject = {
        "principal_ref": {"id": "agent-global-context.capture", "kind": "runtime"},
        "capability": "capture",
        "operation": "observation-quality",
        "implementation_version": implementation_version,
    }
    checked_profile = dict(profile_ref)
    try:
        summaries = tuple(trace_reader.list_traces(limit=1000))
        ordered = sorted(
            summaries,
            key=lambda item: str(_attribute(item, "last_timestamp") or ""),
            reverse=True,
        )
    except Exception as error:
        raise ValueError("capture_eval_trace_invalid") from error
    cases: list[dict[str, Any]] = []
    seen: set[str] = set()
    snapshots: dict[str, Mapping[str, Any]] = {}
    for summary in ordered:
        trace_id = _attribute(summary, "trace_id")
        if not isinstance(trace_id, str) or not trace_id:
            raise ValueError("capture_eval_trace_invalid")
        try:
            events = trace_reader.events(trace_id)
        except Exception as error:
            raise ValueError("capture_eval_trace_invalid") from error
        for event in events:
            reference = _event_reference(event)
            if reference is None:
                continue
            case_id = "evc_" + canonical_sha256(
                {
                    "subject": subject,
                    "profile_ref": checked_profile,
                    "evidence_ref": reference,
                }
            ).removeprefix("sha256:")
            if case_id in seen:
                continue
            if trace_id not in snapshots:
                try:
                    snapshots[trace_id] = trace_reader.snapshot(trace_id)
                except Exception as error:
                    raise ValueError("capture_eval_trace_invalid") from error
            cases.append(
                {
                    "schema_version": "eval.case.v0.1",
                    "case_id": case_id,
                    "subject": subject,
                    "profile_ref": checked_profile,
                    "evidence_refs": [reference],
                    "trace_snapshot": snapshots[trace_id],
                    "reference": None,
                    "metadata": {"sample_reason": "latest-completed-capture-item"},
                }
            )
            seen.add(case_id)
            if len(cases) == max_items:
                return tuple(cases)
    return tuple(cases)


__all__ = ["AGCCaptureEvidenceResolver", "TraceReader", "capture_eval_cases"]
