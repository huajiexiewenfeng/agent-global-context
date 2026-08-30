"""Shared bounded Codex command resolution."""

from __future__ import annotations

import shlex


def resolve_codex_command(value: str) -> tuple[str, ...]:
    if value == "codex-app":
        from agc_runtime.codex_app_runtime import resolve_codex_app_command

        return resolve_codex_app_command()
    try:
        command = tuple(shlex.split(value, posix=True))
    except ValueError as error:
        raise ValueError("codex_command_invalid") from error
    if not 1 <= len(command) <= 4:
        raise ValueError("codex_command_invalid")
    return command


__all__ = ["resolve_codex_command"]
