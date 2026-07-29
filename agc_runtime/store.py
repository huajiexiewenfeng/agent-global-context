import hashlib
import json
import re
import uuid
from contextlib import nullcontext
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agc_runtime.contracts import SourceKey, Status
from agc_runtime.events import (
    MemoryEvent,
    append_event,
    event_exists,
    read_all_events_text,
    remove_event,
)
from agc_runtime.locking import root_write_lock
from agc_runtime.models import MemoryItem
from agc_runtime.paths import MemoryPaths
from agc_runtime.policy import validate_transition
from agc_runtime.schema import KINDS, validate_memory_item
from agc_runtime.utf8_io import atomic_write_text, strict_read_text


_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class MutationResult:
    status: Status
    code: str
    created: bool
    object_id: str
    independent_evidence_count: int


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _validate_source_key(source: SourceKey) -> None:
    if not source.ref or not source.revision:
        raise ValueError("source ref and revision must be non-empty")
    if not _SHA256_PATTERN.fullmatch(source.content_hash):
        raise ValueError("source content_hash must be lowercase SHA-256")


def _source_mapping(source: SourceKey) -> dict[str, str]:
    return {
        "ref": source.ref,
        "revision": source.revision,
        "content_hash": source.content_hash,
    }


def _source_from_mapping(value: dict[str, Any]) -> SourceKey:
    return SourceKey(
        ref=value["ref"],
        revision=value["revision"],
        content_hash=value["content_hash"],
    )


class MemoryStore:
    def __init__(self, paths: MemoryPaths):
        self.paths = paths

    def _memory_path(self, item: MemoryItem) -> Path:
        return self.paths.memories / item.kind / f"{item.id}.md"

    def _find_memory_path(self, memory_id: str) -> Path:
        matches = [
            self.paths.memories / kind / f"{memory_id}.md"
            for kind in sorted(KINDS)
            if (self.paths.memories / kind / f"{memory_id}.md").is_file()
        ]
        if not matches:
            raise FileNotFoundError(f"memory not found: {memory_id}")
        if len(matches) > 1:
            raise RuntimeError(f"duplicate memory id across kinds: {memory_id}")
        return matches[0]

    def get_memory(self, memory_id: str) -> MemoryItem:
        return MemoryItem.from_markdown(
            strict_read_text(self._find_memory_path(memory_id))
        )

    def _empty_receipts(self) -> dict[str, Any]:
        return {"schema_version": 2, "sources": []}

    def _read_receipts(self) -> dict[str, Any]:
        if not self.paths.receipts.exists():
            return self._empty_receipts()
        receipt_file = self.paths.receipts / "source-keys.json"
        if not receipt_file.exists():
            return self._empty_receipts()
        value = json.loads(strict_read_text(receipt_file))
        if (
            not isinstance(value, dict)
            or value.get("schema_version") != 2
            or not isinstance(value.get("sources"), list)
        ):
            raise ValueError("invalid source receipt registry")
        return value

    def _write_receipts(self, receipts: dict[str, Any]) -> None:
        atomic_write_text(
            self.paths.receipts / "source-keys.json",
            json.dumps(receipts, ensure_ascii=False, sort_keys=True, indent=2)
            + "\n",
        )

    @staticmethod
    def _entry_matches_source(entry: dict[str, Any], source: SourceKey) -> bool:
        return (
            entry.get("ref") == source.ref
            and entry.get("revision") == source.revision
            and entry.get("content_hash") == source.content_hash
        )

    def _source_was_recorded_in(
        self, receipts: dict[str, Any], source: SourceKey
    ) -> bool:
        return any(
            self._entry_matches_source(entry, source)
            for entry in receipts["sources"]
        )

    def source_was_recorded(self, source: SourceKey) -> bool:
        _validate_source_key(source)
        return self._source_was_recorded_in(self._read_receipts(), source)

    @staticmethod
    def _evidence_count(receipts: dict[str, Any], object_id: str) -> int:
        return sum(
            1
            for entry in receipts["sources"]
            if entry.get("object_id") == object_id
        )

    def _record_source(
        self,
        receipts: dict[str, Any],
        source: SourceKey,
        object_id: str,
        action: str,
        timestamp: str,
        event_id: str,
    ) -> None:
        receipts["sources"].append(
            {
                **_source_mapping(source),
                "object_id": object_id,
                "action": action,
                "recorded_at": timestamp,
                "event_id": event_id,
            }
        )
        self._write_receipts(receipts)

    def _remove_source_receipt(self, source: SourceKey) -> None:
        receipts = self._read_receipts()
        retained = [
            entry
            for entry in receipts["sources"]
            if not self._entry_matches_source(entry, source)
        ]
        if len(retained) != len(receipts["sources"]):
            receipts["sources"] = retained
            self._write_receipts(receipts)

    def _transaction_id(self, source: SourceKey) -> str:
        digest = hashlib.sha256(source.stable_id.encode("utf-8")).hexdigest()
        return f"{digest}-{uuid.uuid4().hex}"

    def _begin_transaction(
        self,
        transaction_id: str,
        target: Path,
        source: SourceKey,
        event_id: str,
    ) -> tuple[Path, Path | None]:
        self.paths.queue.mkdir(parents=True, exist_ok=True)
        journal = self.paths.queue / f"{transaction_id}.json"
        backup: Path | None = None
        if target.exists():
            backup = self.paths.backups / f"{transaction_id}.md"
            atomic_write_text(backup, strict_read_text(target))
        payload = {
            "schema_version": 2,
            "transaction_id": transaction_id,
            "target": str(target.relative_to(self.paths.root)).replace("\\", "/"),
            "target_existed": target.exists(),
            "backup": (
                str(backup.relative_to(self.paths.root)).replace("\\", "/")
                if backup
                else None
            ),
            "event_id": event_id,
            "source": _source_mapping(source),
        }
        atomic_write_text(
            journal,
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        )
        return journal, backup

    def _cleanup_transaction(self, journal: Path, backup: Path | None) -> None:
        if backup:
            backup.unlink(missing_ok=True)
        journal.unlink(missing_ok=True)

    def _rollback_transaction(
        self,
        journal: Path,
        backup: Path | None,
        target: Path,
        target_existed: bool,
        event_id: str,
        source: SourceKey,
    ) -> None:
        if target_existed and backup and backup.exists():
            atomic_write_text(target, strict_read_text(backup))
        elif not target_existed:
            target.unlink(missing_ok=True)
        remove_event(self.paths, event_id)
        self._remove_source_receipt(source)
        self._cleanup_transaction(journal, backup)

    def _recover_pending_transactions(self) -> None:
        if not self.paths.queue.exists():
            return
        for journal in sorted(self.paths.queue.glob("*.json")):
            value = json.loads(strict_read_text(journal))
            source = _source_from_mapping(value["source"])
            target = self.paths.resolve_managed(value["target"])
            backup_value = value.get("backup")
            backup = (
                self.paths.resolve_managed(backup_value) if backup_value else None
            )
            event_id = value["event_id"]
            committed = (
                target.exists()
                and event_exists(self.paths, event_id)
                and self.source_was_recorded(source)
            )
            if committed:
                self._cleanup_transaction(journal, backup)
                continue
            self._rollback_transaction(
                journal,
                backup,
                target,
                bool(value["target_existed"]),
                event_id,
                source,
            )

    def _apply_mutation(
        self,
        *,
        target: Path,
        text: str,
        source: SourceKey,
        object_id: str,
        action: str,
        old_lifecycle: str | None,
        new_lifecycle: str | None,
        timestamp: str,
        receipts: dict[str, Any],
    ) -> None:
        transaction_id = self._transaction_id(source)
        event_id = transaction_id
        target_existed = target.exists()
        journal, backup = self._begin_transaction(
            transaction_id, target, source, event_id
        )
        try:
            atomic_write_text(target, text)
            append_event(
                self.paths,
                MemoryEvent(
                    event_id=event_id,
                    object_id=object_id,
                    action=action,
                    old_lifecycle=old_lifecycle,
                    new_lifecycle=new_lifecycle,
                    timestamp=timestamp,
                    source=source,
                ),
            )
            self._record_source(
                receipts,
                source,
                object_id,
                action,
                timestamp,
                event_id,
            )
        except BaseException:
            self._rollback_transaction(
                journal,
                backup,
                target,
                target_existed,
                event_id,
                source,
            )
            raise
        self._cleanup_transaction(journal, backup)

    def create_memory(
        self,
        item: MemoryItem,
        source: SourceKey,
        *,
        acquire_lock: bool = True,
    ) -> MutationResult:
        validate_memory_item(item)
        _validate_source_key(source)
        target = self._memory_path(item)
        lock = root_write_lock(self.paths) if acquire_lock else nullcontext()
        with lock:
            self._recover_pending_transactions()
            receipts = self._read_receipts()
            count = self._evidence_count(receipts, item.id)
            if self._source_was_recorded_in(receipts, source):
                return MutationResult(
                    status="accepted",
                    code="duplicate_source",
                    created=False,
                    object_id=item.id,
                    independent_evidence_count=count,
                )
            if target.exists():
                return MutationResult(
                    status="needs_adjudication",
                    code="memory_id_exists",
                    created=False,
                    object_id=item.id,
                    independent_evidence_count=count,
                )
            timestamp = _utc_now()
            self._apply_mutation(
                target=target,
                text=item.to_markdown(),
                source=source,
                object_id=item.id,
                action="memory_created",
                old_lifecycle=None,
                new_lifecycle=item.lifecycle.status,
                timestamp=timestamp,
                receipts=receipts,
            )
            return MutationResult(
                status="accepted",
                code="memory_created",
                created=True,
                object_id=item.id,
                independent_evidence_count=count + 1,
            )

    def add_evidence(
        self, memory_id: str, source: SourceKey, observed_at: str
    ) -> MutationResult:
        _validate_source_key(source)
        observed_date = observed_at[:10]
        with root_write_lock(self.paths):
            self._recover_pending_transactions()
            receipts = self._read_receipts()
            count = self._evidence_count(receipts, memory_id)
            if self._source_was_recorded_in(receipts, source):
                return MutationResult(
                    status="accepted",
                    code="duplicate_source",
                    created=False,
                    object_id=memory_id,
                    independent_evidence_count=count,
                )
            target = self._find_memory_path(memory_id)
            item = MemoryItem.from_markdown(strict_read_text(target))
            updated_refs = item.provenance.evidence_refs
            if source.ref not in updated_refs:
                updated_refs = (*updated_refs, source.ref)
            updated = replace(
                item,
                temporal=replace(item.temporal, last_observed=observed_date),
                provenance=replace(
                    item.provenance,
                    updated_at=observed_date,
                    evidence_refs=updated_refs,
                ),
            )
            validate_memory_item(updated)
            self._apply_mutation(
                target=target,
                text=updated.to_markdown(),
                source=source,
                object_id=memory_id,
                action="evidence_added",
                old_lifecycle=item.lifecycle.status,
                new_lifecycle=updated.lifecycle.status,
                timestamp=observed_at,
                receipts=receipts,
            )
            return MutationResult(
                status="accepted",
                code="evidence_added",
                created=True,
                object_id=memory_id,
                independent_evidence_count=count + 1,
            )

    def replace_memory(
        self,
        memory_id: str,
        updated: MemoryItem,
        source: SourceKey,
        observed_at: str,
        *,
        action: str = "memory_updated",
    ) -> MutationResult:
        _validate_source_key(source)
        validate_memory_item(updated)
        if updated.id != memory_id:
            raise ValueError("updated memory id must match target memory id")
        with root_write_lock(self.paths):
            self._recover_pending_transactions()
            receipts = self._read_receipts()
            count = self._evidence_count(receipts, memory_id)
            if self._source_was_recorded_in(receipts, source):
                return MutationResult(
                    status="accepted",
                    code="duplicate_source",
                    created=False,
                    object_id=memory_id,
                    independent_evidence_count=count,
                )
            target = self._find_memory_path(memory_id)
            current = MemoryItem.from_markdown(strict_read_text(target))
            if current.kind != updated.kind:
                raise ValueError("updated memory kind cannot change")
            validate_transition(current.lifecycle.status, updated.lifecycle.status)
            self._apply_mutation(
                target=target,
                text=updated.to_markdown(),
                source=source,
                object_id=memory_id,
                action=action,
                old_lifecycle=current.lifecycle.status,
                new_lifecycle=updated.lifecycle.status,
                timestamp=observed_at,
                receipts=receipts,
            )
            return MutationResult(
                status="accepted",
                code=action,
                created=True,
                object_id=memory_id,
                independent_evidence_count=count + 1,
            )

    def transition_memory(
        self,
        memory_id: str,
        new_status: str,
        source: SourceKey,
        observed_at: str,
        *,
        action: str,
    ) -> MutationResult:
        _validate_source_key(source)
        with root_write_lock(self.paths):
            self._recover_pending_transactions()
            receipts = self._read_receipts()
            count = self._evidence_count(receipts, memory_id)
            if self._source_was_recorded_in(receipts, source):
                return MutationResult(
                    status="accepted",
                    code="duplicate_source",
                    created=False,
                    object_id=memory_id,
                    independent_evidence_count=count,
                )
            target = self._find_memory_path(memory_id)
            current = MemoryItem.from_markdown(strict_read_text(target))
            validate_transition(current.lifecycle.status, new_status)
            updated = replace(
                current,
                lifecycle=replace(current.lifecycle, status=new_status),
                temporal=replace(
                    current.temporal, last_observed=observed_at[:10]
                ),
                provenance=replace(
                    current.provenance, updated_at=observed_at[:10]
                ),
            )
            validate_memory_item(updated)
            self._apply_mutation(
                target=target,
                text=updated.to_markdown(),
                source=source,
                object_id=memory_id,
                action=action,
                old_lifecycle=current.lifecycle.status,
                new_lifecycle=new_status,
                timestamp=observed_at,
                receipts=receipts,
            )
            return MutationResult(
                status="accepted",
                code=action,
                created=True,
                object_id=memory_id,
                independent_evidence_count=count + 1,
            )

    def read_all_events_text(self) -> str:
        return read_all_events_text(self.paths)
