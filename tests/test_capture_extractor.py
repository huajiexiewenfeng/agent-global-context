from __future__ import annotations

import json
import shutil
import sys
import time
import tomllib
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
FAKE_CODEX = ROOT / "tests" / "fixtures" / "fake_codex_exec.py"
SCHEMA = ROOT / "agc_runtime" / "schemas" / "capture-extractor-v1.schema.json"
RAW_SENTINEL = "RAW_PROCESS_SECRET_SENTINEL"


def _extractor_api():
    try:
        from agc_runtime.capture_extractor import (
            CapabilityProbe,
            CollectedObservationDraft,
            ExtractionResult,
            ExtractorDescriptor,
        )
        from agc_runtime.codex_extractor import CodexExtractor
    except ModuleNotFoundError:
        pytest.fail("Task2 extractor production modules are not implemented")
    return (
        CapabilityProbe,
        CollectedObservationDraft,
        ExtractionResult,
        ExtractorDescriptor,
        CodexExtractor,
    )


def _capsule():
    from agc_runtime.capture_capsule import TaskCapsule

    return TaskCapsule(
        adapter_id="codex",
        adapter_version="1.0",
        source_schema_version="codex-v1",
        source_root_id="7" * 64,
        task_id="task-main",
        revision_id="turn-target",
        rollout_anchor_id="rollout-main",
        identity_quality="session_id",
        completed_at="2026-08-20T12:00:00Z",
        project_scope="project:stable",
        task_title="CAPSULE_ONLY_SENTINEL",
        user_signals=("I prefer privacy.",),
    )


def _command(path: Path = FAKE_CODEX) -> tuple[str, ...]:
    return sys.executable, str(path)


def _extract(*, scenario: str | None = None, timeout: float = 3.0):
    *_unused, CodexExtractor = _extractor_api()
    extractor = CodexExtractor(
        executable=_command(),
        explicit_model=scenario,
        timeout_seconds=timeout,
        max_stdout_bytes=64 * 1024,
        max_stderr_bytes=16 * 1024,
    )
    return extractor.extract(_capsule(), object())


def _valid_draft() -> dict[str, object]:
    return {
        "statement": "The user prefers privacy.",
        "assertion": {
            "subject": "user",
            "mode": "direct",
            "modality": "asserted",
        },
        "primary_category": "personal_growth",
        "kind": "preference",
        "scopes": ["global"],
        "project_scope": "project:stable",
        "confidence": "confirmed",
        "sensitivity": "normal",
        "signal_type": "explicit_user_state",
        "evidence": ["I prefer privacy."],
        "priority": 1,
        "locator": "user:0001",
    }


def test_static_schema_is_closed_and_bounds_drafts_zero_to_eight():
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))

    assert schema["$id"] == "urn:agent-global-context:capture-extractor-v1"
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["schema_version", "drafts"]
    assert schema["properties"]["drafts"]["minItems"] == 0
    assert schema["properties"]["drafts"]["maxItems"] == 8
    assert schema["$defs"]["observation_draft"]["additionalProperties"] is False


def test_pyproject_packages_the_static_extractor_schema():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    package_data = project["tool"]["setuptools"]["package-data"]
    assert "schemas/capture-extractor-v1.schema.json" in package_data["*"]


def test_descriptor_and_draft_dtos_are_strict_and_content_hidden():
    _, CollectedObservationDraft, _, ExtractorDescriptor, _ = _extractor_api()
    descriptor = ExtractorDescriptor.from_mapping(
        {
            "extractor_id": "codex",
            "extractor_version": "1.0",
            "extractor_schema_version": "capture-extractor-v1",
            "taxonomy_version": "agc-taxonomy-v1",
        }
    )
    draft = CollectedObservationDraft.from_mapping(_valid_draft())

    assert descriptor.to_mapping()["extractor_id"] == "codex"
    assert draft.to_mapping() == _valid_draft()
    assert "The user" not in repr(draft)
    with pytest.raises(ValueError, match="capture_extractor_contract_invalid"):
        ExtractorDescriptor.from_mapping({"extractor_id": "codex"})
    with pytest.raises(ValueError, match="capture_extractor_contract_invalid"):
        CollectedObservationDraft.from_mapping({**_valid_draft(), "unknown": True})


@pytest.mark.parametrize(("scenario", "count"), (("zero", 0), (None, 1), ("eight", 8)))
def test_valid_zero_one_and_eight_draft_outputs(scenario: str | None, count: int):
    result = _extract(scenario=scenario)

    assert result.succeeded
    assert result.error is None
    assert len(result.drafts) == count
    assert RAW_SENTINEL not in repr(result)


@pytest.mark.parametrize(
    "scenario",
    (
        "over-eight",
        "missing-field",
        "unknown-field",
        "draft-missing",
        "draft-unknown",
        "draft-enum",
        "draft-type",
        "draft-bool",
        "draft-nan",
        "draft-surrogate",
        "malformed-jsonl",
        "multiple-final",
        "unknown-event",
    ),
)
def test_invalid_or_ambiguous_output_fails_closed_with_fixed_error(scenario: str):
    result = _extract(scenario=scenario)

    assert not result.succeeded
    assert result.drafts == ()
    assert result.usage is None
    assert result.error.to_mapping() == {
        "stage": "extractor_output",
        "code": "invalid_output",
        "retryable": True,
    }
    assert RAW_SENTINEL not in repr(result)
    assert RAW_SENTINEL not in str(result.error)


@pytest.mark.parametrize(
    ("scenario", "code"),
    (
        ("nonzero", "process_nonzero"),
        ("timeout", "process_timeout"),
        ("huge-stdout", "process_output_limit"),
        ("huge-stderr", "process_output_limit"),
    ),
)
def test_process_failures_are_bounded_and_content_safe(
    scenario: str,
    code: str,
    caplog: pytest.LogCaptureFixture,
):
    started = time.monotonic()
    result = _extract(scenario=scenario, timeout=0.35 if scenario == "timeout" else 3.0)

    assert time.monotonic() - started < 4.0
    assert not result.succeeded
    assert result.error.to_mapping() == {
        "stage": "extractor_process",
        "code": code,
        "retryable": True,
    }
    assert RAW_SENTINEL not in repr(result)
    assert RAW_SENTINEL not in caplog.text


def test_timeout_covers_a_child_that_never_reads_stdin():
    *_unused, CodexExtractor = _extractor_api()
    extractor = CodexExtractor(
        executable=_command(),
        explicit_model="stdin-block",
        timeout_seconds=0.35,
    )
    started = time.monotonic()

    with extractor._schema_path() as schema_path:
        outcome = extractor._run(
            extractor._build_argv(schema_path),
            b"X" * (2 * 1024 * 1024),
        )

    assert time.monotonic() - started < 4.0
    assert outcome.timed_out
    assert repr(outcome) == "_ProcessOutcome(content_hidden=True)"


@pytest.mark.parametrize("scenario", ("usage-absent", "usage-partial"))
def test_absent_or_partial_usage_is_successful_but_reports_none(scenario: str):
    result = _extract(scenario=scenario)

    assert result.succeeded
    assert len(result.drafts) == 1
    assert result.usage is None


def test_complete_usage_is_strict_token_usage():
    result = _extract()

    assert result.succeeded
    assert result.usage.to_mapping() == {
        "input_tokens": 11,
        "output_tokens": 7,
        "total_tokens": 18,
    }


def test_representative_codex_events_ignore_reasoning_and_normalize_usage():
    result = _extract(scenario="realistic-events")

    assert result.succeeded
    assert len(result.drafts) == 1
    assert result.usage.to_mapping() == {
        "input_tokens": 11,
        "output_tokens": 7,
        "total_tokens": 18,
    }
    assert RAW_SENTINEL not in repr(result)


def test_real_child_validates_exact_argv_empty_cwd_sanitized_env_and_stdin(
    monkeypatch: pytest.MonkeyPatch,
):
    for key in (
        "AGC_CAPTURE_HOOK_ACTIVE",
        "AGC_MEMORY_ROOT",
        "AGENT_GLOBAL_CONTEXT_ROOT",
        "CODEX_HOME",
        "PYTHONPATH",
        "PYTHONHOME",
        "CLAUDECODE",
    ):
        monkeypatch.setenv(key, "CAPSULE_ONLY_SENTINEL")

    result = _extract()

    assert result.succeeded
    assert len(result.drafts) == 1


def test_argv_is_a_list_boundary_and_optional_model_is_explicitly_appended():
    *_unused, CodexExtractor = _extractor_api()
    without_model = CodexExtractor(executable=_command())
    with_model = CodexExtractor(executable=_command(), explicit_model="gpt-test")

    expected = (
        *_command(),
        "exec",
        "--ephemeral",
        "--ignore-user-config",
        "--ignore-rules",
        "--sandbox",
        "read-only",
        "--output-schema",
        str(SCHEMA.resolve()),
        "--json",
        "-",
    )
    assert without_model._build_argv(SCHEMA.resolve()) == expected
    assert with_model._build_argv(SCHEMA.resolve()) == (
        *expected[:-1],
        "--model",
        "gpt-test",
        "-",
    )
    assert isinstance(with_model._build_argv(SCHEMA.resolve()), tuple)


def test_capability_probe_requires_version_help_flags_and_content_free_smoke():
    *_unused, CodexExtractor = _extractor_api()
    probe = CodexExtractor(executable=_command()).probe_capabilities()

    assert probe.available
    assert probe.auth_available
    assert probe.sandbox_read_only
    assert probe.usage_available
    assert probe.model_boundary == "fake-model"
    assert probe.provider_boundary == "fake-provider"
    assert len(probe.executable_identity) == 64
    assert str(FAKE_CODEX.parent) not in repr(probe)
    assert probe.error is None


def test_help_capability_requires_standalone_stdin_dash_token():
    *_unused, CodexExtractor = _extractor_api()
    help_without_stdin = (
        "--ephemeral --ignore-user-config --ignore-rules --sandbox read-only "
        "--output-schema --json"
    )

    assert not CodexExtractor._help_has_required_flags(help_without_stdin)


@pytest.mark.parametrize(
    "name",
    (
        "fake_codex_missing_flag.py",
        "fake_codex_missing_stdin.py",
        "fake_codex_missing_metadata.py",
        "fake_codex_version_fail.py",
        "fake_codex_smoke_fail.py",
    ),
)
def test_any_missing_capability_prevents_activation_with_content_free_failure(
    tmp_path: Path,
    name: str,
):
    *_unused, CodexExtractor = _extractor_api()
    executable = tmp_path / name
    shutil.copyfile(FAKE_CODEX, executable)

    probe = CodexExtractor(executable=_command(executable)).probe_capabilities()

    assert not probe.available
    assert probe.error.to_mapping() == {
        "stage": "capability_probe",
        "code": "capability_unavailable",
        "retryable": True,
    }
    assert RAW_SENTINEL not in repr(probe)
    assert str(executable) not in repr(probe)


def test_result_dto_rejects_invalid_types_unknown_fields_and_inconsistent_state():
    _, _, ExtractionResult, _, _ = _extractor_api()

    invalid = (
        {
            "succeeded": 1,
            "drafts": [],
            "usage": None,
            "error": None,
        },
        {
            "succeeded": True,
            "drafts": [],
            "usage": None,
            "error": None,
            "unknown": RAW_SENTINEL,
        },
        {
            "succeeded": False,
            "drafts": [_valid_draft()],
            "usage": None,
            "error": None,
        },
    )
    for value in invalid:
        with pytest.raises(ValueError, match="capture_extractor_contract_invalid"):
            ExtractionResult.from_mapping(value)


def test_direct_dto_construction_cannot_bypass_strict_validation():
    from dataclasses import replace

    CapabilityProbe, CollectedObservationDraft, ExtractionResult, ExtractorDescriptor, _ = (
        _extractor_api()
    )
    descriptor = ExtractorDescriptor.from_mapping(
        {
            "extractor_id": "codex",
            "extractor_version": "1.0",
            "extractor_schema_version": "capture-extractor-v1",
            "taxonomy_version": "agc-taxonomy-v1",
        }
    )
    draft = CollectedObservationDraft.from_mapping(_valid_draft())
    probe_error = {
        "stage": "capability_probe",
        "code": "capability_unavailable",
        "retryable": True,
    }
    probe = CapabilityProbe.from_mapping(
        {
            "available": False,
            "executable_identity": "a" * 64,
            "executable_version": "1.0",
            "model_boundary": None,
            "provider_boundary": None,
            "auth_available": False,
            "sandbox_read_only": False,
            "usage_available": False,
            "error": probe_error,
        }
    )
    failure = ExtractionResult.from_mapping(
        {"succeeded": False, "drafts": [], "usage": None, "error": probe_error}
    )

    with pytest.raises(ValueError, match="capture_extractor_contract_invalid"):
        replace(descriptor, extractor_schema_version="unknown")
    with pytest.raises(ValueError, match="capture_extractor_contract_invalid"):
        replace(draft, priority=True)
    with pytest.raises(ValueError, match="capture_extractor_contract_invalid"):
        replace(draft, statement=" The user prefers privacy. ")
    with pytest.raises(ValueError, match="capture_extractor_contract_invalid"):
        replace(probe, available=True)
    with pytest.raises(ValueError, match="capture_extractor_contract_invalid"):
        replace(failure, succeeded=True)

    available_without_boundaries = {
        "available": True,
        "executable_identity": "a" * 64,
        "executable_version": "1.0",
        "model_boundary": None,
        "provider_boundary": None,
        "auth_available": True,
        "sandbox_read_only": True,
        "usage_available": False,
        "error": None,
    }
    with pytest.raises(ValueError, match="capture_extractor_contract_invalid"):
        CapabilityProbe.from_mapping(available_without_boundaries)
