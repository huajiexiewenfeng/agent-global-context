"""Only the content-free smoke probe may retry a transient process timeout."""
import json

import pytest

from agc_runtime.capture_extractor import EXTRACTOR_SCHEMA_VERSION
from agc_runtime.codex_extractor import CodexExtractor, _ProcessOutcome


def _success(*, auth=True):
    events = [
        {"type": "thread.started", "thread_id": "test", "model": "gpt-6-sol",
         "provider": "openai", "auth_available": auth, "sandbox": "read-only"},
        {"type": "item.completed", "item": {"id": "final", "type": "agent_message",
         "text": json.dumps({"schema_version": EXTRACTOR_SCHEMA_VERSION, "drafts": []})}},
    ]
    return _ProcessOutcome(returncode=0, stdout="\n".join(map(json.dumps, events)).encode())


def _probe(monkeypatch, outcomes):
    extractor = CodexExtractor(explicit_model="gpt-6-sol")
    responses = iter([
        _ProcessOutcome(returncode=0, stdout=b"codex 0.159.2"),
        _ProcessOutcome(returncode=0, stdout=b"--ephemeral --ignore-user-config --ignore-rules --skip-git-repo-check --sandbox read-only --output-schema --json -"),
        *outcomes,
    ])
    calls = []

    def run(argv, stdin):
        if len(calls) == 3:
            assert outcomes[0].stdout == outcomes[0].stderr == b""
        calls.append((argv, stdin))
        return next(responses)

    monkeypatch.setattr(extractor, "_run", run)
    return extractor.probe_capabilities(), calls[2:]


def test_transient_smoke_timeout_recovers_with_one_empty_retry(monkeypatch):
    timeout = _ProcessOutcome(returncode=1, timed_out=True, stdout=b"PRIVATE", stderr=b"PRIVATE")
    success = _success()
    result, calls = _probe(monkeypatch, [timeout, success])
    assert result.available is True
    assert result.model_boundary == "gpt-6-sol"
    assert len(calls) == 2 and calls[0] == calls[1]
    assert json.loads(calls[0][1]) == {
        "instruction": "Capability probe only. Return an empty drafts array.",
        "schema_version": "capture-probe-v1",
    }
    assert timeout.stdout == timeout.stderr == success.stdout == success.stderr == b""


def test_repeated_smoke_timeout_stops_after_two_attempts(monkeypatch):
    failures = [_ProcessOutcome(returncode=1, timed_out=True, stderr=b"PRIVATE") for _ in range(2)]
    result, calls = _probe(monkeypatch, failures)
    assert result.available is False
    assert (result.error.stage, result.error.code) == ("probe_smoke", "process_timeout")
    assert len(calls) == 2
    assert all(item.stdout == item.stderr == b"" for item in failures)


@pytest.mark.parametrize("reason", ["spawn", "limit", "timeout_and_limit", "nonzero", "invalid", "auth", "not_exited"])
def test_nontransient_smoke_failures_never_retry(monkeypatch, reason):
    failure = _ProcessOutcome(returncode=1, spawn_failed=reason == "spawn",
                              over_limit=reason in {"limit", "timeout_and_limit"},
                              timed_out=reason == "timeout_and_limit")
    if reason == "invalid":
        failure = _ProcessOutcome(returncode=0, stdout=b"invalid")
    if reason == "auth":
        failure = _success(auth=False)
    if reason == "not_exited":
        failure = _ProcessOutcome(returncode=None, timed_out=True)
    result, calls = _probe(monkeypatch, [failure])
    assert result.available is False
    assert len(calls) == 1
    assert failure.stdout == failure.stderr == b""
