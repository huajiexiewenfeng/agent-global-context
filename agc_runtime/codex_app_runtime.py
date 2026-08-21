"""Bounded resolver for the Windows Codex App Runtime."""

from __future__ import annotations

from collections.abc import Mapping
import os
from pathlib import Path
import stat


_UNAVAILABLE = "capture_extractor_unavailable"
_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


def _is_reparse_point(path: Path) -> bool:
    attributes = getattr(path.stat(), "st_file_attributes", 0)
    return bool(attributes & _REPARSE_POINT)


def _below(candidate: Path, parent: Path) -> bool:
    return candidate != parent and parent in candidate.parents


def _fail() -> None:
    raise RuntimeError(_UNAVAILABLE)


def resolve_codex_app_command(
    *,
    environment: Mapping[str, str] | None = None,
    platform_name: str | None = None,
) -> tuple[str, ...]:
    """Resolve exactly one trusted Codex App executable or fail closed."""

    values = os.environ if environment is None else environment
    if (os.name if platform_name is None else platform_name) != "nt":
        _fail()
    raw_local = values.get("LOCALAPPDATA")
    if not raw_local or not Path(raw_local).is_absolute():
        _fail()
    try:
        local = Path(raw_local).resolve(strict=True)
        if (
            not local.is_dir()
            or local.is_symlink()
            or _is_reparse_point(local)
        ):
            _fail()

        app_bin = local
        for segment in ("OpenAI", "Codex", "bin"):
            app_bin = app_bin / segment
            if (
                not app_bin.is_dir()
                or app_bin.is_symlink()
                or _is_reparse_point(app_bin)
            ):
                _fail()
        app_bin = app_bin.resolve(strict=True)
        if not _below(app_bin, local):
            _fail()

        candidates: list[Path] = []
        for version_dir in app_bin.iterdir():
            if (
                not version_dir.is_dir()
                or version_dir.is_symlink()
                or _is_reparse_point(version_dir)
            ):
                continue
            executable = version_dir / "codex.exe"
            if (
                not executable.is_file()
                or executable.is_symlink()
                or _is_reparse_point(executable)
            ):
                continue
            resolved = executable.resolve(strict=True)
            if _below(resolved, app_bin):
                candidates.append(resolved)
        if len(candidates) != 1:
            _fail()
        return (str(candidates[0]),)
    except RuntimeError:
        raise
    except (OSError, ValueError) as error:
        raise RuntimeError(_UNAVAILABLE) from error


__all__ = ["resolve_codex_app_command"]
