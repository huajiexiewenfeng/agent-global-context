import codecs
import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from agc_runtime.admin_service import dispatch_admin
from agc_runtime.contracts import SourceKey
from agc_runtime.migration_service import migrate_v1
from agc_runtime.models import MemoryItem
from agc_runtime.paths import MemoryPaths
from agc_runtime.store import MemoryStore


def _memory_markdown(memory_id: str = "migrated-principle") -> str:
    fixture = Path(__file__).parent / "fixtures" / "active-principle.md"
    item = MemoryItem.from_markdown(fixture.read_text(encoding="utf-8"))
    return replace(item, id=memory_id).to_markdown()


def _write_source(root: Path, relative: str, data: bytes) -> str:
    path = root / Path(*relative.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def _request(
    source_root: Path,
    *,
    migration_id: str = "v1-20260729",
    source_path: str = "user/preferences.md",
    source_bytes: bytes = b"legacy preference\n",
    memory_id: str = "migrated-principle",
) -> dict:
    digest = _write_source(source_root, source_path, source_bytes)
    return {
        "action": "migrate",
        "migration_id": migration_id,
        "source_root": str(source_root.resolve()),
        "sources": [
            {
                "path": source_path,
                "sha256": digest,
                "disposition": "snapshot",
            }
        ],
        "memories": [
            {
                "source_path": source_path,
                "memory_markdown": _memory_markdown(memory_id),
            }
        ],
    }


def test_migration_requires_distinct_absolute_source_root(tmp_path: Path):
    paths = MemoryPaths.from_root(tmp_path / "target")
    same_root = _request(paths.root)
    same = migrate_v1(paths, same_root)

    relative = dict(same_root, source_root="relative-v1")
    relative_response = migrate_v1(paths, relative)

    assert same.status == "failed"
    assert same.error["code"] == "invalid_request"
    assert relative_response.status == "failed"
    assert relative_response.error["code"] == "invalid_request"
    assert not (paths.root / "schema-version").exists()
    assert not paths.migrations.exists()


def test_migration_rejects_source_path_escape_before_writing(tmp_path: Path):
    paths = MemoryPaths.from_root(tmp_path / "target")
    source_root = tmp_path / "v1"
    outside = tmp_path / "outside.md"
    outside.write_bytes(b"outside\n")
    request = {
        "action": "migrate",
        "migration_id": "v1-20260729",
        "source_root": str(source_root.resolve()),
        "sources": [
            {
                "path": "../outside.md",
                "sha256": hashlib.sha256(outside.read_bytes()).hexdigest(),
                "disposition": "snapshot",
            }
        ],
        "memories": [],
    }

    response = migrate_v1(paths, request)

    assert response.status == "failed"
    assert response.error["code"] == "invalid_request"
    assert not paths.root.exists()


def test_all_source_hashes_are_verified_before_first_target_write(tmp_path: Path):
    paths = MemoryPaths.from_root(tmp_path / "target")
    source_root = tmp_path / "v1"
    request = _request(source_root)
    second_hash = _write_source(source_root, "notes/second.md", b"second\n")
    request["sources"].append(
        {
            "path": "notes/second.md",
            "sha256": "0" * 64 if second_hash != "0" * 64 else "1" * 64,
            "disposition": "ignored",
        }
    )

    response = migrate_v1(paths, request)

    assert response.status == "failed"
    assert response.error["code"] == "source_hash_mismatch"
    assert not paths.root.exists()


def test_snapshot_bom_normalization_and_content_free_metadata(tmp_path: Path):
    paths = MemoryPaths.from_root(tmp_path / "target")
    source_root = tmp_path / "v1"
    request = _request(
        source_root,
        source_bytes=codecs.BOM_UTF8 + "legacy café\n".encode(),
    )
    ignored_hash = _write_source(source_root, "ignored/rejected.md", b"ignored body\n")
    opaque_body = b"\xff\x00opaque secret bytes"
    opaque_hash = _write_source(source_root, "opaque/source.bin", opaque_body)
    request["sources"].extend(
        [
            {
                "path": "ignored/rejected.md",
                "sha256": ignored_hash,
                "disposition": "ignored",
            },
            {
                "path": "opaque/source.bin",
                "sha256": opaque_hash,
                "disposition": "excluded_sensitive",
            },
        ]
    )

    response = migrate_v1(paths, request)

    assert response.status == "accepted"
    assert response.data == {
        "code": "migration_completed",
        "migration_id": "v1-20260729",
        "source_count": 3,
        "snapshot_count": 1,
        "ignored_count": 1,
        "excluded_sensitive_count": 1,
        "memory_count": 1,
    }
    snapshot = (
        paths.migrations
        / "v1-20260729"
        / "snapshot"
        / "user"
        / "preferences.md"
    )
    assert snapshot.read_bytes() == "legacy café\n".encode()
    assert not (paths.migrations / "v1-20260729" / "snapshot" / "ignored").exists()
    assert not (paths.migrations / "v1-20260729" / "snapshot" / "opaque").exists()

    manifest_text = (
        paths.migrations / "v1-20260729" / "manifest.json"
    ).read_text(encoding="utf-8")
    manifest = json.loads(manifest_text)
    assert manifest["status"] == "completed"
    snapshot_metadata = next(
        source
        for source in manifest["sources"]
        if source["path"] == "user/preferences.md"
    )
    assert snapshot_metadata["source_had_bom"] is True
    assert manifest["counts"] == {
        "excluded_sensitive": 1,
        "ignored": 1,
        "memories": 1,
        "snapshots": 1,
        "sources": 3,
    }
    forbidden = [
        "memory_markdown",
        "legacy café",
        "ignored body",
        "opaque secret",
        "Memory Card",
        "Full Meaning",
    ]
    assert all(value not in manifest_text for value in forbidden)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda request: request["memories"][0].update(
                source_path="undeclared.md"
            ),
            "declared snapshot source",
        ),
        (
            lambda request: request["memories"][0].update(
                memory_markdown="not a v2 memory"
            ),
            "frontmatter",
        ),
        (
            lambda request: request["sources"][0].update(extra=True),
            "unknown source field",
        ),
        (
            lambda request: request.update(extra=True),
            "unknown request field",
        ),
    ],
)
def test_request_and_memory_validation_precedes_persistence(
    tmp_path: Path, mutate, message: str
):
    paths = MemoryPaths.from_root(tmp_path / "target")
    request = _request(tmp_path / "v1")
    mutate(request)

    response = migrate_v1(paths, request)

    assert response.status == "failed"
    assert message in response.error["message"]
    assert not paths.root.exists()


def test_migration_does_not_derive_memories_or_candidates(tmp_path: Path):
    paths = MemoryPaths.from_root(tmp_path / "target")
    source_root = tmp_path / "v1"
    source_hash = _write_source(source_root, "notes/only.md", b"ordinary source\n")
    request = {
        "action": "migrate",
        "migration_id": "v1-20260729",
        "source_root": str(source_root.resolve()),
        "sources": [
            {
                "path": "notes/only.md",
                "sha256": source_hash,
                "disposition": "ignored",
            }
        ],
        "memories": [],
    }

    response = migrate_v1(paths, request)

    assert response.status == "accepted"
    assert response.data["memory_count"] == 0
    assert not list(paths.memories.rglob("*.md"))
    assert not list(paths.candidates.rglob("*.json"))


def test_snapshot_with_arbitrary_suffix_is_valid_managed_utf8(tmp_path: Path):
    paths = MemoryPaths.from_root(tmp_path / "target")
    request = _request(
        tmp_path / "v1",
        source_path="legacy/preferences.custom",
    )

    response = migrate_v1(paths, request)
    validation = dispatch_admin(paths, {"action": "validate"})

    assert response.status == "accepted"
    assert validation.status == "accepted"


def test_exact_retry_is_idempotent_and_same_id_different_request_fails(
    tmp_path: Path,
):
    paths = MemoryPaths.from_root(tmp_path / "target")
    request = _request(tmp_path / "v1")

    first = migrate_v1(paths, request)
    first_events = (paths.events / "events.jsonl").read_text(encoding="utf-8")
    retry = migrate_v1(paths, request)
    changed = json.loads(json.dumps(request))
    changed["memories"][0]["memory_markdown"] = _memory_markdown("different-id")
    different = migrate_v1(paths, changed)

    assert first.status == "accepted"
    assert retry.status == "accepted"
    assert retry.data == first.data
    assert (paths.events / "events.jsonl").read_text(encoding="utf-8") == first_events
    assert different.status == "failed"
    assert different.error["code"] == "migration_id_conflict"
    assert len(list(paths.memories.rglob("*.md"))) == 1


def test_partial_retry_converges_and_rebuilds_catalog(tmp_path: Path):
    paths = MemoryPaths.from_root(tmp_path / "target")
    request = _request(tmp_path / "v1")
    first = migrate_v1(paths, request)
    manifest = paths.migrations / "v1-20260729" / "manifest.json"
    manifest.unlink()
    paths.catalog_json.unlink()
    paths.catalog_md.unlink()

    retry = migrate_v1(paths, request)

    assert first.status == "accepted"
    assert retry.status == "accepted"
    assert retry.data["memory_count"] == 1
    assert manifest.is_file()
    catalog = json.loads(paths.catalog_json.read_text(encoding="utf-8"))
    assert catalog["memory_count"] == 1
    assert len(list(paths.memories.rglob("*.md"))) == 1


def test_partial_receipt_rejects_changed_request_and_exact_retry_converges(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from agc_runtime import migration_service

    paths = MemoryPaths.from_root(tmp_path / "target")
    request = _request(tmp_path / "v1")
    original_write = migration_service.atomic_write_text
    failed = False

    def interrupt_final_receipt(path, text):
        nonlocal failed
        if (
            path.name == "manifest.json"
            and '"status": "completed"' in text
            and not failed
        ):
            failed = True
            raise OSError("injected final receipt interruption")
        return original_write(path, text)

    monkeypatch.setattr(
        migration_service, "atomic_write_text", interrupt_final_receipt
    )
    interrupted = migrate_v1(paths, request)
    manifest_path = paths.migrations / "v1-20260729" / "manifest.json"

    assert interrupted.status == "failed"
    assert json.loads(
        manifest_path.read_text(encoding="utf-8")
    )["status"] == "in_progress"

    changed = json.loads(json.dumps(request))
    item = MemoryItem.from_markdown(
        changed["memories"][0]["memory_markdown"]
    )
    changed["memories"][0]["memory_markdown"] = replace(
        item, memory_card="不同但仍有效的卡片"
    ).to_markdown()
    conflict = migrate_v1(paths, changed)
    monkeypatch.setattr(migration_service, "atomic_write_text", original_write)
    retry = migrate_v1(paths, request)

    assert conflict.status == "failed"
    assert conflict.error["code"] == "migration_id_conflict"
    assert retry.status == "accepted"
    assert json.loads(
        manifest_path.read_text(encoding="utf-8")
    )["status"] == "completed"


def test_non_migration_memory_blocks_new_migration_before_writes(tmp_path: Path):
    paths = MemoryPaths.from_root(tmp_path / "target")
    dispatch_admin(paths, {"action": "init"})
    MemoryStore(paths).create_memory(
        MemoryItem.from_markdown(_memory_markdown("existing-memory")),
        SourceKey("codex-task:existing", "r1", "a" * 64),
    )
    request = _request(tmp_path / "v1")

    response = migrate_v1(paths, request)

    assert response.status == "failed"
    assert response.error["code"] == "target_not_empty"
    assert not (paths.migrations / "v1-20260729").exists()
