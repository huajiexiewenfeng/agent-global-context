"""Reconstructible, background-only Capture scheduling metadata.

This is a hint, not a health snapshot or a sending credential. The active
workset seal is its generation fence; an interrupted publication requires an
explicit audit instead of falling back to a hidden historical rebuild.
"""

from __future__ import annotations

import hashlib
import re
from typing import TYPE_CHECKING

from agc_runtime.capture_contracts import CAPTURE_SCHEMA_VERSION, CaptureReceipt, RevisionRef
from agc_runtime.capture_source import CensusRun
from agc_runtime.capture_source_cache import checked_path
from agc_runtime.capture_transaction import atomic_write_json, canonical_json_bytes, read_json, safe_unlink

if TYPE_CHECKING:
    from agc_runtime.capture_store import CaptureSnapshot, CaptureStore


_VERSION = "capture-schedule-v1"
_TERMINAL = {"complete", "excluded", "coalesced"}


def _path(store: CaptureStore):
    return checked_path(store.capture.root, store.capture.root / "scheduling-view.json")


def _seal_path(store: CaptureStore):
    return checked_path(store.capture.root, store.capture.root / "scheduling-view-seal.json")


def _digest(value: dict) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def invalidate_locked(store: CaptureStore) -> None:
    safe_unlink(_seal_path(store))
    safe_unlink(_path(store))


def _bound(workset: dict) -> dict:
    return {
        "baseline_id": workset["baseline_id"],
        "workset_generation": workset["generation"],
        "workset_digest": workset["digest"],
        "input_generation": workset["input_generation"],
    }


def _catalog_id(store: CaptureStore) -> str | None:
    path = checked_path(store.capture.root, store.capture.census_catalog / "active.json")
    if not path.exists():
        return None
    value = read_json(path)
    identifier = value.get("catalog_id") if isinstance(value, dict) else None
    if not isinstance(identifier, str) or re.fullmatch(r"[0-9a-f]{64}", identifier) is None:
        raise ValueError("invalid Census catalog pointer")
    return identifier


def _catalog_run_digest(store: CaptureStore) -> str | None:
    identifier = _catalog_id(store)
    if identifier is None:
        return None
    path = checked_path(store.capture.root, store.capture.census_catalog / "g" / identifier / "manifest.json")
    manifest = read_json(path)
    digest = manifest.get("run_digest") if isinstance(manifest, dict) else None
    if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        raise ValueError("invalid Census catalog manifest")
    return digest


def _equivalent_catalog_locked(store: CaptureStore, value: dict, current_id: str | None) -> bool:
    """Permit a full reader's content-equivalent catalog republish only.

    A pointer change is not accepted on shape alone: the new packed catalog
    must be self-consistent and contain exactly the view's unsuppressed truth.
    This exceptional path reads one packed metadata file, never Receipt bodies.
    """
    if current_id is None:
        return False
    try:
        from agc_runtime.capture_contracts import CaptureSuppressionTombstone
        from agc_runtime.capture_store import _CENSUS_CATALOG_SCHEMA_VERSION

        generation = checked_path(store.capture.root, store.capture.census_catalog / "g" / current_id)
        manifest = read_json(checked_path(store.capture.root, generation / "manifest.json"))
        packed = read_json(checked_path(store.capture.root, generation / "revisions.json"))
        if (not isinstance(manifest, dict) or not isinstance(packed, dict)
                or manifest.get("schema_version") != CAPTURE_SCHEMA_VERSION
                or packed.get("schema_version") != CAPTURE_SCHEMA_VERSION
                or manifest.get("catalog_schema_version") != _CENSUS_CATALOG_SCHEMA_VERSION
                or packed.get("catalog_schema_version") != _CENSUS_CATALOG_SCHEMA_VERSION
                or manifest.get("catalog_id") != current_id
                or packed.get("catalog_id") != current_id
                or manifest.get("run_digest") != value["catalog_run_digest"]
                or manifest.get("run_ids") != [item["census_id"] for item in value["runs"]]
                or not isinstance(packed.get("revisions"), list)):
            return False
        revision_digest = store._catalog_digest({"revisions": packed["revisions"]})
        expected_id = store._catalog_digest({
            "catalog_schema_version": manifest["catalog_schema_version"],
            "run_digest": manifest["run_digest"],
            "revision_digest": revision_digest,
        })
        if (revision_digest != manifest.get("revision_digest")
                or len(packed["revisions"]) != manifest.get("revision_count")
                or expected_id != current_id):
            return False
        suppressed = set()
        for path in store.capture.tombstones.glob("*.json"):
            checked_path(store.capture.root, path)
            tombstone = CaptureSuppressionTombstone.from_mapping(read_json(path))
            if path.stem != tombstone.tombstone_id:
                return False
            suppressed.add(tombstone.capture_key)
        actual = {}
        for item in packed["revisions"]:
            revision = RevisionRef.from_mapping(item)
            if revision.key in actual:
                return False
            if revision.key not in suppressed:
                actual[revision.key] = revision.to_mapping()
        expected = {RevisionRef.from_mapping(item).key: item for item in value["revisions"]}
        return actual == expected
    except (FileNotFoundError, KeyError, OSError, TypeError, ValueError):
        return False


def _publish_locked(store: CaptureStore, body: dict) -> None:
    digest = _digest(body)
    atomic_write_json(_path(store), {**body, "digest": digest})
    atomic_write_json(_seal_path(store), {
        "version": _VERSION,
        "baseline_id": body["baseline_id"],
        "workset_generation": body["workset_generation"],
        "view_digest": digest,
    })


def load_locked(store: CaptureStore, workset: dict, *, allow_pending: bool = False,
                allow_catalog_mismatch: bool = False) -> dict | None:
    """Validate only packed metadata and the current Task 2 generation fence."""
    try:
        value = read_json(_path(store))
        if not isinstance(value, dict) or set(value) != {
            "version", "baseline_id", "workset_generation", "workset_digest",
            "input_generation", "audit_completed_at", "catalog_id", "catalog_run_digest", "runs", "revisions",
            "receipts", "accounted", "excluded", "pending_census", "digest",
        }:
            return None
        body = {key: item for key, item in value.items() if key != "digest"}
        current_catalog_id = _catalog_id(store)
        catalog_ok = (
            value["catalog_id"] == current_catalog_id
            or (allow_catalog_mismatch and value["pending_census"])
            or _equivalent_catalog_locked(store, value, current_catalog_id)
        )
        if (value["version"] != _VERSION or value["digest"] != _digest(body)
                or any(value[key] != expected for key, expected in _bound(workset).items())
                or value["audit_completed_at"] != workset["completed_at"]
                or not catalog_ok
                or not isinstance(value["runs"], list)
                or not isinstance(value["revisions"], list)
                or not isinstance(value["receipts"], dict)
                or not isinstance(value["accounted"], list)
                or not isinstance(value["excluded"], list)
                or not isinstance(value["pending_census"], list)
                or value["accounted"] != sorted(set(value["accounted"]))
                or value["excluded"] != sorted(set(value["excluded"]))
                or not set(value["excluded"]).issubset(value["accounted"])
                or value["pending_census"] != sorted(set(value["pending_census"]))
                or (value["pending_census"] and not allow_pending)):
            return None
        seal = read_json(_seal_path(store))
        if seal != {
            "version": _VERSION,
            "baseline_id": value["baseline_id"],
            "workset_generation": value["workset_generation"],
            "view_digest": value["digest"],
        }:
            return None
        runs = [CensusRun.from_mapping(item) for item in value["runs"]]
        revisions = [RevisionRef.from_mapping(item) for item in value["revisions"]]
        receipts = {key: CaptureReceipt.from_mapping(item) for key, item in value["receipts"].items()}
        if (len({item.census_id for item in runs}) != len(runs)
                or len({item.key for item in revisions}) != len(revisions)
                or any(key != receipt.receipt_id or receipt.status in _TERMINAL
                       for key, receipt in receipts.items())
                or any(key in receipts for key in value["accounted"])):
            return None
        return value
    except (FileNotFoundError, OSError, TypeError, ValueError):
        return None


def bootstrap_locked(store: CaptureStore, snapshot: CaptureSnapshot, workset: dict) -> None:
    """Called only by a successful explicit full audit under its Capture lock."""
    suppressed = {item.capture_key for item in snapshot.tombstones}
    body = {
        "version": _VERSION,
        **_bound(workset),
        "audit_completed_at": workset["completed_at"],
        "catalog_id": _catalog_id(store),
        "catalog_run_digest": _catalog_run_digest(store),
        "runs": [
            {**run.to_mapping(), "revision_keys": [key.to_mapping() for key in run.revision_keys if key not in suppressed]}
            for run in snapshot.census_runs
        ],
        "revisions": [item.to_mapping() for item in snapshot.census if item.key not in suppressed],
        "receipts": {item.receipt_id: item.to_mapping() for item in snapshot.receipts
                     if item.key not in suppressed and item.status not in _TERMINAL},
        "accounted": sorted(item.receipt_id for item in snapshot.receipts
                            if item.key not in suppressed and item.status in _TERMINAL),
        "excluded": sorted(item.receipt_id for item in snapshot.receipts
                           if item.key not in suppressed and item.status == "excluded"),
        "pending_census": [],
    }
    _publish_locked(store, body)


def bind_workset_locked(store: CaptureStore, previous: dict, current: dict) -> None:
    view = load_locked(store, previous, allow_pending=True)
    if view is None:
        return
    body = {key: item for key, item in view.items() if key != "digest"}
    body.update(_bound(current))
    _publish_locked(store, body)


def prepare_retire_locked(store: CaptureStore, previous: dict, next_body: dict, receipt_id: str) -> None:
    """Publish the post-primary view before removing its active crash marker."""
    view = load_locked(store, previous, allow_pending=True)
    if view is None:
        return
    from agc_runtime.capture_maintenance import _digest as workset_digest
    from agc_runtime.capture_contracts import LedgerEntry

    next_workset = {**next_body, "digest": workset_digest(next_body)}
    body = {key: item for key, item in view.items() if key != "digest"}
    receipt_path = store._receipt_path(receipt_id)
    if receipt_path.exists():
        receipt = store._read_receipt(receipt_id)
        ledger = LedgerEntry.from_mapping(read_json(store._ledger_path(receipt_id)))
        if (ledger.receipt_id != receipt_id or ledger.capture_key != receipt.key
                or ledger.status != receipt.status):
            invalidate_locked(store)
            return
        if receipt.status in _TERMINAL:
            body["receipts"].pop(receipt_id, None)
            body["accounted"] = sorted(set((*body["accounted"], receipt_id)))
            if receipt.status == "excluded":
                body["excluded"] = sorted(set((*body["excluded"], receipt_id)))
            else:
                body["excluded"] = [item for item in body["excluded"] if item != receipt_id]
        else:
            body["accounted"] = [item for item in body["accounted"] if item != receipt_id]
            body["excluded"] = [item for item in body["excluded"] if item != receipt_id]
            body["receipts"][receipt_id] = receipt.to_mapping()
    else:
        body["receipts"].pop(receipt_id, None)
        body["accounted"] = [item for item in body["accounted"] if item != receipt_id]
        body["excluded"] = [item for item in body["excluded"] if item != receipt_id]
    body.update(_bound(next_workset))
    _publish_locked(store, body)


def premark_census_locked(store: CaptureStore, workset: dict, census_id: str) -> None:
    view = load_locked(store, workset, allow_pending=True)
    if view is None:
        return
    body = {key: item for key, item in view.items() if key != "digest"}
    body["pending_census"] = sorted(set((*body["pending_census"], census_id)))
    _publish_locked(store, body)


def publish_census_locked(store: CaptureStore, workset: dict, run: CensusRun, revisions: tuple[RevisionRef, ...]) -> None:
    view = load_locked(store, workset, allow_pending=True, allow_catalog_mismatch=True)
    if view is None:
        return
    from agc_runtime.capture_contracts import CaptureSuppressionTombstone, tombstone_id_for
    from agc_runtime.capture_ledger import same_revision_metadata

    suppressed = set()
    for revision in revisions:
        path = store.capture.tombstones / f"{tombstone_id_for(revision.key)}.json"
        checked_path(store.capture.root, path)
        if path.exists():
            tombstone = CaptureSuppressionTombstone.from_mapping(read_json(path))
            if tombstone.capture_key != revision.key:
                invalidate_locked(store)
                return
            suppressed.add(revision.key)
    body = {key: item for key, item in view.items() if key != "digest"}
    runs = {item["census_id"]: item for item in body["runs"]}
    runs[run.census_id] = {**run.to_mapping(), "revision_keys": [key.to_mapping() for key in run.revision_keys if key not in suppressed]}
    known = {RevisionRef.from_mapping(item).key: RevisionRef.from_mapping(item) for item in body["revisions"]}
    for revision in revisions:
        if revision.key in suppressed:
            continue
        prior = known.get(revision.key)
        if prior is not None and not same_revision_metadata(prior, revision):
            invalidate_locked(store)
            return
        known[revision.key] = revision
    body["runs"] = [runs[key] for key in sorted(runs)]
    body["revisions"] = [item.to_mapping() for item in sorted(known.values(), key=store._revision_sort_key)]
    body["catalog_id"] = _catalog_id(store)
    body["catalog_run_digest"] = _catalog_run_digest(store)
    _publish_locked(store, body)


def complete_census_locked(store: CaptureStore, workset: dict, census_id: str) -> None:
    view = load_locked(store, workset, allow_pending=True)
    if view is None or census_id not in view["pending_census"]:
        return
    body = {key: item for key, item in view.items() if key != "digest"}
    body["pending_census"] = [item for item in body["pending_census"] if item != census_id]
    _publish_locked(store, body)
