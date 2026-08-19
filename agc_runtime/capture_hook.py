"""Silent metadata-only Codex Stop Hook."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from agc_runtime.capture_contracts import CAPTURE_SCHEMA_VERSION
from agc_runtime.capture_dirty import write_dirty_marker
from agc_runtime.capture_source import (
    DirtyMarker,
    StopHookEnvelope,
    canonical_source_root,
    source_root_id_for,
)
from agc_runtime.codex_source_adapter import (
    ADAPTER_ID,
    ADAPTER_VERSION,
    SOURCE_SCHEMA_VERSION,
)
from agc_runtime.paths import MemoryPaths
from agc_runtime.runtime_config import load_runtime_config


def _observed_at() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _relative_locator(
    transcript_path: str, source_roots: Sequence[str]
) -> tuple[Path, str] | None:
    transcript = Path(transcript_path)
    if not transcript.is_absolute():
        return None
    resolved = transcript.resolve(strict=True)
    if not resolved.is_file():
        return None
    for configured in source_roots:
        source_root = canonical_source_root(Path(configured))
        if resolved != source_root and source_root in resolved.parents:
            locator = resolved.relative_to(source_root).as_posix()
            return source_root, locator
    return None


def _handle(root: Path, value: Any) -> None:
    if not root.is_absolute() or not root.is_dir():
        return
    paths = MemoryPaths.from_root(root)
    config = load_runtime_config(paths)
    if (
        not config.capture.enabled
        or not config.capture.hook.enabled
        or config.capture.paused
    ):
        return
    envelope = StopHookEnvelope.from_mapping(value)
    located = _relative_locator(envelope.transcript_path, config.capture.sources)
    if located is None:
        return
    source_root, locator = located
    marker = DirtyMarker.from_mapping(
        {
            "schema_version": CAPTURE_SCHEMA_VERSION,
            "adapter_id": ADAPTER_ID,
            "adapter_version": ADAPTER_VERSION,
            "source_schema_version": SOURCE_SCHEMA_VERSION,
            "source_root_id": source_root_id_for(source_root),
            "task_id": envelope.session_id,
            "revision_id": envelope.turn_id,
            "locator": locator,
            "observed_at": _observed_at(),
            "hook_event": envelope.hook_event_name,
        }
    )
    write_dirty_marker(paths.root, marker)


def main(argv: Sequence[str] | None = None) -> int:
    """Consume one Stop event and always leave the foreground task unaffected."""

    try:
        arguments = list(sys.argv[1:] if argv is None else argv)
        if len(arguments) != 2 or arguments[0] != "--root":
            return 0
        raw_input = sys.stdin.read()
        value = json.loads(raw_input)
        _handle(Path(arguments[1]), value)
    except BaseException:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["main"]
