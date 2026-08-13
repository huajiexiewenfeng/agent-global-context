import json
from typing import Any

from agc_runtime.catalog import catalog_counts, load_catalog
from agc_runtime.capture_read_service import CaptureReadError, capture_get, capture_overview, capture_search
from agc_runtime.contracts import ToolResponse
from agc_runtime.models import MemoryItem
from agc_runtime.paths import MemoryPaths
from agc_runtime.response_budget import _with_estimate, fit_overview_response
from agc_runtime.runtime_config import load_runtime_config
from agc_runtime.store import MemoryStore
from agc_runtime.utf8_io import strict_read_text


SEARCH_LIMIT_MAX = 100
SEARCH_FILTERS = frozenset(
    {
        "kind",
        "scopes",
        "decision_impact",
        "sensitivity",
        "exposure",
        "confidence",
    }
)


def _failed(action: str, code: str, message: str) -> ToolResponse:
    return ToolResponse(
        tool="agc.read",
        action=action,
        status="failed",
        error={"code": code, "message": message},
    )


def _handle_overview(paths: MemoryPaths, _request: dict[str, Any]) -> ToolResponse:
    config = load_runtime_config(paths)
    catalog = load_catalog(paths)
    active_cards = [
        card for card in catalog["cards"] if card["lifecycle"] == "active"
    ]
    counts = catalog_counts({"cards": active_cards})
    data: dict[str, Any] = {
        "memory_count": catalog["memory_count"],
        "counts": {
            "by_kind": counts["by_kind"],
            "by_scope": counts["by_scope"],
        },
        "high_impact_scopes": counts["high_impact_scopes"],
        "available_card_count": sum(
            card["exposure"] in {"core_card", "scoped_card"}
            for card in active_cards
        ),
        "cards": [],
    }
    eligible = [
        card
        for card in catalog["cards"]
        if card["lifecycle"] == "active"
        and card["exposure"] in {"core_card", "scoped_card"}
    ]
    data["cards"] = eligible
    return fit_overview_response(
        ToolResponse(
            tool="agc.read",
            action="overview",
            status="accepted",
            data=data,
        ),
        budget=config.recall.overview_token_budget,
    )


def _as_filter_values(filters: dict[str, Any], name: str) -> set[str] | None:
    value = filters.get(name)
    if value is None:
        return None
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"filters.{name} must be a list of strings")
    return set(value)


def _matches_filters(card: dict[str, Any], filters: dict[str, Any]) -> bool:
    scalar_fields = {
        "kind": "kind",
        "decision_impact": "decision_impact",
        "sensitivity": "sensitivity",
        "exposure": "exposure",
        "confidence": "confidence",
    }
    for filter_name, card_name in scalar_fields.items():
        allowed = _as_filter_values(filters, filter_name)
        if allowed is not None and card[card_name] not in allowed:
            return False
    scopes = _as_filter_values(filters, "scopes")
    if scopes is not None and not scopes.intersection(card["scopes"]):
        return False
    return True


def _handle_search(paths: MemoryPaths, request: dict[str, Any]) -> ToolResponse:
    filters = request.get("filters", {})
    if not isinstance(filters, dict):
        raise ValueError("filters must be a mapping")
    unknown_filters = sorted(set(filters) - SEARCH_FILTERS)
    if unknown_filters:
        raise ValueError(
            f"unsupported search filter: {', '.join(unknown_filters)}"
        )
    limit = request.get("limit", 20)
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
        raise ValueError(f"limit must be between 1 and {SEARCH_LIMIT_MAX}")
    query = request.get("query")
    if query is not None and (not isinstance(query, str) or not query):
        raise ValueError("query must be a non-empty string")

    load_runtime_config(paths)
    catalog = load_catalog(paths)
    filtered = []
    query_folded = query.casefold() if query else None
    for card in catalog["cards"]:
        if card["lifecycle"] != "active":
            continue
        if not _matches_filters(card, filters):
            continue
        if query_folded and query_folded not in (
            card["id"] + " " + card["memory_card"]
        ).casefold():
            continue
        filtered.append(card)
        if len(filtered) == limit:
            break
    return _with_estimate(
        ToolResponse(
            tool="agc.read",
            action="search",
            status="accepted",
            data={
                "results": filtered,
                "items": filtered,
                "returned_count": len(filtered),
            },
        )
    )


def _required_id(request: dict[str, Any]) -> str:
    memory_id = request.get("id")
    if not isinstance(memory_id, str) or not memory_id:
        raise LookupError("id_required")
    return memory_id


def _item_mapping(item: MemoryItem) -> dict[str, Any]:
    return {
        "id": item.id,
        "kind": item.kind,
        "subkind": item.subkind,
        "lifecycle": item.lifecycle.status,
        "confidence": item.confidence.level,
        "temporal": {
            "type": item.temporal.type,
            "valid_from": item.temporal.valid_from,
            "last_observed": item.temporal.last_observed,
            "review_after": item.temporal.review_after,
        },
        "recall": {
            "prior": item.recall.prior,
            "decision_impact": item.recall.decision_impact,
            "exposure": item.recall.exposure,
            "scopes": list(item.recall.scopes),
            "applies_when": list(item.recall.applies_when),
            "not_when": list(item.recall.not_when),
            "freshness_policy": item.recall.freshness_policy,
        },
        "sensitivity": item.sensitivity,
        "memory_card": item.memory_card,
        "full_meaning": item.full_meaning,
        "application_boundary": item.application_boundary,
        "rationale": item.rationale,
    }


def _handle_get(paths: MemoryPaths, request: dict[str, Any]) -> ToolResponse:
    memory_id = _required_id(request)
    item = MemoryStore(paths).get_memory(memory_id)
    return _with_estimate(
        ToolResponse(
            tool="agc.read",
            action="get",
            status="accepted",
            data={"item": _item_mapping(item)},
        )
    )


def _handle_history(paths: MemoryPaths, request: dict[str, Any]) -> ToolResponse:
    memory_id = _required_id(request)
    event_file = paths.events / "events.jsonl"
    events = []
    if event_file.exists():
        events = [
            json.loads(line)
            for line in strict_read_text(event_file).splitlines()
            if line and json.loads(line).get("object_id") == memory_id
        ]
    return _with_estimate(
        ToolResponse(
            tool="agc.read",
            action="history",
            status="accepted",
            data={"id": memory_id, "events": events},
        )
    )


def _handle_evidence(paths: MemoryPaths, request: dict[str, Any]) -> ToolResponse:
    memory_id = _required_id(request)
    receipt_file = paths.receipts / "source-keys.json"
    sources = []
    if receipt_file.exists():
        registry = json.loads(strict_read_text(receipt_file))
        sources = [
            entry
            for entry in registry.get("sources", [])
            if entry.get("object_id") == memory_id
        ]
    return _with_estimate(
        ToolResponse(
            tool="agc.read",
            action="evidence",
            status="accepted",
            data={"id": memory_id, "sources": sources},
        )
    )


def _handle_capture_overview(paths: MemoryPaths, _request: dict[str, Any]) -> ToolResponse:
    return ToolResponse(tool="agc.read", action="capture_overview", status="accepted", data=capture_overview(paths))


def _handle_capture_search(paths: MemoryPaths, request: dict[str, Any]) -> ToolResponse:
    return ToolResponse(tool="agc.read", action="capture_search", status="accepted", data=capture_search(paths, request))


def _handle_capture_get(paths: MemoryPaths, request: dict[str, Any]) -> ToolResponse:
    return ToolResponse(tool="agc.read", action="capture_get", status="accepted", data=capture_get(paths, request))


_HANDLERS = {
    "overview": _handle_overview,
    "search": _handle_search,
    "get": _handle_get,
    "history": _handle_history,
    "evidence": _handle_evidence,
    "capture_overview": _handle_capture_overview,
    "capture_search": _handle_capture_search,
    "capture_get": _handle_capture_get,
}


def dispatch_read(paths: MemoryPaths, request: Any) -> ToolResponse:
    if not isinstance(request, dict):
        return _failed("", "invalid_request", "request must be a mapping")
    action = request.get("action")
    if not isinstance(action, str) or action not in _HANDLERS:
        return _failed(
            action if isinstance(action, str) else "",
            "invalid_action",
            "unsupported agc.read action",
        )
    try:
        return _HANDLERS[action](paths, request)
    except CaptureReadError as error:
        if error.code == "capture_integrity_degraded":
            return _failed(action, error.code, "Capture object integrity is degraded")
        return _failed(action, "capture_not_found", "Capture object is not available")
    except LookupError:
        if action in {"get", "history", "evidence"} and (
            not isinstance(request.get("id"), str) or not request.get("id")
        ):
            return _failed(action, "id_required", "explicit memory id is required")
        return _failed(action, "not_found", "requested memory object is not available")
    except FileNotFoundError:
        return _failed(action, "not_found", "requested memory object is not available")
    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        return _failed(action, "invalid_request", "request is invalid")
    except OSError:
        return _failed(action, "read_failed", "read operation failed")
