"""Content-safe diagnostics for the disabled Capture core."""

from __future__ import annotations

import hashlib
import copy
import json
from pathlib import Path
from typing import Any

from agc_runtime import __version__
from agc_runtime.capture_store import CaptureStore, root_fingerprint
from agc_runtime.paths import MemoryPaths
from agc_runtime.runtime_config import default_config_text, load_runtime_config
from agc_runtime.utf8_io import strict_read_text


def _paths(value: MemoryPaths | Path) -> MemoryPaths:
    return value if isinstance(value, MemoryPaths) else MemoryPaths.from_root(value)


def _fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _runtime_fingerprint() -> str:
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def _attach_activation(status: dict[str, Any]) -> dict[str, Any]:
    # Ordinary status must remain byte-inert and may not import the Host
    # activation capability. This is the exact not-assessed projection of the
    # host module's authorization payload.
    evidence = {
        "config_hash_matches": None,
        "effective_v2_skill_count": None,
        "extractor_capability": "not_assessed",
        "frozen_census": None,
        "hook_enabled": None,
        "hook_latency_passed": None,
        "hook_trusted": None,
        "legacy_v1_skill_count": None,
        "mcp_block_count": None,
        "memory_root_count": None,
        "recall_gate_passed": None,
        "runtime_hash_matches": None,
        "scheduler_enabled": None,
        "schema_version": 1,
    }
    exclusions = status["scanner"]["exclusions"]
    authorization = {
        "schema_version": 1,
        "runtime": dict(status["runtime"]),
        "config_source": dict(status["config_source"]),
        "memory_root_id": status["memory_root"]["fingerprint"],
        "source_root_ids": sorted(status["source_roots"]["ids"]),
        "extractor_boundary": dict(status["extractor_boundary"]),
        "budgets": dict(status["budgets"]),
        "state": dict(status["state"]),
        "exclusions": {
            "task_id_count": exclusions["task_id_count"],
            "project_id_count": exclusions["project_id_count"],
        },
        "host_evidence": evidence,
    }
    digest = hashlib.sha256(
        json.dumps(
            authorization,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    state = status["state"]
    installed_inert = (
        status["runtime"]["version"] == __version__
        and state["enabled"] is False
        and state["mode"] == "off"
        and state["paused"] is False
    )
    reasons = ["route_not_assessed"]
    if not state["enabled"]:
        reasons.append("capture_disabled")
    if state["mode"] == "off":
        reasons.append("capture_mode_off")
    if state["paused"]:
        reasons.append("capture_paused")
    if status["source_roots"]["configured_count"] == 0:
        reasons.append("source_roots_unavailable")
    if status["memory_root"]["assessment"] != "verified":
        reasons.append("memory_root_binding_not_assessed")
    reasons.extend(("recall_gate_not_passed", "extractor_capability_not_assessed"))
    status["activation"] = {
        "schema_version": 1,
        "route_assessment": "not_assessed",
        "conflicts": [],
        "readiness": {
            "installed_inert": installed_inert,
            "scanner_ready": False,
            "hook_ready": False,
            "backfill_runner_ready": False,
            "continuous_runner_ready": False,
        },
        "reasons": reasons,
        "consent_digest_matches": False,
        "evidence": evidence,
    }
    status["activation_digest"] = digest
    status["activation_ready"] = False
    status["activation_reasons"] = reasons
    status["route"] = {"assessment": "not_assessed", "conflicts": []}
    return status


def _scanner_reasons(capture: Any) -> list[str]:
    reasons: list[str] = []
    if not capture.enabled:
        reasons.append("capture_disabled")
    if capture.mode == "off":
        reasons.append("capture_mode_off")
    if capture.paused:
        reasons.append("capture_paused")
    if not capture.sources:
        reasons.append("source_roots_unavailable")
    if capture.budgets.backfill_window_days != 7:
        reasons.append("capture_window_unsupported")
    reasons.append("memory_root_binding_not_assessed")
    return reasons


def _not_assessed_scanner(capture: Any) -> dict[str, Any]:
    return {
        "assessment": "not_assessed",
        "code": "capture_disabled",
        "source_health": "not_assessed",
        "latest_census": {
            "assessment": "not_assessed",
            "run_count": None,
            "key_count": None,
        },
        "accounting": {
            "known_key_count": None,
            "accounted_key_count": None,
            "pending_key_count": None,
            "silent_loss_count": None,
        },
        "dirty_marker_count": None,
        "scan_state": {
            "assessment": "not_assessed",
            "binding_count": None,
            "latest_scan_at": None,
            "max_state_version": None,
        },
        "operation_eligible": False,
        "operation_reasons": _scanner_reasons(capture),
        "exclusions": {
            "task_id_count": len(capture.exclude.task_ids),
            "project_id_count": len(capture.exclude.project_ids),
            "project_id_assessment": "not_assessed",
        },
    }


def _not_assessed_runner(capture: Any) -> dict[str, Any]:
    return {
        "assessment": "not_assessed",
        "backlog_count": None,
        "oldest_unresolved_at": None,
        "max_attempt_count": None,
        "status_counts": {},
        "settled_token_count": None,
        "concurrency": capture.runner.concurrency,
    }


def _runner_status(
    snapshot: Any,
    configured: set[tuple[str, str]],
    assessment: str,
) -> dict[str, Any]:
    receipts = tuple(
        item
        for item in snapshot.receipts
        if (item.key.adapter_id, item.key.source_root_id) in configured
    )
    terminal = {"complete", "excluded", "coalesced"}
    unresolved = tuple(item for item in receipts if item.status not in terminal)
    status_counts: dict[str, int] = {}
    for item in receipts:
        status_counts[item.status] = status_counts.get(item.status, 0) + 1
    return {
        "assessment": assessment,
        "backlog_count": len(unresolved),
        "oldest_unresolved_at": min(
            (item.discovered_at for item in unresolved), default=None
        ),
        "max_attempt_count": max((item.attempt_count for item in receipts), default=0),
        "status_counts": dict(sorted(status_counts.items())),
        "settled_token_count": sum(item.token_usage.total_tokens for item in receipts),
        "concurrency": 1,
    }


def _scanner_status(
    paths: MemoryPaths, capture: Any, bindings: tuple[Any, ...]
) -> tuple[dict[str, Any], dict[str, Any]]:
    reasons = _scanner_reasons(capture)
    exclusions = {
        "task_id_count": len(capture.exclude.task_ids),
        "project_id_count": len(capture.exclude.project_ids),
        "project_id_assessment": "not_assessed",
    }
    empty = {
        "latest_census": {"assessment": "absent", "run_count": 0, "key_count": 0},
        "accounting": {
            "known_key_count": 0,
            "accounted_key_count": 0,
            "pending_key_count": 0,
            "silent_loss_count": 0,
        },
        "dirty_marker_count": 0,
        "scan_state": {
            "assessment": "absent",
            "binding_count": 0,
            "latest_scan_at": None,
            "max_state_version": None,
        },
    }
    if not paths.capture.root.exists():
        return (
            {
                "assessment": "absent",
                "code": "scanner_state_absent",
                "source_health": "not_assessed",
                **empty,
                "operation_eligible": False,
                "operation_reasons": reasons,
                "exclusions": exclusions,
            },
            {
                "assessment": "absent",
                "backlog_count": 0,
                "oldest_unresolved_at": None,
                "max_attempt_count": 0,
                "status_counts": {},
                "settled_token_count": 0,
                "concurrency": 1,
            },
        )

    store = CaptureStore(paths)
    try:
        snapshot = store.read_snapshot()
    except RuntimeError:
        busy_reasons = [*reasons, "scanner_busy"]
        return (
            {
                "assessment": "busy",
                "code": "scanner_busy",
                "source_health": "not_assessed",
                "latest_census": {"assessment": "busy", "run_count": None, "key_count": None},
                "accounting": {
                    "known_key_count": None,
                    "accounted_key_count": None,
                    "pending_key_count": None,
                    "silent_loss_count": None,
                },
                "dirty_marker_count": None,
                "scan_state": {
                    "assessment": "busy",
                    "binding_count": None,
                    "latest_scan_at": None,
                    "max_state_version": None,
                },
                "operation_eligible": False,
                "operation_reasons": busy_reasons,
                "exclusions": exclusions,
            },
            {
                "assessment": "busy",
                "backlog_count": None,
                "oldest_unresolved_at": None,
                "max_attempt_count": None,
                "status_counts": {},
                "settled_token_count": None,
                "concurrency": 1,
            },
        )

    corrupt = bool(snapshot.diagnostics)
    configured = {
        (binding.adapter_id, binding.source_root_id) for binding in bindings
    }
    runs = [
        (run.started_at, len(run.revision_keys))
        for run in snapshot.census_runs
        if (run.binding.adapter_id, run.binding.source_root_id) in configured
    ]
    latest = max(runs, default=None, key=lambda item: item[0])

    states = [
        state
        for state in snapshot.scan_states
        if (state.binding.adapter_id, state.binding.source_root_id) in configured
    ]
    dirty_count = sum(
        (marker.adapter_id, marker.source_root_id) in configured
        for marker in snapshot.dirty_markers
    )
    census = tuple(
        revision
        for revision in snapshot.census
        if (revision.key.adapter_id, revision.key.source_root_id) in configured
    )
    known = len(census)
    accounted = sum(item.key in snapshot.accounted_keys for item in census)
    pending = known - accounted
    configured_quarantines = tuple(
        item
        for item in snapshot.source_quarantines
        if (item.adapter_id, item.source_root_id) in configured
    )
    configured_conflict = any(
        hashlib.sha256(
            f"{adapter_id}\0{source_root_id}".encode("utf-8")
        ).hexdigest()
        in snapshot.source_conflict_digests
        for adapter_id, source_root_id in configured
    )
    state_absent = not (
        runs
        or states
        or known
        or dirty_count
        or configured_quarantines
        or configured_conflict
    )
    source_health = (
        "degraded"
        if corrupt or configured_quarantines or configured_conflict
        else ("not_assessed" if state_absent else "healthy")
    )
    assessment = (
        "corrupt"
        if corrupt
        else (
            "absent"
            if state_absent
            else ("degraded" if source_health == "degraded" else "ready")
        )
    )
    code = {
        "corrupt": "scanner_corrupt",
        "degraded": "scanner_degraded",
        "ready": "scanner_ready",
        "absent": "scanner_state_absent",
    }[assessment]
    if corrupt:
        reasons.append("scanner_corrupt")
    return (
        {
            "assessment": assessment,
            "code": code,
            "source_health": source_health,
            "latest_census": {
                "assessment": "available" if latest is not None else "absent",
                "run_count": len(runs),
                "key_count": latest[1] if latest is not None else 0,
            },
            "accounting": {
                "known_key_count": known,
                "accounted_key_count": accounted,
                "pending_key_count": pending,
                "silent_loss_count": pending,
            },
            "dirty_marker_count": dirty_count,
            "scan_state": {
                "assessment": "available" if states else "absent",
                "binding_count": len(states),
                "latest_scan_at": max(
                    (item.last_scan_at for item in states if item.last_scan_at is not None),
                    default=None,
                ),
                "max_state_version": max(
                    (item.state_version for item in states), default=None
                ),
            },
            "operation_eligible": False,
            "operation_reasons": reasons,
            "exclusions": exclusions,
        },
        _runner_status(snapshot, configured, assessment),
    )


def bind_capture_status(status: dict[str, Any], *, evidence_kind: str) -> dict[str, Any]:
    """Bind a fresh status document to the caller's already selected root."""

    bound = copy.deepcopy(status)
    bound["memory_root"] = {
        **bound["memory_root"],
        "assessment": "verified",
        "matches_host_binding": True,
        "evidence": {"kind": evidence_kind},
    }
    scanner = bound["scanner"]
    scanner["operation_reasons"] = [
        item
        for item in scanner["operation_reasons"]
        if item != "memory_root_binding_not_assessed"
    ]
    scanner["operation_eligible"] = not scanner["operation_reasons"]
    return _attach_activation(bound)


def capture_status(value: MemoryPaths | Path) -> dict[str, Any]:
    paths = _paths(value)
    config_path = paths.root / "config.yaml"
    config_exists = config_path.exists()
    config_text = strict_read_text(config_path) if config_exists else default_config_text()
    config = load_runtime_config(paths)
    capture = config.capture
    memory_fingerprint = root_fingerprint(paths)
    bindings: tuple[Any, ...] = ()
    source_ids: list[str] = []
    if capture.enabled:
        from agc_runtime.capture_source import SourceBindingKey, source_root_id_for

        source_ids = [source_root_id_for(Path(item)) for item in capture.sources]
        bindings = tuple(
            SourceBindingKey.from_mapping(
                {
                    "schema_version": 1,
                    "adapter_id": "codex",
                    "source_root_id": source_id,
                }
            )
            for source_id in source_ids
        )
    if not capture.enabled:
        scanner = _not_assessed_scanner(capture)
        runner = _not_assessed_runner(capture)
    else:
        scanner, runner = _scanner_status(paths, capture, bindings)
    status = {
        "schema_version": 2,
        "config_source": {
            "kind": "memory_root_config" if config_exists else "runtime_default",
            "sha256": _fingerprint(config_text),
        },
        "runtime": {"version": __version__, "sha256": _runtime_fingerprint()},
        "memory_root": {
            "fingerprint": memory_fingerprint,
            "assessment": "not_assessed",
            "matches_host_binding": None,
            "evidence": None,
        },
        "source_roots": {
            "configured_count": len(capture.sources),
            "assessment": "configured" if capture.enabled else "unavailable",
            "ids": source_ids,
        },
        "extractor_boundary": {
            "kind": capture.extractor.kind,
            "model_configured": capture.extractor.model is not None,
            "capability_assessment": "not_assessed",
        },
        "budgets": {
            "backfill_window_days": capture.budgets.backfill_window_days,
            "backfill_total_tokens": capture.budgets.backfill_total_tokens,
            "incremental_total_tokens": capture.budgets.incremental_total_tokens,
            "runner_concurrency": capture.runner.concurrency,
            "max_attempts": capture.runner.max_attempts,
        },
        "state": {
            "enabled": capture.enabled,
            "paused": capture.paused,
            "mode": capture.mode,
            "scanner_only": capture.mode == "scanner_only",
        },
        "route": {"assessment": "not_assessed", "conflicts": []},
        "cursor_key": CaptureStore(paths).cursor_key_status(),
        "scanner": scanner,
        "runner": runner,
    }
    return _attach_activation(status)


__all__ = ["bind_capture_status", "capture_status"]
