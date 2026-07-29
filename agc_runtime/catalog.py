import json
from collections import Counter
from contextlib import nullcontext
from pathlib import Path
from typing import Any

from agc_runtime.locking import root_write_lock
from agc_runtime.models import MemoryItem
from agc_runtime.paths import MemoryPaths
from agc_runtime.schema import validate_memory_item
from agc_runtime.utf8_io import atomic_write_text, strict_read_text


def card_from_item(item: MemoryItem) -> dict[str, Any]:
    return {
        "id": item.id,
        "kind": item.kind,
        "scopes": list(item.recall.scopes),
        "updated_at": item.provenance.updated_at,
        "confidence": item.confidence.level,
        "decision_impact": item.recall.decision_impact,
        "exposure": item.recall.exposure,
        "sensitivity": item.sensitivity,
        "memory_card": item.memory_card,
    }


def _memory_files(paths: MemoryPaths) -> list[Path]:
    if not paths.memories.exists():
        return []
    return sorted(
        paths.memories.rglob("*.md"),
        key=lambda path: str(path.relative_to(paths.memories)).encode("utf-8"),
    )


def build_catalog(paths: MemoryPaths) -> dict[str, Any]:
    cards = []
    for path in _memory_files(paths):
        item = MemoryItem.from_markdown(strict_read_text(path))
        validate_memory_item(item)
        cards.append(card_from_item(item))
    cards.sort(key=lambda card: card["id"].encode("utf-8"))
    return {"schema_version": 2, "memory_count": len(cards), "cards": cards}


def render_catalog_markdown(catalog: dict[str, Any]) -> str:
    lines = [
        "# Agent Global Context Catalog",
        "",
        f"Memory count: {catalog['memory_count']}",
        "",
    ]
    for card in catalog["cards"]:
        lines.extend(
            [
                f"## {card['id']}",
                "",
                f"- kind: {card['kind']}",
                f"- scopes: {', '.join(card['scopes'])}",
                f"- updated_at: {card['updated_at']}",
                f"- confidence: {card['confidence']}",
                f"- decision_impact: {card['decision_impact']}",
                f"- exposure: {card['exposure']}",
                f"- sensitivity: {card['sensitivity']}",
                f"- memory_card: {card['memory_card']}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def rebuild_catalog(
    paths: MemoryPaths, *, acquire_lock: bool = True
) -> dict[str, Any]:
    lock = root_write_lock(paths) if acquire_lock else nullcontext()
    with lock:
        catalog = build_catalog(paths)
        atomic_write_text(
            paths.catalog_json,
            json.dumps(catalog, ensure_ascii=False, sort_keys=True, indent=2)
            + "\n",
        )
        atomic_write_text(paths.catalog_md, render_catalog_markdown(catalog))
    return catalog


def load_catalog(paths: MemoryPaths) -> dict[str, Any]:
    if not paths.catalog_json.exists():
        return rebuild_catalog(paths)
    value = json.loads(strict_read_text(paths.catalog_json))
    if (
        not isinstance(value, dict)
        or value.get("schema_version") != 2
        or not isinstance(value.get("cards"), list)
    ):
        raise ValueError("invalid generated catalog")
    return value


def catalog_counts(catalog: dict[str, Any]) -> dict[str, Any]:
    kind_counts = Counter(card["kind"] for card in catalog["cards"])
    scope_counts = Counter(
        scope for card in catalog["cards"] for scope in card["scopes"]
    )
    high_impact_scopes = sorted(
        {
            scope
            for card in catalog["cards"]
            if card["decision_impact"] == "high"
            for scope in card["scopes"]
        },
        key=lambda value: value.encode("utf-8"),
    )
    return {
        "by_kind": dict(sorted(kind_counts.items())),
        "by_scope": dict(sorted(scope_counts.items())),
        "high_impact_scopes": high_impact_scopes,
    }
