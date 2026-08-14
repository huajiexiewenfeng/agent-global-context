"""Census-only adapter for the versioned Codex JSONL source format."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from agc_runtime.capture_contracts import CAPTURE_SCHEMA_VERSION, CaptureKey, RevisionRef
from agc_runtime.capture_source import (
    AdapterDescriptor,
    DiscoveryBatch,
    ScanHint,
    SourceBindingKey,
    SourceProbe,
    StopHookEnvelope,
    TimeWindow,
    canonical_source_root,
    source_root_id_for,
)


ADAPTER_ID = "codex"
ADAPTER_VERSION = "1.0"
SOURCE_SCHEMA_VERSION = "codex-v1"


class CapabilityUnavailable(RuntimeError):
    """Raised when a later Capture-plan capability is requested too early."""


class _SourceIdentityMismatch(ValueError):
    pass


def compare_source_fingerprints(
    left_fingerprint: str | None,
    left_schema_version: str | None,
    right_fingerprint: str | None,
    right_schema_version: str | None,
) -> str:
    """Compare safe fingerprints without treating schema upgrades as conflicts."""

    if (
        left_fingerprint is None
        or right_fingerprint is None
        or left_schema_version is None
        or right_schema_version is None
        or left_schema_version != right_schema_version
    ):
        return "not_comparable"
    return "match" if left_fingerprint == right_fingerprint else "conflict"


def _utc(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.endswith("Z"):
        return None
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return None
    return parsed


def _identifier(value: Any) -> str | None:
    if not isinstance(value, str) or not value or len(value) > 128:
        return None
    allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._:-")
    if not value[0].isalnum() or any(character not in allowed for character in value):
        return None
    return value


class CodexSourceAdapter:
    """Discover completed main-task turns under one configured Codex root."""

    adapter_id = ADAPTER_ID
    adapter_version = ADAPTER_VERSION
    source_schema_version = SOURCE_SCHEMA_VERSION

    def __init__(self, source_root: Path):
        self._source_root = canonical_source_root(source_root)
        self._source_root_id = source_root_id_for(self._source_root)

    def describe(self) -> AdapterDescriptor:
        return AdapterDescriptor.from_mapping(
            {
                "schema_version": CAPTURE_SCHEMA_VERSION,
                "adapter_id": self.adapter_id,
                "adapter_version": self.adapter_version,
                "source_schema_version": self.source_schema_version,
                "source_root_id": self._source_root_id,
                "capabilities": ["discover", "probe"],
            }
        )

    def accept_stop(self, envelope: StopHookEnvelope) -> Any:
        del envelope
        raise CapabilityUnavailable("stop_hook_not_installed")

    def load_capsule(self, ref: RevisionRef, policy: Any) -> Any:
        del ref, policy
        raise CapabilityUnavailable("semantic_capture_not_installed")

    def discover(self, hint: ScanHint | None, window: TimeWindow) -> DiscoveryBatch:
        self._validate_hint(hint)
        window = TimeWindow.from_mapping(window.to_mapping())
        revisions: dict[tuple[str, str], RevisionRef] = {}
        diagnostics: set[str] = set()

        for locator, path in self._source_files(diagnostics):
            records, read_diagnostics = self._read_records(path)
            diagnostics.update(read_diagnostics)
            if records is None:
                continue
            discovered, parse_diagnostics = self._discover_records(records, locator, window)
            diagnostics.update(parse_diagnostics)
            for revision in discovered:
                identity = (revision.key.task_id, revision.key.revision_id)
                # sessions is enumerated before archived_sessions, so an archive move
                # is an exact replay and retains the active relative locator.
                revisions.setdefault(identity, revision)

        ordered = tuple(
            revisions[key]
            for key in sorted(revisions, key=lambda item: (item[0], item[1]))
        )
        return DiscoveryBatch.from_mapping(
            {
                "schema_version": CAPTURE_SCHEMA_VERSION,
                "binding": self._binding().to_mapping(),
                "window": window.to_mapping(),
                "revisions": [revision.to_mapping() for revision in ordered],
                "next_hint": None,
                "diagnostic_codes": sorted(diagnostics),
            }
        )

    def probe(self, ref: RevisionRef) -> SourceProbe:
        self._validate_ref(ref)
        try:
            records = tuple(self._iter_target_turn_records(ref))
        except _SourceIdentityMismatch:
            return self._probe(ref, "unknown", "unreadable", "source_identity_mismatch")
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
            return self._probe(ref, "unknown", "unreadable", "source_unreadable")
        completed = any(
            record.get("type") == "event_msg"
            and isinstance(record.get("payload"), dict)
            and record["payload"].get("type") == "task_complete"
            and record["payload"].get("turn_id") == ref.key.revision_id
            for record in records
        )
        if completed:
            return self._probe(ref, "main", "complete", None)
        return self._probe(ref, "main", "partial", "completion_missing")

    def _probe(
        self,
        ref: RevisionRef,
        source_kind: str,
        completion_state: str,
        diagnostic_code: str | None,
    ) -> SourceProbe:
        return SourceProbe.from_mapping(
            {
                "schema_version": CAPTURE_SCHEMA_VERSION,
                "revision": ref.to_mapping(),
                "source_kind": source_kind,
                "completion_state": completion_state,
                "diagnostic_code": diagnostic_code,
            }
        )

    def _binding(self) -> SourceBindingKey:
        return SourceBindingKey.from_mapping(
            {
                "schema_version": CAPTURE_SCHEMA_VERSION,
                "adapter_id": self.adapter_id,
                "source_root_id": self._source_root_id,
            }
        )

    def _validate_hint(self, hint: ScanHint | None) -> None:
        if hint is None:
            return
        hint = ScanHint.from_mapping(hint.to_mapping())
        if hint.adapter_id != self.adapter_id or hint.source_root_id != self._source_root_id:
            raise ValueError("scan hint does not belong to this source binding")

    def _source_files(self, diagnostics: set[str]) -> Iterator[tuple[str, Path]]:
        for namespace in ("sessions", "archived_sessions"):
            directory = self._source_root / namespace
            if not directory.is_dir():
                continue
            for candidate in sorted(directory.rglob("*.jsonl"), key=lambda item: item.as_posix()):
                try:
                    resolved = candidate.resolve(strict=True)
                    relative = resolved.relative_to(self._source_root)
                except (OSError, RuntimeError, ValueError):
                    diagnostics.add("locator_escape")
                    continue
                if not resolved.is_file():
                    diagnostics.add("source_unreadable")
                    continue
                locator = relative.as_posix()
                if locator.split("/", 1)[0] != namespace:
                    diagnostics.add("locator_escape")
                    continue
                yield locator, resolved

    def _read_records(
        self, path: Path
    ) -> tuple[list[dict[str, Any]] | None, set[str]]:
        diagnostics: set[str] = set()
        records: list[dict[str, Any]] = []
        try:
            with path.open("r", encoding="utf-8", newline="") as handle:
                pending: str | None = None
                for line in handle:
                    if pending is not None:
                        self._parse_source_line(pending, records, diagnostics, final=False)
                    pending = line
                if pending is not None:
                    self._parse_source_line(pending, records, diagnostics, final=True)
        except PermissionError:
            return None, {"source_locked"}
        except (OSError, UnicodeError):
            return None, {"source_unreadable"}
        return records, diagnostics

    @staticmethod
    def _parse_source_line(
        line: str,
        records: list[dict[str, Any]],
        diagnostics: set[str],
        *,
        final: bool,
    ) -> None:
        if final and not line.endswith(("\n", "\r")):
            diagnostics.add("partial_tail")
            return
        stripped = line.strip()
        if not stripped:
            return
        try:
            value = json.loads(stripped)
        except json.JSONDecodeError:
            diagnostics.add("partial_tail" if final else "source_malformed")
            return
        if not isinstance(value, dict):
            diagnostics.add("source_malformed")
            return
        records.append(value)

    def _discover_records(
        self,
        records: list[dict[str, Any]],
        locator: str,
        window: TimeWindow,
    ) -> tuple[list[RevisionRef], set[str]]:
        diagnostics: set[str] = set()
        metadata = [record for record in records if record.get("type") == "session_meta"]
        if not metadata:
            return [], {"unknown_source_shape"}
        identity = self._source_identity(metadata[0])
        if identity is None:
            return [], {"unknown_source_shape"}
        task_id, rollout_id, identity_quality, source_kind = identity
        if source_kind == "subagent":
            return [], set()
        if source_kind != "main":
            return [], {"unknown_source_shape"}
        if any(self._source_identity(record) != identity for record in metadata[1:]):
            return [], {"conflicting_source_identity"}

        start = _utc(window.start_at)
        end = _utc(window.end_at)
        assert start is not None and end is not None
        revisions: dict[str, RevisionRef] = {}
        for record in records:
            if record.get("type") != "event_msg":
                continue
            payload = record.get("payload")
            if not isinstance(payload, dict):
                diagnostics.add("unknown_completion_shape")
                continue
            event_type = payload.get("type")
            if event_type == "task_complete":
                revision_id = _identifier(payload.get("turn_id"))
                completed_at = record.get("timestamp")
                completed = _utc(completed_at)
                if revision_id is None or completed is None:
                    diagnostics.add("unknown_completion_shape")
                    continue
                if start <= completed < end:
                    revisions.setdefault(
                        revision_id,
                        RevisionRef.from_mapping(
                            {
                                "schema_version": CAPTURE_SCHEMA_VERSION,
                                "capture_key": {
                                    "adapter_id": self.adapter_id,
                                    "source_root_id": self._source_root_id,
                                    "task_id": task_id,
                                    "revision_id": revision_id,
                                },
                                "rollout_anchor_id": rollout_id,
                                "completed_at": completed_at,
                                "locator": locator,
                                "identity_quality": identity_quality,
                                "adapter_version": self.adapter_version,
                                "source_schema_version": self.source_schema_version,
                            }
                        ),
                    )
            elif event_type not in {"task_started", "task_aborted"} and self._has_turn_identity(payload):
                diagnostics.add("unknown_completion_shape")
        return list(revisions.values()), diagnostics

    @staticmethod
    def _has_turn_identity(payload: dict[str, Any]) -> bool:
        if _identifier(payload.get("turn_id")) is not None:
            return True
        turn = payload.get("turn")
        return isinstance(turn, dict) and _identifier(turn.get("id")) is not None

    @staticmethod
    def _source_identity(
        record: dict[str, Any]
    ) -> tuple[str, str, str, str] | None:
        payload = record.get("payload")
        if not isinstance(payload, dict):
            return None
        rollout_id = _identifier(payload.get("id"))
        has_session_id = "session_id" in payload
        session_id = _identifier(payload.get("session_id"))
        if rollout_id is None:
            return None
        source = payload.get("source")
        if isinstance(source, str) and source:
            source_kind = "main"
        elif isinstance(source, dict) and (
            "subagent" in source or source.get("thread_source") == "subagent"
        ):
            source_kind = "subagent"
        else:
            source_kind = "unknown"
        if has_session_id:
            if session_id is None:
                return None
            return session_id, rollout_id, "session_id", source_kind
        return rollout_id, rollout_id, "legacy_rollout_id", source_kind

    def _validate_ref(self, ref: RevisionRef) -> None:
        if not isinstance(ref, RevisionRef):
            raise ValueError("revision must be a RevisionRef")
        if ref.key.adapter_id != self.adapter_id or ref.key.source_root_id != self._source_root_id:
            raise ValueError("revision does not belong to this source binding")
        if ref.adapter_version != self.adapter_version or ref.source_schema_version != self.source_schema_version:
            raise ValueError("revision uses an unsupported adapter or source schema version")

    def _path_for_locator(self, locator: str | None) -> Path:
        if not isinstance(locator, str) or not locator or "\\" in locator:
            raise ValueError("locator must be a relative source path")
        relative = Path(locator)
        if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
            raise ValueError("locator must be a relative source path")
        if relative.parts[0] not in {"sessions", "archived_sessions"}:
            raise ValueError("locator must address a configured source namespace")
        try:
            resolved = (self._source_root / relative).resolve(strict=True)
            resolved.relative_to(self._source_root)
        except (OSError, RuntimeError, ValueError) as error:
            raise ValueError("locator must resolve inside the configured source root") from error
        if not resolved.is_file() or resolved.suffix != ".jsonl":
            raise ValueError("locator must identify a JSONL source file")
        return resolved

    def _iter_target_turn_records(self, ref: RevisionRef) -> Iterator[dict[str, Any]]:
        """Yield target-turn records in memory for the future pre-Capsule gate."""

        self._validate_ref(ref)
        path = self._path_for_locator(ref.locator)
        records, diagnostics = self._read_records(path)
        if records is None or diagnostics:
            raise ValueError("source is not settled and readable")
        metadata = next(
            (record for record in records if record.get("type") == "session_meta"), None
        )
        identity = self._source_identity(metadata) if metadata is not None else None
        expected_identity = (
            ref.key.task_id,
            ref.rollout_anchor_id,
            ref.identity_quality,
            "main",
        )
        if identity != expected_identity:
            raise _SourceIdentityMismatch("source identity does not match revision")
        target_active = False
        completed = False
        for record in records:
            if record.get("type") == "session_meta":
                yield record
                continue
            payload = record.get("payload")
            if not isinstance(payload, dict):
                continue
            turn_id = payload.get("turn_id")
            if turn_id == ref.key.revision_id:
                target_active = True
            if target_active:
                yield record
            if (
                record.get("type") == "event_msg"
                and payload.get("type") == "task_complete"
                and turn_id == ref.key.revision_id
            ):
                if record.get("timestamp") != ref.completed_at:
                    raise _SourceIdentityMismatch("completion identity does not match revision")
                completed = True
                break
        if not completed:
            raise ValueError("target turn is not complete")


__all__ = [
    "ADAPTER_ID",
    "ADAPTER_VERSION",
    "SOURCE_SCHEMA_VERSION",
    "CapabilityUnavailable",
    "CodexSourceAdapter",
    "compare_source_fingerprints",
]
