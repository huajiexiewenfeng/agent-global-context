"""Explicit, isolated read views for committed Capture observations."""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import Any

from agc_runtime.capture_contracts import CaptureKey, CaptureSuppressionTombstone, SourceQuarantine
from agc_runtime.capture_store import CaptureStore
from agc_runtime.capture_transaction import read_json
from agc_runtime.paths import MemoryPaths


SEARCH_LIMIT_DEFAULT = 20
SEARCH_LIMIT_MAX = 100
SEARCH_FILTERS = frozenset({"time", "task", "project", "category", "kind", "scope", "state", "sensitivity"})
_CURSOR_VERSION = 1


def _paths(value: MemoryPaths | Path) -> MemoryPaths:
    return value if isinstance(value, MemoryPaths) else MemoryPaths.from_root(value)


def _key_id(key: CaptureKey) -> tuple[str, str, str, str]:
    return (key.adapter_id, key.source_root_id, key.task_id, key.revision_id)


def _capture_key(value: Any) -> CaptureKey:
    return CaptureKey.from_mapping(value)


def _keys_in(directory: Path, *, tombstones: bool = False) -> set[tuple[str, str, str, str]]:
    if not directory.exists():
        return set()
    keys: set[tuple[str, str, str, str]] = set()
    for path in sorted(directory.glob("*.json")):
        value = read_json(path)
        if tombstones:
            keys.add(_key_id(CaptureSuppressionTombstone.from_mapping(value).capture_key))
        else:
            keys.add(_key_id(_capture_key(value["capture_key"])))
    return keys


def _census_keys(paths: MemoryPaths) -> set[tuple[str, str, str, str]]:
    return _keys_in(paths.capture.census)


def _unkeyed_quarantine_count(paths: MemoryPaths) -> int:
    if not paths.capture.quarantines.exists():
        return 0
    count = 0
    for path in sorted(paths.capture.quarantines.glob("*.json")):
        value = read_json(path)
        try:
            SourceQuarantine.from_mapping(value)
        except ValueError:
            # Transaction corruption diagnostics are not Source Quarantines.
            continue
        count += 1
    return count


def _ratio(numerator: int, denominator: int) -> float | str:
    return "not_applicable" if denominator == 0 else numerator / denominator


def _overview(paths: MemoryPaths) -> dict[str, Any]:
    store = CaptureStore(paths)
    receipts = store.iter_receipts()
    census = _census_keys(paths)
    tombstones = _keys_in(paths.capture.tombstones, tombstones=True)
    receipt_keys = {_key_id(item.key) for item in receipts}
    statuses = {status: sum(item.status == status for item in receipts) for status in (
        "discovered", "queued", "extracting", "complete", "retryable", "deferred_budget", "failed", "quarantined", "excluded", "coalesced"
    )}
    eligible = {key for key in census if not any(_key_id(item.key) == key and item.status in {"excluded", "coalesced"} for item in receipts)}
    complete = sum(_key_id(item.key) in eligible and item.status == "complete" for item in receipts)
    inspection_denominator = len(eligible - tombstones)
    unkeyed = _unkeyed_quarantine_count(paths)
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
        "source_health": "degraded" if unkeyed or any(store.source_health(item.adapter_id, item.source_root_id) == "degraded" for item in receipts) else "healthy",
        "unkeyed_source_quarantine_count": unkeyed,
        "source_coverage_complete": not unkeyed and len(census) > 0 and len((receipt_keys | tombstones) & census) == len(census),
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


def _filter_values(filters: dict[str, Any], name: str) -> set[str] | None:
    value = filters.get(name)
    if value is None:
        return None
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"filters.{name} must be a list of strings")
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
            if any(not isinstance(item, str) for item in time_filter) or item.captured_at not in set(time_filter):
                return False
        elif isinstance(time_filter, dict):
            if set(time_filter) - {"from", "to"} or not time_filter:
                raise ValueError("filters.time supports only from and to")
            if any(not isinstance(item, str) for item in time_filter.values()):
                raise ValueError("filters.time bounds must be strings")
            if "from" in time_filter and item.captured_at < time_filter["from"]:
                return False
            if "to" in time_filter and item.captured_at > time_filter["to"]:
                return False
        else:
            raise ValueError("filters.time must be a list or mapping")
    return True


def _encode_cursor(captured_at: str, observation_id: str) -> str:
    payload = json.dumps({"v": _CURSOR_VERSION, "captured_at": captured_at, "observation_id": observation_id}, separators=(",", ":"), sort_keys=True).encode("utf-8")
    signature = hashlib.sha256(payload).digest()
    return base64.urlsafe_b64encode(payload + signature).decode("ascii").rstrip("=")


def _decode_cursor(cursor: Any) -> tuple[str, str] | None:
    if cursor is None:
        return None
    if not isinstance(cursor, str) or not cursor:
        raise ValueError("cursor must be an opaque string")
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        payload, signature = raw[:-32], raw[-32:]
        if hashlib.sha256(payload).digest() != signature:
            raise ValueError
        value = json.loads(payload)
        if set(value) != {"v", "captured_at", "observation_id"} or value["v"] != _CURSOR_VERSION or not isinstance(value["captured_at"], str) or not isinstance(value["observation_id"], str):
            raise ValueError
        return value["captured_at"], value["observation_id"]
    except (ValueError, TypeError, json.JSONDecodeError) as error:
        raise ValueError("invalid capture cursor") from error


def capture_search(value: MemoryPaths | Path, request: dict[str, Any]) -> dict[str, Any]:
    filters = request.get("filters", {})
    if not isinstance(filters, dict):
        raise ValueError("filters must be a mapping")
    unknown = sorted(set(filters) - SEARCH_FILTERS)
    if unknown:
        raise ValueError(f"unsupported capture search filter: {', '.join(unknown)}")
    limit = request.get("limit", SEARCH_LIMIT_DEFAULT)
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= SEARCH_LIMIT_MAX:
        raise ValueError("limit must be between 1 and 100")
    cursor = _decode_cursor(request.get("cursor"))
    items = [
        item for item in CaptureStore(_paths(value)).iter_visible_observations()
        if _matches(item, filters)
    ]
    items.sort(key=lambda item: item.observation_id)
    items.sort(key=lambda item: item.captured_at, reverse=True)
    if cursor is not None:
        index = next((index for index, item in enumerate(items) if (item.captured_at, item.observation_id) == cursor), None)
        if index is None:
            raise ValueError("cursor does not identify a visible observation")
        items = items[index + 1:]
    page = items[:limit]
    return {"results": [_observation_mapping(item) for item in page], "returned_count": len(page), "next_cursor": _encode_cursor(page[-1].captured_at, page[-1].observation_id) if len(items) > len(page) else None}


def capture_get(value: MemoryPaths | Path, request: dict[str, Any]) -> dict[str, Any]:
    observation_id = request.get("observation_id")
    receipt_id = request.get("receipt_id")
    if (observation_id is None) == (receipt_id is None) or any(not isinstance(item, str) or not item for item in (observation_id, receipt_id) if item is not None):
        raise ValueError("provide exactly one non-empty observation_id or receipt_id")
    store = CaptureStore(_paths(value))
    if observation_id is not None:
        for item in store.iter_visible_observations():
            if item.observation_id == observation_id:
                return {"observation": _observation_mapping(item)}
        raise LookupError("capture observation not found")
    receipt = store.read_receipt(receipt_id)
    observations = store.visible_observations(receipt_id)
    if receipt.status != "complete" or len(observations) != receipt.observation_count:
        raise LookupError("capture receipt is not visible")
    return {"receipt": {"receipt_id": receipt.receipt_id, "status": receipt.status, "task_id": receipt.task_id, "revision_id": receipt.revision_id, "source_root_id": receipt.source_root_id, "settled_at": receipt.settled_at, "observation_count": receipt.observation_count}, "observations": [_observation_mapping(item) for item in observations]}
