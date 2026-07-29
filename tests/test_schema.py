from dataclasses import replace
from pathlib import Path

import pytest

from agc_runtime.models import MemoryItem
from agc_runtime.schema import validate_memory_item


FIXTURES = Path(__file__).parent / "fixtures"


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_principle_round_trips_canonically():
    item = MemoryItem.from_markdown(fixture_text("active-principle.md"))

    assert item.id == "difficult-but-correct"
    assert item.kind == "principle"
    validate_memory_item(item)
    assert MemoryItem.from_markdown(item.to_markdown()) == item


def test_evolving_interest_round_trips_with_interest_metadata():
    item = MemoryItem.from_markdown(fixture_text("evolving-interest.md"))

    assert item.topic == "agent-runtime"
    assert item.intensity == "high"
    assert item.trend == "rising"
    assert MemoryItem.from_markdown(item.to_markdown()) == item


def test_content_budgets_are_enforced():
    item = MemoryItem.from_markdown(
        fixture_text("active-principle.md").replace(
            "做难而正确的事情", "难" * 61, 1
        )
    )

    with pytest.raises(ValueError, match="Memory Card exceeds 60"):
        validate_memory_item(item)


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ("kind: principle", "kind: personality", "invalid kind"),
        ("status: active", "status: immortal", "invalid lifecycle status"),
        ("level: confirmed", "level: certain", "invalid confidence level"),
        ("type: durable", "type: permanent", "invalid temporal type"),
        ("exposure: core_card", "exposure: always", "invalid recall exposure"),
        ("sensitivity: normal", "sensitivity: private", "invalid sensitivity"),
    ],
)
def test_enums_are_strict(old: str, new: str, message: str):
    item = MemoryItem.from_markdown(
        fixture_text("active-principle.md").replace(old, new, 1)
    )

    with pytest.raises(ValueError, match=message):
        validate_memory_item(item)


def test_unknown_frontmatter_fields_are_rejected():
    text = fixture_text("active-principle.md").replace(
        "subkind: decision_standard",
        "subkind: decision_standard\nunknown_field: noise",
        1,
    )

    with pytest.raises(ValueError, match="unknown frontmatter field"):
        MemoryItem.from_markdown(text)


def test_unknown_nested_fields_are_rejected():
    text = fixture_text("active-principle.md").replace(
        "status: active", "status: active\n  unknown_status_detail: noise", 1
    )

    with pytest.raises(ValueError, match="unknown lifecycle field"):
        MemoryItem.from_markdown(text)


def test_duplicate_frontmatter_keys_are_rejected():
    text = fixture_text("active-principle.md").replace(
        "id: difficult-but-correct",
        "id: difficult-but-correct\nid: duplicate",
        1,
    )

    with pytest.raises(ValueError, match="duplicate YAML key"):
        MemoryItem.from_markdown(text)


def test_yaml_tags_are_rejected():
    text = fixture_text("active-principle.md").replace(
        "subkind: decision_standard",
        "subkind: !!python/object:builtins.object {}",
        1,
    )

    with pytest.raises(ValueError, match="invalid YAML frontmatter"):
        MemoryItem.from_markdown(text)


def test_fixed_body_sections_are_required_once_and_in_order():
    text = fixture_text("active-principle.md").replace(
        "## Rationale", "## Full Meaning", 1
    )

    with pytest.raises(ValueError, match="body headings"):
        MemoryItem.from_markdown(text)


def test_id_format_is_strict():
    item = MemoryItem.from_markdown(
        fixture_text("active-principle.md").replace(
            "id: difficult-but-correct", "id: Difficult_But_Correct", 1
        )
    )

    with pytest.raises(ValueError, match="invalid memory id"):
        validate_memory_item(item)


def test_personal_identity_core_card_requires_policy_reason():
    item = MemoryItem.from_markdown(fixture_text("active-principle.md"))
    item = replace(
        item,
        kind="identity",
        sensitivity="personal",
        policy_reason=None,
    )

    with pytest.raises(ValueError, match="explicit policy_reason"):
        validate_memory_item(item)


def test_growth_area_requires_goal_refs_for_proactive_exposure():
    item = MemoryItem.from_markdown(fixture_text("active-principle.md"))
    item = replace(
        item,
        kind="capability",
        domain="software_architecture",
        polarity="growth_area",
        current_level="developing",
        goal_refs=(),
    )

    with pytest.raises(ValueError, match="growth_area requires active goal_refs"):
        validate_memory_item(item)
