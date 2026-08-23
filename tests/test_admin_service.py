import json
import zipfile
from dataclasses import replace
from pathlib import Path

import pytest

from agc_runtime.admin_service import dispatch_admin
from agc_runtime.catalog import rebuild_catalog
from agc_runtime.contracts import SourceKey
from agc_runtime.forget_service import forget
from agc_runtime.models import MemoryItem
from agc_runtime.paths import MemoryPaths
from agc_runtime.read_service import dispatch_read
from agc_runtime.store import MemoryStore
from agc_runtime.utf8_io import atomic_write_text


def principle() -> MemoryItem:
    fixture = Path(__file__).parent / "fixtures" / "active-principle.md"
    return MemoryItem.from_markdown(fixture.read_text(encoding="utf-8"))


def family() -> MemoryItem:
    item = principle()
    return replace(
        item,
        id="family-structure",
        kind="identity",
        subkind="family_structure",
        temporal=replace(item.temporal, type="evolving"),
        recall=replace(
            item.recall,
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


def test_init_creates_v2_layout_and_runtime_config(tmp_path: Path):
    paths = MemoryPaths.from_root(tmp_path / "memory")

    response = dispatch_admin(paths, {"action": "init"})

    assert response.status == "accepted"
    assert (paths.root / "schema-version").read_text(encoding="utf-8") == "2\n"
    config = (paths.root / "config.yaml").read_text(encoding="utf-8")
    assert "sensitive_storage: disabled" in config
    assert "schema_version: 3" in config
    assert "overview_token_budget: 250" in config
    assert "compact_card_token_budget: 600" in config
    assert "enabled: false" in config
    assert "mode: off" in config
    assert paths.migrations.is_dir()
    assert paths.capture.cursor_hmac_key.is_file()
    assert len(paths.capture.cursor_hmac_key.read_bytes()) == 32


def test_validate_reports_invalid_memory_without_cataloging_it(tmp_path: Path):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    dispatch_admin(paths, {"action": "init"})
    invalid = principle().to_markdown().replace(
        "kind: principle", "kind: personality", 1
    )
    atomic_write_text(
        paths.memories / "principle" / "invalid.md",
        invalid,
    )

    response = dispatch_admin(paths, {"action": "validate"})

    assert response.status == "failed"
    assert response.data["invalid_count"] >= 1
    assert any("invalid kind" in issue["message"] for issue in response.data["issues"])


def test_validate_rejects_invalid_runtime_config(tmp_path: Path):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    dispatch_admin(paths, {"action": "init"})
    atomic_write_text(
        paths.root / "config.yaml",
        "schema_version: 3\nsensitive_storage: enabled\n",
    )

    response = dispatch_admin(paths, {"action": "validate"})

    assert response.status == "failed"
    assert any(
        "missing runtime config field: capture" in issue["message"]
        for issue in response.data["issues"]
    )


def test_validate_reports_invalid_review_graph_content_safely(
    tmp_path: Path, visible_capture_observations
):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    assert dispatch_admin(paths, {"action": "init"}).status == "accepted"
    _store, observations = visible_capture_observations(
        paths,
        [
            "Private invalid-filename statement.",
            "Private unknown-outcome statement.",
            "Private dangling-target statement.",
        ],
    )
    MemoryStore(paths).create_memory(
        principle(), SourceKey("codex-task:t1", "r1", "a" * 64)
    )
    rebuild_catalog(paths)

    def write_review(filename: str, observation_id: str, outcome: str, target):
        atomic_write_text(
            paths.capture.reviews / filename,
            json.dumps(
                {
                    "schema_version": 1,
                    "observation_id": observation_id,
                    "outcome": outcome,
                    "target_memory_id": target,
                    "reviewed_at": "2026-08-23T12:00:00Z",
                },
                sort_keys=True,
            )
            + "\n",
        )

    write_review("bad review.json", observations[0].observation_id, "discard", None)
    write_review(
        f"{observations[1].observation_id}.json",
        observations[1].observation_id,
        "unknown",
        None,
    )
    write_review(
        f"{observations[2].observation_id}.json",
        observations[2].observation_id,
        "draft",
        "missing-memory",
    )
    orphan_id = "co_" + "f" * 64
    write_review(f"{orphan_id}.json", orphan_id, "discard", None)

    response = dispatch_admin(paths, {"action": "validate"})

    assert response.status == "failed"
    review_issues = [
        issue
        for issue in response.data["issues"]
        if issue["path"].startswith(".runtime/capture/reviews/")
    ]
    assert len(review_issues) >= 4
    rendered = json.dumps(review_issues, ensure_ascii=False)
    assert "<invalid-name>" in rendered
    assert "outcome" in rendered
    assert "target" in rendered
    assert "orphan" in rendered
    assert str(paths.root) not in rendered
    assert "Private " not in rendered


def test_backup_is_deterministic_and_excludes_runtime_noise(tmp_path: Path):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    dispatch_admin(paths, {"action": "init"})
    MemoryStore(paths).create_memory(
        principle(), SourceKey("codex-task:t1", "r1", "a" * 64)
    )
    rebuild_catalog(paths)
    atomic_write_text(paths.locks / "orphan.lock", "noise\n")
    atomic_write_text(paths.cache / "partial.tmp", "noise\n")

    first = dispatch_admin(paths, {"action": "backup"})
    second = dispatch_admin(paths, {"action": "backup"})

    assert first.status == "accepted"
    assert first.data["archive_sha256"] == second.data["archive_sha256"]
    assert all(
        ".runtime/locks" not in item["path"]
        and not item["path"].endswith(".tmp")
        and ".runtime/backups" not in item["path"]
        and item["path"] != ".runtime/capture/cursor-hmac-key"
        for item in first.data["manifest"]["files"]
    )


def test_restore_rejects_corrupted_backup_before_changes(tmp_path: Path):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    dispatch_admin(paths, {"action": "init"})
    MemoryStore(paths).create_memory(
        principle(), SourceKey("codex-task:t1", "r1", "a" * 64)
    )
    rebuild_catalog(paths)
    backup = dispatch_admin(paths, {"action": "backup"}).data["backup_path"]
    with zipfile.ZipFile(backup, "r") as archive:
        entries = {
            name: archive.read(name)
            for name in archive.namelist()
        }
    entries["config.yaml"] = b"tampered: true\n"
    with zipfile.ZipFile(backup, "w") as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    before = dispatch_read(
        paths, {"action": "get", "id": "difficult-but-correct"}
    )

    response = dispatch_admin(
        paths, {"action": "restore", "backup_path": backup}
    )

    assert response.status == "failed"
    assert response.error["code"] == "backup_verification_failed"
    assert before.data == dispatch_read(
        paths, {"action": "get", "id": "difficult-but-correct"}
    ).data


def test_restore_recovers_memory_from_verified_backup(tmp_path: Path):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    dispatch_admin(paths, {"action": "init"})
    cursor_key_before = paths.capture.cursor_hmac_key.read_bytes()
    MemoryStore(paths).create_memory(
        principle(), SourceKey("codex-task:t1", "r1", "a" * 64)
    )
    rebuild_catalog(paths)
    backup = dispatch_admin(paths, {"action": "backup"}).data["backup_path"]
    memory_file = (
        paths.memories / "principle" / "difficult-but-correct.md"
    )
    memory_file.unlink()
    rebuild_catalog(paths)

    response = dispatch_admin(
        paths, {"action": "restore", "backup_path": backup}
    )

    assert response.status == "accepted"
    assert paths.capture.cursor_hmac_key.read_bytes() == cursor_key_before
    assert dispatch_read(
        paths, {"action": "get", "id": "difficult-but-correct"}
    ).status == "accepted"


def test_restore_write_failure_rolls_back_current_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    dispatch_admin(paths, {"action": "init"})
    item = principle()
    MemoryStore(paths).create_memory(
        item, SourceKey("codex-task:t1", "r1", "a" * 64)
    )
    rebuild_catalog(paths)
    backup = dispatch_admin(paths, {"action": "backup"}).data["backup_path"]
    current = replace(item, memory_card="当前状态应保留")
    memory_file = paths.memories / "principle" / f"{item.id}.md"
    atomic_write_text(memory_file, current.to_markdown())
    rebuild_catalog(paths)

    from agc_runtime import admin_service

    original_write = admin_service.atomic_write_text
    failed = False

    def fail_once(path, text):
        nonlocal failed
        if path == memory_file and not failed:
            failed = True
            raise OSError("injected restore write failure")
        return original_write(path, text)

    monkeypatch.setattr(admin_service, "atomic_write_text", fail_once)

    response = dispatch_admin(
        paths, {"action": "restore", "backup_path": backup}
    )

    assert response.status == "failed"
    assert MemoryStore(paths).get_memory(item.id).memory_card == "当前状态应保留"


def test_restore_cannot_resurrect_forgotten_memory(tmp_path: Path):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    dispatch_admin(paths, {"action": "init"})
    MemoryStore(paths).create_memory(
        family(), SourceKey("codex-task:family", "r1", "a" * 64)
    )
    rebuild_catalog(paths)
    backup = dispatch_admin(paths, {"action": "backup"}).data["backup_path"]
    forget(
        paths,
        {
            "memory_id": "family-structure",
            "suppression_scope": "family_structure",
            "authorization": "explicit_user_request",
            "verification_terms": ["妻子和儿子"],
        },
    )

    response = dispatch_admin(
        paths, {"action": "restore", "backup_path": backup}
    )

    assert response.status == "accepted"
    assert response.data["suppressed_memory_ids"] == ["family-structure"]
    assert dispatch_read(
        paths, {"action": "get", "id": "family-structure"}
    ).status == "failed"


def test_migrate_routes_to_migration_service(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from agc_runtime import admin_service
    from agc_runtime.contracts import ToolResponse

    called = {}

    def fake_migrate(paths, request):
        called["paths"] = paths
        called["request"] = request
        return ToolResponse(
            tool="agc.admin",
            action="migrate",
            status="accepted",
            data={"code": "migration_completed"},
        )

    monkeypatch.setattr(admin_service, "migrate_v1", fake_migrate, raising=False)
    paths = MemoryPaths.from_root(tmp_path / "memory")
    request = {"action": "migrate"}
    response = dispatch_admin(
        paths,
        request,
    )

    assert response.status == "accepted"
    assert response.data["code"] == "migration_completed"
    assert called == {"paths": paths, "request": request}
