"""Isolated baseline/new Capture cycles with real synthetic sources, no model.

Use the same managed source directory for both runs, with distinct fresh memory
roots and output files. The source fixture is deterministically reset between
runs. This is a synthetic work-count benchmark, not production acceptance.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager, redirect_stdout
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import hashlib
import inspect
import io
import json
from pathlib import Path
import sys
import time


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--capture-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--history", type=int, default=40)
    args = parser.parse_args()
    boundary = Path("D:/tmp_test").resolve()
    for candidate in (args.source, args.capture_root, args.output):
        if candidate.resolve() == boundary or not candidate.resolve().is_relative_to(boundary):
            parser.error("all fixture artifacts must be beneath D:/tmp_test")
    if args.capture_root.exists() or args.output.exists() or not 1 <= args.history <= 100:
        parser.error("use fresh memory/output paths and history 1..100")
    marker = args.source / "cycle-fixture.json"
    fixture_contract = {"format": "agc-cycle-benchmark-v1", "history": args.history}
    if args.source.exists() and (not marker.is_file() or json.loads(marker.read_text()) != fixture_contract):
        parser.error("existing source is not this exact managed synthetic fixture")
    args.source.mkdir(parents=True, exist_ok=True)
    if not marker.exists():
        marker.write_text(json.dumps(fixture_contract), encoding="utf-8")
    sessions = args.source / "sessions"
    if not sessions.resolve().is_relative_to(args.source.resolve()):
        parser.error("sessions must not redirect outside the managed synthetic source")
    sessions.mkdir(exist_ok=True)
    allowed = {f"task-{index}.jsonl" for index in range(args.history + 1)}
    if any(item.name not in allowed or not item.is_file() or item.is_symlink()
           or item.stat().st_nlink != 1 for item in sessions.iterdir()):
        parser.error("unexpected content in managed synthetic sessions")

    def stamp(value: datetime) -> str:
        return value.isoformat().replace("+00:00", "Z")

    start = datetime(2026, 10, 4, tzinfo=timezone.utc)

    def turn(revision: str, at: datetime) -> list[dict]:
        return [
            {"timestamp": stamp(at), "type": "event_msg", "payload": {"type": "task_started", "turn_id": revision}},
            {"timestamp": stamp(at), "type": "event_msg", "payload": {"type": "user_message", "message": "I prefer Rust."}},
            {"timestamp": stamp(at + timedelta(seconds=1)), "type": "event_msg", "payload": {"type": "task_complete", "turn_id": revision}},
        ]

    records = {}
    for index in range(args.history + 1):
        records[index] = [{"timestamp": stamp(start - timedelta(hours=2)), "type": "session_meta",
                           "payload": {"id": f"rollout-{index}", "session_id": f"task-{index}", "source": "vscode"}}]
        if index < args.history:
            records[index].extend(turn(f"history-{index}", start - timedelta(hours=1)))

    def write_source(index: int) -> None:
        (sessions / f"task-{index}.jsonl").write_text(
            "".join(json.dumps(item) + "\n" for item in records[index]), encoding="utf-8")

    for index in records:
        write_source(index)
    sys.path.insert(0, str(args.repo.resolve()))

    def fingerprints() -> dict[str, str]:
        return {item.name: hashlib.sha256(item.read_bytes()).hexdigest()
                for item in sorted((args.repo / "agc_runtime").glob("*.py"))}

    implementation = fingerprints()
    from agc_runtime.capture_backfill import prepare_backfill
    from agc_runtime.capture_budget import CaptureTokenBudget
    from agc_runtime.capture_runner import CaptureRunner
    from agc_runtime.capture_scanner import CaptureScanner
    from agc_runtime.capture_store import CaptureStore
    from agc_runtime.codex_source_adapter import CodexSourceAdapter
    from agc_runtime.paths import MemoryPaths
    from tests.test_capture_manual_runner import FakeExtractor, _write_config
    import agc_runtime.capture_transaction as transaction
    import agc_runtime.locking as locking
    import agc_runtime.capture_store as store_module

    # Preparation constructs its own Store; freeze that default clock too so
    # its Census cannot outrank later synthetic cycles by real wall time.
    current_time = [stamp(start)]
    store_module._utc_now = lambda: current_time[0]

    class FixtureExtractor(FakeExtractor):
        def extract(self, capsule, reservation):
            from agc_runtime.capture_extractor import ExtractionResult
            value = super().extract(capsule, reservation).to_mapping()
            for draft in value["drafts"]:
                draft["project_scope"] = capsule.project_scope
            return ExtractionResult.from_mapping(value)

    class SeedAdapter:
        """Seed primary history without warming new discovery metadata."""
        def __init__(self):
            self.delegate = CodexSourceAdapter(args.source)

        def describe(self):
            return self.delegate.describe()

        def discover(self, hint, window):
            return self.delegate.discover(hint, window)

        def probe(self, revision):
            return self.delegate.probe(revision)

        def load_capsule(self, revision, policy):
            return self.delegate.load_capsule(revision, policy)

    _write_config(args.capture_root, args.source, total=1_000_000)
    paths = MemoryPaths.from_root(args.capture_root)
    extractor = FixtureExtractor()
    adapter = SeedAdapter()
    preparation = prepare_backfill(paths=paths, adapters=(adapter,), extractor=extractor, now=stamp(start))
    seed = CaptureRunner(paths, (adapter,), extractor, preparation).run_manual_backfill(
        authorization_digest=preparation.authorization_digest, max_items=100, now=stamp(start))
    if (seed.completed_count != args.history or seed.extractor_call_count != args.history
            or seed.observation_count != args.history):
        raise RuntimeError(f"synthetic history did not seed completely: {seed}")
    config = paths.root / "config.yaml"
    config.write_text(config.read_text(encoding="utf-8").replace(
        "mode: scanner_only", "mode: runner").replace(
        "incremental_total_tokens: null", "incremental_total_tokens: 1000000"), encoding="utf-8")

    bootstrap_seconds = 0.0
    bootstrap_report = None
    if (args.repo / "agc_runtime/capture_maintenance.py").exists():
        import agc_runtime.capture_cli as cli
        old_cli_clock = cli._utc_now
        cli._utc_now = lambda: current_time[0]
        output = io.StringIO()
        timer = time.perf_counter()
        try:
            with redirect_stdout(output):
                exit_code = cli.main(["audit", "--root", str(paths.root), "--once"])
        finally:
            cli._utc_now = old_cli_clock
        bootstrap_seconds = time.perf_counter() - timer
        if exit_code:
            raise RuntimeError(f"synthetic audit bootstrap failed: {output.getvalue()}")
        bootstrap_report = json.loads(output.getvalue())

    original_read = transaction.read_json
    original_lock = locking.capture_write_lock
    original_scan = CodexSourceAdapter._scan_file
    reads = []
    body_parses = []
    lock_times = []

    def measured_read(path):
        result = original_read(path)
        try:
            reads.append(Path(path).relative_to(paths.capture.root).as_posix())
        except ValueError:
            pass
        return result

    @contextmanager
    def measured_lock(*positional, **keyword):
        waiting = time.perf_counter()
        with original_lock(*positional, **keyword) as result:
            acquired = time.perf_counter()
            try:
                yield result
            finally:
                lock_times.append((acquired - waiting, time.perf_counter() - acquired))

    def measured_scan(self, path):
        body_parses.append(path.name)
        return original_scan(self, path)

    patches = []
    for module_name, module in tuple(sys.modules.items()):
        if not module_name.startswith("agc_runtime."):
            continue
        for name, old, replacement in (("read_json", original_read, measured_read),
                                       ("capture_write_lock", original_lock, measured_lock)):
            if getattr(module, name, None) is old:
                patches.append((module, name, old))
                setattr(module, name, replacement)
    CodexSourceAdapter._scan_file = measured_scan
    results = []
    try:
        for iteration in range(4):
            at = start + timedelta(minutes=iteration + 1)
            current_time[0] = stamp(at)
            records[0].extend(turn(f"delta-{iteration}", at - timedelta(seconds=20)))
            write_source(0)
            if iteration == 0:
                records[args.history].extend(turn("new-task", at - timedelta(seconds=20)))
                write_source(args.history)
            adapter = CodexSourceAdapter(args.source)
            store = CaptureStore(paths, clock=lambda: stamp(at))
            scanner_options = {}
            if "incremental" in inspect.signature(CaptureScanner).parameters:
                scanner_options["incremental"] = True
            scanner = CaptureScanner(store, (adapter,), **scanner_options)
            reads.clear(); body_parses.clear(); lock_times.clear()
            timer = time.perf_counter()
            scan = scanner.scan(run_started_at=stamp(at))
            scan_seconds = time.perf_counter() - timer
            extractor = FixtureExtractor()
            timer = time.perf_counter()
            report = CaptureRunner(paths, (adapter,), extractor, None).run_once(max_items=3, now=stamp(at))
            runner_seconds = time.perf_counter() - timer
            expected = 2 if iteration == 0 else 1
            if (report.completed_count != expected or report.extractor_call_count != expected
                    or report.observation_count != expected):
                raise RuntimeError(f"cycle did not actually extract the fixed delta: {report}")
            work = {"source_body_parses": len(body_parses), "capture_json_reads": len(reads),
                    "unique_capture_json_paths": len(set(reads)), "read_namespaces": dict(Counter(path.split('/')[0] for path in reads)),
                    "capture_lock_acquisitions": len(lock_times), "lock_wait_seconds": sum(item[0] for item in lock_times),
                    "lock_held_seconds": sum(item[1] for item in lock_times)}
            # Full verification is deliberately outside the measured hot path.
            snapshot = store.read_snapshot()
            if snapshot.integrity_state != "healthy":
                raise RuntimeError(f"synthetic cycle failed full integrity verification: {snapshot.diagnostics}")
            budget = CaptureTokenBudget(paths, pool="incremental", census_id=None, ceiling=1_000_000)
            results.append({"phase": "cold_discovery_after_bootstrap" if not iteration else f"warm-{iteration}",
                            "scan_seconds": scan_seconds, "runner_seconds": runner_seconds,
                            "work": work, "scan_report": asdict(scan), "runner_report": asdict(report),
                            "selected_revision_ids": extractor.seen_revision_ids,
                            "receipts": [item.to_mapping() for item in sorted(snapshot.receipts, key=lambda item: item.receipt_id)],
                            "observations": [item.to_mapping() for item in sorted(snapshot.observations, key=lambda item: item.observation_id)],
                            "ledger": [original_read(item) for item in sorted(paths.capture.ledger.glob("*.json"))],
                            "accounted_keys": [item.to_mapping() for item in sorted(snapshot.accounted_keys, key=lambda item: (item.task_id, item.revision_id))],
                            "incremental_budget": asdict(budget.snapshot()),
                            "revisions": [item.to_mapping() for item in sorted(snapshot.census, key=lambda item: (item.key.task_id, item.key.revision_id))]})
    finally:
        CodexSourceAdapter._scan_file = original_scan
        for module, name, old in patches:
            setattr(module, name, old)
    if implementation != fingerprints():
        raise RuntimeError("code changed during benchmark; discard this run")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"scope": "synthetic real sources; fake extractor; no production claims",
                                      "measurement_limits": "successful Capture JSON-helper reads, not all OS I/O; selected Capsule verification included in body parses; OS cache is not flushed",
                                      "harness_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                                      "fake_extractor_fixture_sha256": hashlib.sha256((args.repo / "tests/test_capture_manual_runner.py").read_bytes()).hexdigest(),
                                      "history": args.history, "implementation_sha256": implementation,
                                      "fixed_clock_start": stamp(start), "max_items": 3,
                                      "configuration_sha256": hashlib.sha256(config.read_bytes()).hexdigest(),
                                      "source_sha256": {item.name: hashlib.sha256(item.read_bytes()).hexdigest() for item in sorted(sessions.glob('*.jsonl'))},
                                      "bootstrap_seconds": bootstrap_seconds, "bootstrap_report": bootstrap_report,
                                      "runs": results}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps([{key: item[key] for key in ("phase", "scan_seconds", "runner_seconds", "work", "selected_revision_ids")} for item in results]))


if __name__ == "__main__":
    main()
