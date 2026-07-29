import json
import zipfile
from dataclasses import replace
from pathlib import Path

import pytest

from agc_runtime.catalog import rebuild_catalog
from agc_runtime.contracts import SourceKey
from agc_runtime.forget_service import forget
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


def test_write_dispatch_exposes_authorized_forget(populated):
    paths, _source_task = populated

    response = dispatch_write(
        paths, {"action": "forget", **authorized_request()}
    )

    assert response.status == "accepted"
    assert response.action == "forget"
