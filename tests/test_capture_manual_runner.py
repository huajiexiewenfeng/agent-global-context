from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import sys
import threading

import pytest

from agc_runtime.capture_contracts import RevisionRef, TokenUsage
from agc_runtime.paths import MemoryPaths


ROOT_ID = "1" * 64
NOW = "2026-08-13T12:00:00Z"
RUN_AT = "2026-08-13T12:01:00Z"
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module", autouse=True)
def _runner_api():
    global CaptureRunner, prepare_backfill
    before = set(sys.modules)
    from agc_runtime.capture_backfill import prepare_backfill as _prepare_backfill
    from agc_runtime.capture_runner import CaptureRunner as _CaptureRunner

    CaptureRunner = _CaptureRunner
    prepare_backfill = _prepare_backfill
    yield
    for name in set(sys.modules) - before:
        if name.startswith("agc_runtime.capture_") or name in {
            "agc_runtime.codex_source_adapter",
            "agc_runtime.codex_extractor",
            "agc_runtime.project_identity",
        }:
            sys.modules.pop(name, None)


def _write_config(
    memory_root: Path,
    source_root: Path,
    *,
    total: int,
    paused: bool = False,
    max_attempts: int = 5,
) -> None:
    memory_root.mkdir(parents=True, exist_ok=True)
    text = (REPOSITORY_ROOT / "agc_runtime" / "default_config.yaml").read_text(
        encoding="utf-8"
    )
    text = (
        text.replace("enabled: false", "enabled: true", 1)
        .replace("mode: off", "mode: scanner_only", 1)
        .replace("sources: []", f"sources:\n    - {source_root.as_posix()}", 1)
        .replace("backfill_total_tokens: 100000", f"backfill_total_tokens: {total}", 1)
        .replace("paused: false", f"paused: {str(paused).lower()}", 1)
        .replace("max_attempts: 5", f"max_attempts: {max_attempts}", 1)
    )
    (memory_root / "config.yaml").write_text(text, encoding="utf-8")


def _revision(revision_id: str = "turn-1") -> RevisionRef:
    return RevisionRef.from_mapping(
        {
            "schema_version": 1,
            "capture_key": {
                "adapter_id": "synthetic",
                "source_root_id": ROOT_ID,
                "task_id": f"task-{revision_id}",
                "revision_id": revision_id,
            },
            "rollout_anchor_id": "rollout-1",
            "completed_at": "2026-08-12T12:00:00Z",
            "locator": "sessions/synthetic.jsonl",
            "identity_quality": "session_id",
            "adapter_version": "1",
            "source_schema_version": "1",
        }
    )


@dataclass
class FakeAdapter:
    revisions: tuple[RevisionRef, ...] = (_revision(),)
    user_signals: tuple[str, ...] = ("I prefer Rust.",)
    discover_calls: int = 0
    load_calls: int = 0
    load_error: bool = False
    identity_changed: bool = False

    def describe(self):
        from agc_runtime.capture_source import AdapterDescriptor

        return AdapterDescriptor(1, "synthetic", "1", "1", ROOT_ID, ("discover", "probe"))

    def discover(self, hint, window):
        from agc_runtime.capture_source import DiscoveryBatch, SourceBindingKey

        del hint
        self.discover_calls += 1
        return DiscoveryBatch(1, SourceBindingKey(1, "synthetic", ROOT_ID), window, self.revisions, None, ())

    def probe(self, ref):
        from agc_runtime.capture_source import SourceProbe

        return SourceProbe(1, ref, "main", "complete", None)

    def load_capsule(self, ref, policy):
        from agc_runtime.capture_capsule import CapsuleCounts, CapsuleResult, TaskCapsule

        self.load_calls += 1
        if self.load_error:
            raise OSError("private source error must not persist")
        if self.identity_changed:
            raise ValueError("capsule_source_identity_changed")
        capsule = TaskCapsule(
            adapter_id=ref.key.adapter_id,
            adapter_version=ref.adapter_version,
            source_schema_version=ref.source_schema_version,
            source_root_id=ref.key.source_root_id,
            task_id=ref.key.task_id,
            revision_id=ref.key.revision_id,
            rollout_anchor_id=ref.rollout_anchor_id,
            identity_quality=ref.identity_quality,
            completed_at=ref.completed_at,
            project_scope="project:stable",
            user_signals=self.user_signals,
        )
        return CapsuleResult(
            capsule,
            "a" * 64,
            "source-v1",
            "b" * 64,
            "capsule-v1",
            ("1",),
            100,
            CapsuleCounts(1, 1, 1, 0, 0, 0, 0, 0),
        )


@dataclass
class FakeExtractor:
    extract_calls: int = 0
    fail_first: bool = False
    always_fail: bool = False

    def describe(self):
        from agc_runtime.capture_extractor import (
            EXTRACTOR_SCHEMA_VERSION,
            EXTRACTOR_VERSION,
            TAXONOMY_VERSION,
            ExtractorDescriptor,
        )

        return ExtractorDescriptor("codex", EXTRACTOR_VERSION, EXTRACTOR_SCHEMA_VERSION, TAXONOMY_VERSION)

    def probe_capabilities(self):
        from agc_runtime.capture_extractor import CapabilityProbe

        return CapabilityProbe(True, "c" * 64, "1", "gpt-5", "openai", True, True, True, None)

    def extract(self, capsule, reservation):
        from agc_runtime.capture_extractor import ExtractionResult

        del capsule, reservation
        self.extract_calls += 1
        if self.always_fail or (self.fail_first and self.extract_calls == 1):
            return ExtractionResult.from_mapping(
                {
                    "succeeded": False,
                    "drafts": [],
                    "usage": None,
                    "error": {
                        "stage": "extractor",
                        "code": "timeout",
                        "retryable": True,
                    },
                }
            )
        return ExtractionResult.from_mapping(
            {
                "succeeded": True,
                "drafts": [
                    {
                        "statement": "The user prefers Rust.",
                        "assertion": {"subject": "user", "mode": "direct", "modality": "asserted"},
                        "primary_category": "personal_growth",
                        "kind": "preference",
                        "scopes": ["global"],
                        "project_scope": "project:stable",
                        "confidence": "confirmed",
                        "sensitivity": "normal",
                        "signal_type": "explicit_user_state",
                        "evidence": ["I prefer Rust."],
                        "priority": 1,
                        "locator": "user:0001",
                    }
                ],
                "usage": TokenUsage(100, 50, 150).to_mapping(),
                "error": None,
            }
        )


def _prepared(tmp_path: Path, *, total: int = 100_000):
    memory = tmp_path / "memory"
    source = tmp_path / "source"
    source.mkdir()
    _write_config(memory, source, total=total)
    paths = MemoryPaths.from_root(memory)
    adapter = FakeAdapter()
    extractor = FakeExtractor()
    preparation = prepare_backfill(paths=paths, adapters=(adapter,), extractor=extractor, now=NOW)
    return paths, adapter, extractor, preparation


def test_manual_runner_collects_one_observation_and_settles_actual_usage(tmp_path: Path) -> None:
    paths, adapter, extractor, preparation = _prepared(tmp_path)
    report = CaptureRunner(paths, (adapter,), extractor, preparation).run_manual_backfill(
        authorization_digest=preparation.authorization_digest,
        max_items=20,
        now=RUN_AT,
    )

    assert report.attempted_count == 1
    assert report.completed_count == 1
    assert report.observation_count == 1
    assert report.extractor_call_count == report.reserved_attempt_count == 1
    assert report.charged_tokens == 150
    assert report.silent_loss_count == 0
    assert extractor.extract_calls == 1


def test_empty_capsule_completes_without_reservation_or_extractor_call(tmp_path: Path):
    paths, adapter, extractor, preparation = _prepared(tmp_path)
    adapter.user_signals = ()

    report = CaptureRunner(
        paths, (adapter,), extractor, preparation
    ).run_manual_backfill(
        authorization_digest=preparation.authorization_digest,
        max_items=20,
        now=RUN_AT,
    )

    receipt = json.loads(
        next(paths.capture.receipts.glob("*.json")).read_text(encoding="utf-8")
    )
    assert report.attempted_count == report.completed_count == 1
    assert report.observation_count == 0
    assert report.reserved_attempt_count == 0
    assert report.extractor_call_count == 0
    assert report.charged_tokens == 0
    assert extractor.extract_calls == 0
    assert receipt["status"] == "complete"
    assert receipt["zero_reason"] == "no_durable_signal"
    assert receipt["token_usage"] == {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
    }


def test_stale_authorization_stops_before_model_call(tmp_path: Path) -> None:
    paths, adapter, extractor, preparation = _prepared(tmp_path)

    with pytest.raises(RuntimeError, match="capture_backfill_authorization_stale"):
        CaptureRunner(paths, (adapter,), extractor, preparation).run_manual_backfill(
            authorization_digest="0" * 64,
            max_items=20,
            now=RUN_AT,
        )

    assert extractor.extract_calls == 0


def test_insufficient_budget_persists_deferred_status_without_model_call(tmp_path: Path) -> None:
    paths, adapter, extractor, preparation = _prepared(tmp_path, total=1)
    report = CaptureRunner(paths, (adapter,), extractor, preparation).run_manual_backfill(
        authorization_digest=preparation.authorization_digest,
        max_items=20,
        now=RUN_AT,
    )

    assert report.deferred_budget_count == 1
    assert report.extractor_call_count == 0
    assert extractor.extract_calls == 0
    receipt_files = tuple(paths.capture.receipts.glob("*.json"))
    assert len(receipt_files) == 1
    assert json.loads(receipt_files[0].read_text(encoding="utf-8"))["status"] == "deferred_budget"


def test_backfill_cli_form_is_exact_and_preparation_is_durable(tmp_path: Path) -> None:
    from agc_runtime.capture_backfill import load_backfill_preparation
    from agc_runtime.capture_cli import _parse

    paths, _, _, preparation = _prepared(tmp_path)
    arguments = [
        "backfill",
        "--root",
        str(paths.root),
        "--authorization-digest",
        preparation.authorization_digest,
        "--max-items",
        "20",
        "--once",
    ]

    assert _parse(arguments) == (
        "backfill",
        paths.root,
        f"{preparation.authorization_digest}:20",
    )
    assert _parse(arguments[:-1]) is None
    assert load_backfill_preparation(paths, preparation.authorization_digest) == preparation


def test_one_failed_item_is_settled_and_does_not_block_the_next(tmp_path: Path) -> None:
    memory = tmp_path / "memory"
    source = tmp_path / "source"
    source.mkdir()
    _write_config(memory, source, total=100_000)
    paths = MemoryPaths.from_root(memory)
    adapter = FakeAdapter((_revision("turn-1"), _revision("turn-2")))
    extractor = FakeExtractor(fail_first=True)
    preparation = prepare_backfill(
        paths=paths, adapters=(adapter,), extractor=extractor, now=NOW
    )

    report = CaptureRunner(paths, (adapter,), extractor, preparation).run_manual_backfill(
        authorization_digest=preparation.authorization_digest,
        max_items=20,
        now=RUN_AT,
    )

    assert report.attempted_count == 2
    assert report.failed_count == 1
    assert report.completed_count == 1
    assert report.extractor_call_count == report.reserved_attempt_count == 2
    assert report.charged_tokens == 6_150


def test_paused_backfill_preserves_backlog_without_model_call(tmp_path: Path) -> None:
    paths, adapter, extractor, preparation = _prepared(tmp_path)
    config_path = paths.root / "config.yaml"
    config = config_path.read_text(encoding="utf-8")
    config_path.write_text(
        config.replace("paused: false", "paused: true", 1), encoding="utf-8"
    )

    report = CaptureRunner(paths, (adapter,), extractor, preparation).run_manual_backfill(
        authorization_digest=preparation.authorization_digest,
        max_items=20,
        now=RUN_AT,
    )

    assert report.attempted_count == 0
    assert report.backlog_count == 1
    assert extractor.extract_calls == 0


def test_retryable_receipt_waits_until_configured_backoff(tmp_path: Path) -> None:
    paths, adapter, extractor, preparation = _prepared(tmp_path)
    extractor.always_fail = True
    runner = CaptureRunner(paths, (adapter,), extractor, preparation)

    first = runner.run_manual_backfill(
        authorization_digest=preparation.authorization_digest,
        max_items=20,
        now=RUN_AT,
    )
    immediate = runner.run_manual_backfill(
        authorization_digest=preparation.authorization_digest,
        max_items=20,
        now=RUN_AT,
    )

    assert first.failed_count == 1
    assert immediate.attempted_count == 0
    assert immediate.backlog_count == 1
    assert extractor.extract_calls == 1


def test_fifth_automatic_failure_parks_receipt_as_failed(tmp_path: Path) -> None:
    paths, adapter, extractor, preparation = _prepared(tmp_path)
    extractor.always_fail = True
    runner = CaptureRunner(paths, (adapter,), extractor, preparation)
    run_times = (
        "2026-08-13T12:01:00Z",
        "2026-08-13T12:02:01Z",
        "2026-08-13T12:07:02Z",
        "2026-08-13T12:37:03Z",
        "2026-08-13T14:37:04Z",
    )

    for run_at in run_times:
        runner.run_manual_backfill(
            authorization_digest=preparation.authorization_digest,
            max_items=20,
            now=run_at,
        )

    receipt_path = next(paths.capture.receipts.glob("*.json"))
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert extractor.extract_calls == 5
    assert receipt["attempt_count"] == 5
    assert receipt["status"] == "failed"
    assert receipt["next_retry_at"] is None


def test_explicit_retry_requeues_parked_receipt_without_model_call(tmp_path: Path) -> None:
    memory = tmp_path / "memory"
    source = tmp_path / "source"
    source.mkdir()
    _write_config(memory, source, total=100_000, max_attempts=1)
    paths = MemoryPaths.from_root(memory)
    adapter = FakeAdapter()
    extractor = FakeExtractor(always_fail=True)
    preparation = prepare_backfill(
        paths=paths, adapters=(adapter,), extractor=extractor, now=NOW
    )
    runner = CaptureRunner(paths, (adapter,), extractor, preparation)
    runner.run_manual_backfill(
        authorization_digest=preparation.authorization_digest,
        max_items=20,
        now=RUN_AT,
    )
    calls_before_retry = extractor.extract_calls

    reopened = runner.retry_revision(_revision().key, now="2026-08-13T12:02:00Z")

    assert reopened.status == "queued"
    assert reopened.attempt_count == 1
    assert reopened.sanitized_error is None
    assert extractor.extract_calls == calls_before_retry


def test_max_items_reports_remaining_queue_backlog(tmp_path: Path) -> None:
    memory = tmp_path / "memory"
    source = tmp_path / "source"
    source.mkdir()
    _write_config(memory, source, total=100_000)
    paths = MemoryPaths.from_root(memory)
    adapter = FakeAdapter((_revision("turn-1"), _revision("turn-2")))
    extractor = FakeExtractor()
    preparation = prepare_backfill(
        paths=paths, adapters=(adapter,), extractor=extractor, now=NOW
    )

    report = CaptureRunner(paths, (adapter,), extractor, preparation).run_manual_backfill(
        authorization_digest=preparation.authorization_digest,
        max_items=1,
        now=RUN_AT,
    )

    assert report.attempted_count == 1
    assert report.completed_count == 1
    assert report.backlog_count == 1


def test_retry_cli_uses_opaque_receipt_key_and_requeues_without_extractor(
    tmp_path: Path, capsys
) -> None:
    from agc_runtime.capture_cli import _parse, _run_retry

    memory = tmp_path / "memory"
    source = tmp_path / "source"
    source.mkdir()
    _write_config(memory, source, total=100_000, max_attempts=1)
    paths = MemoryPaths.from_root(memory)
    adapter = FakeAdapter()
    extractor = FakeExtractor(always_fail=True)
    preparation = prepare_backfill(
        paths=paths, adapters=(adapter,), extractor=extractor, now=NOW
    )
    CaptureRunner(paths, (adapter,), extractor, preparation).run_manual_backfill(
        authorization_digest=preparation.authorization_digest,
        max_items=20,
        now=RUN_AT,
    )
    receipt = next(paths.capture.receipts.glob("*.json"))
    receipt_id = json.loads(receipt.read_text(encoding="utf-8"))["receipt_id"]
    arguments = ["retry", "--root", str(paths.root), "--revision-key", receipt_id]
    calls_before = extractor.extract_calls

    assert _parse(arguments) == ("retry", paths.root, receipt_id)
    assert _run_retry(paths, receipt_id) == 0
    response = json.loads(capsys.readouterr().out)

    assert response["status"] == "accepted"
    assert response["data"] == {
        "receipt_id": receipt_id,
        "status": "queued",
        "attempt_count": 1,
    }
    assert extractor.extract_calls == calls_before


def test_restart_recovers_unknown_reserved_call_and_retries_without_refund(
    tmp_path: Path,
) -> None:
    from agc_runtime.capture_budget import CaptureTokenBudget
    from agc_runtime.capture_capsule import CapsulePolicy
    from agc_runtime.capture_store import CaptureStore

    paths, adapter, extractor, preparation = _prepared(tmp_path)
    store = CaptureStore(paths, clock=lambda: RUN_AT)
    current = store.ready_revisions()[0]
    lease = store.acquire_lease(
        current.key, owner_id="crashed-runner", now=RUN_AT, ttl_seconds=300
    )
    assert lease is not None
    revision = store.frozen_revisions()[0]
    capsule = adapter.load_capsule(revision, CapsulePolicy())
    budget = CaptureTokenBudget(
        paths,
        pool="backfill",
        census_id=preparation.census_id,
        ceiling=100_000,
        clock=lambda: RUN_AT,
    )
    reservation = budget.reserve(
        current.key, 1, TokenUsage(3000, 3000, 6000)
    )
    store.begin_extraction(lease, capsule, extractor.describe(), now=RUN_AT)
    store.release_lease(lease)

    report = CaptureRunner(paths, (adapter,), extractor, preparation).run_manual_backfill(
        authorization_digest=preparation.authorization_digest,
        max_items=20,
        now="2026-08-13T12:10:00Z",
    )

    receipt = json.loads(next(paths.capture.receipts.glob("*.json")).read_text(encoding="utf-8"))
    assert report.completed_count == 1
    assert extractor.extract_calls == 1
    assert receipt["status"] == "complete"
    assert receipt["attempt_count"] == 2
    assert budget.snapshot().charged_tokens == 6150
    assert budget.snapshot().active_reservations == 1


def _switch_to_runner_mode(
    paths: MemoryPaths, *, incremental_total: int | None
) -> None:
    config_path = paths.root / "config.yaml"
    config = config_path.read_text(encoding="utf-8")
    value = "null" if incremental_total is None else str(incremental_total)
    config_path.write_text(
        config.replace("mode: scanner_only", "mode: runner", 1).replace(
            "incremental_total_tokens: null",
            f"incremental_total_tokens: {value}",
            1,
        ),
        encoding="utf-8",
    )


def test_runner_mode_processes_latest_frozen_census_with_incremental_budget(
    tmp_path: Path,
) -> None:
    from agc_runtime.capture_budget import CaptureTokenBudget

    paths, adapter, extractor, _preparation = _prepared(tmp_path)
    _switch_to_runner_mode(paths, incremental_total=100_000)

    report = CaptureRunner(paths, (adapter,), extractor, None).run_once(
        max_items=20,
        now=RUN_AT,
    )

    receipt = json.loads(next(paths.capture.receipts.glob("*.json")).read_text(encoding="utf-8"))
    incremental = CaptureTokenBudget(
        paths,
        pool="incremental",
        census_id=None,
        ceiling=100_000,
        clock=lambda: RUN_AT,
    )
    assert report.completed_count == 1
    assert report.backlog_count == 0
    assert report.charged_tokens == 150
    assert receipt["status"] == "complete"
    assert incremental.snapshot().charged_tokens == 150


def test_runner_report_exposes_content_free_backpressure_diagnostics(tmp_path: Path) -> None:
    paths, adapter, extractor, preparation = _prepared(tmp_path)
    report = CaptureRunner(paths, (adapter,), extractor, preparation).run_manual_backfill(
        authorization_digest=preparation.authorization_digest,
        max_items=20,
        now=RUN_AT,
    )

    mapping = report.to_mapping()
    assert mapping["oldest_unresolved_at"] is None
    assert mapping["attempt_count_delta"] == 1
    assert mapping["status_deltas"] == {"complete": 1}
    assert type(mapping["run_time_ms"]) is int and mapping["run_time_ms"] >= 0
    assert mapping["source_bytes_read"] is None
    assert mapping["peak_process_count"] == 1


def test_two_background_workers_enforce_single_concurrency_and_preserve_backlog(
    tmp_path: Path,
) -> None:
    from agc_runtime.capture_store import CaptureStore

    memory = tmp_path / "memory"
    source = tmp_path / "source"
    source.mkdir()
    _write_config(memory, source, total=100_000)
    paths = MemoryPaths.from_root(memory)
    adapter = FakeAdapter(revisions=(_revision("turn-1"), _revision("turn-2")))
    extractor = FakeExtractor()
    prepare_backfill(
        paths=paths,
        adapters=(adapter,),
        extractor=extractor,
        now=NOW,
    )
    _switch_to_runner_mode(paths, incremental_total=100_000)

    entered = threading.Event()
    release = threading.Event()
    original_extract = extractor.extract

    def blocked_extract(capsule, reservation):
        if not entered.is_set():
            entered.set()
            assert release.wait(5)
        return original_extract(capsule, reservation)

    extractor.extract = blocked_extract
    reports = []
    worker = threading.Thread(
        target=lambda: reports.append(
            CaptureRunner(paths, (adapter,), extractor, None).run_once(
                max_items=1, now=RUN_AT
            )
        )
    )
    worker.start()
    assert entered.wait(5)

    competing = CaptureRunner(paths, (adapter,), extractor, None).run_once(
        max_items=2, now=RUN_AT
    )
    release.set()
    worker.join(5)

    assert not worker.is_alive()
    assert competing.attempted_count == 0
    assert competing.lease_contention_count == 1
    assert competing.backlog_count == 2
    assert extractor.extract_calls == 1
    assert reports[0].completed_count == 1
    snapshot = CaptureStore(paths).read_snapshot()
    assert sorted(item.status for item in snapshot.receipts) == ["complete", "discovered"]


def test_runner_mode_without_incremental_budget_preserves_backlog(
    tmp_path: Path,
) -> None:
    paths, adapter, extractor, _preparation = _prepared(tmp_path)
    _switch_to_runner_mode(paths, incremental_total=None)

    report = CaptureRunner(paths, (adapter,), extractor, None).run_once(
        max_items=20,
        now=RUN_AT,
    )

    assert report.attempted_count == 0
    assert report.backlog_count == 1
    assert extractor.extract_calls == 0


def test_background_run_and_cycle_cli_forms_are_exact(tmp_path: Path) -> None:
    from agc_runtime.capture_cli import _parse

    root = (tmp_path / "memory").resolve()
    assert _parse(["run", "--root", str(root), "--max-items", "20"]) == (
        "run",
        root,
        "20",
    )
    assert _parse(
        ["cycle", "--root", str(root), "--once", "--max-items", "20"]
    ) == ("runner-cycle", root, "20")
    assert _parse(["run", "--root", str(root), "--max-items", "0"]) is None
    assert _parse(
        ["cycle", "--root", str(root), "--max-items", "20", "--once"]
    ) is None


def test_transient_source_failure_is_content_free_retryable_with_backoff(
    tmp_path: Path,
) -> None:
    paths, adapter, extractor, preparation = _prepared(tmp_path)
    adapter.load_error = True
    runner = CaptureRunner(paths, (adapter,), extractor, preparation)

    first = runner.run_manual_backfill(
        authorization_digest=preparation.authorization_digest,
        max_items=20,
        now=RUN_AT,
    )
    immediate = runner.run_manual_backfill(
        authorization_digest=preparation.authorization_digest,
        max_items=20,
        now=RUN_AT,
    )

    receipt = json.loads(next(paths.capture.receipts.glob("*.json")).read_text(encoding="utf-8"))
    assert first.failed_count == 1
    assert immediate.attempted_count == 0
    assert extractor.extract_calls == 0
    assert receipt["status"] == "retryable"
    assert receipt["attempt_count"] == 0
    assert receipt["next_retry_at"] == "2026-08-13T12:02:00Z"
    assert receipt["sanitized_error"] == {
        "stage": "source",
        "code": "source_unavailable",
        "retryable": True,
    }
    assert "private" not in json.dumps(receipt)


def test_source_identity_change_is_quarantined_without_model_call(
    tmp_path: Path,
) -> None:
    paths, adapter, extractor, preparation = _prepared(tmp_path)
    adapter.identity_changed = True

    report = CaptureRunner(paths, (adapter,), extractor, preparation).run_manual_backfill(
        authorization_digest=preparation.authorization_digest,
        max_items=20,
        now=RUN_AT,
    )

    receipt = json.loads(next(paths.capture.receipts.glob("*.json")).read_text(encoding="utf-8"))
    assert report.failed_count == 1
    assert report.backlog_count == 1
    assert extractor.extract_calls == 0
    assert receipt["status"] == "quarantined"
    assert receipt["sanitized_error"] == {
        "stage": "source",
        "code": "source_identity_changed",
        "retryable": False,
    }
