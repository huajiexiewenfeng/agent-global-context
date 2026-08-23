"""Host activation diagnosis and consent-digest contracts."""

from __future__ import annotations

import importlib
import json
from pathlib import Path
import sys

import pytest


def _module():
    try:
        return importlib.import_module("agc_runtime.capture_activation")
    except ModuleNotFoundError as error:
        if error.name != "agc_runtime.capture_activation":
            raise
        pytest.fail("agc_runtime.capture_activation is not implemented")


@pytest.fixture(autouse=True)
def _unload_activation_module():
    before = set(sys.modules)
    yield
    if "agc_runtime.capture_activation" not in before:
        sys.modules.pop("agc_runtime.capture_activation", None)


def _status(*, enabled: bool = True, mode: str = "scanner_only") -> dict:
    return {
        "schema_version": 2,
        "runtime": {"version": "0.4.1", "sha256": "1" * 64},
        "config_source": {"kind": "memory_root_config", "sha256": "2" * 64},
        "memory_root": {
            "fingerprint": "3" * 64,
            "assessment": "verified",
            "matches_host_binding": True,
            "evidence": {"kind": "synthetic_host"},
        },
        "source_roots": {
            "configured_count": 1,
            "assessment": "configured",
            "ids": ["4" * 64],
        },
        "extractor_boundary": {
            "kind": "codex_exec",
            "model_configured": True,
            "capability_assessment": "ready",
        },
        "budgets": {
            "backfill_window_days": 7,
            "backfill_total_tokens": 100_000,
            "incremental_total_tokens": 20_000,
            "runner_concurrency": 1,
            "max_attempts": 3,
        },
        "state": {
            "enabled": enabled,
            "paused": False,
            "mode": mode,
            "scanner_only": mode == "scanner_only",
        },
        "scanner": {
            "assessment": "ready",
            "latest_census": {"assessment": "available", "run_count": 1},
            "exclusions": {
                "task_id_count": 2,
                "project_id_count": 1,
            },
        },
    }


def _evidence(**changes):
    values = {
        "schema_version": 1,
        "effective_v2_skill_count": 1,
        "legacy_v1_skill_count": 0,
        "mcp_block_count": 1,
        "memory_root_count": 1,
        "runtime_hash_matches": True,
        "config_hash_matches": True,
        "recall_gate_passed": True,
        "extractor_capability": "ready",
        "hook_enabled": False,
        "hook_trusted": False,
        "hook_latency_passed": False,
        "scheduler_enabled": False,
        "frozen_census": True,
    }
    values.update(changes)
    return values


def test_ac_01_route_and_explicit_consent_gate():
    activation = _module()
    evidence = activation.ActivationEvidence.from_mapping(_evidence())

    scanner = activation.diagnose_activation(_status(), evidence)

    assert scanner.route_assessment == "ready"
    assert scanner.conflicts == ()
    assert scanner.readiness == {
        "installed_inert": False,
        "scanner_ready": True,
        "hook_ready": False,
        "backfill_runner_ready": True,
        "continuous_runner_ready": False,
    }
    digest = activation.activation_digest_for(scanner)
    assert len(digest) == 64
    assert set(digest) <= set("0123456789abcdef")

    runner_status = _status(mode="runner")
    runner_evidence = activation.ActivationEvidence.from_mapping(
        _evidence(scheduler_enabled=True)
    )
    without_consent = activation.diagnose_activation(runner_status, runner_evidence)
    assert without_consent.readiness["continuous_runner_ready"] is False
    with_consent = activation.diagnose_activation(
        runner_status,
        runner_evidence,
        consent_digest=activation.activation_digest_for(without_consent),
    )
    assert with_consent.readiness["continuous_runner_ready"] is True
    assert activation.activation_digest_for(with_consent) == activation.activation_digest_for(without_consent)


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"effective_v2_skill_count": 0}, "effective_v2_skill_missing"),
        ({"effective_v2_skill_count": 2}, "multiple_effective_v2_skills"),
        ({"legacy_v1_skill_count": 1}, "legacy_v1_route_present"),
        ({"mcp_block_count": 2}, "multiple_mcp_blocks"),
        ({"memory_root_count": 2}, "multiple_memory_roots"),
        ({"runtime_hash_matches": False}, "runtime_hash_stale"),
        ({"config_hash_matches": False}, "config_hash_stale"),
    ],
)
def test_route_conflicts_fail_closed_without_paths(changes, code):
    activation = _module()
    evidence = activation.ActivationEvidence.from_mapping(_evidence(**changes))

    report = activation.diagnose_activation(_status(), evidence)

    assert report.route_assessment == "conflict"
    assert code in report.conflicts
    assert report.readiness["scanner_ready"] is False
    assert "D:\\" not in json.dumps(report.to_mapping())


def test_disabled_paused_and_capability_gates_are_separate():
    activation = _module()
    evidence = activation.ActivationEvidence.from_mapping(_evidence())
    disabled = activation.diagnose_activation(_status(enabled=False, mode="off"), evidence)
    paused_status = _status()
    paused_status["state"]["paused"] = True
    paused = activation.diagnose_activation(paused_status, evidence)
    invalid_extractor = activation.diagnose_activation(
        _status(),
        activation.ActivationEvidence.from_mapping(
            _evidence(extractor_capability="invalid")
        ),
    )
    recall_failed = activation.diagnose_activation(
        _status(),
        activation.ActivationEvidence.from_mapping(_evidence(recall_gate_passed=False)),
    )

    assert disabled.readiness["installed_inert"] is True
    assert disabled.readiness["scanner_ready"] is False
    assert paused.readiness["scanner_ready"] is False
    assert invalid_extractor.readiness["scanner_ready"] is True
    assert invalid_extractor.readiness["backfill_runner_ready"] is False
    assert recall_failed.readiness["scanner_ready"] is False


def test_digest_changes_for_every_authorization_relevant_boundary():
    activation = _module()
    base_status = _status()
    base_evidence = activation.ActivationEvidence.from_mapping(_evidence())
    base = activation.activation_digest_for(
        activation.diagnose_activation(base_status, base_evidence)
    )

    variants = []
    for section, key, value in (
        ("runtime", "sha256", "a" * 64),
        ("config_source", "sha256", "b" * 64),
        ("memory_root", "fingerprint", "c" * 64),
        ("source_roots", "ids", ["d" * 64]),
        ("extractor_boundary", "kind", "other_exec"),
        ("budgets", "incremental_total_tokens", 20_001),
        ("state", "mode", "runner"),
        ("scanner", "exclusions", {"task_id_count": 3, "project_id_count": 1}),
    ):
        changed = json.loads(json.dumps(base_status))
        changed[section][key] = value
        variants.append(changed)
    changed_evidence = activation.ActivationEvidence.from_mapping(
        _evidence(hook_enabled=True)
    )

    assert all(
        activation.activation_digest_for(
            activation.diagnose_activation(item, base_evidence)
        )
        != base
        for item in variants
    )
    assert activation.activation_digest_for(
        activation.diagnose_activation(base_status, changed_evidence)
    ) != base


def test_evidence_schema_is_strict_and_content_safe():
    activation = _module()
    with pytest.raises(ValueError, match="invalid activation evidence"):
        activation.ActivationEvidence.from_mapping({**_evidence(), "source_path": "secret"})
    with pytest.raises(ValueError, match="invalid activation evidence"):
        activation.ActivationEvidence.from_mapping(
            {key: value for key, value in _evidence().items() if key != "mcp_block_count"}
        )


def test_status_not_assessed_digest_uses_the_same_authorization_contract(tmp_path):
    activation = _module()
    from agc_runtime.capture_status_service import capture_status

    status = capture_status(tmp_path / "memory")
    report = activation.diagnose_activation(
        status, activation.ActivationEvidence.not_assessed()
    )

    assert activation.activation_digest_for(report) == status["activation_digest"]
