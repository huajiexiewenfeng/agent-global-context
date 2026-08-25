"""Versioned Codex source discovery and in-memory target-turn loading."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from agc_runtime.capture_contracts import CAPTURE_SCHEMA_VERSION, CaptureKey, RevisionRef
from agc_runtime.capture_project_scope import project_scope_from_cwd
from agc_runtime.capture_source import (
    AdapterDescriptor,
    DiscoveryBatch,
    ScanHint,
    SourceAdapter,
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


@dataclass(frozen=True)
class _FileScan:
    identity: tuple[str, str, str, str] | None
    completions: tuple[tuple[str, str], ...]
    diagnostic_code: str | None


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


def _session_project_scope(records: tuple[dict[str, Any], ...]) -> str | None:
    for record in records:
        payload = record.get("payload")
        if record.get("type") == "session_meta" and isinstance(payload, dict):
            return project_scope_from_cwd(payload.get("cwd"))
    return None


class CodexSourceAdapter(SourceAdapter):
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
        from agc_runtime.capture_capsule import CapsulePolicy, build_capsule

        if not isinstance(policy, CapsulePolicy):
            raise CapabilityUnavailable("semantic_capture_not_installed")
        self._validate_ref(ref)
        try:
            records = tuple(self._iter_target_turn_records(ref))
            effective_policy = policy
            if policy.project_scope is None:
                effective_policy = replace(
                    policy,
                    project_scope=_session_project_scope(records),
                )
            return build_capsule(records, ref, effective_policy)
        except _SourceIdentityMismatch:
            raise ValueError("capsule_source_identity_changed") from None
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
            raise ValueError("capsule_source_unavailable") from None

    def discover(self, hint: ScanHint | None, window: TimeWindow) -> DiscoveryBatch:
        self._validate_hint(hint)
        window = TimeWindow.from_mapping(window.to_mapping())
        revisions: dict[tuple[str, str], RevisionRef] = {}
        conflicting_revisions: set[tuple[str, str]] = set()
        diagnostics: set[str] = set()
        start = _utc(window.start_at)
        end = _utc(window.end_at)
        assert start is not None and end is not None

        for locator, path in self._source_files(diagnostics):
            scan = self._scan_file(path)
            if scan.diagnostic_code is not None:
                try:
                    modified_at = datetime.fromtimestamp(
                        path.stat().st_mtime, tz=start.tzinfo
                    )
                except OSError:
                    diagnostics.add("source_unreadable")
                else:
                    latest_record_at = (
                        self._latest_record_timestamp(path)
                        if modified_at >= start
                        else None
                    )
                    if modified_at >= start and (
                        latest_record_at is None or latest_record_at >= start
                    ):
                        diagnostics.add(scan.diagnostic_code)
                continue
            if scan.identity is None or scan.identity[3] != "main":
                continue
            task_id, rollout_id, identity_quality, _source_kind = scan.identity
            for revision_id, completed_at in scan.completions:
                revision = RevisionRef.from_mapping(
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
                )
                identity = (revision.key.task_id, revision.key.revision_id)
                if identity in conflicting_revisions:
                    continue
                prior = revisions.get(identity)
                if prior is None:
                    revisions[identity] = revision
                elif not self._same_census_revision(prior, revision):
                    revisions.pop(identity)
                    conflicting_revisions.add(identity)
                    diagnostics.add("conflicting_revision_identity")

        ordered_list: list[RevisionRef] = []
        for key in sorted(revisions, key=lambda item: (item[0], item[1])):
            revision = revisions[key]
            completed = _utc(revision.completed_at)
            assert completed is not None
            if start <= completed < end:
                ordered_list.append(revision)
        ordered = tuple(ordered_list)
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

    def _scan_file(self, path: Path) -> _FileScan:
        identity: tuple[str, str, str, str] | None = None
        completions: dict[str, str] = {}
        try:
            with path.open("r", encoding="utf-8", newline="") as handle:
                for line, final in self._source_lines(handle):
                    record, diagnostic = self._decode_source_line(line, final=final)
                    if diagnostic is not None:
                        return _FileScan(None, (), diagnostic)
                    if record is None:
                        continue
                    record_type = record.get("type")
                    if record_type == "session_meta":
                        current = self._source_identity(record)
                        if current is None or current[3] == "unknown":
                            return _FileScan(None, (), "unknown_source_shape")
                        if identity is None:
                            identity = current
                            if identity[3] == "subagent":
                                return _FileScan(identity, (), None)
                        elif current != identity:
                            same_anchor = (
                                current[0] == identity[0]
                                and current[1] == identity[1]
                                and current[3] == identity[3]
                            )
                            quality_upgrade = {
                                current[2],
                                identity[2],
                            } == {"legacy_rollout_id", "session_id"}
                            if not same_anchor or not quality_upgrade:
                                return _FileScan(
                                    None, (), "conflicting_source_identity"
                                )
                            if current[2] == "session_id":
                                identity = current
                    elif record_type == "event_msg":
                        completion, diagnostic = self._critical_completion(record)
                        if diagnostic is not None:
                            return _FileScan(None, (), diagnostic)
                        if completion is not None:
                            if identity is None:
                                return _FileScan(None, (), "unknown_source_shape")
                            revision_id, completed_at = completion
                            prior = completions.setdefault(revision_id, completed_at)
                            if prior != completed_at:
                                return _FileScan(None, (), "unknown_completion_shape")
                    del record
        except PermissionError:
            return _FileScan(None, (), "source_locked")
        except (OSError, UnicodeError):
            return _FileScan(None, (), "source_unreadable")
        if identity is None:
            return _FileScan(None, (), "unknown_source_shape")
        return _FileScan(identity, tuple(completions.items()), None)

    def _latest_record_timestamp(self, path: Path) -> datetime | None:
        latest: datetime | None = None
        try:
            with path.open("r", encoding="utf-8", newline="") as handle:
                for line, final in self._source_lines(handle):
                    record, _diagnostic = self._decode_source_line(line, final=final)
                    if record is None:
                        continue
                    observed_at = _utc(record.get("timestamp"))
                    if observed_at is not None and (
                        latest is None or observed_at > latest
                    ):
                        latest = observed_at
                    del record
        except (OSError, UnicodeError):
            return None
        return latest

    @staticmethod
    def _source_lines(handle: Any) -> Iterator[tuple[str, bool]]:
        pending: str | None = None
        for line in handle:
            if pending is not None:
                yield pending, False
            pending = line
        if pending is not None:
            yield pending, True

    @staticmethod
    def _decode_source_line(
        line: str, *, final: bool
    ) -> tuple[dict[str, Any] | None, str | None]:
        if final and not line.endswith(("\n", "\r")):
            return None, "partial_tail"
        stripped = line.strip()
        if not stripped:
            return None, None
        try:
            value = json.loads(stripped)
        except json.JSONDecodeError:
            return None, "partial_tail" if final else "source_malformed"
        if not isinstance(value, dict):
            return None, "source_malformed"
        return value, None

    @staticmethod
    def _turn_identity(payload: dict[str, Any]) -> tuple[bool, str | None]:
        candidates: list[str] = []
        if "turn_id" in payload:
            turn_id = _identifier(payload.get("turn_id"))
            if turn_id is None:
                return True, None
            candidates.append(turn_id)
        turn = payload.get("turn")
        if isinstance(turn, dict) and "id" in turn:
            nested_id = _identifier(turn.get("id"))
            if nested_id is None:
                return True, None
            candidates.append(nested_id)
        if not candidates:
            return False, None
        if any(candidate != candidates[0] for candidate in candidates[1:]):
            return True, None
        return True, candidates[0]

    def _critical_completion(
        self, record: dict[str, Any]
    ) -> tuple[tuple[str, str] | None, str | None]:
        payload = record.get("payload")
        if not isinstance(payload, dict):
            return None, "unknown_completion_shape"
        event_type = payload.get("type")
        has_turn_identity, turn_identity = self._turn_identity(payload)
        if has_turn_identity and turn_identity is None:
            return None, "unknown_completion_shape"
        if event_type == "task_complete":
            revision_id = _identifier(payload.get("turn_id"))
            completed_at = record.get("timestamp")
            if (
                revision_id is None
                or revision_id != turn_identity
                or _utc(completed_at) is None
            ):
                return None, "unknown_completion_shape"
            return (revision_id, completed_at), None
        if event_type not in {
            "task_started",
            "task_aborted",
            "turn_aborted",
            "patch_apply_end",
            "item_completed",
            "exec_command_end",
            "dynamic_tool_call_response",
        } and has_turn_identity:
            return None, "unknown_completion_shape"
        return None, None

    @staticmethod
    def _same_census_revision(left: RevisionRef, right: RevisionRef) -> bool:
        return (
            left.key == right.key
            and left.rollout_anchor_id == right.rollout_anchor_id
            and left.completed_at == right.completed_at
            and left.identity_quality == right.identity_quality
            and left.adapter_version == right.adapter_version
            and left.source_schema_version == right.source_schema_version
        )

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

    @staticmethod
    def _source_signature(path: Path) -> tuple[int, int, int, int, int]:
        status = path.stat()
        return (
            status.st_dev,
            status.st_ino,
            status.st_size,
            status.st_mtime_ns,
            status.st_ctime_ns,
        )

    @staticmethod
    def _bind_target_record(record: dict[str, Any], revision_id: str) -> dict[str, Any]:
        payload = record.get("payload")
        if not isinstance(payload, dict) or "turn_id" in payload:
            return record
        bound = dict(record)
        bound_payload = dict(payload)
        bound_payload["turn_id"] = revision_id
        bound["payload"] = bound_payload
        return bound

    def _iter_target_turn_records(self, ref: RevisionRef) -> Iterator[dict[str, Any]]:
        """Yield target-turn records in memory for the future pre-Capsule gate."""

        self._validate_ref(ref)
        path = self._path_for_locator(ref.locator)
        settled_signature = self._source_signature(path)
        scan = self._scan_file(path)
        if self._source_signature(path) != settled_signature:
            raise ValueError("source changed during target validation")
        if scan.diagnostic_code in {"unknown_source_shape", "conflicting_source_identity"}:
            raise _SourceIdentityMismatch("source identity does not match revision")
        if scan.diagnostic_code is not None or scan.identity is None:
            raise ValueError("source is not settled and readable")
        expected_identity = (
            ref.key.task_id,
            ref.rollout_anchor_id,
            ref.identity_quality,
            "main",
        )
        if scan.identity != expected_identity:
            raise _SourceIdentityMismatch("source identity does not match revision")
        if (ref.key.revision_id, ref.completed_at) not in scan.completions:
            raise _SourceIdentityMismatch("completion identity does not match revision")

        target_records: list[dict[str, Any]] = []
        target_active = False
        completed = False
        seen_metadata = False
        loaded_identity: tuple[str, str, str, str] | None = None
        loaded_completions: dict[str, str] = {}
        try:
            with path.open("r", encoding="utf-8", newline="") as handle:
                for line, final in self._source_lines(handle):
                    record, diagnostic = self._decode_source_line(line, final=final)
                    if diagnostic is not None:
                        raise ValueError("source changed during target load")
                    if record is None:
                        continue
                    if record.get("type") == "session_meta":
                        current_identity = self._source_identity(record)
                        if current_identity != expected_identity:
                            raise _SourceIdentityMismatch("source identity does not match revision")
                        loaded_identity = current_identity
                        if not seen_metadata:
                            target_records.append(record)
                            seen_metadata = True
                        continue
                    payload = record.get("payload")
                    if record.get("type") == "event_msg":
                        completion, diagnostic = self._critical_completion(record)
                        if diagnostic is not None:
                            raise ValueError("critical source record changed during target load")
                        if completion is not None:
                            if loaded_identity is None:
                                raise ValueError("critical source record changed during target load")
                            revision_id, completed_at = completion
                            prior = loaded_completions.setdefault(revision_id, completed_at)
                            if prior != completed_at:
                                raise ValueError("critical source record changed during target load")
                    elif not isinstance(payload, dict):
                        continue
                    assert isinstance(payload, dict)
                    turn_id = payload.get("turn_id")
                    if (
                        target_active
                        and record.get("type") == "event_msg"
                        and payload.get("type") in {"task_started", "task_complete", "task_aborted"}
                        and turn_id != ref.key.revision_id
                    ):
                        raise ValueError("interleaved turn state is ambiguous")
                    if turn_id == ref.key.revision_id and not completed:
                        target_active = True
                    if target_active and not completed:
                        target_records.append(
                            self._bind_target_record(record, ref.key.revision_id)
                        )
                    if (
                        record.get("type") == "event_msg"
                        and payload.get("type") == "task_complete"
                        and turn_id == ref.key.revision_id
                    ):
                        if record.get("timestamp") != ref.completed_at:
                            raise _SourceIdentityMismatch("completion identity does not match revision")
                        completed = True
                        target_active = False
        except PermissionError as error:
            raise ValueError("source is locked") from error
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise ValueError("source is unreadable") from error
        if loaded_identity is None:
            raise _SourceIdentityMismatch("source identity does not match revision")
        if loaded_identity != scan.identity:
            raise _SourceIdentityMismatch("source identity does not match revision")
        if loaded_completions != dict(scan.completions):
            raise ValueError("critical source records changed during target load")
        if self._source_signature(path) != settled_signature:
            raise ValueError("source changed during target load")
        if not completed:
            raise ValueError("target turn is not complete")
        yield from target_records


__all__ = [
    "ADAPTER_ID",
    "ADAPTER_VERSION",
    "SOURCE_SCHEMA_VERSION",
    "CapabilityUnavailable",
    "CodexSourceAdapter",
    "compare_source_fingerprints",
]
