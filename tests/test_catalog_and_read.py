import json
from dataclasses import replace
from pathlib import Path

import pytest

from agc_runtime.catalog import rebuild_catalog
from agc_runtime.contracts import SourceKey
from agc_runtime.models import MemoryItem
from agc_runtime.paths import MemoryPaths
from agc_runtime.read_service import dispatch_read
from agc_runtime.store import MemoryStore


def base_principle() -> MemoryItem:
    fixture = Path(__file__).parent / "fixtures" / "active-principle.md"
    return MemoryItem.from_markdown(fixture.read_text(encoding="utf-8"))


@pytest.fixture
def populated_paths(tmp_path: Path) -> MemoryPaths:
    paths = MemoryPaths.from_root(tmp_path / "memory")
    store = MemoryStore(paths)
    principle = base_principle()
    family = replace(
        principle,
        id="family-structure",
        kind="identity",
        subkind="family_structure",
        temporal=replace(principle.temporal, type="evolving"),
        recall=replace(
            principle.recall,
            prior="low",
            decision_impact="low",
            exposure="discoverable_only",
            scopes=("life",),
            applies_when=("family_context_matters",),
            not_when=("ordinary_work",),
        ),
        sensitivity="personal",
        memory_card="用户有一般家庭结构",
        full_meaning="用户明确表达过自己有妻子和儿子；仅在家庭结构实质相关时使用。",
        application_boundary="普通工作和研究任务中不主动提及。",
        rationale="这是带边界的个人背景。",
    )
    old_role = replace(
        principle,
        id="old-role",
        kind="context",
        subkind="career_role",
        lifecycle=replace(principle.lifecycle, status="historical"),
        temporal=replace(principle.temporal, type="contextual"),
        recall=replace(
            principle.recall,
            prior="low",
            decision_impact="low",
            exposure="history_only",
            scopes=("career",),
            applies_when=("career_history",),
            not_when=("current_role",),
        ),
        memory_card="曾经承担旧岗位职责",
        full_meaning="这是已经结束的职业上下文，只用于解释历史。",
        application_boundary="不得当作当前职责。",
        rationale="旧上下文已经结束。",
    )
    writing = replace(
        principle,
        id="implementation-plan-first",
        kind="preference",
        subkind="collaboration",
        recall=replace(
            principle.recall,
            prior="high",
            decision_impact="medium",
            exposure="scoped_card",
            scopes=("work", "writing"),
            applies_when=("implementation",),
            not_when=("trivial_task",),
        ),
        memory_card="复杂改动先确认实施计划",
        full_meaning="面对复杂改动时，用户偏好先形成清晰计划，再持续推进实现。",
        application_boundary="简单、低风险且可逆的修改无需增加流程。",
        rationale="这会直接改善协作效率。",
    )
    for index, item in enumerate(
        [principle, family, old_role, writing], start=1
    ):
        store.create_memory(
            item,
            SourceKey(
                f"codex-task:t{index}",
                "r1",
                f"{index:x}" * 64,
            ),
        )
    rebuild_catalog(paths)
    return paths


def test_overview_returns_metadata_not_full_meaning(
    populated_paths: MemoryPaths,
):
    response = dispatch_read(populated_paths, {"action": "overview"})
    encoded = json.dumps(response.to_dict(), ensure_ascii=False)

    assert response.status == "accepted"
    assert response.data["estimated_tokens"] <= 250
    assert "长期价值" not in encoded
    assert "复杂改动时" not in encoded


def test_search_filters_before_loading_bodies(populated_paths: MemoryPaths):
    response = dispatch_read(
        populated_paths,
        {
            "action": "search",
            "filters": {
                "kind": ["principle"],
                "scopes": ["architecture"],
                "decision_impact": ["high"],
                "sensitivity": ["normal"],
            },
            "limit": 10,
        },
    )

    assert [item["id"] for item in response.data["items"]] == [
        "difficult-but-correct"
    ]
    assert "full_meaning" not in response.data["items"][0]


def test_discoverable_and_history_are_not_default(
    populated_paths: MemoryPaths,
):
    response = dispatch_read(populated_paths, {"action": "overview"})
    ids = {item["id"] for item in response.data.get("cards", [])}

    assert "family-structure" not in ids
    assert "old-role" not in ids
    assert "difficult-but-correct" in ids


def test_catalog_is_sorted_by_utf8_id_and_rebuild_is_deterministic(
    populated_paths: MemoryPaths,
):
    first = populated_paths.catalog_json.read_bytes()
    catalog = json.loads(first.decode("utf-8"))

    rebuild_catalog(populated_paths)

    assert [card["id"] for card in catalog["cards"]] == sorted(
        (card["id"] for card in catalog["cards"]),
        key=lambda value: value.encode("utf-8"),
    )
    assert populated_paths.catalog_json.read_bytes() == first


def test_get_requires_exact_id_and_returns_full_sections(
    populated_paths: MemoryPaths,
):
    missing = dispatch_read(populated_paths, {"action": "get"})
    found = dispatch_read(
        populated_paths, {"action": "get", "id": "difficult-but-correct"}
    )

    assert missing.status == "failed"
    assert missing.error["code"] == "id_required"
    assert found.data["item"]["full_meaning"].startswith("在重要工作")


def test_history_and_evidence_require_id_and_remain_sanitized(
    populated_paths: MemoryPaths,
):
    history = dispatch_read(
        populated_paths,
        {"action": "history", "id": "difficult-but-correct"},
    )
    evidence = dispatch_read(
        populated_paths,
        {"action": "evidence", "id": "difficult-but-correct"},
    )
    encoded = json.dumps(
        {"history": history.to_dict(), "evidence": evidence.to_dict()},
        ensure_ascii=False,
    )

    assert history.data["events"]
    assert evidence.data["sources"]
    assert "做难而正确的事情" not in encoded
    assert "长期价值" not in encoded
