"""Explicit, isolated read views for committed Capture observations."""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
from typing import Any

from agc_runtime.capture_contracts import CaptureKey
from agc_runtime.capture_store import CaptureSnapshot, CaptureStore
from agc_runtime.paths import MemoryPaths


SEARCH_LIMIT_DEFAULT = 20
SEARCH_LIMIT_MAX = 100
SEARCH_FILTERS = frozenset({"time", "task", "project", "category", "kind", "scope", "state", "sensitivity"})
_FILTER_ENUMS = {
    "category": frozenset({"personal_growth", "research", "learning", "project", "work"}),
    "kind": frozenset({"identity", "principle", "preference", "interest", "capability", "goal", "pattern", "context"}),
    "state": frozenset({"collected"}),
    "sensitivity": frozenset({"normal", "personal"}),
}


class CaptureReadError(LookupError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _paths(value: MemoryPaths | Path) -> MemoryPaths:
    return value if isinstance(value, MemoryPaths) else MemoryPaths.from_root(value)


def _key_id(key: CaptureKey) -> tuple[str, str, str, str]:
    return (key.adapter_id, key.source_root_id, key.task_id, key.revision_id)


def _ratio(numerator: int, denominator: int) -> float | str:
    return "not_applicable" if denominator == 0 else numerator / denominator


def _overview(paths: MemoryPaths) -> dict[str, Any]:
    snapshot = CaptureStore(paths).read_snapshot()
    receipts = snapshot.receipts
    census = {_key_id(item.key) for item in snapshot.census}
    tombstones = {_key_id(item.capture_key) for item in snapshot.tombstones}
    receipt_keys = {_key_id(item.key) for item in receipts}
    statuses = {status: sum(item.status == status for item in receipts) for status in (
        "discovered", "queued", "extracting", "complete", "retryable", "deferred_budget", "failed", "quarantined", "excluded", "coalesced"
    )}
    eligible = {key for key in census if not any(_key_id(item.key) == key and item.status in {"excluded", "coalesced"} for item in receipts)}
    complete = sum(_key_id(item.key) in eligible and item.status == "complete" for item in receipts)
    inspection_denominator = len(eligible - tombstones)
    unkeyed = len(snapshot.source_quarantines)
    degraded = bool(snapshot.diagnostics or snapshot.source_conflict_count or unkeyed)
    return {
        "coverage_unit": "ratio_0_to_1",
        "census_key_count": len(census),
        "receipt_key_count": len(receipt_keys),
        "suppression_tombstone_key_count": len(tombstones),
        "accounting_coverage": _ratio(len((receipt_keys | tombstones) & census), len(census)),
        "inspection_eligible_count": len(eligible),
        "inspection_denominator": inspection_denominator,
        "complete_count": complete,
        "inspection_completion": _ratio(complete, inspection_denominator),
        "silent_loss": len(census - (receipt_keys | tombstones)),
        "unresolved": sum(statuses[item] for item in ("discovered", "queued", "extracting", "retryable", "deferred_budget")),
        "parked": sum(statuses[item] for item in ("failed", "quarantined")),
        "status_counts": statuses,
        "source_health": "degraded" if degraded else "healthy",
        "unkeyed_source_quarantine_count": unkeyed,
        "source_coverage_complete": not degraded and len(census) > 0 and len((receipt_keys | tombstones) & census) == len(census),
        "integrity": {
            "state": snapshot.integrity_state,
            "diagnostics": [item.to_mapping() for item in snapshot.diagnostics],
        },
    }


def capture_overview(value: MemoryPaths | Path) -> dict[str, Any]:
    return _overview(_paths(value))


def _observation_mapping(item: Any) -> dict[str, Any]:
    # Explicit Capture action intentionally omits hash, extractor raw metadata,
    # journal/staging state, and any non-essential source data.
    return {
        "observation_id": item.observation_id, "receipt_id": item.receipt_id,
        "statement": item.statement, "assertion": dict(item.assertion),
        "primary_category": item.primary_category, "kind": item.kind,
        "scopes": list(item.scopes), "project_scope": item.project_scope,
        "confidence": item.confidence, "sensitivity": item.sensitivity,
        "signal_type": item.signal_type, "observed_at": item.observed_at,
        "captured_at": item.captured_at, "processing_state": item.processing_state,
        "source": {key: item.source.get(key) for key in ("adapter_id", "source_root_id", "task_id", "revision_id")},
    }


def _utc_datetime(value: Any, *, field: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z") or value == "Z":
        raise ValueError(f"{field} must be a UTC timestamp ending in Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise ValueError(f"{field} must be a UTC timestamp ending in Z") from error
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise ValueError(f"{field} must be a UTC timestamp ending in Z")
    return parsed


def _normalize_filters(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("filters must be a mapping")
    unknown = sorted(set(value) - SEARCH_FILTERS)
    if unknown:
        raise ValueError(f"unsupported capture search filter: {', '.join(unknown)}")
    normalized: dict[str, Any] = {}
    for name in SEARCH_FILTERS - {"time"}:
        if name not in value:
            continue
        items = value[name]
        if not isinstance(items, list) or not items or any(type(item) is not str or not item for item in items):
            raise ValueError(f"filters.{name} must be a non-empty list of non-empty strings")
        choices = _FILTER_ENUMS.get(name)
        if choices is not None and any(item not in choices for item in items):
            raise ValueError(f"filters.{name} contains an unsupported value")
        normalized[name] = sorted(set(items))
    if "time" in value:
        time_filter = value["time"]
        if isinstance(time_filter, list):
            if not time_filter:
                raise ValueError("filters.time must not be empty")
            for item in time_filter:
                _utc_datetime(item, field="filters.time")
            normalized["time"] = sorted(set(time_filter))
        elif isinstance(time_filter, dict):
            if not time_filter or set(time_filter) - {"from", "to"}:
                raise ValueError("filters.time supports only from and to")
            parsed = {
                name: _utc_datetime(item, field=f"filters.time.{name}")
                for name, item in time_filter.items()
            }
            if "from" in parsed and "to" in parsed and parsed["from"] > parsed["to"]:
                raise ValueError("filters.time.from must not be after filters.time.to")
            normalized["time"] = {name: time_filter[name] for name in sorted(time_filter)}
        else:
            raise ValueError("filters.time must be a list or mapping")
    return normalized


def _filter_values(filters: dict[str, Any], name: str) -> set[str] | None:
    value = filters.get(name)
    if value is None:
        return None
    return set(value)


def _matches(item: Any, filters: dict[str, Any]) -> bool:
    mapping = {"task": item.source.get("task_id"), "project": item.project_scope, "category": item.primary_category, "kind": item.kind, "state": item.processing_state, "sensitivity": item.sensitivity}
    for name, actual in mapping.items():
        values = _filter_values(filters, name)
        if values is not None and actual not in values:
            return False
    scopes = _filter_values(filters, "scope")
    if scopes is not None and not scopes.intersection(item.scopes):
        return False
    time_filter = filters.get("time")
    if time_filter is not None:
        if isinstance(time_filter, list):
            if item.captured_at not in set(time_filter):
                return False
        else:
            captured_at = _utc_datetime(item.captured_at, field="observation.captured_at")
            if "from" in time_filter and captured_at < _utc_datetime(time_filter["from"], field="filters.time.from"):
                return False
            if "to" in time_filter and captured_at > _utc_datetime(time_filter["to"], field="filters.time.to"):
                return False
    return True


def _query_digest(
    filters: dict[str, Any], limit: int, include_reviewed: bool
) -> str:
    payload = json.dumps(
        {
            "filters": filters,
            "include_reviewed": include_reviewed,
            "limit": limit,
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def capture_search(value: MemoryPaths | Path, request: dict[str, Any]) -> dict[str, Any]:
    filters = _normalize_filters(request.get("filters", {}))
    limit = request.get("limit", SEARCH_LIMIT_DEFAULT)
    if type(limit) is not int or not 1 <= limit <= SEARCH_LIMIT_MAX:
        raise ValueError("limit must be between 1 and 100")
    include_reviewed = request.get("include_reviewed", False)
    if type(include_reviewed) is not bool:
        raise ValueError("include_reviewed must be a boolean")
    store = CaptureStore(_paths(value))
    query_digest = _query_digest(filters, limit, include_reviewed)
    cursor = store.decode_cursor(request.get("cursor"), query_digest=query_digest)
    snapshot = store.read_snapshot()
    reviewed_ids = {item.observation_id for item in snapshot.review_receipts}
    items = [
        item for item in snapshot.observations
        if _matches(item, filters)
        and (include_reviewed or item.observation_id not in reviewed_ids)
    ]
    items.sort(key=lambda item: (-_utc_datetime(item.captured_at, field="observation.captured_at").timestamp(), item.observation_id))
    if cursor is not None:
        index = next((index for index, item in enumerate(items) if (item.captured_at, item.observation_id) == cursor), None)
        if index is None:
            raise ValueError("cursor does not identify a visible observation")
        items = items[index + 1:]
    page = items[:limit]
    return {
        "results": [_observation_mapping(item) for item in page],
        "returned_count": len(page),
        "next_cursor": store.encode_cursor(query_digest=query_digest, captured_at=page[-1].captured_at, observation_id=page[-1].observation_id) if len(items) > len(page) else None,
        "integrity": {
            "state": snapshot.integrity_state,
            "diagnostics": [item.to_mapping() for item in snapshot.diagnostics],
        },
    }


def capture_get(value: MemoryPaths | Path, request: dict[str, Any]) -> dict[str, Any]:
    observation_id = request.get("observation_id")
    receipt_id = request.get("receipt_id")
    if (observation_id is None) == (receipt_id is None) or any(not isinstance(item, str) or not item for item in (observation_id, receipt_id) if item is not None):
        raise ValueError("provide exactly one non-empty observation_id or receipt_id")
    snapshot = CaptureStore(_paths(value)).read_snapshot()
    if observation_id is not None:
        reviews = {item.observation_id: item for item in snapshot.review_receipts}
        for item in snapshot.observations:
            if item.observation_id == observation_id:
                review = reviews.get(item.observation_id)
                return {
                    "observation": _observation_mapping(item),
                    "review": review.to_mapping() if review is not None else None,
                }
        if observation_id in snapshot.unavailable_ids:
            raise CaptureReadError("capture_integrity_degraded")
        raise CaptureReadError("capture_not_found")
    receipt = next((item for item in snapshot.receipts if item.receipt_id == receipt_id and item.status == "complete"), None)
    if receipt is None:
        if receipt_id in snapshot.unavailable_ids:
            raise CaptureReadError("capture_integrity_degraded")
        raise CaptureReadError("capture_not_found")
    observations = tuple(item for item in snapshot.observations if item.receipt_id == receipt_id)
    if len(observations) != receipt.observation_count:
        raise CaptureReadError("capture_integrity_degraded")
    return {"receipt": {"receipt_id": receipt.receipt_id, "status": receipt.status, "task_id": receipt.task_id, "revision_id": receipt.revision_id, "source_root_id": receipt.source_root_id, "settled_at": receipt.settled_at, "observation_count": receipt.observation_count}, "observations": [_observation_mapping(item) for item in observations]}
