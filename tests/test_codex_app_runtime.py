from pathlib import Path

import pytest

from agc_runtime.codex_app_runtime import (
    _below,
    resolve_codex_app_command,
)


def _environment(local_app_data: Path) -> dict[str, str]:
    return {"LOCALAPPDATA": str(local_app_data.resolve())}


def _candidate(local_app_data: Path, version: str = "version-a") -> Path:
    executable = (
        local_app_data
        / "OpenAI"
        / "Codex"
        / "bin"
        / version
        / "codex.exe"
    )
    executable.parent.mkdir(parents=True, exist_ok=True)
    executable.write_bytes(b"runtime")
    return executable


def test_resolves_only_codex_exe_below_fixed_app_bin(tmp_path: Path):
    executable = _candidate(tmp_path)

    assert resolve_codex_app_command(
        environment=_environment(tmp_path), platform_name="nt"
    ) == (str(executable.resolve()),)


@pytest.mark.parametrize(
    ("environment", "platform_name"),
    (({}, "nt"), ({"LOCALAPPDATA": "relative"}, "nt"), ({}, "posix")),
)
def test_missing_invalid_or_non_windows_environment_fails_closed(
    environment: dict[str, str], platform_name: str
):
    with pytest.raises(RuntimeError, match="^capture_extractor_unavailable$"):
        resolve_codex_app_command(
            environment=environment, platform_name=platform_name
        )


def test_missing_app_bin_or_candidate_fails_closed(tmp_path: Path):
    with pytest.raises(RuntimeError, match="^capture_extractor_unavailable$"):
        resolve_codex_app_command(
            environment=_environment(tmp_path), platform_name="nt"
        )

    (tmp_path / "OpenAI" / "Codex" / "bin").mkdir(parents=True)

    with pytest.raises(RuntimeError, match="^capture_extractor_unavailable$"):
        resolve_codex_app_command(
            environment=_environment(tmp_path), platform_name="nt"
        )


def test_multiple_candidates_fail_closed(tmp_path: Path):
    _candidate(tmp_path, "version-a")
    _candidate(tmp_path, "version-b")

    with pytest.raises(RuntimeError, match="^capture_extractor_unavailable$"):
        resolve_codex_app_command(
            environment=_environment(tmp_path), platform_name="nt"
        )


def test_non_file_codex_candidate_is_ignored(tmp_path: Path):
    candidate = (
        tmp_path
        / "OpenAI"
        / "Codex"
        / "bin"
        / "version-a"
        / "codex.exe"
    )
    candidate.mkdir(parents=True)

    with pytest.raises(RuntimeError, match="^capture_extractor_unavailable$"):
        resolve_codex_app_command(
            environment=_environment(tmp_path), platform_name="nt"
        )


def test_reparse_candidate_is_ignored_without_following_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    executable = _candidate(tmp_path)
    monkeypatch.setattr(
        "agc_runtime.codex_app_runtime._is_reparse_point",
        lambda path: path == executable.parent,
    )

    with pytest.raises(RuntimeError, match="^capture_extractor_unavailable$"):
        resolve_codex_app_command(
            environment=_environment(tmp_path), platform_name="nt"
        )


def test_containment_helper_rejects_parent_and_sibling(tmp_path: Path):
    parent = (tmp_path / "parent").resolve()
    child = (parent / "child").resolve()
    sibling = (tmp_path / "sibling").resolve()

    assert _below(child, parent)
    assert not _below(parent, parent)
    assert not _below(sibling, parent)
