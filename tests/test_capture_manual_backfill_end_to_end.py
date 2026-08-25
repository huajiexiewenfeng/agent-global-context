from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys

from agc_runtime.capture_contracts import CaptureReceipt, CollectedObservation
from agc_runtime.capture_project_scope import project_scope_from_cwd
from agc_runtime.capture_transaction import read_json
from agc_runtime.paths import MemoryPaths


ROOT = Path(__file__).resolve().parents[1]


def _invoke(*arguments: str) -> tuple[subprocess.CompletedProcess[str], dict[str, object]]:
    result = subprocess.run(
        [sys.executable, "-m", "agc_runtime.capture_cli", *arguments],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.stderr == ""
    assert len(result.stdout.splitlines()) == 1
    return result, json.loads(result.stdout)


def test_manual_backfill_cli_prepares_authorizes_collects_and_replays(
    tmp_path: Path,
) -> None:
    memory = tmp_path / "memory"
    source = tmp_path / "source"
    sessions = source / "sessions"
    sessions.mkdir(parents=True)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    completed = now - timedelta(minutes=1)
    started = completed - timedelta(minutes=1)
    cwd = "C:" + r"\Synthetic\XPublisher"
    expected_scope = project_scope_from_cwd(cwd)
    assert expected_scope is not None
    records = (
        {
            "timestamp": started.isoformat().replace("+00:00", "Z"),
            "type": "session_meta",
            "payload": {
                "id": "rollout-manual",
                "session_id": "task-manual",
                "source": "cli",
                "cwd": cwd,
            },
        },
        {
            "timestamp": started.isoformat().replace("+00:00", "Z"),
            "type": "event_msg",
            "payload": {"type": "task_started", "turn_id": "turn-manual"},
        },
        {
            "timestamp": started.isoformat().replace("+00:00", "Z"),
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": "I prefer Rust.",
                "turn_id": "turn-manual",
            },
        },
        {
            "timestamp": completed.isoformat().replace("+00:00", "Z"),
            "type": "event_msg",
            "payload": {"type": "task_complete", "turn_id": "turn-manual"},
        },
    )
    (sessions / "manual.jsonl").write_text(
        "".join(json.dumps(item) + "\n" for item in records), encoding="utf-8"
    )

    fake = tmp_path / "fake_backfill.py"
    fake_text = (ROOT / "tests" / "fixtures" / "fake_codex_exec.py").read_text(
        encoding="utf-8"
    )
    fake.write_text(
        fake_text.replace("The user prefers privacy.", "The user prefers Rust.")
        .replace("I prefer privacy.", "I prefer Rust.")
        .replace("CAPSULE_ONLY_SENTINEL", "I prefer Rust.")
        .replace(
            '"project_scope": "project:stable"',
            f'"project_scope": {json.dumps(expected_scope)}',
        ),
        encoding="utf-8",
    )
    memory.mkdir()
    config = (ROOT / "agc_runtime" / "default_config.yaml").read_text(
        encoding="utf-8"
    )
    command = f"{Path(sys.executable).as_posix()} {fake.as_posix()}"
    config = (
        config.replace("enabled: false", "enabled: true", 1)
        .replace("mode: off", "mode: scanner_only", 1)
        .replace("sources: []", f"sources:\n    - {source.as_posix()}", 1)
        .replace("executable: codex", f"executable: {command}", 1)
    )
    (memory / "config.yaml").write_text(config, encoding="utf-8")

    prepared_result, prepared = _invoke(
        "prepare-backfill", "--root", str(memory)
    )
    assert prepared_result.returncode == 0
    assert prepared["status"] == "accepted"
    digest = prepared["data"]["authorization_digest"]

    run_result, run = _invoke(
        "backfill",
        "--root",
        str(memory),
        "--authorization-digest",
        digest,
        "--max-items",
        "20",
        "--once",
    )
    assert run_result.returncode == 0
    assert run["status"] == "accepted"
    assert run["data"]["completed_count"] == 1
    assert run["data"]["observation_count"] == 1
    assert run["data"]["charged_tokens"] == 18

    paths = MemoryPaths.from_root(memory)
    receipt_path = next(paths.capture.receipts.glob("*.json"))
    observation_path = next(paths.capture.observations.glob("*.json"))
    assert CaptureReceipt.from_mapping(read_json(receipt_path)).status == "complete"
    observation = CollectedObservation.from_mapping(read_json(observation_path))
    assert observation.statement == "The user prefers Rust."
    assert observation.project_scope == expected_scope

    replay_result, replay = _invoke(
        "backfill",
        "--root",
        str(memory),
        "--authorization-digest",
        digest,
        "--max-items",
        "20",
        "--once",
    )
    assert replay_result.returncode == 0
    assert replay["data"]["attempted_count"] == 0
    assert replay["data"]["extractor_call_count"] == 0

    runner_records = (
        {
            "timestamp": started.isoformat().replace("+00:00", "Z"),
            "type": "session_meta",
            "payload": {
                "id": "rollout-runner",
                "session_id": "task-runner",
                "source": "cli",
                "cwd": cwd,
            },
        },
        {
            "timestamp": started.isoformat().replace("+00:00", "Z"),
            "type": "event_msg",
            "payload": {"type": "task_started", "turn_id": "turn-runner"},
        },
        {
            "timestamp": started.isoformat().replace("+00:00", "Z"),
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": "I prefer Rust.",
                "turn_id": "turn-runner",
            },
        },
        {
            "timestamp": completed.isoformat().replace("+00:00", "Z"),
            "type": "event_msg",
            "payload": {"type": "task_complete", "turn_id": "turn-runner"},
        },
    )
    (sessions / "runner.jsonl").write_text(
        "".join(json.dumps(item) + "\n" for item in runner_records),
        encoding="utf-8",
    )
    runner_config = (memory / "config.yaml").read_text(encoding="utf-8")
    (memory / "config.yaml").write_text(
        runner_config.replace("mode: scanner_only", "mode: runner", 1).replace(
            "incremental_total_tokens: null",
            "incremental_total_tokens: 100000",
            1,
        ),
        encoding="utf-8",
    )

    cycle_result, cycle = _invoke(
        "cycle",
        "--root",
        str(memory),
        "--once",
        "--max-items",
        "20",
    )
    assert cycle_result.returncode == 0
    assert cycle["status"] == "accepted"
    assert cycle["data"]["completed_count"] == 1
    assert cycle["data"]["observation_count"] == 1
    assert cycle["data"]["charged_tokens"] == 18
    assert cycle["data"]["backlog_count"] == 0

    observations = [
        CollectedObservation.from_mapping(read_json(path))
        for path in paths.capture.observations.glob("co_*.json")
    ]
    assert len(observations) == 2
    assert {item.project_scope for item in observations} == {expected_scope}

    probe_result, probe = _invoke("probe", "--root", str(memory))
    assert probe_result.returncode == 0
    assert probe["data"]["runner"] == {
        "assessment": "ready",
        "backlog_count": 0,
        "oldest_unresolved_at": None,
        "max_attempt_count": 1,
        "status_counts": {"complete": 2},
        "settled_token_count": 36,
        "concurrency": 1,
    }
