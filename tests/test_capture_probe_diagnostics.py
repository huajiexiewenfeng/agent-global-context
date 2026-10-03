"""Probe failure diagnostics must retain stages but never process content."""
import json
import pytest

from agc_runtime.codex_extractor import CodexExtractor, _ProcessOutcome


@pytest.mark.parametrize('stage', ['version', 'help', 'smoke'])
@pytest.mark.parametrize('reason', ['timeout', 'output_limit', 'spawn_failed', 'nonzero'])
def test_probe_failure_has_safe_stage_and_reason(monkeypatch, stage, reason):
    extractor = CodexExtractor(explicit_model='gpt-6-sol')
    outcomes = [
        _ProcessOutcome(returncode=0, stdout=b'codex 0.159.2'),
        _ProcessOutcome(returncode=0, stdout=b'--ephemeral --ignore-user-config --ignore-rules --skip-git-repo-check --sandbox read-only --output-schema --json -'),
    ]
    failure = _ProcessOutcome(returncode=7, stdout=b'PRIVATE_SENTINEL', stderr=b'PRIVATE_SENTINEL',
                              timed_out=reason == 'timeout', over_limit=reason == 'output_limit',
                              spawn_failed=reason == 'spawn_failed')
    failures = [failure]
    if stage == 'smoke' and reason == 'timeout':
        failures.append(_ProcessOutcome(returncode=7, timed_out=True,
                                        stdout=b'PRIVATE_SENTINEL', stderr=b'PRIVATE_SENTINEL'))
    responses = iter(outcomes[:['version', 'help', 'smoke'].index(stage)] + failures)
    monkeypatch.setattr(extractor, '_run', lambda *args: next(responses))
    probe = extractor.probe_capabilities()
    assert probe.available is False
    assert probe.error.stage == 'probe_' + stage
    assert probe.error.code == 'process_' + reason
    assert 'PRIVATE_SENTINEL' not in json.dumps(probe.to_mapping())
    assert failure.stdout == failure.stderr == b''
    assert all(item.stdout == item.stderr == b'' for item in failures)


def test_probe_exception_only_accepts_allowlisted_diagnostics():
    from agc_runtime.capture_extractor import CapabilityUnavailable
    from agc_runtime.capture_contracts import SanitizedError
    error = CapabilityUnavailable(SanitizedError('probe_smoke', 'process_timeout', True))
    assert str(error) == 'capture_extractor_unavailable'
    assert error.safe_message == 'Capture capability probe failed: probe_smoke/process_timeout'
    unsafe = CapabilityUnavailable(SanitizedError('secret', 'private_path', True))
    assert unsafe.safe_message == 'Capture capability probe failed: unknown/unknown'
