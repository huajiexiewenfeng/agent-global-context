"""Background-only incremental Capture safety and accounting contracts."""

from __future__ import annotations

from pathlib import Path
import json
from datetime import datetime, timedelta, timezone

import pytest

from agc_runtime.capture_maintenance import run_full_audit
from agc_runtime.capture_scanner import CaptureScanner
from agc_runtime.capture_source import AdapterDescriptor, DiscoveryBatch, ScanHint, SourceBindingKey
from agc_runtime.capture_store import CaptureStore
from agc_runtime.paths import MemoryPaths
from tests.test_capture_scanner import _revision
from tests.test_capture_manual_runner import FakeAdapter, FakeExtractor, _write_config


NOW = "2026-08-13T12:00:00Z"
LATER = "2026-08-13T12:01:00Z"


class FixedAdapter:
    def __init__(self, revisions=(), *, adapter_id="synthetic", root_id="3" * 64):
        self.revisions = revisions
        self.adapter_id = adapter_id
        self.root_id = root_id
        self.discovery_calls = 0

    def describe(self):
        return AdapterDescriptor.from_mapping({
            "schema_version": 1,
            "adapter_id": self.adapter_id,
            "adapter_version": "1",
            "source_schema_version": "1",
            "source_root_id": self.root_id,
            "capabilities": ["discover", "probe"],
        })

    def discover(self, hint, window):
        self.discovery_calls += 1
        return DiscoveryBatch.from_mapping({
            "schema_version": 1,
            "binding": SourceBindingKey(1, self.adapter_id, self.root_id).to_mapping(),
            "window": window.to_mapping(),
            "revisions": [revision.to_mapping() for revision in self.revisions],
            "next_hint": ScanHint.from_mapping({
                "schema_version": 1,
                "adapter_id": self.adapter_id,
                "source_root_id": self.root_id,
                "hint_schema_version": "fixed-v1",
                "opaque_value": "fixed",
            }).to_mapping(),
            "diagnostic_codes": [],
        })


def test_incremental_scanner_requires_audit_before_source_discovery(tmp_path: Path) -> None:
    paths = MemoryPaths.from_root(tmp_path / "memory")
    adapter = FixedAdapter((_revision("first"),))
    scanner = CaptureScanner(CaptureStore(paths), (adapter,), incremental=True)

    with pytest.raises(RuntimeError, match="capture_bootstrap_required"):
        scanner.scan(run_started_at=NOW)

    assert adapter.discovery_calls == 0


def test_incremental_scanner_reuses_audited_complete_accounting(tmp_path: Path) -> None:
    paths = MemoryPaths.from_root(tmp_path / "memory")
    revisions = (_revision("old"), _revision("new"))
    adapter = FixedAdapter(revisions)
    store = CaptureStore(paths, clock=lambda: NOW)
    baseline = CaptureScanner(store, (adapter,)).scan(run_started_at=NOW)
    assert run_full_audit(store, now=NOW).status == "healthy"

    current = CaptureScanner(CaptureStore(paths, clock=lambda: LATER), (adapter,), incremental=True).scan(run_started_at=LATER)

    assert current.known_key_count == baseline.known_key_count == 2
    assert current.accounted_key_count == baseline.accounted_key_count == 2
    assert current.silent_loss_count == 0
    assert current.created_receipt_count == 0
    assert current.replay_count == 2


def _runner_config(memory: Path, source: Path) -> None:
    _write_config(memory, source, total=100_000)
    path = memory / "config.yaml"
    path.write_text(
        path.read_text(encoding="utf-8")
        .replace("mode: scanner_only", "mode: runner")
        .replace("incremental_total_tokens: null", "incremental_total_tokens: 100000"),
        encoding="utf-8",
    )


def test_background_runner_missing_baseline_stops_before_model_probe(tmp_path: Path) -> None:
    from agc_runtime.capture_runner import CaptureRunner

    memory, source = tmp_path / "memory", tmp_path / "source"
    source.mkdir()
    _runner_config(memory, source)
    paths = MemoryPaths.from_root(memory)
    adapter = FakeAdapter()
    CaptureScanner(CaptureStore(paths, clock=lambda: NOW), (adapter,)).scan(run_started_at=NOW)
    extractor = FakeExtractor()
    probes = []
    original = extractor.probe_capabilities
    extractor.probe_capabilities = lambda: (probes.append(True), original())[1]

    with pytest.raises(RuntimeError, match="capture_bootstrap_required"):
        CaptureRunner(paths, (adapter,), extractor, None).run_once(max_items=1, now=NOW)

    assert probes == []
    assert extractor.extract_calls == 0


def test_background_runner_uses_scheduling_view_not_full_snapshot(tmp_path: Path, monkeypatch) -> None:
    from agc_runtime.capture_runner import CaptureRunner

    memory, source = tmp_path / "memory", tmp_path / "source"
    source.mkdir()
    _runner_config(memory, source)
    paths = MemoryPaths.from_root(memory)
    adapter = FakeAdapter()
    store = CaptureStore(paths, clock=lambda: NOW)
    CaptureScanner(store, (adapter,)).scan(run_started_at=NOW)
    assert run_full_audit(store, now=NOW).status == "healthy"

    def forbidden_full_read(*args, **kwargs):
        raise AssertionError("background runner reopened full historical snapshot")

    monkeypatch.setattr(CaptureStore, "read_snapshot", forbidden_full_read)
    extractor = FakeExtractor()
    report = CaptureRunner(paths, (adapter,), extractor, None).run_once(max_items=1, now=NOW)

    assert report.completed_count == 1
    assert report.extractor_call_count == 1


def test_old_valid_scheduling_view_replay_cannot_hide_new_census(tmp_path: Path) -> None:
    paths = MemoryPaths.from_root(tmp_path / "memory")
    adapter = FixedAdapter((_revision("old"),))
    CaptureScanner(CaptureStore(paths, clock=lambda: NOW), (adapter,)).scan(run_started_at=NOW)
    assert run_full_audit(CaptureStore(paths), now=NOW).status == "healthy"
    view = paths.capture.root / "scheduling-view.json"
    seal = paths.capture.root / "scheduling-view-seal.json"
    previous = view.read_bytes(), seal.read_bytes()

    # A new frozen run changes the current scheduling epoch without changing
    # Receipt/workset generation; replay must still be detected.
    CaptureScanner(CaptureStore(paths, clock=lambda: LATER), (adapter,), incremental=True).scan(run_started_at=LATER)
    view.write_bytes(previous[0])
    seal.write_bytes(previous[1])

    with pytest.raises(RuntimeError, match="capture_bootstrap_required"):
        CaptureStore(paths).read_background_scheduling_view(now=LATER)


def test_public_catalog_rebuild_with_same_scheduling_truth_keeps_view_usable(tmp_path: Path) -> None:
    from agc_runtime.capture_source import CensusRun
    from agc_runtime.capture_contracts import RevisionRef
    from agc_runtime.locking import capture_write_lock

    paths = MemoryPaths.from_root(tmp_path / "memory")
    adapter = FixedAdapter((_revision("old", locator="sessions/old.jsonl"),))
    CaptureScanner(CaptureStore(paths, clock=lambda: NOW), (adapter,)).scan(run_started_at=NOW)
    assert run_full_audit(CaptureStore(paths), now=NOW).status == "healthy"
    adapter.revisions = (_revision("old", locator="archived_sessions/old.jsonl"),)
    CaptureScanner(CaptureStore(paths, clock=lambda: LATER), (adapter,), incremental=True).scan(run_started_at=LATER)
    store = CaptureStore(paths)
    view_path = paths.capture.root / "scheduling-view.json"
    view = json.loads(view_path.read_text(encoding="utf-8"))
    before = view["catalog_id"]
    # This is the same canonical republish a full reader may do after a
    # metadata relocation. It changes the pointer, not current eligibility.
    with capture_write_lock(paths):
        store._publish_census_catalog_locked(
            tuple(CensusRun.from_mapping(item) for item in view["runs"]),
            tuple(RevisionRef.from_mapping(item) for item in view["revisions"]),
        )
    active = json.loads((paths.capture.census_catalog / "active.json").read_text(encoding="utf-8"))
    assert active["catalog_id"] != before

    scheduling = store.read_background_scheduling_view(now=LATER)
    assert len(scheduling.runs) == 2
    assert len(scheduling.revisions) == 1


def test_catalog_republish_with_changed_run_metadata_cannot_reuse_view(tmp_path: Path) -> None:
    from agc_runtime.capture_source import CensusRun
    from agc_runtime.capture_contracts import RevisionRef
    from agc_runtime.locking import capture_write_lock

    paths = MemoryPaths.from_root(tmp_path / "memory")
    adapter = FixedAdapter((_revision("old"),))
    CaptureScanner(CaptureStore(paths, clock=lambda: NOW), (adapter,)).scan(run_started_at=NOW)
    assert run_full_audit(CaptureStore(paths), now=NOW).status == "healthy"
    store = CaptureStore(paths)
    view = json.loads((paths.capture.root / "scheduling-view.json").read_text(encoding="utf-8"))
    changed_runs = list(view["runs"])
    changed_runs[0] = {**changed_runs[0], "frozen_at": "2026-08-13T12:00:01Z"}
    with capture_write_lock(paths):
        store._publish_census_catalog_locked(
            tuple(CensusRun.from_mapping(item) for item in changed_runs),
            tuple(RevisionRef.from_mapping(item) for item in view["revisions"]),
        )

    with pytest.raises(RuntimeError, match="capture_bootstrap_required"):
        store.read_background_scheduling_view(now=NOW)


def test_public_full_read_between_three_normal_scans_keeps_catalog_canonical(tmp_path: Path) -> None:
    from agc_runtime.capture_ledger import canonical_census_id
    from agc_runtime.capture_source import TimeWindow

    paths = MemoryPaths.from_root(tmp_path / "memory")
    adapter = FixedAdapter((_revision("old"),))
    CaptureScanner(CaptureStore(paths, clock=lambda: NOW), (adapter,)).scan(run_started_at=NOW)
    assert run_full_audit(CaptureStore(paths), now=NOW).status == "healthy"
    binding = SourceBindingKey(1, "synthetic", "3" * 64)
    anchor = datetime.fromisoformat(NOW.replace("Z", "+00:00"))
    times = []
    for minute in range(1, 30):
        at = anchor + timedelta(minutes=minute)
        stamp = at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        start = (at - timedelta(days=7)).isoformat().replace("+00:00", "Z")
        census_id = canonical_census_id(binding, TimeWindow(1, start, stamp), stamp)
        times.append((stamp, census_id))
    trio = next(tuple(times[index:index + 3]) for index in range(len(times) - 2)
                if times[index + 1][1] < times[index][1])

    for stamp, _census_id in trio:
        CaptureScanner(CaptureStore(paths, clock=lambda stamp=stamp: stamp), (adapter,), incremental=True).scan(run_started_at=stamp)
        assert CaptureStore(paths).read_snapshot().integrity_state == "healthy"
        assert CaptureStore(paths).read_background_scheduling_view(now=stamp).scope == "bounded_scheduling_not_full_audit"


def test_incremental_scanner_does_not_open_unchanged_completed_history(tmp_path: Path, monkeypatch) -> None:
    from agc_runtime.capture_runner import CaptureRunner

    memory, source = tmp_path / "memory", tmp_path / "source"
    source.mkdir()
    _runner_config(memory, source)
    paths = MemoryPaths.from_root(memory)
    adapter = FakeAdapter()
    CaptureScanner(CaptureStore(paths, clock=lambda: NOW), (adapter,)).scan(run_started_at=NOW)
    assert run_full_audit(CaptureStore(paths), now=NOW).status == "healthy"
    assert CaptureRunner(paths, (adapter,), FakeExtractor(), None).run_once(max_items=1, now=NOW).completed_count == 1
    assert run_full_audit(CaptureStore(paths), now=NOW).status == "healthy"

    def forbidden_manifest(*args, **kwargs):
        raise AssertionError("unchanged complete manifest reopened")

    monkeypatch.setattr(CaptureStore, "_manifest_valid", forbidden_manifest)
    report = CaptureScanner(CaptureStore(paths, clock=lambda: LATER), (adapter,), incremental=True).scan(run_started_at=LATER)
    assert report.known_key_count == report.accounted_key_count == 1
    assert report.created_receipt_count == 0


def test_census_publication_interruption_keeps_background_view_untrusted(tmp_path: Path, monkeypatch) -> None:
    import agc_runtime.capture_schedule as schedule

    paths = MemoryPaths.from_root(tmp_path / "memory")
    adapter = FixedAdapter((_revision("old"),))
    CaptureScanner(CaptureStore(paths, clock=lambda: NOW), (adapter,)).scan(run_started_at=NOW)
    assert run_full_audit(CaptureStore(paths), now=NOW).status == "healthy"

    def interrupted(*args, **kwargs):
        raise RuntimeError("synthetic after-Census interruption")

    monkeypatch.setattr(schedule, "publish_census_locked", interrupted)
    with pytest.raises(RuntimeError, match="synthetic after-Census interruption"):
        CaptureScanner(CaptureStore(paths, clock=lambda: LATER), (adapter,), incremental=True).scan(run_started_at=LATER)

    with pytest.raises(RuntimeError, match="capture_bootstrap_required"):
        CaptureStore(paths).read_background_scheduling_view(now=LATER)
    monkeypatch.undo()
    assert run_full_audit(CaptureStore(paths), now=LATER).status == "healthy"
    assert CaptureStore(paths).read_background_scheduling_view(now=LATER).scope == "bounded_scheduling_not_full_audit"


def test_selected_cold_census_mismatch_stops_before_extractor(tmp_path: Path) -> None:
    from agc_runtime.capture_runner import CaptureRunner

    memory, source = tmp_path / "memory", tmp_path / "source"
    source.mkdir()
    _runner_config(memory, source)
    paths = MemoryPaths.from_root(memory)
    adapter = FakeAdapter()
    CaptureScanner(CaptureStore(paths, clock=lambda: NOW), (adapter,)).scan(run_started_at=NOW)
    assert run_full_audit(CaptureStore(paths), now=NOW).status == "healthy"
    member = next(paths.capture.root.rglob("members/*.json"))
    value = json.loads(member.read_text(encoding="utf-8"))
    value["rollout_anchor_id"] = "different-rollout"
    member.write_text(json.dumps(value), encoding="utf-8")
    extractor = FakeExtractor()

    with pytest.raises(RuntimeError, match="capture_bootstrap_required"):
        CaptureRunner(paths, (adapter,), extractor, None).run_once(max_items=1, now=NOW)

    assert extractor.extract_calls == 0


def test_selected_ledger_corruption_fails_cycle_before_extractor(tmp_path: Path) -> None:
    from agc_runtime.capture_runner import CaptureRunner

    memory, source = tmp_path / "memory", tmp_path / "source"
    source.mkdir()
    _runner_config(memory, source)
    paths = MemoryPaths.from_root(memory)
    adapter = FakeAdapter()
    CaptureScanner(CaptureStore(paths, clock=lambda: NOW), (adapter,)).scan(run_started_at=NOW)
    assert run_full_audit(CaptureStore(paths), now=NOW).status == "healthy"
    ledger = next(paths.capture.ledger.glob("*.json"))
    ledger.write_text("{}", encoding="utf-8")
    extractor = FakeExtractor()

    with pytest.raises(RuntimeError, match="capture_bootstrap_required"):
        CaptureRunner(paths, (adapter,), extractor, None).run_once(max_items=1, now=NOW)

    assert extractor.extract_calls == 0


def test_selected_census_window_corruption_fails_cycle_before_extractor(tmp_path: Path) -> None:
    from agc_runtime.capture_runner import CaptureRunner

    memory, source = tmp_path / "memory", tmp_path / "source"
    source.mkdir()
    _runner_config(memory, source)
    paths = MemoryPaths.from_root(memory)
    adapter = FakeAdapter()
    CaptureScanner(CaptureStore(paths, clock=lambda: NOW), (adapter,)).scan(run_started_at=NOW)
    assert run_full_audit(CaptureStore(paths), now=NOW).status == "healthy"
    run_path = next((paths.capture.root / "census-runs").glob("*/run.json"))
    run = json.loads(run_path.read_text(encoding="utf-8"))
    run["window"]["start_at"] = "2026-08-05T12:00:00Z"
    run_path.write_text(json.dumps(run), encoding="utf-8")
    extractor = FakeExtractor()

    with pytest.raises(RuntimeError, match="capture_bootstrap_required"):
        CaptureRunner(paths, (adapter,), extractor, None).run_once(max_items=1, now=NOW)

    assert extractor.extract_calls == 0


@pytest.mark.parametrize(
    ("field", "value"),
    [("discovered_at", "2026-08-12T12:00:00Z"), ("processed_at", NOW)],
)
def test_selected_ledger_time_mismatch_fails_cycle_before_extractor(
    tmp_path: Path, field: str, value: str,
) -> None:
    from agc_runtime.capture_runner import CaptureRunner

    memory, source = tmp_path / "memory", tmp_path / "source"
    source.mkdir()
    _runner_config(memory, source)
    paths = MemoryPaths.from_root(memory)
    adapter = FakeAdapter()
    CaptureScanner(CaptureStore(paths, clock=lambda: NOW), (adapter,)).scan(run_started_at=NOW)
    assert run_full_audit(CaptureStore(paths), now=NOW).status == "healthy"
    ledger_path = next(paths.capture.ledger.glob("*.json"))
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    ledger[field] = value
    ledger_path.write_text(json.dumps(ledger), encoding="utf-8")
    extractor = FakeExtractor()

    with pytest.raises(RuntimeError, match="capture_bootstrap_required"):
        CaptureRunner(paths, (adapter,), extractor, None).run_once(max_items=1, now=NOW)

    assert extractor.extract_calls == 0


def test_audit_due_reports_scope_but_does_not_block_selected_extraction(tmp_path: Path) -> None:
    from agc_runtime.capture_runner import CaptureRunner

    memory, source = tmp_path / "memory", tmp_path / "source"
    source.mkdir()
    _runner_config(memory, source)
    paths = MemoryPaths.from_root(memory)
    adapter = FakeAdapter()
    CaptureScanner(CaptureStore(paths, clock=lambda: NOW), (adapter,)).scan(run_started_at=NOW)
    assert run_full_audit(CaptureStore(paths), now=NOW).status == "healthy"
    due_at = "2026-08-14T12:00:01Z"
    view = CaptureStore(paths).read_background_scheduling_view(now=due_at)
    assert view.audit_status == "audit_due"
    assert view.scope == "bounded_scheduling_not_full_audit"

    extractor = FakeExtractor()
    report = CaptureRunner(paths, (adapter,), extractor, None).run_once(max_items=1, now=due_at)
    assert report.completed_count == 1
    assert extractor.extract_calls == 1


def test_forget_then_fresh_audit_and_scan_do_not_recreate_candidate_metadata(tmp_path: Path) -> None:
    from agc_runtime.write_service import dispatch_write
    from tests.test_capture_forget import _freeze_census, _key, _populated, _request, _revision as forgotten_revision

    paths, store, _receipt, _observations = _populated(tmp_path)
    key = _key()
    _freeze_census(store, (forgotten_revision(key),))
    assert run_full_audit(store, now=NOW).status == "healthy"
    assert dispatch_write(paths, _request({"type": "revision", **key.to_mapping()})).status == "accepted"
    assert run_full_audit(CaptureStore(paths), now=NOW).status == "healthy"
    # Public verification may republish a packed catalog between cycles.
    assert CaptureStore(paths).read_snapshot().integrity_state == "healthy"
    adapter = FixedAdapter((forgotten_revision(key),), adapter_id=key.adapter_id, root_id=key.source_root_id)

    report = CaptureScanner(CaptureStore(paths, clock=lambda: LATER), (adapter,), incremental=True).scan(run_started_at=LATER)
    view = json.loads((paths.capture.root / "scheduling-view.json").read_text(encoding="utf-8"))

    assert report.created_receipt_count == 0
    assert report.known_key_count == report.accounted_key_count == 1
    assert all(item["capture_key"] != key.to_mapping() for item in view["revisions"])
    assert all(item["task_id"] != key.task_id for item in view["receipts"].values())


def test_background_cli_exposes_audit_due_without_claiming_full_health(tmp_path: Path, monkeypatch, capsys) -> None:
    from agc_runtime.capture_cli import _run_runner

    memory, source = tmp_path / "memory", tmp_path / "source"
    source.mkdir()
    _runner_config(memory, source)
    paths = MemoryPaths.from_root(memory)
    assert run_full_audit(CaptureStore(paths), now=NOW).status == "healthy"
    monkeypatch.setattr("agc_runtime.capture_cli._utc_now", lambda: "2026-08-14T12:00:01Z")

    assert _run_runner(paths, action="run", maximum=1, scan_first=False) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["data"]["scheduling"] == {
        "scope": "bounded_scheduling_not_full_audit",
        "audit_status": "audit_due",
        "audit_completed_at": NOW,
    }


def test_background_cli_missing_baseline_reports_bootstrap_required(tmp_path: Path, monkeypatch, capsys) -> None:
    from agc_runtime.capture_cli import _run_runner

    memory, source = tmp_path / "memory", tmp_path / "source"
    source.mkdir()
    _runner_config(memory, source)
    monkeypatch.setattr("agc_runtime.capture_cli._utc_now", lambda: NOW)

    assert _run_runner(MemoryPaths.from_root(memory), action="run", maximum=1, scan_first=False) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"]["code"] == "capture_bootstrap_required"
