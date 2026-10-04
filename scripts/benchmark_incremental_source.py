"""Compare source scans on shared synthetic input; never opens production roots.

Run once per checkout with distinct empty capture/output directories under
D:/tmp_test and the same source directory. Timings include scanner accounting;
body parse counts isolate discovery work. This is not a production benchmark.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import inspect
import hashlib
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
    parser.add_argument("--files", type=int, default=40)
    args = parser.parse_args()
    boundary = Path("D:/tmp_test").resolve()
    for path in (args.source, args.capture_root, args.output):
        if path.resolve() == boundary or not path.resolve().is_relative_to(boundary):
            parser.error("synthetic artifacts must be below D:/tmp_test")
    if not 1 <= args.files <= 1000 or args.capture_root.exists() or args.output.exists():
        parser.error("use 1..1000 files and fresh capture/output paths")
    sys.path.insert(0, str(args.repo.resolve()))
    module_names = ("capture_scanner.py", "capture_store.py", "codex_source_adapter.py", "capture_source_cache.py")

    def code_fingerprints():
        return {name: hashlib.sha256((args.repo / "agc_runtime" / name).read_bytes()).hexdigest()
                for name in module_names if (args.repo / "agc_runtime" / name).exists()}

    implementation = code_fingerprints()
    from agc_runtime.capture_scanner import CaptureScanner
    from agc_runtime.capture_store import CaptureStore
    from agc_runtime.codex_source_adapter import CodexSourceAdapter
    from agc_runtime.paths import MemoryPaths

    if not args.source.exists():
        sessions = args.source / "sessions"
        sessions.mkdir(parents=True)
        for index in range(args.files):
            records = [
                {"timestamp": "2026-10-03T10:00:00Z", "type": "session_meta",
                 "payload": {"id": f"rollout-{index}", "session_id": f"task-{index}", "source": "vscode"}},
                {"timestamp": "2026-10-03T10:00:01Z", "type": "event_msg",
                 "payload": {"type": "task_started", "turn_id": f"turn-{index}"}},
            ]
            records.extend({"type": "event_msg", "payload": {
                "type": "user_message", "message": "synthetic-padding " * 128}}
                for _ in range(32))
            records.append({"timestamp": "2026-10-03T10:01:00Z", "type": "event_msg",
                            "payload": {"type": "task_complete", "turn_id": f"turn-{index}"}})
            (sessions / f"task-{index}.jsonl").write_text(
                "".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
    if len(tuple((args.source / "sessions").glob("*.jsonl"))) != args.files:
        parser.error("shared synthetic input does not match requested file count")

    paths = MemoryPaths.from_root(args.capture_root)
    started = datetime(2026, 10, 4, tzinfo=timezone.utc)
    results = []
    original = CodexSourceAdapter._scan_file
    calls: list[str] = []

    def counted(self, path):
        calls.append(path.name)
        return original(self, path)

    CodexSourceAdapter._scan_file = counted
    try:
        for iteration in range(4):
            now = (started + timedelta(minutes=iteration)).isoformat().replace("+00:00", "Z")
            options = {}
            if "metadata_cache_root" in inspect.signature(CodexSourceAdapter).parameters:
                options["metadata_cache_root"] = paths.capture.root / "source-cache"
            # New instances deliberately reproduce scheduled process restarts.
            adapter = CodexSourceAdapter(args.source, **options)
            store = CaptureStore(paths, clock=lambda: now)
            calls.clear()
            clock = time.perf_counter()
            report = CaptureScanner(store, [adapter]).scan(run_started_at=now)
            elapsed = time.perf_counter() - clock
            revisions = store.frozen_revisions()
            results.append({
                "phase": "cold" if iteration == 0 else f"warm-{iteration}",
                "elapsed_seconds": elapsed,
                "source_body_parses": len(calls),
                "scan_report": asdict(report),
                "revisions": [item.to_mapping() for item in revisions],
            })
    finally:
        CodexSourceAdapter._scan_file = original
    if code_fingerprints() != implementation:
        raise RuntimeError("implementation changed during benchmark; discard run")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({
        "repo": str(args.repo.resolve()), "files": args.files,
        "harness_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "implementation_sha256": implementation,
        "source_sha256": {item.relative_to(args.source).as_posix(): hashlib.sha256(item.read_bytes()).hexdigest()
                          for item in sorted(args.source.rglob("*.jsonl"))},
        "source_bytes": sum(item.stat().st_size for item in args.source.rglob("*.jsonl")),
        "scope": "synthetic scanner; no model; no production-speed claim",
        "runs": results,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps([{key: run[key] for key in
        ("phase", "elapsed_seconds", "source_body_parses")} for run in results]))


if __name__ == "__main__":
    main()
