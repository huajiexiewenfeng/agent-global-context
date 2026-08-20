"""Content-free preparation and authorization for explicit Capture backfill."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping, Sequence

from agc_runtime.capture_budget import CaptureTokenBudget
from agc_runtime.capture_store import CaptureStore, root_fingerprint
from agc_runtime.paths import MemoryPaths
from agc_runtime.runtime_config import load_runtime_config


def _canonical_digest(value: Mapping[str, Any]) -> str:
    try:
        payload = json.dumps(
            dict(value),
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
    except (TypeError, ValueError, UnicodeError) as error:
        raise ValueError("capture_backfill_contract_invalid") from error
    return hashlib.sha256(payload).hexdigest()


def authorization_digest_for(value: Mapping[str, Any]) -> str:
    """Bind a user authorization to content-free execution boundaries."""

    if not isinstance(value, Mapping) or not value:
        raise ValueError("capture_backfill_contract_invalid")
    return _canonical_digest(value)


@dataclass(frozen=True)
class BackfillPreparation:
    schema_version: int
    memory_root_fingerprint: str
    census_id: str
    source_binding_digest: str
    capture_config_digest: str
    extractor_identity: str
    extractor_version: str
    extractor_schema_version: str
    model_boundary: str
    provider_boundary: str
    frozen_revision_count: int
    ready_revision_count: int
    accounted_revision_count: int
    backfill_total_tokens: int
    charged_tokens: int
    remaining_tokens: int
    scanner_health: str
    authorization_digest: str

    def to_mapping(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "memory_root_fingerprint": self.memory_root_fingerprint,
            "census_id": self.census_id,
            "source_binding_digest": self.source_binding_digest,
            "capture_config_digest": self.capture_config_digest,
            "extractor_identity": self.extractor_identity,
            "extractor_version": self.extractor_version,
            "extractor_schema_version": self.extractor_schema_version,
            "model_boundary": self.model_boundary,
            "provider_boundary": self.provider_boundary,
            "frozen_revision_count": self.frozen_revision_count,
            "ready_revision_count": self.ready_revision_count,
            "accounted_revision_count": self.accounted_revision_count,
            "backfill_total_tokens": self.backfill_total_tokens,
            "charged_tokens": self.charged_tokens,
            "remaining_tokens": self.remaining_tokens,
            "scanner_health": self.scanner_health,
            "authorization_digest": self.authorization_digest,
        }


def _effective_config_digest(capture: object, descriptors: Sequence[object]) -> str:
    def hashed(items: Sequence[str]) -> list[str]:
        return sorted(hashlib.sha256(item.encode("utf-8")).hexdigest() for item in items)

    value = {
        "schema_version": capture.schema_version,
        "enabled": capture.enabled,
        "mode": capture.mode,
        "paused": capture.paused,
        "include_subagents": capture.include_subagents,
        "sources": [item.to_mapping() for item in descriptors],
        "hook": {"enabled": capture.hook.enabled},
        "runner": {
            "concurrency": capture.runner.concurrency,
            "max_attempts": capture.runner.max_attempts,
            "backoff_seconds": list(capture.runner.backoff_seconds),
        },
        "capsule": {
            "target_tokens": capture.capsule.target_tokens,
            "max_tokens": capture.capsule.max_tokens,
        },
        "budgets": {
            "backfill_window_days": capture.budgets.backfill_window_days,
            "backfill_total_tokens": capture.budgets.backfill_total_tokens,
            "incremental_total_tokens": capture.budgets.incremental_total_tokens,
        },
        "extractor": {
            "kind": capture.extractor.kind,
            "executable_digest": hashlib.sha256(
                capture.extractor.executable.encode("utf-8")
            ).hexdigest(),
            "model": capture.extractor.model,
        },
        "exclude": {
            "task_id_digests": hashed(capture.exclude.task_ids),
            "project_id_digests": hashed(capture.exclude.project_ids),
        },
    }
    return _canonical_digest(value)


def prepare_backfill(
    *,
    paths: MemoryPaths,
    adapters: Sequence[object],
    extractor: object,
    now: str,
) -> BackfillPreparation:
    """Freeze one Census and return a content-free authorization summary."""

    config = load_runtime_config(paths)
    capture = config.capture
    if not capture.enabled:
        raise ValueError("capture_disabled")
    if capture.mode != "scanner_only":
        raise ValueError("capture_mode_unsupported")
    if capture.paused:
        raise ValueError("capture_paused")
    if not capture.sources:
        raise ValueError("capture_sources_unconfigured")
    if capture.budgets.backfill_window_days != 7:
        raise ValueError("capture_window_unsupported")
    if capture.budgets.backfill_total_tokens is None:
        raise ValueError("capture_budget_unavailable")
    if len(adapters) != 1 or len(capture.sources) != 1:
        raise ValueError("capture_backfill_source_count_unsupported")

    descriptor = extractor.describe()
    probe = extractor.probe_capabilities()
    if not probe.available:
        raise RuntimeError("capture_extractor_unavailable")
    adapter_descriptors = tuple(item.describe() for item in adapters)

    from agc_runtime.capture_scanner import CaptureScanner

    store = CaptureStore(paths)
    report = CaptureScanner(
        store,
        tuple(adapters),
        excluded_task_ids=capture.exclude.task_ids,
    ).scan(run_started_at=now, force_full=True)
    if report.source_health != "healthy":
        raise ValueError("capture_scanner_unhealthy")
    snapshot = store.read_snapshot()
    if snapshot.diagnostics:
        raise ValueError("capture_integrity_failed")
    binding = adapter_descriptors[0]
    runs = tuple(
        item
        for item in snapshot.census_runs
        if item.binding.adapter_id == binding.adapter_id
        and item.binding.source_root_id == binding.source_root_id
        and item.started_at == now
    )
    if len(runs) != 1:
        raise ValueError("capture_census_unavailable")
    census = runs[0]
    keys = frozenset(census.revision_keys)
    ready_statuses = frozenset({"discovered", "queued", "retryable"})
    ready = sum(item.key in keys and item.status in ready_statuses for item in snapshot.receipts)
    accounted = sum(key in snapshot.accounted_keys for key in keys)
    budget = CaptureTokenBudget(
        paths,
        pool="backfill",
        census_id=census.census_id,
        ceiling=capture.budgets.backfill_total_tokens,
    ).snapshot()
    if budget.remaining_tokens is None:
        raise ValueError("capture_budget_unavailable")

    source_binding_digest = _canonical_digest(
        {"sources": [item.to_mapping() for item in adapter_descriptors]}
    )
    config_digest = _effective_config_digest(capture, adapter_descriptors)
    authorization_fields = {
        "memory_root_fingerprint": root_fingerprint(paths),
        "census_id": census.census_id,
        "source_binding_digest": source_binding_digest,
        "capture_config_digest": config_digest,
        "extractor_identity": probe.executable_identity,
        "extractor_version": descriptor.extractor_version,
        "extractor_schema_version": descriptor.extractor_schema_version,
        "model_boundary": probe.model_boundary,
        "provider_boundary": probe.provider_boundary,
        "backfill_total_tokens": capture.budgets.backfill_total_tokens,
    }
    return BackfillPreparation(
        1,
        authorization_fields["memory_root_fingerprint"],
        census.census_id,
        source_binding_digest,
        config_digest,
        probe.executable_identity,
        descriptor.extractor_version,
        descriptor.extractor_schema_version,
        probe.model_boundary,
        probe.provider_boundary,
        len(keys),
        ready,
        accounted,
        capture.budgets.backfill_total_tokens,
        budget.charged_tokens,
        budget.remaining_tokens,
        report.source_health,
        authorization_digest_for(authorization_fields),
    )


__all__ = [
    "BackfillPreparation",
    "authorization_digest_for",
    "prepare_backfill",
]
