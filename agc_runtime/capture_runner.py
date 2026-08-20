"""Explicit, single-concurrency manual Capture backfill runner."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Sequence

from agc_runtime.capture_backfill import (
    BackfillPreparation,
    _canonical_digest,
    _effective_config_digest,
)
from agc_runtime.capture_budget import BudgetUnavailable, CaptureTokenBudget
from agc_runtime.capture_contracts import (
    CAPTURE_SCHEMA_VERSION,
    CaptureReceipt,
    CollectedObservation,
    SanitizedError,
    TokenUsage,
    observation_fingerprint_for,
    observation_id_for,
)
from agc_runtime.capture_store import CaptureStore, ReceiptTransitionPatch, root_fingerprint
from agc_runtime.paths import MemoryPaths
from agc_runtime.runtime_config import load_runtime_config


@dataclass(frozen=True)
class RunnerReport:
    attempted_count: int
    completed_count: int
    failed_count: int
    deferred_budget_count: int
    lease_contention_count: int
    reserved_attempt_count: int
    extractor_call_count: int
    observation_count: int
    charged_tokens: int
    silent_loss_count: int

    def to_mapping(self) -> dict[str, int]:
        return {
            name: getattr(self, name)
            for name in self.__dataclass_fields__
        }


class CaptureRunner:
    def __init__(
        self,
        paths: MemoryPaths,
        adapters: Sequence[object],
        extractor: object,
        preparation: BackfillPreparation,
    ) -> None:
        if not isinstance(paths, MemoryPaths) or not isinstance(
            preparation, BackfillPreparation
        ):
            raise ValueError("capture_runner_contract_invalid")
        self.paths = paths
        self.adapters = tuple(adapters)
        self.extractor = extractor
        self.preparation = preparation

    def _validate_authorization(self, digest: str) -> tuple[object, object]:
        if digest != self.preparation.authorization_digest:
            raise RuntimeError("capture_backfill_authorization_stale")
        config = load_runtime_config(self.paths)
        descriptors = tuple(item.describe() for item in self.adapters)
        if len(descriptors) != 1:
            raise RuntimeError("capture_backfill_authorization_stale")
        source_digest = _canonical_digest(
            {"sources": [item.to_mapping() for item in descriptors]}
        )
        descriptor = self.extractor.describe()
        probe = self.extractor.probe_capabilities()
        snapshot = CaptureStore(self.paths).read_snapshot()
        census_present = any(
            item.census_id == self.preparation.census_id
            for item in snapshot.census_runs
        )
        boundaries = (
            root_fingerprint(self.paths) == self.preparation.memory_root_fingerprint,
            source_digest == self.preparation.source_binding_digest,
            _effective_config_digest(config.capture, descriptors)
            == self.preparation.capture_config_digest,
            descriptor.extractor_version == self.preparation.extractor_version,
            descriptor.extractor_schema_version
            == self.preparation.extractor_schema_version,
            probe.available,
            probe.executable_identity == self.preparation.extractor_identity,
            probe.model_boundary == self.preparation.model_boundary,
            probe.provider_boundary == self.preparation.provider_boundary,
            config.capture.budgets.backfill_total_tokens
            == self.preparation.backfill_total_tokens,
            census_present,
        )
        if not all(boundaries):
            raise RuntimeError("capture_backfill_authorization_stale")
        return config.capture, descriptor

    @staticmethod
    def _retry_at(now: str) -> str:
        parsed = datetime.fromisoformat(now.replace("Z", "+00:00"))
        return (parsed + timedelta(seconds=60)).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _observations(
        accepted: Sequence[object],
        receipt: CaptureReceipt,
        revision: object,
        *,
        captured_at: str,
        extractor_version: str,
    ) -> tuple[CollectedObservation, ...]:
        observations: list[CollectedObservation] = []
        for ordinal, draft in enumerate(accepted):
            mapping = {
                "schema_version": CAPTURE_SCHEMA_VERSION,
                "observation_id": "co_" + "0" * 64,
                "receipt_id": receipt.receipt_id,
                "source": {
                    **receipt.key.to_mapping(),
                    "locator": revision.locator,
                },
                "ordinal": ordinal,
                "observation_fingerprint": "0" * 64,
                "statement": draft.statement,
                "assertion": {
                    "subject": draft.assertion_subject,
                    "mode": draft.assertion_mode,
                    "modality": draft.modality,
                },
                "primary_category": draft.primary_category,
                "taxonomy_version": receipt.taxonomy_version,
                "kind": draft.kind,
                "scopes": list(draft.scopes),
                "project_scope": draft.project_scope,
                "confidence": draft.confidence,
                "sensitivity": draft.sensitivity,
                "signal_type": draft.signal_type,
                "observed_at": revision.completed_at,
                "captured_at": captured_at,
                "extractor_version": extractor_version,
                "processing_state": "collected",
            }
            mapping["observation_fingerprint"] = observation_fingerprint_for(mapping)
            mapping["observation_id"] = observation_id_for(
                receipt.receipt_id, mapping["observation_fingerprint"]
            )
            observations.append(CollectedObservation.from_mapping(mapping))
        return tuple(observations)

    def run_manual_backfill(
        self,
        *,
        authorization_digest: str,
        max_items: int,
        now: str,
    ) -> RunnerReport:
        if (
            not isinstance(authorization_digest, str)
            or len(authorization_digest) != 64
            or type(max_items) is not int
            or not 1 <= max_items <= 100
        ):
            raise ValueError("capture_runner_contract_invalid")
        capture, extractor_descriptor = self._validate_authorization(
            authorization_digest
        )
        from agc_runtime.capture_capsule import CapsulePolicy
        from agc_runtime.capture_safety import persistence_gate

        policy = CapsulePolicy(
            target_token_limit=capture.capsule.target_tokens,
            hard_token_limit=capture.capsule.max_tokens,
        )
        store = CaptureStore(self.paths, clock=lambda: now)
        snapshot = store.read_snapshot()
        run = next(
            item
            for item in snapshot.census_runs
            if item.census_id == self.preparation.census_id
        )
        revisions = {
            item.key: item
            for item in store.frozen_revisions()
            if item.key in frozenset(run.revision_keys)
        }
        ready = tuple(
            sorted(
                (
                    item
                    for item in store.ready_revisions()
                    if item.key in revisions
                ),
                key=lambda item: (item.discovered_at, item.receipt_id),
            )[:max_items]
        )
        budget = CaptureTokenBudget(
            self.paths,
            pool="backfill",
            census_id=self.preparation.census_id,
            ceiling=capture.budgets.backfill_total_tokens,
            clock=lambda: now,
        )
        before_charge = budget.snapshot().charged_tokens
        attempted = completed = failed = deferred = contention = 0
        reserved_count = extractor_calls = observation_count = 0
        adapter_by_binding = {
            (item.describe().adapter_id, item.describe().source_root_id): item
            for item in self.adapters
        }
        maximum = TokenUsage(
            capture.capsule.max_tokens,
            capture.capsule.max_tokens,
            capture.capsule.max_tokens * 2,
        )
        for current in ready:
            attempted += 1
            lease = store.acquire_lease(
                current.key,
                owner_id="manual-backfill",
                now=now,
                ttl_seconds=300,
            )
            if lease is None:
                contention += 1
                continue
            reservation = None
            try:
                revision = revisions[current.key]
                adapter = adapter_by_binding[
                    (current.key.adapter_id, current.key.source_root_id)
                ]
                capsule_result = adapter.load_capsule(revision, policy)
                try:
                    reservation = budget.reserve(
                        current.key,
                        current.attempt_count + 1,
                        maximum,
                    )
                except BudgetUnavailable:
                    store.transition(
                        lease,
                        expected=frozenset({current.status}),
                        target="deferred_budget",
                        patch=ReceiptTransitionPatch(updated_at=now),
                    )
                    deferred += 1
                    continue
                reserved_count += 1
                extracting = store.begin_extraction(
                    lease, capsule_result, extractor_descriptor, now=now
                )
                extractor_calls += 1
                result = self.extractor.extract(
                    capsule_result.capsule, reservation
                )
                settlement = budget.prepare_settlement(reservation, result.usage)
                if not result.succeeded:
                    store.transition_with_settlement(
                        lease,
                        expected=frozenset({"extracting"}),
                        target="retryable",
                        patch=ReceiptTransitionPatch(
                            updated_at=now,
                            next_retry_at=self._retry_at(now),
                            sanitized_error=result.error,
                        ),
                        reservation=reservation,
                        settlement=settlement,
                    )
                    failed += 1
                    continue
                persisted = persistence_gate(
                    (item.to_mapping() for item in result.drafts),
                    capsule_result.capsule,
                )
                observations = self._observations(
                    persisted.accepted,
                    extracting,
                    revision,
                    captured_at=now,
                    extractor_version=extractor_descriptor.extractor_version,
                )
                if observations:
                    zero_reason = None
                elif not result.drafts:
                    zero_reason = "extractor_empty"
                elif persisted.filtered_safety_count:
                    zero_reason = "all_filtered_safety"
                elif persisted.duplicate_count:
                    zero_reason = "all_duplicates_within_revision"
                else:
                    zero_reason = "all_filtered_policy"
                terminal = CaptureReceipt.from_mapping(
                    {
                        **extracting.to_mapping(),
                        "status": "complete",
                        "updated_at": now,
                        "observation_count": len(observations),
                        "filtered_counts": {
                            "safety": persisted.filtered_safety_count,
                            "policy": persisted.filtered_policy_count,
                            "over_limit": persisted.over_limit_count,
                        },
                        "duplicate_suppression_count": persisted.duplicate_count,
                        "token_usage": settlement.charged_usage.to_mapping(),
                        "usage_quality": settlement.usage_quality,
                        "zero_reason": zero_reason,
                    }
                )
                store.commit_extraction(
                    lease,
                    observations,
                    terminal,
                    reservation=reservation,
                    settlement=settlement,
                )
                completed += 1
                observation_count += len(observations)
            except (KeyError, OSError, TypeError, UnicodeError, ValueError):
                failed += 1
            finally:
                try:
                    store.release_lease(lease)
                except (FileNotFoundError, OSError, ValueError):
                    pass
        charged = budget.snapshot().charged_tokens - before_charge
        return RunnerReport(
            attempted,
            completed,
            failed,
            deferred,
            contention,
            reserved_count,
            extractor_calls,
            observation_count,
            charged,
            0,
        )


__all__ = ["CaptureRunner", "RunnerReport"]
