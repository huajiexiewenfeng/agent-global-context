"""Explicit, single-concurrency manual Capture backfill runner."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
import time
from typing import Any, Sequence

from agc_runtime.capture_backfill import (
    BackfillPreparation,
    _canonical_digest,
    _effective_config_digest,
)
from agc_runtime.capture_budget import BudgetUnavailable, CaptureTokenBudget
from agc_runtime.capture_contracts import (
    CAPTURE_SCHEMA_VERSION,
    CaptureKey,
    CaptureReceipt,
    CollectedObservation,
    SanitizedError,
    TokenUsage,
    observation_fingerprint_for,
    observation_id_for,
)
from agc_runtime.capture_store import CaptureStore, ReceiptTransitionPatch, root_fingerprint
from agc_runtime.locking import capture_runner_lock
from agc_runtime.paths import MemoryPaths
from agc_runtime.runtime_config import load_runtime_config


def retry_capture_receipt(
    paths: MemoryPaths, receipt_id: str, *, now: str
) -> CaptureReceipt:
    """Explicitly requeue one parked receipt without invoking semantic work."""

    if not isinstance(receipt_id, str):
        raise ValueError("capture_retry_target_invalid")
    store = CaptureStore(paths, clock=lambda: now)
    current = next(
        (item for item in store.read_snapshot().receipts if item.receipt_id == receipt_id),
        None,
    )
    if current is None or current.status not in {"failed", "quarantined"}:
        raise ValueError("capture_retry_target_not_parked")
    lease = store.acquire_lease(
        current.key,
        owner_id="explicit-retry",
        now=now,
        ttl_seconds=60,
    )
    if lease is None:
        raise RuntimeError("capture_retry_busy")
    try:
        return store.transition(
            lease,
            expected=frozenset({current.status}),
            target="queued",
            patch=ReceiptTransitionPatch(
                updated_at=now,
                reopen_reason="explicit_retry",
            ),
        )
    finally:
        try:
            store.release_lease(lease)
        except (FileNotFoundError, OSError, ValueError):
            pass


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
    backlog_count: int
    oldest_unresolved_at: str | None
    attempt_count_delta: int
    status_deltas: tuple[tuple[str, int], ...]
    run_time_ms: int
    source_bytes_read: int | None
    peak_process_count: int

    def to_mapping(self) -> dict[str, Any]:
        result = {name: getattr(self, name) for name in self.__dataclass_fields__}
        result["status_deltas"] = dict(self.status_deltas)
        return result


class CaptureRunner:
    def __init__(
        self,
        paths: MemoryPaths,
        adapters: Sequence[object],
        extractor: object,
        preparation: BackfillPreparation | None,
    ) -> None:
        if not isinstance(paths, MemoryPaths) or (
            preparation is not None
            and not isinstance(preparation, BackfillPreparation)
        ):
            raise ValueError("capture_runner_contract_invalid")
        self.paths = paths
        self.adapters = tuple(adapters)
        self.extractor = extractor
        self.preparation = preparation

    def _validate_authorization(self, digest: str) -> tuple[object, object]:
        if self.preparation is None:
            raise RuntimeError("capture_backfill_authorization_stale")
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

    def retry_revision(self, key: CaptureKey, *, now: str) -> CaptureReceipt:
        """Explicitly requeue one parked revision without invoking the Extractor."""

        key = CaptureKey.from_mapping(key.to_mapping())
        current = next(
            (
                item
                for item in CaptureStore(self.paths).read_snapshot().receipts
                if item.key == key
            ),
            None,
        )
        if current is None:
            raise ValueError("capture_retry_target_not_parked")
        return retry_capture_receipt(self.paths, current.receipt_id, now=now)

    @staticmethod
    def _retry_at(now: str, seconds: int) -> str:
        parsed = datetime.fromisoformat(now.replace("Z", "+00:00"))
        return (parsed + timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _is_due(receipt: CaptureReceipt, now: str) -> bool:
        if receipt.status != "retryable":
            return receipt.status in {"discovered", "queued"}
        if receipt.next_retry_at is None:
            return False
        return datetime.fromisoformat(
            receipt.next_retry_at.replace("Z", "+00:00")
        ) <= datetime.fromisoformat(now.replace("Z", "+00:00"))

    @staticmethod
    def _backlog_count(
        receipts: Sequence[CaptureReceipt], keys: frozenset[object]
    ) -> int:
        terminal = {"complete", "excluded", "coalesced"}
        return sum(item.key in keys and item.status not in terminal for item in receipts)

    @staticmethod
    def _oldest_unresolved_at(
        receipts: Sequence[CaptureReceipt], keys: frozenset[object]
    ) -> str | None:
        terminal = {"complete", "excluded", "coalesced"}
        return min(
            (
                item.discovered_at
                for item in receipts
                if item.key in keys and item.status not in terminal
            ),
            default=None,
        )

    @staticmethod
    def _attempt_and_status_deltas(
        before: Sequence[CaptureReceipt],
        after: Sequence[CaptureReceipt],
        keys: frozenset[object],
    ) -> tuple[int, tuple[tuple[str, int], ...]]:
        prior = {item.key: item for item in before if item.key in keys}
        attempts = 0
        statuses: dict[str, int] = {}
        for item in after:
            if item.key not in keys:
                continue
            old = prior.get(item.key)
            attempts += item.attempt_count - (old.attempt_count if old else 0)
            if old is None or old.status != item.status:
                statuses[item.status] = statuses.get(item.status, 0) + 1
        return attempts, tuple(sorted(statuses.items()))

    @classmethod
    def _empty_report(
        cls,
        receipts: Sequence[CaptureReceipt],
        keys: frozenset[object],
        *,
        started_ns: int,
    ) -> RunnerReport:
        return RunnerReport(
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
            cls._backlog_count(receipts, keys),
            cls._oldest_unresolved_at(receipts, keys),
            0,
            (),
            max(0, (time.monotonic_ns() - started_ns) // 1_000_000),
            None,
            0,
        )

    def run_once(self, *, max_items: int, now: str) -> RunnerReport:
        """Run one explicit background cycle against the latest frozen Census."""

        return self.run_manual_backfill(
            authorization_digest="",
            max_items=max_items,
            now=now,
            _background=True,
        )

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
        _background: bool = False,
    ) -> RunnerReport:
        if (
            type(max_items) is not int
            or not 1 <= max_items <= 100
            or type(_background) is not bool
            or (
                not _background
                and (
                    not isinstance(authorization_digest, str)
                    or len(authorization_digest) != 64
                )
            )
        ):
            raise ValueError("capture_runner_contract_invalid")
        try:
            with capture_runner_lock(self.paths):
                return self._run_manual_backfill_locked(
                    authorization_digest=authorization_digest,
                    max_items=max_items,
                    now=now,
                    _background=_background,
                )
        except RuntimeError as error:
            if str(error) != "active Capture runner lock exists":
                raise
            started_ns = time.monotonic_ns()
            snapshot = CaptureStore(self.paths).read_snapshot()
            if _background:
                run = max(
                    snapshot.census_runs,
                    key=lambda item: (item.frozen_at, item.census_id),
                    default=None,
                )
            elif self.preparation is not None:
                run = next(
                    (
                        item
                        for item in snapshot.census_runs
                        if item.census_id == self.preparation.census_id
                    ),
                    None,
                )
            else:
                run = None
            keys = frozenset(run.revision_keys) if run is not None else frozenset()
            return replace(
                self._empty_report(snapshot.receipts, keys, started_ns=started_ns),
                lease_contention_count=1,
            )

    def _run_manual_backfill_locked(
        self,
        *,
        authorization_digest: str,
        max_items: int,
        now: str,
        _background: bool = False,
    ) -> RunnerReport:
        started_ns = time.monotonic_ns()
        current_config = load_runtime_config(self.paths).capture
        store = CaptureStore(self.paths, clock=lambda: now)
        snapshot = store.read_snapshot()
        if _background:
            run = max(
                snapshot.census_runs,
                key=lambda item: (item.frozen_at, item.census_id),
                default=None,
            )
        else:
            if self.preparation is None:
                raise RuntimeError("capture_backfill_authorization_stale")
            run = next(
                (
                    item
                    for item in snapshot.census_runs
                    if item.census_id == self.preparation.census_id
                ),
                None,
            )
        run_keys = frozenset(run.revision_keys) if run is not None else frozenset()
        if _background:
            if (
                not current_config.enabled
                or current_config.mode != "runner"
                or current_config.paused
                or current_config.budgets.incremental_total_tokens is None
                or run is None
            ):
                return self._empty_report(
                    snapshot.receipts, run_keys, started_ns=started_ns
                )
            capture = current_config
            extractor_descriptor = self.extractor.describe()
            probe = self.extractor.probe_capabilities()
            if not probe.available:
                raise RuntimeError("capture_extractor_unavailable")
            pool = "incremental"
            budget_census_id = None
            ceiling = capture.budgets.incremental_total_tokens
        else:
            if current_config.paused:
                return self._empty_report(
                    snapshot.receipts, run_keys, started_ns=started_ns
                )
            capture, extractor_descriptor = self._validate_authorization(
                authorization_digest
            )
            pool = "backfill"
            assert self.preparation is not None
            budget_census_id = self.preparation.census_id
            ceiling = capture.budgets.backfill_total_tokens
        from agc_runtime.capture_capsule import (
            CapsulePolicy,
            capsule_has_durable_signal,
        )
        from agc_runtime.capture_safety import persistence_gate

        policy = CapsulePolicy(
            target_token_limit=capture.capsule.target_tokens,
            hard_token_limit=capture.capsule.max_tokens,
        )
        store.recover_transactions(now=now)
        snapshot = store.read_snapshot()
        run = next(
            item for item in snapshot.census_runs if item.census_id == run.census_id
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
                    if item.key in revisions and self._is_due(item, now)
                ),
                key=lambda item: (item.discovered_at, item.receipt_id),
            )[:max_items]
        )
        budget = CaptureTokenBudget(
            self.paths,
            pool=pool,
            census_id=budget_census_id,
            ceiling=ceiling,
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
                owner_id=("background-runner" if _background else "manual-backfill"),
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
                if not capsule_has_durable_signal(capsule_result.capsule):
                    extracting = store.begin_extraction(
                        lease, capsule_result, extractor_descriptor, now=now
                    )
                    terminal = CaptureReceipt.from_mapping(
                        {
                            **extracting.to_mapping(),
                            "status": "complete",
                            "updated_at": now,
                            "observation_count": 0,
                            "filtered_counts": {
                                "safety": 0,
                                "policy": 0,
                                "over_limit": 0,
                            },
                            "duplicate_suppression_count": 0,
                            "zero_reason": "no_durable_signal",
                        }
                    )
                    store.commit_extraction(lease, (), terminal)
                    completed += 1
                    continue
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
                    final_attempt = extracting.attempt_count >= capture.runner.max_attempts
                    target = "failed" if final_attempt else "retryable"
                    error = result.error
                    if error is None:
                        error = SanitizedError("extractor", "failed", not final_attempt)
                    elif final_attempt:
                        error = SanitizedError(error.stage, error.code, False)
                    backoff_index = min(
                        max(extracting.attempt_count - 1, 0),
                        len(capture.runner.backoff_seconds) - 1,
                    )
                    store.transition_with_settlement(
                        lease,
                        expected=frozenset({"extracting"}),
                        target=target,
                        patch=ReceiptTransitionPatch(
                            updated_at=now,
                            next_retry_at=(
                                None
                                if final_attempt
                                else self._retry_at(
                                    now,
                                    capture.runner.backoff_seconds[backoff_index],
                                )
                            ),
                            sanitized_error=error,
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
            except OSError:
                if reservation is None:
                    expected_status = current.status
                    if expected_status == "retryable":
                        store.transition(
                            lease,
                            expected=frozenset({"retryable"}),
                            target="queued",
                            patch=ReceiptTransitionPatch(updated_at=now),
                        )
                        expected_status = "queued"
                    store.transition(
                        lease,
                        expected=frozenset({expected_status}),
                        target="retryable",
                        patch=ReceiptTransitionPatch(
                            updated_at=now,
                            next_retry_at=self._retry_at(
                                now, capture.runner.backoff_seconds[0]
                            ),
                            sanitized_error=SanitizedError(
                                "source", "source_unavailable", True
                            ),
                        ),
                    )
                failed += 1
            except ValueError as error:
                code = str(error)
                if reservation is None and code in {
                    "capsule_source_identity_changed",
                    "capsule_source_unavailable",
                }:
                    if code == "capsule_source_identity_changed":
                        target = "quarantined"
                        next_retry_at = None
                        sanitized = SanitizedError(
                            "source", "source_identity_changed", False
                        )
                    else:
                        target = "retryable"
                        next_retry_at = self._retry_at(
                            now, capture.runner.backoff_seconds[0]
                        )
                        sanitized = SanitizedError(
                            "source", "source_unavailable", True
                        )
                    expected_status = current.status
                    if expected_status == "retryable" and target == "retryable":
                        store.transition(
                            lease,
                            expected=frozenset({"retryable"}),
                            target="queued",
                            patch=ReceiptTransitionPatch(updated_at=now),
                        )
                        expected_status = "queued"
                    store.transition(
                        lease,
                        expected=frozenset({expected_status}),
                        target=target,
                        patch=ReceiptTransitionPatch(
                            updated_at=now,
                            next_retry_at=next_retry_at,
                            sanitized_error=sanitized,
                        ),
                    )
                failed += 1
            except (KeyError, TypeError, UnicodeError):
                failed += 1
            finally:
                try:
                    store.release_lease(lease)
                except (FileNotFoundError, OSError, ValueError):
                    pass
        charged = budget.snapshot().charged_tokens - before_charge
        final_snapshot = store.read_snapshot()
        attempt_delta, status_deltas = self._attempt_and_status_deltas(
            snapshot.receipts,
            final_snapshot.receipts,
            frozenset(run.revision_keys),
        )
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
            self._backlog_count(final_snapshot.receipts, frozenset(run.revision_keys)),
            self._oldest_unresolved_at(
                final_snapshot.receipts, frozenset(run.revision_keys)
            ),
            attempt_delta,
            status_deltas,
            max(0, (time.monotonic_ns() - started_ns) // 1_000_000),
            None,
            1 if extractor_calls else 0,
        )


__all__ = ["CaptureRunner", "RunnerReport", "retry_capture_receipt"]
