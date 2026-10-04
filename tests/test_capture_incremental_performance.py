"""Deterministic work-count guard; synthetic timing is benchmarked separately."""

from __future__ import annotations

from pathlib import Path

from agc_runtime.capture_maintenance import run_full_audit
from agc_runtime.capture_runner import CaptureRunner
from agc_runtime.capture_scanner import CaptureScanner
from agc_runtime.capture_store import CaptureStore
from agc_runtime.paths import MemoryPaths
from tests.test_capture_manual_runner import (
    FakeAdapter, FakeExtractor, _revision, _write_config,
)


NOW = "2026-08-13T12:00:00Z"
LATER = "2026-08-13T12:01:00Z"


def test_warm_cycle_does_not_reopen_completed_receipts_or_cold_census(tmp_path: Path, monkeypatch) -> None:
    from agc_runtime.capture_backfill import prepare_backfill
    import agc_runtime.capture_store as store_module

    memory, source = tmp_path / "memory", tmp_path / "source"
    source.mkdir()
    monkeypatch.setattr(store_module, "_utc_now", lambda: NOW)
    _write_config(memory, source, total=1_000_000)
    paths = MemoryPaths.from_root(memory)
    history = tuple(_revision(f"history-{index}") for index in range(8))
    adapter = FakeAdapter(revisions=history)
    extractor = FakeExtractor()
    preparation = prepare_backfill(paths=paths, adapters=(adapter,), extractor=extractor, now=NOW)
    seeded = CaptureRunner(paths, (adapter,), extractor, preparation).run_manual_backfill(
        authorization_digest=preparation.authorization_digest, max_items=100, now=NOW,
    )
    assert seeded.completed_count == len(history)
    config = memory / "config.yaml"
    config.write_text(config.read_text(encoding="utf-8")
                      .replace("mode: scanner_only", "mode: runner")
                      .replace("incremental_total_tokens: null", "incremental_total_tokens: 1000000"),
                      encoding="utf-8")
    assert run_full_audit(CaptureStore(paths), now=NOW).status == "healthy"
    old_receipt_ids = {item.receipt_id for item in CaptureStore(paths).read_snapshot().receipts}

    original_read = store_module.read_json
    reopened_history: list[Path] = []

    def measured(path: Path):
        path = Path(path)
        if path.stem in old_receipt_ids and path.parent.name in {"receipts", "indexes"}:
            reopened_history.append(path)
        return original_read(path)

    def forbidden_cold(*args, **kwargs):
        raise AssertionError("ordinary cycle reconstructed historical Census")

    monkeypatch.setattr(store_module, "read_json", measured)
    monkeypatch.setattr(CaptureStore, "_read_census_run_manifests", forbidden_cold)
    monkeypatch.setattr(CaptureStore, "_read_cold_census_truth", forbidden_cold)
    monkeypatch.setattr(CaptureStore, "read_snapshot", forbidden_cold)
    adapter.revisions = (*history, _revision("delta"))

    scan = CaptureScanner(CaptureStore(paths, clock=lambda: LATER), (adapter,), incremental=True).scan(run_started_at=LATER)
    report = CaptureRunner(paths, (adapter,), FakeExtractor(), None).run_once(max_items=3, now=LATER)

    assert scan.known_key_count == scan.accounted_key_count == len(history) + 1
    assert report.completed_count == 1
    assert reopened_history == []
