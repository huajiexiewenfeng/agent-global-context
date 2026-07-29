from __future__ import annotations

import codecs
import json
import os
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "install-local.ps1"
SOURCE_SKILL = ROOT / "skills" / "agent-global-context"
BEGIN_MARKER = "# BEGIN agent-global-context"
END_MARKER = "# END agent-global-context"
RETIRED_SKILLS = (
    "agent-global-context-recall",
    "agent-global-context-commit",
    "agent-global-context-capture",
    "agent-global-context-review",
)
RESULT_KEYS = {
    "repository_root",
    "skills_root",
    "codex_config",
    "memory_root",
    "install_root",
    "mcp_executable",
    "launcher",
    "backup_path",
    "restart_required",
}


def _powershell() -> str:
    for name in ("pwsh", "powershell.exe"):
        executable = shutil.which(name)
        if executable:
            return executable
    pytest.skip("PowerShell is required for the local installer integration test")


def _write_utf8(path: Path, text: str, *, newline: str = "\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.replace("\n", newline).encode("utf-8"))


def _create_repository(root: Path) -> Path:
    repository = root / "repository"
    target = repository / "skills" / "agent-global-context"
    shutil.copytree(SOURCE_SKILL, target)
    return repository


def _create_active_install(root: Path) -> tuple[Path, Path]:
    skills = root / "active-skills"
    skills.mkdir()
    for name in ("agent-global-context", *RETIRED_SKILLS):
        _write_utf8(
            skills / name / "SKILL.md",
            f"---\nname: {name}\n---\n\nalpha café 中文 {name}\n",
        )
    _write_utf8(skills / "unrelated-skill" / "SKILL.md", "keep me\n")

    config = root / "codex" / "config.toml"
    _write_utf8(
        config,
        'model = "gpt-test"\n\n[unrelated]\nlabel = "café 中文"\n',
        newline="\r\n",
    )
    return skills, config


def _invoke(
    repository: Path,
    skills: Path,
    config: Path,
    memory: Path,
    install: Path,
    *,
    env: dict[str, str] | None = None,
    check: bool = True,
) -> tuple[subprocess.CompletedProcess[bytes], dict[str, object] | None]:
    command = [
        _powershell(),
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(SCRIPT),
        "-RepositoryRoot",
        str(repository),
        "-SkillsRoot",
        str(skills),
        "-CodexConfig",
        str(config),
        "-MemoryRoot",
        str(memory),
        "-InstallRoot",
        str(install),
        "-SkipRuntimeInstall",
    ]
    process_env = os.environ.copy()
    if env:
        process_env.update(env)
    completed = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        check=False,
        env=process_env,
    )
    if check:
        assert completed.returncode == 0, (
            completed.stdout.decode("utf-8", errors="replace")
            + completed.stderr.decode("utf-8", errors="replace")
        )
    result = None
    if completed.stdout.strip():
        result = json.loads(completed.stdout.decode("utf-8", errors="strict"))
    return completed, result


def _strict_utf8_without_bom(path: Path) -> str:
    data = path.read_bytes()
    assert not data.startswith(codecs.BOM_UTF8), path
    return data.decode("utf-8", errors="strict")


def _tree_snapshot(root: Path) -> dict[str, bytes]:
    if not root.exists():
        return {}
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _outside_marked_block(config_text: str) -> str:
    begin = config_text.index(BEGIN_MARKER)
    end = config_text.index(END_MARKER, begin) + len(END_MARKER)
    if config_text[end : end + 1] == "\n":
        end += 1
    return config_text[:begin] + config_text[end:]


def _assert_toml_paths(
    config: Path, *, expected_executable: Path, expected_memory: Path
) -> None:
    parsed = tomllib.loads(_strict_utf8_without_bom(config))
    server = parsed["mcp_servers"]["agent_global_context"]
    assert server["enabled"] is True
    assert server["command"] == str(expected_executable.resolve())
    assert server["args"] == []
    assert server["env"]["AGC_MEMORY_ROOT"] == str(expected_memory.resolve())


def test_initial_install_backs_up_alpha_skills_and_registers_valid_toml(
    tmp_path: Path,
):
    repository = _create_repository(tmp_path)
    skills, config = _create_active_install(tmp_path)
    memory = tmp_path / "memory-v2"
    install = tmp_path / "runtime"
    original_config = config.read_bytes()

    _, result = _invoke(repository, skills, config, memory, install)

    assert result is not None
    assert set(result) == RESULT_KEYS
    assert result["restart_required"] is True
    assert result["repository_root"] == str(repository.resolve())
    assert result["skills_root"] == str(skills.resolve())
    assert result["codex_config"] == str(config.resolve())
    assert result["memory_root"] == str(memory.resolve())
    assert result["install_root"] == str(install.resolve())

    expected_executable = install / "venv" / "Scripts" / "agc-mcp.exe"
    launcher = install / "bin" / "agc-mcp.cmd"
    assert result["mcp_executable"] == str(expected_executable.resolve())
    assert result["launcher"] == str(launcher.resolve())

    active_agc = sorted(
        path.name for path in skills.glob("agent-global-context*") if path.is_dir()
    )
    assert active_agc == ["agent-global-context"]
    assert _tree_snapshot(skills / "agent-global-context") == _tree_snapshot(
        repository / "skills" / "agent-global-context"
    )
    assert (skills / "unrelated-skill" / "SKILL.md").read_bytes() == b"keep me\n"

    backup = Path(str(result["backup_path"]))
    assert backup.is_dir()
    assert (backup / "codex-config" / config.name).read_bytes() == original_config
    for name in ("agent-global-context", *RETIRED_SKILLS):
        assert (backup / "skills" / name / "SKILL.md").is_file()
        assert not (skills / name).exists() or name == "agent-global-context"

    config_text = _strict_utf8_without_bom(config)
    assert "\r" not in config_text
    assert config_text.count(BEGIN_MARKER) == 1
    assert config_text.count(END_MARKER) == 1
    assert _outside_marked_block(config_text) == (
        'model = "gpt-test"\n\n[unrelated]\nlabel = "café 中文"\n\n'
    )
    _assert_toml_paths(
        config,
        expected_executable=expected_executable,
        expected_memory=memory,
    )

    launcher_text = _strict_utf8_without_bom(launcher)
    assert launcher_text == f'@"{expected_executable.resolve()}" %*\n'
    for path in (repository / "skills" / "agent-global-context").rglob("*.md"):
        relative = path.relative_to(repository / "skills" / "agent-global-context")
        assert _strict_utf8_without_bom(skills / "agent-global-context" / relative)


def test_rerun_is_noop_then_memory_change_replaces_only_marked_block(
    tmp_path: Path,
):
    repository = _create_repository(tmp_path)
    skills, config = _create_active_install(tmp_path)
    install = tmp_path / "runtime"
    first_memory = tmp_path / "memory-v2"

    _, first = _invoke(repository, skills, config, first_memory, install)
    first_config = config.read_bytes()
    first_backup = Path(str(first["backup_path"]))
    first_backup_snapshot = _tree_snapshot(first_backup)

    _, second = _invoke(repository, skills, config, first_memory, install)
    assert second["backup_path"] is None
    assert config.read_bytes() == first_config
    assert _tree_snapshot(first_backup) == first_backup_snapshot
    assert len(list((install / "backups").iterdir())) == 1

    second_memory = tmp_path / "memory-v2-next"
    before_change = _strict_utf8_without_bom(config)
    _, third = _invoke(repository, skills, config, second_memory, install)
    after_change = _strict_utf8_without_bom(config)

    assert third["backup_path"] is not None
    assert Path(str(third["backup_path"])) != first_backup
    assert before_change.count(BEGIN_MARKER) == after_change.count(BEGIN_MARKER) == 1
    assert before_change.count(END_MARKER) == after_change.count(END_MARKER) == 1
    assert _outside_marked_block(after_change) == _outside_marked_block(before_change)
    _assert_toml_paths(
        config,
        expected_executable=install / "venv" / "Scripts" / "agc-mcp.exe",
        expected_memory=second_memory,
    )


def test_repeated_changes_use_unique_backups_without_overwriting_history(
    tmp_path: Path,
):
    repository = _create_repository(tmp_path)
    skills, config = _create_active_install(tmp_path)
    install = tmp_path / "runtime"

    results = []
    snapshots: dict[Path, dict[str, bytes]] = {}
    for index in range(4):
        _, result = _invoke(
            repository,
            skills,
            config,
            tmp_path / f"memory-{index}",
            install,
        )
        backup = Path(str(result["backup_path"]))
        results.append(backup)
        for old_backup, snapshot in snapshots.items():
            assert _tree_snapshot(old_backup) == snapshot
        snapshots[backup] = _tree_snapshot(backup)

    assert len(set(results)) == len(results)
    assert set(results) == set((install / "backups").iterdir())


@pytest.mark.parametrize(
    "config_text",
    [
        f'{BEGIN_MARKER}\nvalue = 1\n',
        f'value = 1\n{END_MARKER}\n',
        f'{END_MARKER}\n{BEGIN_MARKER}\n',
        (
            f"{BEGIN_MARKER}\nvalue = 1\n{BEGIN_MARKER}\n"
            f"{END_MARKER}\n{END_MARKER}\n"
        ),
        (
            f"{BEGIN_MARKER}\nvalue = 1\n{END_MARKER}\n"
            f"{BEGIN_MARKER}\nvalue = 2\n{END_MARKER}\n"
        ),
    ],
)
def test_malformed_markers_fail_before_active_mutation(
    tmp_path: Path, config_text: str
):
    repository = _create_repository(tmp_path)
    skills, config = _create_active_install(tmp_path)
    _write_utf8(config, config_text)
    before_skills = _tree_snapshot(skills)
    before_config = config.read_bytes()
    install = tmp_path / "runtime"

    completed, result = _invoke(
        repository,
        skills,
        config,
        tmp_path / "memory",
        install,
        check=False,
    )

    assert completed.returncode != 0
    assert result is None
    assert config.read_bytes() == before_config
    assert _tree_snapshot(skills) == before_skills
    assert not (install / "backups").exists()


@pytest.mark.parametrize(
    "missing",
    ["repository", "source_skill", "skills", "config"],
)
def test_missing_required_inputs_fail_before_active_mutation(
    tmp_path: Path, missing: str
):
    repository = _create_repository(tmp_path)
    skills, config = _create_active_install(tmp_path)
    if missing == "repository":
        repository = tmp_path / "missing-repository"
    elif missing == "source_skill":
        shutil.rmtree(repository / "skills" / "agent-global-context")
    elif missing == "skills":
        skills = tmp_path / "missing-skills"
    else:
        config.unlink()

    skills_before = _tree_snapshot(tmp_path / "active-skills")
    completed, result = _invoke(
        repository,
        skills,
        config,
        tmp_path / "memory",
        tmp_path / "runtime",
        check=False,
    )

    assert completed.returncode != 0
    assert result is None
    assert _tree_snapshot(tmp_path / "active-skills") == skills_before
    assert not (tmp_path / "runtime" / "backups").exists()


@pytest.mark.parametrize(
    "relationship",
    ["skills_in_repository", "install_in_skills", "config_in_public_skill"],
)
def test_dangerous_overlapping_paths_fail_before_active_mutation(
    tmp_path: Path, relationship: str
):
    repository = _create_repository(tmp_path)
    skills, config = _create_active_install(tmp_path)
    install = tmp_path / "runtime"
    if relationship == "skills_in_repository":
        skills = repository / "skills"
    elif relationship == "install_in_skills":
        install = skills / "agent-global-context-runtime"
    else:
        config = skills / "agent-global-context" / "config.toml"
        _write_utf8(config, 'model = "test"\n')

    active_root = tmp_path / "active-skills"
    before_skills = _tree_snapshot(active_root)
    before_config = config.read_bytes()
    completed, result = _invoke(
        repository,
        skills,
        config,
        tmp_path / "memory",
        install,
        check=False,
    )

    assert completed.returncode != 0
    assert result is None
    assert config.read_bytes() == before_config
    assert _tree_snapshot(active_root) == before_skills
    assert not (install / "backups").exists()


@pytest.mark.parametrize("source_bytes", [codecs.BOM_UTF8 + b"text\n", b"\xff\n"])
def test_invalid_source_skill_encoding_fails_before_active_mutation(
    tmp_path: Path, source_bytes: bytes
):
    repository = _create_repository(tmp_path)
    skills, config = _create_active_install(tmp_path)
    source = repository / "skills" / "agent-global-context" / "SKILL.md"
    source.write_bytes(source_bytes)
    before_skills = _tree_snapshot(skills)
    before_config = config.read_bytes()

    completed, result = _invoke(
        repository,
        skills,
        config,
        tmp_path / "memory",
        tmp_path / "runtime",
        check=False,
    )

    assert completed.returncode != 0
    assert result is None
    assert config.read_bytes() == before_config
    assert _tree_snapshot(skills) == before_skills
    assert not (tmp_path / "runtime" / "backups").exists()


def test_caught_mid_mutation_failure_restores_config_and_all_skills(
    tmp_path: Path,
):
    repository = _create_repository(tmp_path)
    skills, config = _create_active_install(tmp_path)
    before_skills = _tree_snapshot(skills)
    before_config = config.read_bytes()
    install = tmp_path / "runtime"

    completed, result = _invoke(
        repository,
        skills,
        config,
        tmp_path / "memory",
        install,
        env={"AGC_INSTALL_TEST_FAIL_AFTER": "config"},
        check=False,
    )

    assert completed.returncode != 0
    assert result is None
    assert config.read_bytes() == before_config
    assert _tree_snapshot(skills) == before_skills
    backups = list((install / "backups").iterdir())
    assert len(backups) == 1
    assert _tree_snapshot(backups[0])
