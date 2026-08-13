"""Content-safe diagnostics for the disabled Capture core."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from agc_runtime import __version__
from agc_runtime.paths import MemoryPaths
from agc_runtime.runtime_config import load_runtime_config
from agc_runtime.utf8_io import strict_read_text


def _paths(value: MemoryPaths | Path) -> MemoryPaths:
    return value if isinstance(value, MemoryPaths) else MemoryPaths.from_root(value)


def _fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def capture_status(value: MemoryPaths | Path) -> dict[str, Any]:
    paths = _paths(value)
    config_path = paths.root / "config.yaml"
    config_text = strict_read_text(config_path) if config_path.exists() else ""
    config = load_runtime_config(paths)
    capture = config.capture
    # Source paths are intentionally converted to opaque IDs; no absolute source
    # path is returned by this diagnostic surface.
    source_root_ids = tuple(sorted({_fingerprint(item) for item in capture.sources}))
    enabled = capture.enabled
    scanner_only = capture.mode == "scanner_only"
    route_conflicts: list[dict[str, str]] = []
    return {
        "config_source": {"kind": "memory_root_config", "fingerprint": _fingerprint(config_text)},
        "runtime": {"version": __version__},
        "memory_root": {"fingerprint": _fingerprint(str(paths.root)), "matches_host_binding": True},
        "configured_source_root_ids": list(source_root_ids),
        "extractor_boundary": {"kind": capture.extractor.kind, "model_configured": capture.extractor.model is not None, "host_binding_present": False},
        "budgets": {"backfill_window_days": capture.budgets.backfill_window_days, "backfill_total_tokens": capture.budgets.backfill_total_tokens, "incremental_total_tokens": capture.budgets.incremental_total_tokens, "runner_concurrency": capture.runner.concurrency, "max_attempts": capture.runner.max_attempts},
        "state": {"enabled": enabled, "paused": capture.paused, "mode": capture.mode, "scanner_only": scanner_only},
        "route_conflicts": route_conflicts,
        "activation_ready": False,
    }
