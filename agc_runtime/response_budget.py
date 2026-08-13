import json
from typing import Any

from agc_runtime.contracts import ToolResponse


def estimate_tool_response_tokens(response: ToolResponse) -> int:
    serialized = json.dumps(
        response.to_dict(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return (len(serialized) + 2) // 3


def _with_estimate(response: ToolResponse) -> ToolResponse:
    data = dict(response.data)
    estimate = 0
    for _ in range(10):
        data["estimated_tokens"] = estimate
        candidate = ToolResponse(
            tool=response.tool,
            action=response.action,
            status=response.status,
            data=data,
            warnings=response.warnings,
            error=response.error,
        )
        updated = estimate_tool_response_tokens(candidate)
        if updated == estimate:
            return candidate
        estimate = updated
    data["estimated_tokens"] = estimate
    return ToolResponse(
        tool=response.tool,
        action=response.action,
        status=response.status,
        data=data,
        warnings=response.warnings,
        error=response.error,
    )


def _response_with_data(response: ToolResponse, data: dict[str, Any]) -> ToolResponse:
    return _with_estimate(
        ToolResponse(
            tool=response.tool,
            action=response.action,
            status=response.status,
            data=data,
            warnings=response.warnings,
            error=response.error,
        )
    )


def fit_overview_response(response: ToolResponse, *, budget: int) -> ToolResponse:
    """Return an accepted overview within budget, or the stable budget error."""
    data = dict(response.data)
    stages = (
        ("cards", lambda value: value[:-1]),
        ("high_impact_scopes", lambda value: value[:-1]),
        ("by_scope", lambda value: dict(list(value.items())[:-1])),
        ("by_kind", lambda value: dict(list(value.items())[:-1])),
    )
    candidate = _response_with_data(response, data)
    if candidate.data["estimated_tokens"] <= budget:
        return candidate
    for field, compact in stages:
        container = data["counts"] if field in {"by_scope", "by_kind"} else data
        while container[field]:
            next_data = dict(data)
            if container is data:
                next_data[field] = compact(container[field])
            else:
                next_counts = dict(data["counts"])
                next_counts[field] = compact(container[field])
                next_data["counts"] = next_counts
            data = next_data
            container = data["counts"] if field in {"by_scope", "by_kind"} else data
            candidate = _response_with_data(response, data)
            if candidate.data["estimated_tokens"] <= budget:
                return candidate
    return ToolResponse(
        tool=response.tool,
        action=response.action,
        status="failed",
        error={
            "code": "response_budget_exceeded",
            "message": "overview response cannot fit configured token budget",
        },
    )
