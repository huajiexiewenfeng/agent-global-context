import hashlib
import json
import os
import subprocess
import zipfile
from dataclasses import replace
from pathlib import Path

import pytest

from agc_runtime import forget_transaction
from agc_runtime.catalog import rebuild_catalog
from agc_runtime.capture_transaction import safe_unlink as durable_unlink
from agc_runtime.contracts import SourceKey
from agc_runtime.forget_service import forget
from agc_runtime.migration_manifest import migration_manifest_integrity
from agc_runtime.migration_service import migrate_v1
from agc_runtime.models import MemoryItem
from agc_runtime.paths import MemoryPaths
from agc_runtime.read_service import dispatch_read
from agc_runtime.store import MemoryStore
from agc_runtime.utf8_io import atomic_write_text
from agc_runtime.write_service import dispatch_write


def family_memory() -> MemoryItem:
    fixture = Path(__file__).parent / "fixtures" / "active-principle.md"
    principle = MemoryItem.from_markdown(fixture.read_text(encoding="utf-8"))
    return replace(
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
        application_boundary="普通工作任务中不主动提及。",
        rationale="这是带边界的个人背景。",
    )


def parent_memory() -> MemoryItem:
    item = family_memory()
    return replace(
        item,
        id="parent-history",
        subkind="parent_history",
        memory_card="用户提到父母",
        full_meaning="用户明确表达过与父母有关的背景；仅在相关语境中使用。",
        application_boundary="普通任务中不主动提及父母。",
        rationale="这是另一条有边界的个人背景。",
    )


@pytest.fixture
def populated(tmp_path: Path):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    source_task = tmp_path / "codex-source-task.jsonl"
    atomic_write_text(source_task, "原始任务提到妻子和儿子\n")
    item = family_memory()
    MemoryStore(paths).create_memory(
        item,
        SourceKey("codex-task:family", "r1", "a" * 64),
    )
    rebuild_catalog(paths)
    atomic_write_text(
        paths.candidates / "ordinary" / "candidate.json",
        json.dumps(
            {
                "schema_version": 2,
                "candidate_id": "family-structure",
                "rationale": "妻子和儿子",
                "sources": [],
            },
            ensure_ascii=False,
        )
        + "\n",
    )
    atomic_write_text(paths.cache / "family.txt", "妻子和儿子\n")
    atomic_write_text(paths.queue / "family.txt", "family-structure\n")
    atomic_write_text(
        paths.archive / "identity" / "family-structure.md",
        item.to_markdown(),
    )
    atomic_write_text(
        paths.backups / "snapshot" / "family-structure.md",
        item.to_markdown(),
    )
    atomic_write_text(
        paths.root / "migration-staging" / "family.json",
        '{"memory_id":"family-structure","text":"妻子和儿子"}\n',
    )
    return paths, source_task


def authorized_request() -> dict:
    return {
        "memory_id": "family-structure",
        "suppression_scope": "family_structure",
        "authorization": "explicit_user_request",
        "verification_terms": ["妻子和儿子"],
    }


def migrate_family(
    paths: MemoryPaths,
    source_root: Path,
    source_texts: dict[str, str] | None = None,
):
    source_texts = source_texts or {
        "user/family.md": "保留：无关内容\n忘记：妻子和儿子\n保留：其他内容\n"
    }
    sources = []
    for relative, text in source_texts.items():
        source = source_root / Path(*relative.split("/"))
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(text, encoding="utf-8")
        sources.append(
            {
                "path": relative,
                "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "disposition": "snapshot",
            }
        )
    request = {
        "action": "migrate",
        "migration_id": "v1-family",
        "source_root": str(source_root.resolve()),
        "sources": sources,
        "memories": [
            {
                "source_path": next(iter(source_texts)),
                "memory_markdown": family_memory().to_markdown(),
            }
        ],
    }
    assert migrate_v1(paths, request).status == "accepted"
    return request


def _link_directory(link: Path, target: Path) -> None:
    try:
        os.symlink(target, link, target_is_directory=True)
        return
    except (OSError, NotImplementedError):
        if os.name != "nt":
            raise
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.skip(f"directory links unavailable: {result.stderr}")


def _forget_journals(paths: MemoryPaths) -> list[Path]:
    return list((paths.tombstones / "in-progress").glob("*.json"))


def test_forget_requires_authorization(populated):
    paths, _source_task = populated

    response = forget(paths, {"memory_id": "family-structure"})

    assert response.status == "failed"
    assert response.error["code"] == "forget_authorization_required"
    assert dispatch_read(
        paths, {"action": "get", "id": "family-structure"}
    ).status == "accepted"


def test_forget_requires_precise_suppression_scope(populated):
    paths, _source_task = populated
    request = authorized_request()
    request["suppression_scope"] = "all"

    response = forget(paths, request)

    assert response.status == "needs_adjudication"
    assert response.data["code"] == "ambiguous_suppression_scope"


def test_forget_removes_all_managed_copies_but_not_source_task(populated):
    paths, source_task = populated

    response = forget(paths, authorized_request())

    assert response.status == "accepted"
    assert set(response.data["tombstone"]) == {
        "memory_id",
        "status",
        "forgotten_at",
        "suppression_scope",
    }
    assert response.data["managed_agc_copies_deleted"] is True
    assert response.data["source_task_deleted"] is False
    assert source_task.read_text(encoding="utf-8") == "原始任务提到妻子和儿子\n"
    assert dispatch_read(
        paths, {"action": "get", "id": "family-structure"}
    ).status == "failed"
    assert all(
        "妻子和儿子" not in path.read_text(encoding="utf-8")
        for path in paths.root.rglob("*")
        if path.is_file() and path.suffix.lower() in {".md", ".json", ".jsonl", ".txt"}
    )


def test_forget_removes_events_receipts_and_catalog_card(populated):
    paths, _source_task = populated

    forget(paths, authorized_request())

    assert "family-structure" not in paths.catalog_json.read_text(encoding="utf-8")
    assert "family-structure" not in (
        paths.events / "events.jsonl"
    ).read_text(encoding="utf-8")
    assert "family-structure" not in (
        paths.receipts / "source-keys.json"
    ).read_text(encoding="utf-8")


def test_forget_rewrites_backup_zip_and_injects_tombstone(populated):
    paths, _source_task = populated
    backup_zip = paths.backups / "agc-backup.zip"
    with zipfile.ZipFile(backup_zip, "w") as archive:
        archive.writestr(
            "memories/identity/family-structure.md",
            family_memory().to_markdown(),
        )
        archive.writestr("config.yaml", "sensitive_storage: disabled\n")

    forget(paths, authorized_request())

    with zipfile.ZipFile(backup_zip, "r") as archive:
        names = set(archive.namelist())
        all_text = "\n".join(
            archive.read(name).decode("utf-8")
            for name in names
            if not name.endswith("/")
        )
    assert "memories/identity/family-structure.md" not in names
    assert "config.yaml" in names
    assert any(".runtime/tombstones/" in name for name in names)
    assert "妻子和儿子" not in all_text


def test_formal_forget_never_scans_or_rewrites_capture_model_paths(populated):
    paths, _source_task = populated
    capture_copy = paths.capture.dirty / "strict-copy.json"
    capture_copy.parent.mkdir(parents=True, exist_ok=True)
    capture_bytes = json.dumps(
        {"schema_version": 1, "statement": "妻子和儿子"},
        ensure_ascii=False,
    ).encode("utf-8")
    capture_copy.write_bytes(capture_bytes)
    backup_zip = paths.backups / "capture-isolation.zip"
    capture_name = ".runtime/capture/schema-version"
    archived_capture_bytes = b"1\n"
    with zipfile.ZipFile(backup_zip, "w") as archive:
        archive.writestr(capture_name, archived_capture_bytes)
        archive.writestr(
            "memories/identity/family-structure.md",
            family_memory().to_markdown(),
        )

    response = forget(paths, authorized_request())

    assert response.status == "accepted"
    assert capture_copy.read_bytes() == capture_bytes
    with zipfile.ZipFile(backup_zip) as archive:
        assert archive.read(capture_name) == archived_capture_bytes


def test_formal_forget_never_deletes_casefolded_capture_archive_path(populated):
    paths, _source_task = populated
    backup_zip = paths.backups / "casefolded-capture.zip"
    capture_name = ".RUNTIME/capture/dirty/strict-copy.json"
    capture_bytes = json.dumps(
        {"schema_version": 1, "statement": "妻子和儿子"},
        ensure_ascii=False,
    ).encode("utf-8")
    with zipfile.ZipFile(backup_zip, "w") as archive:
        archive.writestr(capture_name, capture_bytes)
        archive.writestr(
            "memories/identity/family-structure.md",
            family_memory().to_markdown(),
        )
    before = backup_zip.read_bytes()

    response = forget(paths, authorized_request())

    assert response.status == "failed"
    assert response.error["code"] == "forget_failed"
    assert backup_zip.read_bytes() == before
    with zipfile.ZipFile(backup_zip) as archive:
        assert archive.read(capture_name) == capture_bytes
    assert MemoryStore(paths).get_memory("family-structure") == family_memory()


@pytest.mark.parametrize(
    "source_name",
    [
        "../memories/identity/family-structure.md",
        "memories/identity/../identity/family-structure.md",
        "memories//identity/family-structure.md",
        ".runtime./capture/dirty/strict-copy.json",
    ],
)
def test_formal_forget_validates_every_source_archive_name_before_filtering(
    populated, source_name: str
):
    paths, _source_task = populated
    digest = hashlib.sha256(source_name.encode("utf-8")).hexdigest()[:12]
    backup_zip = paths.backups / f"invalid-source-name-{digest}.zip"
    with zipfile.ZipFile(backup_zip, "w") as archive:
        archive.writestr(source_name, family_memory().to_markdown())
        archive.writestr("config.yaml", "sensitive_storage: disabled\n")
    before = backup_zip.read_bytes()

    response = forget(paths, authorized_request())

    assert response.status == "failed"
    assert response.error["code"] == "forget_failed"
    assert backup_zip.read_bytes() == before
    assert MemoryStore(paths).get_memory("family-structure") == family_memory()


@pytest.mark.parametrize("resource", ["compression_ratio", "manifest_size"])
def test_formal_forget_rejects_unrestorable_rebuilt_archive_before_mutation(
    populated, resource: str
):
    paths, _source_task = populated
    backup_zip = paths.backups / f"unsafe-rewrite-{resource}.zip"
    with zipfile.ZipFile(
        backup_zip, "w", compression=zipfile.ZIP_DEFLATED
    ) as archive:
        archive.writestr(
            "memories/identity/family-structure.md",
            family_memory().to_markdown(),
        )
        if resource == "compression_ratio":
            archive.writestr("highly-compressible.txt", b"0" * (1024 * 1024))
        else:
            suffix = "x" * 220
            for index in range(4095):
                archive.writestr(f"contexts/{index:04d}-{suffix}.txt", b"")
    before = backup_zip.read_bytes()

    response = forget(paths, authorized_request())

    assert response.status == "failed"
    assert response.error["code"] == "forget_failed"
    assert backup_zip.read_bytes() == before
    assert MemoryStore(paths).get_memory("family-structure") == family_memory()


def test_formal_forget_primary_delete_uses_durable_unlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    target = paths.cache / "delete-me.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"managed")
    calls: list[Path] = []

    def record(path: Path) -> None:
        calls.append(path)
        durable_unlink(path)

    monkeypatch.setattr(forget_transaction, "safe_unlink", record, raising=False)
    forget_transaction._apply_forget_operation(
        forget_transaction.ForgetOperation(target, None, "managed_purge")
    )

    assert calls == [target]


def test_write_dispatch_exposes_authorized_forget(populated):
    paths, _source_task = populated

    response = dispatch_write(
        paths, {"action": "forget", **authorized_request()}
    )

    assert response.status == "accepted"
    assert response.action == "forget"


def test_forget_migrated_memory_surgically_rewrites_legacy_and_snapshot(
    tmp_path: Path,
):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    source_root = tmp_path / "v1"
    source_file = source_root / "user" / "family-structure.md"
    source_text = "保留：无关内容\n忘记：妻子和儿子\n保留：其他内容\n"
    request = migrate_family(
        paths,
        source_root,
        {"user/family-structure.md": source_text},
    )
    snapshot = (
        paths.migrations
        / "v1-family"
        / "snapshot"
        / "user"
        / "family-structure.md"
    )

    response = forget(paths, authorized_request())

    assert response.status == "accepted"
    text = source_file.read_text(encoding="utf-8")
    assert "妻子和儿子" not in text
    assert "保留：无关内容" in text
    assert "保留：其他内容" in text
    assert not snapshot.exists()
    manifest_text = (
        paths.migrations / "v1-family" / "manifest.json"
    ).read_text(encoding="utf-8")
    manifest = json.loads(manifest_text)
    assert manifest["migrated_ids"] == []
    assert manifest["memories"] == []
    tombstone_text = next(paths.tombstones.glob("*.json")).read_text(
        encoding="utf-8"
    )
    assert "妻子和儿子" not in tombstone_text
    assert request["sources"][0]["sha256"] not in tombstone_text


def test_forget_exact_term_surgery_preserves_same_line_and_multiline_text(
    tmp_path: Path,
):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    source_root = tmp_path / "v1"
    term = "妻子和儿子"
    source_texts = {
        "user/first.md": f"left {term} right\nrelated line without literal\n",
        "user/second.md": f"alpha {term} omega\nuntouched multiline\n",
    }
    migrate_family(paths, source_root, source_texts)

    response = forget(paths, authorized_request())

    assert response.status == "accepted"
    first_source = source_root / "user" / "first.md"
    first_snapshot = (
        paths.migrations / "v1-family" / "snapshot" / "user" / "first.md"
    )
    second_source = source_root / "user" / "second.md"
    second_snapshot = (
        paths.migrations / "v1-family" / "snapshot" / "user" / "second.md"
    )
    assert first_source.read_text(encoding="utf-8") == source_texts[
        "user/first.md"
    ].replace(term, "")
    assert not first_snapshot.exists()
    assert second_source.read_text(encoding="utf-8") == source_texts[
        "user/second.md"
    ]
    assert second_snapshot.read_text(encoding="utf-8") == source_texts[
        "user/second.md"
    ]


def test_two_memories_sharing_source_can_be_forgotten_sequentially(
    tmp_path: Path,
):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    source_root = tmp_path / "v1"
    relative = "user/shared.md"
    source = source_root / "user" / "shared.md"
    source.parent.mkdir(parents=True)
    original = "keep\n妻子和儿子\n父母\n"
    source.write_text(original, encoding="utf-8")
    original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    request = {
        "action": "migrate",
        "migration_id": "v1-shared",
        "source_root": str(source_root.resolve()),
        "sources": [
            {
                "path": relative,
                "sha256": original_hash,
                "disposition": "snapshot",
            }
        ],
        "memories": [
            {
                "source_path": relative,
                "memory_markdown": family_memory().to_markdown(),
            },
            {
                "source_path": relative,
                "memory_markdown": parent_memory().to_markdown(),
            },
        ],
    }
    assert migrate_v1(paths, request).status == "accepted"
    snapshot = (
        paths.migrations / "v1-shared" / "snapshot" / "user" / "shared.md"
    )

    first = forget(paths, authorized_request())

    assert first.status == "accepted", first
    for path in (source, snapshot):
        text = path.read_text(encoding="utf-8")
        assert "妻子和儿子" not in text
        assert "父母" in text
        assert "keep" in text
    manifest_path = paths.migrations / "v1-shared" / "manifest.json"
    after_first = json.loads(manifest_path.read_text(encoding="utf-8"))
    retained_source = after_first["sources"][0]
    assert retained_source["sha256"] == original_hash
    assert retained_source["current_sha256"] == hashlib.sha256(
        source.read_bytes()
    ).hexdigest()
    assert retained_source["current_sha256"] != original_hash
    assert retained_source["pending_rewrite_sha256"] is None
    assert {entry["id"] for entry in after_first["memories"]} == {
        "parent-history"
    }
    assert after_first["forget_operations"][-1]["status"] == "completed"

    second_request = {
        "memory_id": "parent-history",
        "suppression_scope": "parent_history",
        "authorization": "explicit_user_request",
        "verification_terms": ["父母"],
    }
    second = forget(paths, second_request)

    assert second.status == "accepted", second
    assert source.read_text(encoding="utf-8") == "keep\n\n\n"
    assert not snapshot.exists()
    after_second = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert after_second["sources"] == []
    assert after_second["memories"] == []
    assert [marker["status"] for marker in after_second["forget_operations"]] == [
        "completed",
        "completed",
    ]


def test_forget_rejects_same_content_registered_source_replacement(
    tmp_path: Path,
):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    source_root = tmp_path / "v1"
    migrate_family(paths, source_root)
    source = source_root / "user" / "family.md"
    before = source.read_bytes()
    old_identity = (source.stat().st_dev, source.stat().st_ino)
    replacement = source.with_suffix(".replacement")
    replacement.write_bytes(before)
    os.replace(replacement, source)
    assert (source.stat().st_dev, source.stat().st_ino) != old_identity

    response = forget(paths, authorized_request())

    assert response.status == "failed"
    assert response.error["code"] == "legacy_source_replaced"
    assert source.read_bytes() == before
    assert MemoryStore(paths).get_memory("family-structure") == family_memory()


def test_forget_preserves_unrelated_migration_source_metadata(
    tmp_path: Path,
):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    source_root = tmp_path / "v1"
    source_texts = {
        "user/primary.md": "keep\n妻子和儿子\n",
        "user/unrelated.md": "unrelated snapshot\n",
        "user/ignored.md": "ignored metadata\n",
        "user/secret.bin": "excluded metadata\n",
    }
    sources = []
    for relative, text in source_texts.items():
        source = source_root / Path(*relative.split("/"))
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(text, encoding="utf-8")
        disposition = {
            "user/primary.md": "snapshot",
            "user/unrelated.md": "snapshot",
            "user/ignored.md": "ignored",
            "user/secret.bin": "excluded_sensitive",
        }[relative]
        sources.append(
            {
                "path": relative,
                "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "disposition": disposition,
            }
        )
    migration = {
        "action": "migrate",
        "migration_id": "v1-metadata",
        "source_root": str(source_root.resolve()),
        "sources": sources,
        "memories": [
            {
                "source_path": "user/primary.md",
                "memory_markdown": family_memory().to_markdown(),
            }
        ],
    }
    assert migrate_v1(paths, migration).status == "accepted"
    migration_root = paths.migrations / "v1-metadata"

    response = forget(paths, authorized_request())

    assert response.status == "accepted", response
    manifest = json.loads(
        (migration_root / "manifest.json").read_text(encoding="utf-8")
    )
    assert {source["path"] for source in manifest["sources"]} == {
        "user/unrelated.md",
        "user/ignored.md",
        "user/secret.bin",
    }
    assert not (migration_root / "snapshot" / "user" / "primary.md").exists()
    assert (
        migration_root / "snapshot" / "user" / "unrelated.md"
    ).read_text(encoding="utf-8") == "unrelated snapshot\n"


def test_forget_rejects_tampered_manifest_before_external_writes(tmp_path: Path):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    source_root = tmp_path / "v1"
    migrate_family(paths, source_root)
    source = source_root / "user" / "family.md"
    before = source.read_bytes()
    manifest_path = paths.migrations / "v1-family" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["source_root"] = str((tmp_path / "redirected").resolve())
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )

    response = forget(paths, authorized_request())

    assert response.status == "failed"
    assert response.error["code"] == "invalid_migration_manifest"
    assert source.read_bytes() == before
    assert MemoryStore(paths).get_memory("family-structure") == family_memory()


def test_forget_rejects_missing_source_receipt_evidence(tmp_path: Path):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    source_root = tmp_path / "v1"
    migrate_family(paths, source_root)
    receipt_path = paths.receipts / "source-keys.json"
    registry = json.loads(receipt_path.read_text(encoding="utf-8"))
    registry["sources"] = []
    receipt_path.write_text(
        json.dumps(registry, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    source = source_root / "user" / "family.md"
    before = source.read_bytes()

    response = forget(paths, authorized_request())

    assert response.status == "failed"
    assert response.error["code"] == "migration_evidence_mismatch"
    assert source.read_bytes() == before


def test_forget_rejects_changed_registered_legacy_source(tmp_path: Path):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    source_root = tmp_path / "v1"
    migrate_family(paths, source_root)
    source = source_root / "user" / "family.md"
    source.write_text(
        source.read_text(encoding="utf-8") + "later legitimate change\n",
        encoding="utf-8",
    )
    before = source.read_bytes()

    response = forget(paths, authorized_request())

    assert response.status == "failed"
    assert response.error["code"] == "legacy_source_changed"
    assert source.read_bytes() == before


def test_forget_rejects_snapshot_symlink_escape(tmp_path: Path):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    source_root = tmp_path / "v1"
    migrate_family(paths, source_root)
    snapshot = (
        paths.migrations / "v1-family" / "snapshot" / "user" / "family.md"
    )
    snapshot.unlink()
    snapshot.parent.rmdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    outside_file = outside / "family.md"
    outside_file.write_text("妻子和儿子\n", encoding="utf-8")
    _link_directory(snapshot.parent, outside)

    response = forget(paths, authorized_request())

    assert response.status == "failed"
    assert response.error["code"] == "migration_path_escape"
    assert outside_file.read_text(encoding="utf-8") == "妻子和儿子\n"


@pytest.mark.parametrize("boundary", ["legacy", "managed_purge", "tombstone"])
def test_forget_rolls_back_injected_write_failures_and_exact_retry_converges(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    boundary: str,
):
    from agc_runtime import forget_service

    paths = MemoryPaths.from_root(tmp_path / "memory")
    source_root = tmp_path / "v1"
    relative_source = "user/妻子和儿子.md"
    migrate_family(
        paths,
        source_root,
        {
            relative_source: (
                "保留：无关内容\n忘记：妻子和儿子\n保留：其他内容\n"
            )
        },
    )
    source = source_root / Path(*relative_source.split("/"))
    snapshot = (
        paths.migrations
        / "v1-family"
        / "snapshot"
        / Path(*relative_source.split("/"))
    )
    original_source = source.read_bytes()
    original_snapshot = snapshot.read_bytes()
    original_apply = forget_service._apply_forget_operation
    failed = False

    def fail_boundary(operation):
        nonlocal failed
        if operation.category == boundary and not failed:
            failed = True
            raise OSError(f"injected {boundary} failure")
        return original_apply(operation)

    monkeypatch.setattr(
        forget_service, "_apply_forget_operation", fail_boundary
    )
    response = forget(paths, authorized_request())

    assert response.status == "failed"
    assert response.error["code"] == "forget_failed"
    assert source.read_bytes() == original_source
    assert snapshot.read_bytes() == original_snapshot
    assert MemoryStore(paths).get_memory("family-structure") == family_memory()
    assert not list(paths.tombstones.glob("*.json"))
    journals = _forget_journals(paths)
    assert len(journals) == 1
    journal_text = journals[0].read_text(encoding="utf-8")
    assert "妻子和儿子" not in journal_text
    assert hashlib.sha256(original_source).hexdigest() not in journal_text
    assert family_memory().full_meaning not in journal_text

    monkeypatch.setattr(
        forget_service, "_apply_forget_operation", original_apply
    )
    retry = forget(paths, authorized_request())

    assert retry.status == "accepted", retry
    assert not _forget_journals(paths)
    assert "妻子和儿子" not in source.read_text(encoding="utf-8")
    assert not snapshot.exists()


def test_forget_rolls_back_verification_failure_and_retry_converges(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from agc_runtime import forget_service

    paths = MemoryPaths.from_root(tmp_path / "memory")
    source_root = tmp_path / "v1"
    migrate_family(paths, source_root)
    source = source_root / "user" / "family.md"
    before = source.read_bytes()
    original_verify = forget_service._verify_forget_plan

    def fail_verification(*_args, **_kwargs):
        raise RuntimeError("injected verification failure")

    monkeypatch.setattr(
        forget_service, "_verify_forget_plan", fail_verification
    )
    response = forget(paths, authorized_request())

    assert response.status == "failed"
    assert response.error["code"] == "forget_failed"
    assert source.read_bytes() == before
    assert MemoryStore(paths).get_memory("family-structure") == family_memory()
    assert _forget_journals(paths)

    monkeypatch.setattr(
        forget_service, "_verify_forget_plan", original_verify
    )
    retry = forget(paths, authorized_request())

    assert retry.status == "accepted"
    assert not _forget_journals(paths)


def test_forget_journal_rejects_changed_request_and_resumes_partial_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from agc_runtime import forget_service

    paths = MemoryPaths.from_root(tmp_path / "memory")
    source_root = tmp_path / "v1"
    migrate_family(paths, source_root)
    original_apply = forget_service._apply_forget_operation
    original_rollback = forget_service._rollback_forget_operations

    def fail_tombstone(operation):
        if operation.category == "tombstone":
            raise OSError("simulated interruption after managed mutations")
        return original_apply(operation)

    monkeypatch.setattr(
        forget_service, "_apply_forget_operation", fail_tombstone
    )
    monkeypatch.setattr(
        forget_service, "_rollback_forget_operations", lambda *_args: None
    )
    interrupted = forget(paths, authorized_request())

    assert interrupted.status == "failed"
    assert _forget_journals(paths)
    with pytest.raises(FileNotFoundError):
        MemoryStore(paths).get_memory("family-structure")

    changed = authorized_request()
    changed["suppression_scope"] = "different_scope"
    conflict = forget(paths, changed)
    assert conflict.status == "failed"
    assert conflict.error["code"] == "forget_request_conflict"

    monkeypatch.setattr(
        forget_service, "_apply_forget_operation", original_apply
    )
    monkeypatch.setattr(
        forget_service, "_rollback_forget_operations", original_rollback
    )
    retry = forget(paths, authorized_request())

    assert retry.status == "accepted"
    assert not _forget_journals(paths)


def test_forget_journal_is_content_free_integrity_bound_and_not_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from agc_runtime import forget_service

    paths = MemoryPaths.from_root(tmp_path / "memory")
    source_root = tmp_path / "v1"
    migrate_family(paths, source_root)

    unrelated_root = tmp_path / "unrelated-v1"
    unrelated_source = unrelated_root / "user" / "unrelated.md"
    unrelated_source.parent.mkdir(parents=True)
    unrelated_source.write_text("unrelated\n", encoding="utf-8")
    unrelated_snapshot = (
        paths.migrations
        / "v1-unrelated"
        / "snapshot"
        / "user"
        / "unrelated.md"
    )
    unrelated_snapshot.parent.mkdir(parents=True)
    unrelated_snapshot.write_text("unrelated\n", encoding="utf-8")
    source_stat = unrelated_source.stat()
    unrelated_hash = hashlib.sha256(unrelated_source.read_bytes()).hexdigest()
    original_manifest = json.loads(
        (
            paths.migrations / "v1-family" / "manifest.json"
        ).read_text(encoding="utf-8")
    )
    unrelated_manifest = json.loads(json.dumps(original_manifest))
    unrelated_manifest.update(
        {
            "migration_id": "v1-unrelated",
            "request_digest": "b" * 64,
            "source_root": str(unrelated_root.resolve()),
            "memories": [],
            "migrated_ids": [],
            "forget_operations": [],
        }
    )
    unrelated_manifest["sources"] = [
        {
            **unrelated_manifest["sources"][0],
            "path": "user/unrelated.md",
            "sha256": unrelated_hash,
            "current_sha256": unrelated_hash,
            "canonical_path": str(unrelated_source.resolve()),
            "file_identity": {
                "device": source_stat.st_dev,
                "inode": source_stat.st_ino,
            },
        }
    ]
    unrelated_manifest["counts"] = {
        "sources": 1,
        "snapshots": 1,
        "ignored": 0,
        "excluded_sensitive": 0,
        "memories": 0,
    }
    unrelated_manifest["integrity_sha256"] = migration_manifest_integrity(
        unrelated_manifest
    )
    unrelated_manifest_path = (
        paths.migrations / "v1-unrelated" / "manifest.json"
    )
    unrelated_manifest_path.write_text(
        json.dumps(
            unrelated_manifest,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    original_apply = forget_service._apply_forget_operation
    failed = False

    def fail_legacy(operation):
        nonlocal failed
        if operation.category == "legacy" and not failed:
            failed = True
            raise OSError("simulated interruption")
        return original_apply(operation)

    monkeypatch.setattr(
        forget_service, "_apply_forget_operation", fail_legacy
    )
    interrupted = forget(paths, authorized_request())
    assert interrupted.status == "failed"
    journal_path = _forget_journals(paths)[0]
    original_journal = json.loads(journal_path.read_text(encoding="utf-8"))
    assert "migration_ids" not in original_journal
    assert set(original_journal) == {
        "schema_version",
        "operation",
        "memory_id",
        "request_digest",
        "operation_id",
        "status",
        "integrity_sha256",
    }

    tampered = {**original_journal, "operation_id": "f" * 64}
    journal_path.write_text(
        json.dumps(tampered, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    rejected = forget(paths, authorized_request())
    assert rejected.status == "failed"
    assert rejected.error["code"] == "invalid_forget_journal"
    assert unrelated_source.read_text(encoding="utf-8") == "unrelated\n"
    assert unrelated_snapshot.read_text(encoding="utf-8") == "unrelated\n"

    journal_path.write_text(
        json.dumps(original_journal, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        forget_service, "_apply_forget_operation", original_apply
    )
    retry = forget(paths, authorized_request())

    assert retry.status == "accepted", retry
    assert unrelated_source.read_text(encoding="utf-8") == "unrelated\n"
    assert unrelated_snapshot.read_text(encoding="utf-8") == "unrelated\n"


def test_retry_rejects_identical_pre_forget_source_replacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from agc_runtime import forget_service

    paths = MemoryPaths.from_root(tmp_path / "memory")
    source_root = tmp_path / "v1"
    migrate_family(paths, source_root)
    source = source_root / "user" / "family.md"
    original = source.read_bytes()
    original_apply = forget_service._apply_forget_operation
    failed = False

    def interrupt_before_legacy(operation):
        nonlocal failed
        if operation.category == "legacy" and not failed:
            failed = True
            raise OSError("simulated interruption before legacy rewrite")
        return original_apply(operation)

    monkeypatch.setattr(
        forget_service, "_apply_forget_operation", interrupt_before_legacy
    )
    monkeypatch.setattr(
        forget_service, "_rollback_forget_operations", lambda *_args: None
    )
    interrupted = forget(paths, authorized_request())

    assert interrupted.status == "failed"
    assert _forget_journals(paths)
    manifest_path = paths.migrations / "v1-family" / "manifest.json"
    interrupted_manifest = json.loads(
        manifest_path.read_text(encoding="utf-8")
    )
    pending_hash = interrupted_manifest["sources"][0][
        "pending_rewrite_sha256"
    ]
    assert pending_hash is not None
    assert pending_hash != interrupted_manifest["sources"][0]["current_sha256"]

    replacement = source.with_suffix(".replacement")
    replacement.write_bytes(original)
    old_identity = (source.stat().st_dev, source.stat().st_ino)
    os.replace(replacement, source)
    assert (source.stat().st_dev, source.stat().st_ino) != old_identity
    monkeypatch.setattr(
        forget_service, "_apply_forget_operation", original_apply
    )

    retry = forget(paths, authorized_request())

    assert retry.status == "failed"
    assert retry.error["code"] == "legacy_source_replaced"
    assert source.read_bytes() == original
    assert MemoryStore(paths).get_memory("family-structure") == family_memory()
    assert _forget_journals(paths)


def test_retry_accepts_only_manifest_bound_interrupted_rewrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from agc_runtime import forget_service

    paths = MemoryPaths.from_root(tmp_path / "memory")
    source_root = tmp_path / "v1"
    migrate_family(paths, source_root)
    source = source_root / "user" / "family.md"
    original_apply = forget_service._apply_forget_operation
    original_rollback = forget_service._rollback_forget_operations
    failed = False

    def interrupt_before_snapshot(operation):
        nonlocal failed
        if operation.category == "snapshot" and not failed:
            failed = True
            raise OSError("simulated interruption after legacy rewrite")
        return original_apply(operation)

    monkeypatch.setattr(
        forget_service, "_apply_forget_operation", interrupt_before_snapshot
    )
    monkeypatch.setattr(
        forget_service, "_rollback_forget_operations", lambda *_args: None
    )
    interrupted = forget(paths, authorized_request())

    assert interrupted.status == "failed"
    assert "妻子和儿子" not in source.read_text(encoding="utf-8")
    manifest = json.loads(
        (
            paths.migrations / "v1-family" / "manifest.json"
        ).read_text(encoding="utf-8")
    )
    assert manifest["sources"][0]["pending_rewrite_sha256"] == hashlib.sha256(
        source.read_bytes()
    ).hexdigest()

    monkeypatch.setattr(
        forget_service, "_apply_forget_operation", original_apply
    )
    monkeypatch.setattr(
        forget_service, "_rollback_forget_operations", original_rollback
    )
    retry = forget(paths, authorized_request())

    assert retry.status == "accepted", retry
    assert not _forget_journals(paths)
