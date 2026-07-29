from pathlib import Path

import pytest

from agc_runtime.contracts import SourceKey
from agc_runtime.models import MemoryItem
from agc_runtime.paths import MemoryPaths
from agc_runtime.store import MemoryStore


def load_principle() -> MemoryItem:
    fixture = Path(__file__).parent / "fixtures" / "active-principle.md"
    return MemoryItem.from_markdown(fixture.read_text(encoding="utf-8"))


@pytest.fixture
def store(tmp_path: Path) -> MemoryStore:
    return MemoryStore(MemoryPaths.from_root(tmp_path / "memory"))


def test_same_source_is_idempotent(store: MemoryStore):
    principle = load_principle()
    source = SourceKey("codex-task:t1", "r1", "a" * 64)

    assert store.create_memory(principle, source).created is True
    duplicate = store.create_memory(principle, source)

    assert duplicate.created is False
    assert duplicate.code == "duplicate_source"
    assert duplicate.independent_evidence_count == 1


def test_new_revision_is_independent(store: MemoryStore):
    principle = load_principle()
    store.create_memory(
        principle, SourceKey("codex-task:t1", "r1", "a" * 64)
    )

    result = store.add_evidence(
        principle.id,
        SourceKey("codex-task:t1", "r2", "b" * 64),
        "2026-07-29T00:00:00Z",
    )

    assert result.independent_evidence_count == 2


def test_new_content_hash_is_independent_even_with_same_revision(
    store: MemoryStore,
):
    principle = load_principle()
    store.create_memory(
        principle, SourceKey("codex-task:t1", "r1", "a" * 64)
    )

    result = store.add_evidence(
        principle.id,
        SourceKey("codex-task:t1", "r1", "b" * 64),
        "2026-07-29T00:00:00Z",
    )

    assert result.independent_evidence_count == 2


def test_event_does_not_copy_memory_body(store: MemoryStore):
    principle = load_principle()
    store.create_memory(
        principle, SourceKey("codex-task:t1", "r1", "a" * 64)
    )

    events = store.read_all_events_text()

    assert "做难而正确的事情" not in events
    assert "长期价值" not in events
    assert principle.id in events
    assert "codex-task:t1" in events


def test_memory_path_is_deterministic_by_kind(store: MemoryStore):
    principle = load_principle()
    store.create_memory(
        principle, SourceKey("codex-task:t1", "r1", "a" * 64)
    )

    assert (
        store.paths.memories / "principle" / "difficult-but-correct.md"
    ).is_file()


def test_existing_id_with_new_source_needs_adjudication(store: MemoryStore):
    principle = load_principle()
    store.create_memory(
        principle, SourceKey("codex-task:t1", "r1", "a" * 64)
    )

    result = store.create_memory(
        principle, SourceKey("codex-task:t2", "r1", "b" * 64)
    )

    assert result.created is False
    assert result.code == "memory_id_exists"
    assert result.status == "needs_adjudication"
    assert result.independent_evidence_count == 1


def test_failed_event_write_rolls_back_memory_and_receipt(
    store: MemoryStore, monkeypatch: pytest.MonkeyPatch
):
    principle = load_principle()
    source = SourceKey("codex-task:t1", "r1", "a" * 64)

    def fail_event(*_args, **_kwargs):
        raise OSError("injected event failure")

    monkeypatch.setattr("agc_runtime.store.append_event", fail_event)

    with pytest.raises(OSError, match="injected event failure"):
        store.create_memory(principle, source)

    assert not list(store.paths.memories.rglob("*.md"))
    assert not store.source_was_recorded(source)
    assert not list(store.paths.queue.glob("*.json"))


def test_add_evidence_updates_dates_without_copying_body_to_event(
    store: MemoryStore,
):
    principle = load_principle()
    store.create_memory(
        principle, SourceKey("codex-task:t1", "r1", "a" * 64)
    )

    store.add_evidence(
        principle.id,
        SourceKey("codex-task:t2", "r1", "b" * 64),
        "2026-07-30T10:20:30Z",
    )
    updated = store.get_memory(principle.id)

    assert updated.temporal.last_observed == "2026-07-30"
    assert updated.provenance.updated_at == "2026-07-30"
    assert "做难而正确的事情" not in store.read_all_events_text()


def test_retry_finalizes_fully_committed_pending_transaction(
    store: MemoryStore, monkeypatch: pytest.MonkeyPatch
):
    principle = load_principle()
    source = SourceKey("codex-task:t1", "r1", "a" * 64)
    original_cleanup = store._cleanup_transaction

    def interrupt_cleanup(*_args, **_kwargs):
        raise OSError("injected cleanup interruption")

    monkeypatch.setattr(store, "_cleanup_transaction", interrupt_cleanup)
    with pytest.raises(OSError, match="injected cleanup interruption"):
        store.create_memory(principle, source)

    assert list(store.paths.queue.glob("*.json"))
    monkeypatch.setattr(store, "_cleanup_transaction", original_cleanup)

    retry = store.create_memory(principle, source)

    assert retry.code == "duplicate_source"
    assert not list(store.paths.queue.glob("*.json"))
    assert store.get_memory(principle.id) == principle
