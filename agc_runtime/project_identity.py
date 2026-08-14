"""Content-free project identity resolution for Capture observations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from agc_runtime.capture_source import source_root_id_for


@dataclass(frozen=True)
class ProjectIdentity:
    schema_version: int
    project_id: str
    resolution: str

    @classmethod
    def from_mapping(cls, value: Any) -> "ProjectIdentity":
        from agc_runtime.capture_schema import project_identity_from_mapping

        return project_identity_from_mapping(value)

    def to_mapping(self) -> dict[str, Any]:
        validated = self.from_mapping(self._to_mapping_unchecked())
        return validated._to_mapping_unchecked()

    def _to_mapping_unchecked(self) -> dict[str, Any]:
        return dict(self.__dict__)


def _git_common_dir(project_root: Path) -> Path | None:
    git_entry = project_root / ".git"
    if git_entry.is_dir():
        common = git_entry
    elif git_entry.is_file():
        try:
            line = git_entry.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeError):
            return None
        if not line.startswith("gitdir: "):
            return None
        admin = (project_root / line[8:]).resolve()
        common_file = admin / "commondir"
        if common_file.is_file():
            try:
                common = (admin / common_file.read_text(encoding="utf-8").strip()).resolve()
            except (OSError, UnicodeError):
                return None
        else:
            common = admin
    else:
        return None
    return common if common.is_dir() else None


def _registry_identity(
    registry: Mapping[str, str] | None,
    key: str,
    resolution: str,
) -> ProjectIdentity | None:
    if registry is None or key not in registry:
        return None
    return ProjectIdentity.from_mapping(
        {"schema_version": 1, "project_id": registry[key], "resolution": resolution}
    )


def resolve_project_identity(
    project_root: Path,
    *,
    explicit_registry: Mapping[str, str] | None = None,
    git_registry: Mapping[str, str] | None = None,
    generated_registry: Mapping[str, str] | None = None,
) -> ProjectIdentity | None:
    root_key = source_root_id_for(project_root)
    explicit = _registry_identity(explicit_registry, root_key, "explicit_registry")
    if explicit is not None:
        return explicit

    common = _git_common_dir(project_root)
    if common is not None:
        git = _registry_identity(
            git_registry, source_root_id_for(common), "git_common_dir_registry"
        )
        if git is not None:
            return git

    return _registry_identity(generated_registry, root_key, "generated_registry")


__all__ = ["ProjectIdentity", "resolve_project_identity"]
