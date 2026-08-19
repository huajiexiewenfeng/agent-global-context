"""Content-safe diagnostics for the disabled Capture core."""

from __future__ import annotations

import hashlib
import copy
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


def _scanner_reasons(capture: Any) -> list[str]:
    reasons: list[str] = []
    if not capture.enabled:
        reasons.append("capture_disabled")
    if capture.mode == "off":
        reasons.append("capture_mode_off")
    elif capture.mode == "runner":
        reasons.append("capture_runner_unsupported")
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


def _scanner_status(paths: MemoryPaths, capture: Any) -> tuple[dict[str, Any], list[str]]:
    from agc_runtime.capture_source import DirtyMarker, ScanState
    from agc_runtime.capture_transaction import read_json

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
            [],
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
            [],
        )

    corrupt = bool(snapshot.diagnostics)
    runs: list[tuple[str, int]] = []
    run_root = paths.capture.root / "census-runs"
    if run_root.exists():
        try:
            for path in sorted(run_root.iterdir()):
                if path.name.startswith("."):
                    continue
                census, members = store._read_frozen_run(path)
                runs.append((census.started_at, len(members)))
        except (OSError, TypeError, ValueError):
            corrupt = True
    latest = max(runs, default=None, key=lambda item: item[0])

    states: list[ScanState] = []
    if paths.capture.scan_state.exists():
        try:
            for path in sorted(paths.capture.scan_state.iterdir()):
                if not path.is_file() or not path.name.startswith("state-") or path.suffix != ".json":
                    raise ValueError("invalid scan state object")
                states.append(ScanState.from_mapping(read_json(path)))
        except (OSError, TypeError, ValueError):
            corrupt = True

    dirty_count = 0
    if paths.capture.dirty.exists():
        try:
            for path in sorted(paths.capture.dirty.iterdir()):
                if not path.is_file() or path.suffix != ".json":
                    raise ValueError("invalid dirty marker object")
                DirtyMarker.from_mapping(read_json(path))
                dirty_count += 1
        except (OSError, TypeError, ValueError):
            corrupt = True

    known = len(snapshot.census)
    accounted = sum(store.is_revision_accounted(item) for item in snapshot.census)
    pending = known - accounted
    state_absent = not (
        runs
        or states
        or known
        or dirty_count
        or snapshot.source_quarantines
        or snapshot.source_conflict_count
    )
    source_health = (
        "degraded"
        if corrupt or snapshot.source_quarantines or snapshot.source_conflict_count
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
        "corrupt": "scanner_state_corrupt",
        "degraded": "scanner_degraded",
        "ready": "scanner_ready",
        "absent": "scanner_state_absent",
    }[assessment]
    if corrupt:
        reasons.append("scanner_state_corrupt")
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
        [],
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
    bound["activation_reasons"] = [
        item
        for item in bound["activation_reasons"]
        if item != "memory_root_binding_not_assessed"
    ]
    scanner = bound["scanner"]
    scanner["operation_reasons"] = [
        item
        for item in scanner["operation_reasons"]
        if item != "memory_root_binding_not_assessed"
    ]
    scanner["operation_eligible"] = not scanner["operation_reasons"]
    return bound


def capture_status(value: MemoryPaths | Path) -> dict[str, Any]:
    paths = _paths(value)
    config_path = paths.root / "config.yaml"
    config_exists = config_path.exists()
    config_text = strict_read_text(config_path) if config_exists else default_config_text()
    config = load_runtime_config(paths)
    capture = config.capture
    memory_fingerprint = root_fingerprint(paths)
    reasons: list[str] = []
    if not capture.enabled:
        reasons.append("capture_disabled")
    if capture.mode == "off":
        reasons.append("capture_mode_off")
    if not capture.sources:
        reasons.append("source_roots_unavailable")
    reasons.extend(("extractor_capability_not_assessed", "route_not_assessed"))
    reasons.append("memory_root_binding_not_assessed")
    scanner, source_ids = (
        (_not_assessed_scanner(capture), [])
        if not capture.enabled
        else _scanner_status(paths, capture)
    )
    if capture.enabled:
        from agc_runtime.capture_source import source_root_id_for

        source_ids = [source_root_id_for(Path(item)) for item in capture.sources]
    return {
        "config_source": {
            "kind": "memory_root_config" if config_exists else "runtime_default",
            "sha256": _fingerprint(config_text),
        },
        "runtime": {"version": __version__},
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
        "activation_ready": False,
        "activation_reasons": reasons,
    }


__all__ = ["bind_capture_status", "capture_status"]
