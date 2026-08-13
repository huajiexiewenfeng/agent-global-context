"""Content-safe diagnostics for the disabled Capture core."""

from __future__ import annotations

import hashlib
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


def capture_status(
    value: MemoryPaths | Path,
    *,
    _host_bound: bool = False,
) -> dict[str, Any]:
    paths = _paths(value)
    config_path = paths.root / "config.yaml"
    config_exists = config_path.exists()
    config_text = strict_read_text(config_path) if config_exists else default_config_text()
    config = load_runtime_config(paths)
    capture = config.capture
    memory_fingerprint = root_fingerprint(paths)
    memory_assessment = "verified" if _host_bound else "not_assessed"
    reasons: list[str] = []
    if not capture.enabled:
        reasons.append("capture_disabled")
    if capture.mode == "off":
        reasons.append("capture_mode_off")
    reasons.extend((
        "source_roots_unavailable",
        "extractor_capability_not_assessed",
        "route_not_assessed",
    ))
    if not _host_bound:
        reasons.append("memory_root_binding_not_assessed")
    return {
        "config_source": {
            "kind": "memory_root_config" if config_exists else "runtime_default",
            "sha256": _fingerprint(config_text),
        },
        "runtime": {"version": __version__},
        "memory_root": {
            "fingerprint": memory_fingerprint,
            "assessment": memory_assessment,
            "matches_host_binding": True if _host_bound else None,
            "evidence": {"kind": "mcp_memory_root"} if _host_bound else None,
        },
        "source_roots": {
            "configured_count": len(capture.sources),
            "assessment": "unavailable",
            "ids": [],
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
        "activation_ready": False,
        "activation_reasons": reasons,
    }
