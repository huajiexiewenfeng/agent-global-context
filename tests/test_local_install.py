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
USER_INSTALL_DOCS = (
    ROOT / "README.md",
    ROOT / "README.en.md",
    ROOT / "README.zh.md",
    ROOT / "docs" / "install.md",
)


def _powershell() -> str:
    for name in ("pwsh", "powershell.exe"):
        executable = shutil.which(name)
        if executable:
            return executable
    pytest.skip("PowerShell is required for the local installer integration test")


def _windows_powershell() -> str:
    executable = shutil.which("powershell.exe")
    assert executable, "Windows PowerShell 5.1 is required for this regression"
    return executable


def _create_junction(link: Path, target: Path) -> None:
    completed = subprocess.run(
        ["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, (
        "junction creation failed explicitly: "
        + completed.stdout.decode(errors="replace")
        + completed.stderr.decode(errors="replace")
    )
    assert link.is_dir()


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
    powershell: str | None = None,
    check: bool = True,
) -> tuple[subprocess.CompletedProcess[bytes], dict[str, object] | None]:
    command = [
        powershell or _powershell(),
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


def test_install_root_junction_alias_to_skills_is_rejected_before_writes(
    tmp_path: Path,
):
    repository = _create_repository(tmp_path)
    skills, config = _create_active_install(tmp_path)
    for name in ("agent-global-context", *RETIRED_SKILLS):
        shutil.rmtree(skills / name)
    before_skills = _tree_snapshot(skills)
    before_config = config.read_bytes()
    install = tmp_path / "runtime-junction"
    _create_junction(install, skills)

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


def test_active_agc_skill_junction_is_rejected_before_writes(tmp_path: Path):
    repository = _create_repository(tmp_path)
    skills, config = _create_active_install(tmp_path)
    active = skills / "agent-global-context-recall"
    shutil.rmtree(active)
    junction_target = tmp_path / "junction-target"
    _write_utf8(junction_target / "SKILL.md", "external sentinel\n")
    _create_junction(active, junction_target)
    before_config = config.read_bytes()
    before_target = _tree_snapshot(junction_target)
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
    assert active.is_dir()
    assert _tree_snapshot(junction_target) == before_target
    assert not install.exists()


@pytest.mark.parametrize(
    "declaration",
    [
        "[mcp_servers.agent_global_context]",
        "[mcp_servers.agent_global_context.env]",
        "[mcp_servers.agent_global_context.logging]",
        '["mcp_servers"."agent_global_context"]',
        r'''['mcp_servers'."agent_global_\u0063ontext"]''',
        r'''["mcp_\u0073ervers".agent_global_context]''',
        r'''[mcp_servers."agent_global_\U00000063ontext"]''',
    ],
)
def test_unmanaged_agc_server_table_fails_before_active_mutation(
    tmp_path: Path, declaration: str
):
    repository = _create_repository(tmp_path)
    skills, config = _create_active_install(tmp_path)
    _write_utf8(config, f'{declaration}\nenabled = false\n')
    before_config = config.read_bytes()
    before_skills = _tree_snapshot(skills)
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
    assert not install.exists()


@pytest.mark.parametrize(
    "header",
    [
        '[mcp_servers."agent_global_context]',
        r"[mcp_servers.agent_global_context\q]",
    ],
)
def test_malformed_toml_table_header_fails_before_active_mutation(
    tmp_path: Path, header: str
):
    repository = _create_repository(tmp_path)
    skills, config = _create_active_install(tmp_path)
    _write_utf8(config, f"{header}\nenabled = false\n")
    before_config = config.read_bytes()
    before_skills = _tree_snapshot(skills)
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
    assert not install.exists()


@pytest.mark.parametrize(
    "config_text",
    [
        "matrix = [\n  [1, 2],\n  [3, 4],\n]\n",
        (
            'message = """\n'
            "[mcp_servers.agent_global_context]\n"
            'still = "string content"\n'
            '"""\n'
        ),
        (
            "message = '''\n"
            "[mcp_servers.agent_global_context]\n"
            'still = "literal string content"\n'
            "'''\n"
        ),
        (
            "nested = [\n"
            "  [\n"
            "    [1, 2],\n"
            "    [3, 4],\n"
            "  ],\n"
            "]\n\n"
            "[[products]]\n"
            'name = "Hammer"\n\n'
            "[[products]]\n"
            'name = "Nail"\n'
        ),
    ],
    ids=("matrix", "multiline-basic", "multiline-literal", "nested-and-array-table"),
)
def test_valid_bracket_leading_value_lines_are_not_table_headers(
    tmp_path: Path, config_text: str
):
    original = tomllib.loads(config_text)
    repository = _create_repository(tmp_path)
    skills, config = _create_active_install(tmp_path)
    _write_utf8(config, config_text)

    _, result = _invoke(
        repository,
        skills,
        config,
        tmp_path / "memory",
        tmp_path / "runtime",
    )

    installed = tomllib.loads(_strict_utf8_without_bom(config))
    for key, value in original.items():
        assert installed[key] == value
    assert installed["mcp_servers"]["agent_global_context"]["enabled"] is True
    assert result["restart_required"] is True
    assert sorted(
        path.name for path in skills.glob("agent-global-context*") if path.is_dir()
    ) == ["agent-global-context"]


def test_windows_powershell_native_stderr_helper_uses_exit_code(
    tmp_path: Path,
):
    host = _windows_powershell()
    zero_root = tmp_path / "zero"
    repository = _create_repository(zero_root)
    skills, config = _create_active_install(zero_root)
    zero_probe = tmp_path / "stderr-zero.cmd"
    _write_utf8(
        zero_probe,
        "@echo harmless-native-warning 1>&2\n@exit /b 0\n",
        newline="\r\n",
    )

    completed, result = _invoke(
        repository,
        skills,
        config,
        zero_root / "memory",
        zero_root / "runtime",
        env={"AGC_INSTALL_TEST_NATIVE_PROBE": str(zero_probe)},
        powershell=host,
        check=False,
    )

    assert completed.returncode == 0
    assert result is not None
    assert b"harmless-native-warning" in completed.stderr

    nonzero_root = tmp_path / "nonzero"
    repository = _create_repository(nonzero_root)
    skills, config = _create_active_install(nonzero_root)
    nonzero_probe = tmp_path / "stderr-nonzero.cmd"
    _write_utf8(
        nonzero_probe,
        "@echo fatal-native-warning 1>&2\n@exit /b 7\n",
        newline="\r\n",
    )
    before_config = config.read_bytes()
    before_skills = _tree_snapshot(skills)

    completed, result = _invoke(
        repository,
        skills,
        config,
        nonzero_root / "memory",
        nonzero_root / "runtime",
        env={"AGC_INSTALL_TEST_NATIVE_PROBE": str(nonzero_probe)},
        powershell=host,
        check=False,
    )

    assert completed.returncode != 0
    assert result is None
    assert b"fatal-native-warning" in completed.stderr
    assert config.read_bytes() == before_config
    assert _tree_snapshot(skills) == before_skills
    assert not (nonzero_root / "runtime").exists()


def test_user_install_docs_describe_only_the_v2_public_surface():
    forbidden = (
        "agent-global-context-recall",
        "agent-global-context-commit",
        "agent-global-context-capture",
        "agent-global-context-review",
        "all five skills",
        "five alpha",
        "五个",
    )
    for path in USER_INSTALL_DOCS:
        text = path.read_text(encoding="utf-8")
        assert all(token not in text for token in forbidden), path
        assert ".agent-global-context-v2" in text, path
        assert all(tool in text for tool in ("agc.read", "agc.write", "agc.admin")), path
        assert "backfill" in text, path


def test_launcher_escapes_literal_percent_characters_for_cmd(tmp_path: Path):
    repository = _create_repository(tmp_path)
    skills, config = _create_active_install(tmp_path)
    install = tmp_path / "runtime%literal%"

    _, result = _invoke(
        repository,
        skills,
        config,
        tmp_path / "memory",
        install,
    )

    executable = Path(str(result["mcp_executable"]))
    launcher = Path(str(result["launcher"]))
    launcher_text = _strict_utf8_without_bom(launcher)
    escaped_executable = str(executable).replace("%", "%%")
    assert launcher_text == f'@"{escaped_executable}" %*\n'
    assert launcher_text.replace("%%", "%") == f'@"{executable}" %*\n'
