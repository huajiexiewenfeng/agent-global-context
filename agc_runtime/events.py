import json
from dataclasses import dataclass
from typing import Any

from agc_runtime.contracts import SourceKey
from agc_runtime.paths import MemoryPaths
from agc_runtime.utf8_io import atomic_write_text, strict_read_text


@dataclass(frozen=True)
class MemoryEvent:
    event_id: str
    object_id: str
    action: str
    old_lifecycle: str | None
    new_lifecycle: str | None
    timestamp: str
    source: SourceKey

    def to_mapping(self) -> dict[str, Any]:
        return {
            "schema_version": 2,
            "event_id": self.event_id,
            "object_id": self.object_id,
            "action": self.action,
            "old_lifecycle": self.old_lifecycle,
            "new_lifecycle": self.new_lifecycle,
            "timestamp": self.timestamp,
            "source": {
                "ref": self.source.ref,
                "revision": self.source.revision,
                "content_hash": self.source.content_hash,
            },
        }


def _events_file(paths: MemoryPaths):
    return paths.events / "events.jsonl"


def _read_event_mappings(paths: MemoryPaths) -> list[dict[str, Any]]:
    event_file = _events_file(paths)
    if not event_file.exists():
        return []
    mappings: list[dict[str, Any]] = []
    for line in strict_read_text(event_file).splitlines():
        if line:
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError("event log entry must be a mapping")
            mappings.append(value)
    return mappings


def _write_event_mappings(paths: MemoryPaths, values: list[dict[str, Any]]) -> None:
    event_file = _events_file(paths)
    serialized = "".join(
        json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n"
        for value in values
    )
    if serialized:
        atomic_write_text(event_file, serialized)
    elif event_file.exists():
        event_file.unlink()


def append_event(paths: MemoryPaths, event: MemoryEvent) -> None:
    values = _read_event_mappings(paths)
    if any(value.get("event_id") == event.event_id for value in values):
        return
    values.append(event.to_mapping())
    _write_event_mappings(paths, values)


def remove_event(paths: MemoryPaths, event_id: str) -> None:
    values = _read_event_mappings(paths)
    retained = [value for value in values if value.get("event_id") != event_id]
    if len(retained) != len(values):
        _write_event_mappings(paths, retained)


def event_exists(paths: MemoryPaths, event_id: str) -> bool:
    return any(
        value.get("event_id") == event_id for value in _read_event_mappings(paths)
    )


def read_all_events_text(paths: MemoryPaths) -> str:
    event_file = _events_file(paths)
    return strict_read_text(event_file) if event_file.exists() else ""
