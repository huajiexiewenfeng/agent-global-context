"""Content-safe project-scope derivation for Capture source metadata."""

from __future__ import annotations

import hashlib
import ntpath
import posixpath
from pathlib import PurePosixPath, PureWindowsPath
import re
import unicodedata
from typing import Any


_PREFIX = "project:cwd:"
_MAX_CWD_CODEPOINTS = 4096
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def project_scope_from_cwd(value: Any) -> str | None:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > _MAX_CWD_CODEPOINTS
        or _CONTROL.search(value)
    ):
        return None

    try:
        candidate = unicodedata.normalize("NFC", value)
        candidate.encode("utf-8")
    except UnicodeError:
        return None

    windows = PureWindowsPath(candidate)
    posix = PurePosixPath(candidate)
    if windows.is_absolute():
        normalized = ntpath.normcase(ntpath.normpath(candidate)).replace("\\", "/")
        if PureWindowsPath(normalized).parent == PureWindowsPath(normalized):
            return None
        domain = "windows"
    elif posix.is_absolute():
        normalized = posixpath.normpath(candidate)
        if normalized == "/":
            return None
        domain = "posix"
    else:
        return None

    digest = hashlib.sha256(f"{domain}\0{normalized}".encode("utf-8")).hexdigest()
    return f"{_PREFIX}{digest}"


__all__ = ["project_scope_from_cwd"]
