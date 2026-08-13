from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

from agc_runtime.admin_service import dispatch_admin
from agc_runtime.catalog import rebuild_catalog
from agc_runtime.contracts import SourceKey, ToolResponse
from agc_runtime.models import MemoryItem
from agc_runtime.paths import MemoryPaths
from agc_runtime.read_service import dispatch_read
from agc_runtime.response_budget import fit_overview_response
from agc_runtime.runtime_config import load_runtime_config
from agc_runtime.store import MemoryStore
from agc_runtime.utf8_io import atomic_write_text


def initialized_root_with_active_and_historical_memories(tmp_path: Path) -> MemoryPaths:
    paths = MemoryPaths.from_root(tmp_path / "memory")
    assert dispatch_admin(paths, {"action": "init"}).status == "accepted"
    fixture = Path(__file__).parent / "fixtures" / "active-principle.md"
    active = MemoryItem.from_markdown(fixture.read_text(encoding="utf-8"))
    historical = replace(
        active,
        id="historical-shared-text",
        lifecycle=replace(active.lifecycle, status="historical"),
        memory_card="Shared text only for historical recall gating",
    )
    store = MemoryStore(paths)
    for number, item in enumerate((active, historical), start=1):
        store.create_memory(item, SourceKey(f"test:{number}", "r1", f"{number}" * 64))
    rebuild_catalog(paths)
    return paths


def test_ac_02_lifecycle_and_hard_overview_budget(tmp_path: Path):
    paths = initialized_root_with_active_and_historical_memories(tmp_path)
    response = dispatch_read(paths, {"action": "overview"})

    assert response.status == "accepted"
    assert response.data["estimated_tokens"] <= load_runtime_config(paths).recall.overview_token_budget
    assert {card["lifecycle"] for card in response.data["cards"]} <= {"active"}

    search = dispatch_read(paths, {"action": "search", "query": "shared text"})
    assert {item["lifecycle"] for item in search.data["results"]} <= {"active"}


def test_overview_fails_when_fixed_counts_cannot_fit(tmp_path: Path):
    paths = initialized_root_with_active_and_historical_memories(tmp_path)
    config_file = paths.root / "config.yaml"
    atomic_write_text(
        config_file,
        config_file.read_text(encoding="utf-8").replace(
            "overview_token_budget: 250", "overview_token_budget: 1"
        ),
    )

    response = dispatch_read(paths, {"action": "overview"})

    assert response.status == "failed"
    assert response.error == {
        "code": "response_budget_exceeded",
        "message": "overview response cannot fit configured token budget",
    }


def overview_data_for_compression() -> dict:
    return {
        "memory_count": 41,
        "available_card_count": 2,
        "cards": [
            {"id": "card-a", "memory_card": "a" * 240},
            {"id": "card-b", "memory_card": "b" * 240},
        ],
        "high_impact_scopes": ["scope-a-" * 30, "scope-b-" * 30],
        "counts": {
            "by_scope": {"scope-a-" * 30: 20, "scope-b-" * 30: 21},
            "by_kind": {"kind-a-" * 30: 20, "kind-b-" * 30: 21},
        },
    }


def accepted_estimate(data: dict) -> int:
    response = fit_overview_response(
        ToolResponse(
            tool="agc.read", action="overview", status="accepted", data=data
        ),
        budget=10**9,
    )
    return response.data["estimated_tokens"]


def compact_field(data: dict, field: str) -> None:
    container = data["counts"] if field in {"by_scope", "by_kind"} else data
    value = container[field]
    container[field] = (
        dict(list(value.items())[:-1]) if isinstance(value, dict) else value[:-1]
    )


@pytest.mark.parametrize(
    ("stage", "field"),
    tuple(enumerate(("cards", "high_impact_scopes", "by_scope", "by_kind"))),
)
def test_overview_compresses_in_documented_order_and_preserves_memory_count(
    stage: int, field: str
):
    original = overview_data_for_compression()
    target = deepcopy(original)
    fields = ("cards", "high_impact_scopes", "by_scope", "by_kind")
    for earlier in fields[:stage]:
        container = target["counts"] if earlier in {"by_scope", "by_kind"} else target
        container[earlier] = {} if isinstance(container[earlier], dict) else []
    compact_field(target, field)
    budget = accepted_estimate(target)
    before_current_stage = deepcopy(target)
    before_container = (
        before_current_stage["counts"]
        if field in {"by_scope", "by_kind"}
        else before_current_stage
    )
    original_container = (
        original["counts"] if field in {"by_scope", "by_kind"} else original
    )
    before_container[field] = deepcopy(original_container[field])
    assert accepted_estimate(before_current_stage) > budget

    fitted = fit_overview_response(
        ToolResponse(
            tool="agc.read", action="overview", status="accepted", data=original
        ),
        budget=budget,
    )

    assert fitted.status == "accepted"
    assert fitted.data["estimated_tokens"] <= budget
    assert fitted.data["memory_count"] == original["memory_count"]
    for earlier in fields[:stage]:
        container = (
            fitted.data["counts"]
            if earlier in {"by_scope", "by_kind"}
            else fitted.data
        )
        assert not container[earlier]
    fitted_container = (
        fitted.data["counts"] if field in {"by_scope", "by_kind"} else fitted.data
    )
    target_container = (
        target["counts"] if field in {"by_scope", "by_kind"} else target
    )
    assert fitted_container[field] == target_container[field]
    for later in fields[stage + 1 :]:
        fitted_later = (
            fitted.data["counts"]
            if later in {"by_scope", "by_kind"}
            else fitted.data
        )
        original_later = (
            original["counts"] if later in {"by_scope", "by_kind"} else original
        )
        assert fitted_later[later] == original_later[later]
