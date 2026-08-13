from dataclasses import replace
from pathlib import Path

from agc_runtime.admin_service import dispatch_admin
from agc_runtime.catalog import rebuild_catalog
from agc_runtime.contracts import SourceKey
from agc_runtime.models import MemoryItem
from agc_runtime.paths import MemoryPaths
from agc_runtime.read_service import dispatch_read
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
