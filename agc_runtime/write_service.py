import hashlib
import json
from collections import Counter
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from agc_runtime.catalog import rebuild_catalog
from agc_runtime.contracts import (
    EvidenceSummary,
    ObservationEnvelope,
    SourceKey,
    ToolResponse,
)
from agc_runtime.locking import root_write_lock
from agc_runtime.models import MemoryItem
from agc_runtime.paths import MemoryPaths
from agc_runtime.policy import PolicyDecision, evaluate_observation
from agc_runtime.schema import validate_memory_item
from agc_runtime.store import MemoryStore, MutationResult
from agc_runtime.utf8_io import atomic_write_text, strict_read_text


def _response(
    action: str,
    status: str,
    code: str,
    *,
    data: dict[str, Any] | None = None,
) -> ToolResponse:
    return ToolResponse(
        tool="agc.write",
        action=action,
        status=status,
        data={"code": code, **(data or {})},
    )


def _source_key(envelope: ObservationEnvelope) -> SourceKey:
    return SourceKey(
        envelope.source.ref,
        envelope.source.revision,
        envelope.source.content_hash,
    )


def _candidate_path(paths: MemoryPaths, candidate_id: str) -> Path:
    digest = hashlib.sha256(candidate_id.encode("utf-8")).hexdigest()
    return paths.candidates / "ordinary" / f"{digest}.json"


def _read_candidate(path: Path, candidate_id: str) -> dict[str, Any]:
    if not path.exists():
        return {
            "schema_version": 2,
            "candidate_id": candidate_id,
            "candidate_status": "candidate",
            "sources": [],
        }
    value = json.loads(strict_read_text(path))
    if (
        not isinstance(value, dict)
        or value.get("schema_version") != 2
        or value.get("candidate_id") != candidate_id
        or not isinstance(value.get("sources"), list)
    ):
        raise ValueError(f"invalid candidate record: {candidate_id}")
    return value


def _same_source(entry: dict[str, Any], envelope: ObservationEnvelope) -> bool:
    source = envelope.source
    return (
        entry.get("ref") == source.ref
        and entry.get("revision") == source.revision
        and entry.get("content_hash") == source.content_hash
    )


def _evidence_summary(sources: list[dict[str, Any]]) -> EvidenceSummary:
    observed_dates = [
        datetime.fromisoformat(source["observed_at"].replace("Z", "+00:00")).date()
        for source in sources
    ]
    span = (max(observed_dates) - min(observed_dates)).days if observed_dates else 0
    return EvidenceSummary(
        count=len(sources),
        distinct_sessions=len({source["ref"] for source in sources}),
        time_span_days=span,
    )


def _record_candidate(
    paths: MemoryPaths,
    envelope: ObservationEnvelope,
) -> tuple[PolicyDecision, EvidenceSummary]:
    path = _candidate_path(paths, envelope.observation_id)
    with root_write_lock(paths):
        candidate = _read_candidate(path, envelope.observation_id)
        sources = candidate["sources"]
        if not any(_same_source(entry, envelope) for entry in sources):
            sources.append(
                {
                    "ref": envelope.source.ref,
                    "revision": envelope.source.revision,
                    "content_hash": envelope.source.content_hash,
                    "observed_at": envelope.source.observed_at,
                }
            )
        evidence = _evidence_summary(sources)
        evaluated = replace(envelope, evidence=evidence)
        decision = evaluate_observation(evaluated)
        candidate.update(
            {
                "candidate_status": decision.persistable_metadata.get(
                    "candidate_status", "candidate"
                ),
                "kind": envelope.proposal.kind,
                "scopes": list(envelope.proposal.scopes),
                "temporal_type": envelope.proposal.temporal_type,
                "sensitivity": envelope.proposal.sensitivity,
                "rationale": envelope.proposal.rationale,
                "sources": sources,
            }
        )
        atomic_write_text(
            path,
            json.dumps(candidate, ensure_ascii=False, sort_keys=True, indent=2)
            + "\n",
        )
    return decision, evidence


def _validate_item_matches_observation(
    item: MemoryItem, envelope: ObservationEnvelope
) -> None:
    proposal = envelope.proposal
    mismatches = []
    if item.kind != proposal.kind:
        mismatches.append("kind")
    if item.temporal.type != proposal.temporal_type:
        mismatches.append("temporal_type")
    if item.sensitivity != proposal.sensitivity:
        mismatches.append("sensitivity")
    if item.confidence.level != proposal.requested_confidence:
        mismatches.append("requested_confidence")
    if set(item.recall.scopes) != set(proposal.scopes):
        mismatches.append("scopes")
    if mismatches:
        raise ValueError(
            "memory_markdown conflicts with observation: "
            + ", ".join(mismatches)
        )


def _mutation_response(
    action: str, result: MutationResult, item: MemoryItem | None = None
) -> ToolResponse:
    data: dict[str, Any] = {
        "memory_id": result.object_id,
        "created": result.created,
        "independent_evidence_count": result.independent_evidence_count,
    }
    if item is not None:
        data.update(
            {
                "lifecycle": item.lifecycle.status,
                "confidence": item.confidence.level,
            }
        )
    return _response(action, result.status, result.code, data=data)


def _refresh_catalog_after_formal_memory(
    paths: MemoryPaths, response: ToolResponse
) -> ToolResponse:
    memory_id = response.data.get("memory_id")
    if response.status != "accepted" or not isinstance(memory_id, str):
        return response
    try:
        rebuild_catalog(paths)
    except (KeyError, OSError, RuntimeError, TypeError, ValueError):
        return replace(
            response,
            warnings=(*response.warnings, "catalog_refresh_failed"),
        )
    return response


def _load_observation(request: dict[str, Any]) -> ObservationEnvelope:
    if "observation" not in request:
        raise ValueError("observation is required")
    return ObservationEnvelope.from_mapping(request["observation"])


def _load_memory_markdown(request: dict[str, Any]) -> MemoryItem:
    markdown = request.get("memory_markdown")
    if not isinstance(markdown, str) or not markdown:
        raise ValueError("memory_markdown is required")
    item = MemoryItem.from_markdown(markdown)
    validate_memory_item(item)
    return item


def _decision_response(
    action: str,
    decision: PolicyDecision,
    *,
    extra: dict[str, Any] | None = None,
) -> ToolResponse:
    return _response(
        action,
        decision.status,
        decision.code,
        data=extra,
    )


def _handle_observe(paths: MemoryPaths, request: dict[str, Any]) -> ToolResponse:
    envelope = _load_observation(request)
    initial = evaluate_observation(envelope)
    if initial.status == "rejected_policy":
        return _decision_response("observe", initial)
    if initial.code == "match_memory_id_required":
        return _decision_response("observe", initial)
    if initial.code == "ignored":
        return _decision_response("observe", initial)

    if (
        envelope.assertion.mode == "behavior_observed"
        or initial.status == "deferred"
        or envelope.proposal.disposition == "need_more_evidence"
    ):
        decision, evidence = _record_candidate(paths, envelope)
        return _decision_response(
            "observe",
            decision,
            extra={
                "candidate_id": envelope.observation_id,
                "candidate_status": decision.persistable_metadata.get(
                    "candidate_status", "candidate"
                ),
                "evidence_count": evidence.count,
                "distinct_sessions": evidence.distinct_sessions,
                "time_span_days": evidence.time_span_days,
            },
        )

    store = MemoryStore(paths)
    disposition = envelope.proposal.disposition
    match_memory_id = envelope.proposal.match_memory_id
    source = _source_key(envelope)

    if disposition == "new":
        item = _load_memory_markdown(request)
        _validate_item_matches_observation(item, envelope)
        return _mutation_response(
            "observe", store.create_memory(item, source), item
        )
    if disposition == "reinforce":
        result = store.add_evidence(
            match_memory_id or "", source, envelope.source.observed_at
        )
        return _mutation_response(
            "observe", result, store.get_memory(match_memory_id or "")
        )
    if disposition == "update":
        item = _load_memory_markdown(request)
        if item.id != match_memory_id:
            raise ValueError("memory_markdown id must match match_memory_id")
        _validate_item_matches_observation(item, envelope)
        result = store.replace_memory(
            match_memory_id or "",
            item,
            source,
            envelope.source.observed_at,
        )
        return _mutation_response("observe", result, item)
    if disposition == "conflict":
        current = store.get_memory(match_memory_id or "")
        if current.recall.decision_impact == "high":
            return _response(
                "observe",
                "needs_adjudication",
                "high_impact_conflict",
                data={
                    "memory_id": current.id,
                    "lifecycle": current.lifecycle.status,
                },
            )
        result = store.transition_memory(
            current.id,
            "challenged",
            source,
            envelope.source.observed_at,
            action="memory_challenged",
        )
        return _mutation_response(
            "observe", result, store.get_memory(current.id)
        )
    raise ValueError(f"unsupported observation disposition: {disposition}")


def _handle_observe_batch(
    paths: MemoryPaths, request: dict[str, Any]
) -> ToolResponse:
    items = request.get("items")
    if not isinstance(items, list):
        raise ValueError("items must be a list")
    results: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    for item in items:
        if not isinstance(item, dict):
            result = ToolResponse(
                tool="agc.write",
                action="observe",
                status="failed",
                error={
                    "code": "invalid_request",
                    "message": "batch item must be a mapping",
                },
            )
        else:
            nested = {**item, "action": "observe"}
            result = dispatch_write(paths, nested)
        counts[result.status] += 1
        results.append(result.to_dict())
    return _response(
        "observe_batch",
        "accepted",
        "batch_evaluated",
        data={"status_counts": dict(counts), "results": results},
    )


def _handle_propose(paths: MemoryPaths, request: dict[str, Any]) -> ToolResponse:
    envelope = _load_observation(request)
    decision = evaluate_observation(envelope)
    if decision.status == "rejected_policy":
        return _decision_response("propose", decision)
    decision, evidence = _record_candidate(paths, envelope)
    return _response(
        "propose",
        "deferred",
        "proposal_recorded",
        data={
            "candidate_id": envelope.observation_id,
            "candidate_status": decision.persistable_metadata.get(
                "candidate_status", "candidate"
            ),
            "evidence_count": evidence.count,
        },
    )


def _handle_confirm(paths: MemoryPaths, request: dict[str, Any]) -> ToolResponse:
    nested = {**request, "action": "observe"}
    observation = dict(nested.get("observation", {}))
    proposal = dict(observation.get("proposal", {}))
    proposal["disposition"] = "new"
    proposal["requested_confidence"] = "confirmed"
    observation["proposal"] = proposal
    nested["observation"] = observation
    response = _handle_observe(paths, nested)
    return replace(response, action="confirm")


def _handle_update(paths: MemoryPaths, request: dict[str, Any]) -> ToolResponse:
    nested = {**request, "action": "observe"}
    observation = dict(nested.get("observation", {}))
    proposal = dict(observation.get("proposal", {}))
    proposal["disposition"] = "update"
    observation["proposal"] = proposal
    nested["observation"] = observation
    response = _handle_observe(paths, nested)
    return replace(response, action="update")


def _handle_transition(
    paths: MemoryPaths,
    request: dict[str, Any],
    *,
    action: str,
    new_status: str,
) -> ToolResponse:
    envelope = _load_observation(request)
    memory_id = request.get("memory_id") or envelope.proposal.match_memory_id
    if not isinstance(memory_id, str) or not memory_id:
        raise ValueError("memory_id is required")
    if envelope.proposal.match_memory_id != memory_id:
        raise ValueError("memory_id must match proposal.match_memory_id")
    decision = evaluate_observation(envelope)
    if decision.status in {"rejected_policy", "needs_adjudication"}:
        return _decision_response(action, decision)
    store = MemoryStore(paths)
    result = store.transition_memory(
        memory_id,
        new_status,
        _source_key(envelope),
        envelope.source.observed_at,
        action=f"memory_{new_status}",
    )
    return _mutation_response(action, result, store.get_memory(memory_id))


def _handle_supersede(
    paths: MemoryPaths, request: dict[str, Any]
) -> ToolResponse:
    return _handle_transition(
        paths, request, action="supersede", new_status="superseded"
    )


def _handle_archive(paths: MemoryPaths, request: dict[str, Any]) -> ToolResponse:
    return _handle_transition(
        paths, request, action="archive", new_status="historical"
    )


def _handle_reject(paths: MemoryPaths, request: dict[str, Any]) -> ToolResponse:
    candidate_id = request.get("candidate_id")
    if not isinstance(candidate_id, str) or not candidate_id:
        raise ValueError("candidate_id is required")
    path = _candidate_path(paths, candidate_id)
    with root_write_lock(paths):
        existed = path.exists()
        path.unlink(missing_ok=True)
    return _response(
        "reject",
        "accepted",
        "candidate_rejected" if existed else "candidate_not_found",
        data={"candidate_id": candidate_id, "removed": existed},
    )


def _handle_forget(paths: MemoryPaths, request: dict[str, Any]) -> ToolResponse:
    from agc_runtime.forget_service import forget

    return forget(paths, request)


def _handle_capture_forget(paths: MemoryPaths, request: dict[str, Any]) -> ToolResponse:
    from agc_runtime.capture_forget_service import capture_forget

    return capture_forget(paths, request)


Handler = Callable[[MemoryPaths, dict[str, Any]], ToolResponse]
_HANDLERS: dict[str, Handler] = {
    "observe": _handle_observe,
    "observe_batch": _handle_observe_batch,
    "propose": _handle_propose,
    "confirm": _handle_confirm,
    "update": _handle_update,
    "supersede": _handle_supersede,
    "archive": _handle_archive,
    "reject": _handle_reject,
    "forget": _handle_forget,
    "capture_forget": _handle_capture_forget,
}


def dispatch_write(paths: MemoryPaths, request: Any) -> ToolResponse:
    if not isinstance(request, dict):
        return ToolResponse(
            tool="agc.write",
            action="",
            status="failed",
            error={
                "code": "invalid_request",
                "message": "request must be a mapping",
            },
        )
    action = request.get("action")
    if not isinstance(action, str) or action not in _HANDLERS:
        return ToolResponse(
            tool="agc.write",
            action=action if isinstance(action, str) else "",
            status="failed",
            error={
                "code": "invalid_action",
                "message": "unsupported agc.write action",
            },
        )
    try:
        response = _HANDLERS[action](paths, request)
        if action in {"forget", "capture_forget"}:
            return response
        return _refresh_catalog_after_formal_memory(paths, response)
    except (ValueError, KeyError, TypeError) as error:
        return ToolResponse(
            tool="agc.write",
            action=action,
            status="failed",
            error={"code": "invalid_request", "message": str(error)},
        )
    except OSError as error:
        return ToolResponse(
            tool="agc.write",
            action=action,
            status="failed",
            error={"code": "write_failed", "message": str(error)},
        )
