from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

pytest.importorskip("agent_trace_runtime")
pytest.importorskip("agent_eval_codex")
pytest.importorskip("agent_eval_runtime")

from agent_eval_runtime import EvalStore, load_eval_result

from agc_runtime import eval_cli
from agc_runtime.capture_eval_evidence import (
    CaptureItemTraceReport,
    canonical_sha256,
)
from agc_runtime.capture_trace import record_capture_success
from agc_runtime.paths import MemoryPaths

SENTINEL = "private-eval-evidence-must-not-persist"

FAKE_CODEX = r'''
from __future__ import annotations
import json
import os
import sys
from pathlib import Path

args = sys.argv[1:]
if not args or args[0] != "exec" or args[-1] != "-":
    raise SystemExit(3)
if "--output-schema" not in args or "--sandbox" not in args:
    raise SystemExit(3)
schema = Path(args[args.index("--output-schema") + 1])
json.loads(schema.read_text(encoding="utf-8"))
payload = json.load(sys.stdin)
counter = Path(os.environ["TEMP"]) / "agc-eval-fake-judge-count.txt"
count = int(counter.read_text(encoding="utf-8")) if counter.exists() else 0
counter.write_text(str(count + 1), encoding="utf-8")
reference = payload["eval_case"]["evidence_refs"][0]["ref"]
dimensions = [
    {
        "dimension_id": item["id"],
        "score": 4,
        "explanation": "Supported by the authorized evidence bundle.",
        "evidence": [reference],
    }
    for item in payload["eval_profile"]["dimensions"]
]
result = {
    "schema_version": "eval.judge-output.v1",
    "dimensions": dimensions,
    "findings": [],
    "recommendations": [],
}
events = [
    {
        "type": "thread.started",
        "thread_id": "agc-eval-fixture",
        "model": "gpt-5.6-sol",
        "provider": "openai",
        "authenticated": True,
        "sandbox": "read-only",
    },
    {"type": "turn.started"},
    {
        "type": "item.completed",
        "item": {"type": "agent_message", "text": json.dumps(result, separators=(",", ":"))},
    },
    {
        "type": "turn.completed",
        "usage": {"input_tokens": 20, "output_tokens": 5, "total_tokens": 25},
    },
]
for event in events:
    print(json.dumps(event, separators=(",", ":")))
'''


def _config(root: Path, source: Path) -> MemoryPaths:
    root.mkdir()
    source.mkdir()
    default = (Path(__file__).resolve().parents[1] / "agc_runtime" / "default_config.yaml").read_text(
        encoding="utf-8"
    )
    configured = (
        default.replace("sources: []", f"sources:\n    - {source.as_posix()}", 1)
        .replace("executable: codex", "executable: codex-app", 1)
        .replace("model: null", "model: gpt-5.6-sol", 1)
    )
    (root / "config.yaml").write_text(configured, encoding="utf-8")
    return MemoryPaths.from_root(root)


def _response(capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    output = capsys.readouterr()
    assert output.err == ""
    return json.loads(output.out)


def test_capture_eval_pilot_is_idempotent_content_safe_and_read_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    paths = _config(tmp_path / "memory", tmp_path / "source")
    trace_db = tmp_path / "trace.sqlite3"
    eval_db = tmp_path / "eval.sqlite3"
    fake_codex = tmp_path / "fake-codex-eval.py"
    fake_codex.write_text(FAKE_CODEX, encoding="utf-8")
    monkeypatch.setenv("TEMP", str(tmp_path))
    monkeypatch.setenv("TMP", str(tmp_path))
    monkeypatch.setenv("AGENT_TRACE_DB", str(trace_db))

    evidence = {
        "schema_version": "agc.capture-evidence.v1",
        "capsule": {"user_signals": [SENTINEL]},
        "decision": {
            "outcome": "collected",
            "reason_code": "observations_collected",
            "observations": [{"statement": SENTINEL}],
        },
        "runtime": {"extractor_version": "1", "taxonomy_version": "1"},
    }
    reference = {
        "schema_version": "eval.evidence-ref.v0.1",
        "provider": "agc",
        "kind": "capture-item",
        "ref": "cr_" + "a" * 64,
        "digest": canonical_sha256(evidence),
        "version": "1",
    }
    item = CaptureItemTraceReport(
        occurred_at="2026-08-30T08:00:01Z",
        payload={
            "schema_version": "agc.capture.item-trace.v1",
            "outcome": "collected",
            "reason_code": "observations_collected",
            "observation_count": 1,
            "filtered_counts": {"safety": 0, "policy": 0, "over_limit": 0},
            "duplicate_suppression_count": 0,
            "token_usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
            "extractor_version": "1",
            "taxonomy_version": "1",
            "evidence_ref": reference,
        },
    )
    report = {
        "attempted_count": 1,
        "completed_count": 1,
        "failed_count": 0,
        "deferred_budget_count": 0,
        "lease_contention_count": 0,
        "observation_count": 1,
        "charged_tokens": 2,
        "backlog_count": 0,
        "silent_loss_count": 0,
        "run_time_ms": 1,
        "status_deltas": {"complete": 1},
    }
    started = datetime(2026, 8, 30, 8, 0, tzinfo=UTC)
    assert record_capture_success(
        action="cycle",
        started_at=started,
        finished_at=started + timedelta(seconds=2),
        report=report,
        items=(item,),
    ) == "recorded"

    state_files = (
        paths.capture.receipts / "receipt-state.bin",
        paths.capture.observations / "observation-state.bin",
        paths.capture.budgets / "budget-state.bin",
        paths.capture.reviews / "review-state.bin",
        paths.memories / "formal-memory.md",
    )
    for index, path in enumerate(state_files):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"stable-{index}".encode())
    before = {path: path.read_bytes() for path in state_files}
    formal_count = len(tuple(paths.memories.glob("*.md")))

    class Resolver:
        def __init__(self, **_values: object) -> None:
            pass

        def resolve(self, supplied):
            assert supplied == reference
            return evidence

    monkeypatch.setattr(eval_cli, "AGCCaptureEvidenceResolver", Resolver)
    monkeypatch.setattr(
        eval_cli,
        "resolve_codex_command",
        lambda _value: (sys.executable, str(fake_codex)),
    )

    prepare_args = [
        "prepare-capture",
        "--root",
        str(paths.root),
        "--trace-db",
        str(trace_db),
        "--max-items",
        "1",
    ]
    assert eval_cli.main(prepare_args) == 0
    prepared = _response(capsys)["data"]
    assert prepared["case_count"] == 1
    digest = prepared["authorization_digest"]
    capture_args = [
        "capture",
        "--root",
        str(paths.root),
        "--trace-db",
        str(trace_db),
        "--eval-db",
        str(eval_db),
        "--max-items",
        "1",
        "--authorization-digest",
        digest,
    ]
    assert eval_cli.main(capture_args) == 0
    first = _response(capsys)["data"]
    assert eval_cli.main(capture_args) == 0
    second = _response(capsys)["data"]
    assert first["result_ids"] == second["result_ids"]
    assert (tmp_path / "agc-eval-fake-judge-count.txt").read_text(encoding="utf-8") == "1"

    stored = EvalStore(eval_db).get(first["result_ids"][0])
    assert stored is not None
    assert load_eval_result(stored) == stored
    assert stored["status"] == "pass"
    assert reference["ref"] in json.dumps(stored)
    assert SENTINEL.encode() not in trace_db.read_bytes()
    assert SENTINEL.encode() not in eval_db.read_bytes()
    assert reference["ref"].encode() in trace_db.read_bytes()
    assert {path: path.read_bytes() for path in state_files} == before
    assert len(tuple(paths.memories.glob("*.md"))) == formal_count
