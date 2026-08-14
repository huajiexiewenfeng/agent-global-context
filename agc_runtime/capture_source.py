"""Versioned, content-free contracts for Capture source discovery."""

from __future__ import annotations

import hashlib
import os
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from agc_runtime.capture_contracts import CAPTURE_SCHEMA_VERSION, CaptureKey, RevisionRef


def _validated_mapping(instance: Any) -> dict[str, Any]:
    validated = instance.__class__.from_mapping(instance._to_mapping_unchecked())
    return validated._to_mapping_unchecked()


@dataclass(frozen=True)
class AdapterDescriptor:
    schema_version: int
    adapter_id: str
    adapter_version: str
    source_schema_version: str
    source_root_id: str
    capabilities: tuple[str, ...]

    @classmethod
    def from_mapping(cls, value: Any) -> "AdapterDescriptor":
        from agc_runtime.capture_schema import adapter_descriptor_from_mapping

        return adapter_descriptor_from_mapping(value)

    def to_mapping(self) -> dict[str, Any]:
        return _validated_mapping(self)

    def _to_mapping_unchecked(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "adapter_id": self.adapter_id,
            "adapter_version": self.adapter_version,
            "source_schema_version": self.source_schema_version,
            "source_root_id": self.source_root_id,
            "capabilities": list(self.capabilities),
        }


@dataclass(frozen=True)
class SourceBindingKey:
    schema_version: int
    adapter_id: str
    source_root_id: str

    @classmethod
    def from_mapping(cls, value: Any) -> "SourceBindingKey":
        from agc_runtime.capture_schema import source_binding_key_from_mapping

        return source_binding_key_from_mapping(value)

    def to_mapping(self) -> dict[str, Any]:
        return _validated_mapping(self)

    def _to_mapping_unchecked(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "adapter_id": self.adapter_id,
            "source_root_id": self.source_root_id,
        }


@dataclass(frozen=True)
class StopHookEnvelope:
    session_id: str
    turn_id: str
    transcript_path: str
    cwd: str
    hook_event_name: str
    model: str
    stop_hook_active: bool
    last_assistant_message: str

    @classmethod
    def from_mapping(cls, value: Any) -> "StopHookEnvelope":
        from agc_runtime.capture_schema import stop_hook_envelope_from_mapping

        return stop_hook_envelope_from_mapping(value)

    def to_mapping(self) -> dict[str, Any]:
        return _validated_mapping(self)

    def _to_mapping_unchecked(self) -> dict[str, Any]:
        return dict(self.__dict__)

@dataclass(frozen=True)
class DirtyMarker:
    schema_version: int
    adapter_id: str
    adapter_version: str
    source_schema_version: str
    source_root_id: str
    task_id: str
    revision_id: str
    locator: str | None
    observed_at: str
    hook_event: str

    @classmethod
    def from_mapping(cls, value: Any) -> "DirtyMarker":
        from agc_runtime.capture_schema import dirty_marker_from_mapping

        return dirty_marker_from_mapping(value)

    def to_mapping(self) -> dict[str, Any]:
        return _validated_mapping(self)

    def _to_mapping_unchecked(self) -> dict[str, Any]:
        return dict(self.__dict__)

    @property
    def key(self) -> CaptureKey:
        return CaptureKey(self.adapter_id, self.source_root_id, self.task_id, self.revision_id)


@dataclass(frozen=True)
class ScanHint:
    schema_version: int
    adapter_id: str
    source_root_id: str
    hint_schema_version: str
    opaque_value: str

    @classmethod
    def from_mapping(cls, value: Any) -> "ScanHint":
        from agc_runtime.capture_schema import scan_hint_from_mapping

        return scan_hint_from_mapping(value)

    def to_mapping(self) -> dict[str, Any]:
        return _validated_mapping(self)

    def _to_mapping_unchecked(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class TimeWindow:
    schema_version: int
    start_at: str
    end_at: str

    @classmethod
    def from_mapping(cls, value: Any) -> "TimeWindow":
        from agc_runtime.capture_schema import time_window_from_mapping

        return time_window_from_mapping(value)

    def to_mapping(self) -> dict[str, Any]:
        return _validated_mapping(self)

    def _to_mapping_unchecked(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class DiscoveryBatch:
    schema_version: int
    binding: SourceBindingKey
    window: TimeWindow
    revisions: tuple[RevisionRef, ...]
    next_hint: ScanHint | None
    diagnostic_codes: tuple[str, ...]

    @classmethod
    def from_mapping(cls, value: Any) -> "DiscoveryBatch":
        from agc_runtime.capture_schema import discovery_batch_from_mapping

        return discovery_batch_from_mapping(value)

    def to_mapping(self) -> dict[str, Any]:
        return _validated_mapping(self)

    def _to_mapping_unchecked(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "binding": self.binding._to_mapping_unchecked(),
            "window": self.window._to_mapping_unchecked(),
            "revisions": [revision._to_mapping_unchecked() for revision in self.revisions],
            "next_hint": self.next_hint._to_mapping_unchecked() if self.next_hint else None,
            "diagnostic_codes": list(self.diagnostic_codes),
        }


@dataclass(frozen=True)
class SourceProbe:
    schema_version: int
    revision: RevisionRef
    source_kind: str
    completion_state: str
    diagnostic_code: str | None

    @classmethod
    def from_mapping(cls, value: Any) -> "SourceProbe":
        from agc_runtime.capture_schema import source_probe_from_mapping

        return source_probe_from_mapping(value)

    def to_mapping(self) -> dict[str, Any]:
        return _validated_mapping(self)

    def _to_mapping_unchecked(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "revision": self.revision._to_mapping_unchecked(),
            "source_kind": self.source_kind,
            "completion_state": self.completion_state,
            "diagnostic_code": self.diagnostic_code,
        }


@dataclass(frozen=True)
class CensusRun:
    schema_version: int
    census_id: str
    binding: SourceBindingKey
    window: TimeWindow
    started_at: str
    frozen_at: str
    revision_keys: tuple[CaptureKey, ...]
    source_quarantine_count: int

    @classmethod
    def from_mapping(cls, value: Any) -> "CensusRun":
        from agc_runtime.capture_schema import census_run_from_mapping

        return census_run_from_mapping(value)

    def to_mapping(self) -> dict[str, Any]:
        return _validated_mapping(self)

    def _to_mapping_unchecked(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "census_id": self.census_id,
            "binding": self.binding._to_mapping_unchecked(),
            "window": self.window._to_mapping_unchecked(),
            "started_at": self.started_at,
            "frozen_at": self.frozen_at,
            "revision_keys": [key._to_mapping_unchecked() for key in self.revision_keys],
            "source_quarantine_count": self.source_quarantine_count,
        }


@dataclass(frozen=True)
class ScanState:
    schema_version: int
    binding: SourceBindingKey
    state_version: int
    hint: ScanHint | None
    last_scan_at: str | None
    lookback_started_at: str

    @classmethod
    def from_mapping(cls, value: Any) -> "ScanState":
        from agc_runtime.capture_schema import scan_state_from_mapping

        return scan_state_from_mapping(value)

    def to_mapping(self) -> dict[str, Any]:
        return _validated_mapping(self)

    def _to_mapping_unchecked(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "binding": self.binding._to_mapping_unchecked(),
            "state_version": self.state_version,
            "hint": self.hint._to_mapping_unchecked() if self.hint else None,
            "last_scan_at": self.last_scan_at,
            "lookback_started_at": self.lookback_started_at,
        }


class SourceAdapter(Protocol):
    def describe(self) -> AdapterDescriptor: ...
    def accept_stop(self, envelope: StopHookEnvelope) -> DirtyMarker: ...
    def discover(self, hint: ScanHint | None, window: TimeWindow) -> DiscoveryBatch: ...
    def probe(self, ref: RevisionRef) -> SourceProbe: ...


def canonical_source_root(path: Path) -> Path:
    if not isinstance(path, Path):
        raise ValueError("source root must be a Path")
    try:
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise ValueError("source root must be an existing directory") from error
    if not resolved.is_dir():
        raise ValueError("source root must be an existing directory")
    normalized = unicodedata.normalize("NFC", os.path.normcase(os.path.realpath(resolved)))
    return Path(normalized)


def source_root_id_for(path: Path) -> str:
    canonical = canonical_source_root(path)
    normalized = canonical.as_posix()
    if os.name == "nt":
        normalized = normalized.casefold()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


__all__ = [
    "AdapterDescriptor", "CensusRun", "DirtyMarker", "DiscoveryBatch", "ScanHint",
    "ScanState", "SourceAdapter", "SourceBindingKey", "SourceProbe", "StopHookEnvelope",
    "TimeWindow", "canonical_source_root", "source_root_id_for",
]
