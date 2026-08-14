from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest


def _identity_contracts():
    from agc_runtime import capture_source, project_identity

    return capture_source, project_identity


def _make_git_worktree(root: Path, common_dir: Path) -> None:
    root.mkdir(parents=True)
    relative = os.path.relpath(common_dir, root)
    (root / ".git").write_text(f"gitdir: {relative}/worktrees/w1\n", encoding="utf-8")
    admin = common_dir / "worktrees" / "w1"
    admin.mkdir(parents=True)
    (admin / "commondir").write_text("../..\n", encoding="utf-8")


def test_project_identity_resolution_order_and_content_free_values(tmp_path: Path):
    source, identity = _identity_contracts()
    root = tmp_path / "project"
    common = tmp_path / "repo.git"
    _make_git_worktree(root, common)
    root_key = source.source_root_id_for(root)
    common_key = source.source_root_id_for(common)

    explicit = identity.resolve_project_identity(
        root,
        explicit_registry={root_key: "project:explicit"},
        git_registry={common_key: "project:git"},
        generated_registry={root_key: "project:generated"},
    )
    git = identity.resolve_project_identity(
        root,
        git_registry={common_key: "project:git"},
        generated_registry={root_key: "project:generated"},
    )
    generated = identity.resolve_project_identity(
        root,
        generated_registry={root_key: "project:generated"},
    )
    unknown = identity.resolve_project_identity(root)

    assert explicit == identity.ProjectIdentity.from_mapping(
        {"schema_version": 1, "project_id": "project:explicit", "resolution": "explicit_registry"}
    )
    assert git.resolution == "git_common_dir_registry"
    assert generated.resolution == "generated_registry"
    assert unknown is None
    for identity in (explicit, git, generated):
        assert str(tmp_path) not in repr(identity.to_mapping())


def test_project_identity_rejects_absolute_paths_and_unknown_fields():
    _, identity = _identity_contracts()
    for absolute in ("C:\\private\\repo", "C:/private/repo", "/home/private/repo"):
        with pytest.raises(ValueError, match="project_id"):
            identity.ProjectIdentity.from_mapping(
                {"schema_version": 1, "project_id": absolute, "resolution": "explicit_registry"}
            )
    with pytest.raises(ValueError, match="unknown"):
        identity.ProjectIdentity.from_mapping(
            {"schema_version": 1, "project_id": "project:one", "resolution": "explicit_registry", "path": "C:\\private"}
        )


@pytest.mark.skipif(os.name != "nt", reason="Windows canonical path identity")
def test_windows_canonical_source_identity_handles_case_unicode_long_paths_and_junctions(tmp_path: Path):
    source, _ = _identity_contracts()
    physical = tmp_path / ("资料" + "x" * 80) / ("nested" + "y" * 80)
    physical.mkdir(parents=True)
    alias = tmp_path / "alias"
    created = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(alias), str(physical)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert created.returncode == 0, created.stdout + created.stderr

    case_variant = Path(str(physical).swapcase())
    assert source.canonical_source_root(case_variant) == source.canonical_source_root(physical)
    assert source.source_root_id_for(case_variant) == source.source_root_id_for(physical)
    assert source.source_root_id_for(alias) == source.source_root_id_for(physical)


def test_canonical_source_root_requires_an_existing_directory(tmp_path: Path):
    source, _ = _identity_contracts()
    with pytest.raises(ValueError, match="existing directory"):
        source.canonical_source_root(tmp_path / "missing")
    file_path = tmp_path / "file"
    file_path.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="existing directory"):
        source.canonical_source_root(file_path)
