from __future__ import annotations

import builtins
import json
from pathlib import Path

import pytest

from agc_runtime.capture_eval_evidence import canonical_sha256
from agc_runtime.eval_cli import (
    _authorization_digest,
    _load_profile,
    main,
)

PROFILE_REF = {"id": "agc.capture-quality", "version": "1"}
EVIDENCE_REF = {
    "schema_version": "eval.evidence-ref.v0.1",
    "provider": "agc",
    "kind": "capture-item",
    "ref": "cr_" + "a" * 64,
    "digest": "sha256:" + "b" * 64,
    "version": "1",
}


def _case(suffix: str) -> dict[str, object]:
    return {
        "schema_version": "eval.case.v0.1",
        "case_id": "evc_" + suffix * 64,
        "subject": {
            "principal_ref": {"id": "agent-global-context.capture", "kind": "runtime"},
            "capability": "capture",
            "operation": "observation-quality",
            "implementation_version": "0.4.4",
        },
        "profile_ref": PROFILE_REF,
        "evidence_refs": [{**EVIDENCE_REF, "ref": "cr_" + suffix * 64}],
        "trace_snapshot": {"schema_version": "trace.snapshot.v0.1", "trace_id": suffix},
        "reference": None,
        "metadata": {"sample_reason": "latest-completed-capture-item"},
    }


CASES = (_case("c"), _case("d"))
PASS_RESULT = {
    "result_id": "evr_" + "1" * 64,
    "status": "pass",
    "usage": {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12},
}
INSUFFICIENT_RESULT = {
    "result_id": "evr_" + "2" * 64,
    "status": "insufficient_evidence",
    "usage": None,
}


def fixed_judge_binding(_capture) -> dict[str, object]:
    return {
        "provider": "openai",
        "model": "gpt-5.6-sol",
        "executable_identity": "a" * 64,
        "command": (r"C:\trusted\codex.exe",),
    }


def eval_cli_fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    root = tmp_path / "memory"
    root.mkdir()
    default = (Path(__file__).resolve().parents[1] / "agc_runtime" / "default_config.yaml").read_text(
        encoding="utf-8"
    )
    configured = default.replace("executable: codex", "executable: codex-app", 1).replace(
        "model: null", "model: gpt-5.6-sol", 1
    )
    (root / "config.yaml").write_text(configured, encoding="utf-8")
    return root, tmp_path / "trace.sqlite3", tmp_path / "eval.sqlite3"


def test_profile_is_the_packaged_confirmed_contract() -> None:
    profile = _load_profile()
    assert profile["profile_id"] == "agc.capture-quality"
    assert profile["profile_version"] == "1"
    assert [item["id"] for item in profile["dimensions"]] == [
        "faithfulness",
        "durability",
        "noise_control",
        "atomicity",
        "classification",
    ]
    assert sum(item["weight"] for item in profile["dimensions"]) == 1.0


def test_prepare_never_resolves_evidence_or_imports_judge(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root, trace_db, _eval_db = eval_cli_fixture(tmp_path)
    profile = _load_profile()
    monkeypatch.setattr("agc_runtime.eval_cli._capture_cases", lambda **_values: CASES)
    monkeypatch.setattr("agc_runtime.eval_cli._judge_binding", fixed_judge_binding)
    real_import = builtins.__import__

    def guarded_import(name: str, *args: object, **kwargs: object):
        if name in {"agent_eval_runtime", "agent_eval_codex"}:
            raise AssertionError("prepare must not import Eval or Judge packages")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    assert main(
        [
            "prepare-capture",
            "--root",
            str(root),
            "--trace-db",
            str(trace_db),
            "--max-items",
            "2",
        ]
    ) == 0
    data = json.loads(capsys.readouterr().out)["data"]
    assert data["case_count"] == 2
    assert data["provider"] == "openai"
    assert data["model"] == "gpt-5.6-sol"
    assert data["executable_identity"] == "a" * 64
    assert data["profile_digest"] == canonical_sha256(profile)
    assert data["case_digests"] == [canonical_sha256(item) for item in CASES]
    assert "command" not in data
    assert "trace_snapshot" not in json.dumps(data)


def test_authorization_digest_binds_complete_cases_profile_judge_and_limit() -> None:
    profile = _load_profile()
    binding = fixed_judge_binding(None)
    digest = _authorization_digest(CASES, profile, binding, 2)
    changed = json.loads(json.dumps(CASES))
    changed[0]["trace_snapshot"]["trace_id"] = "changed"
    assert len(digest) == 64
    assert digest != _authorization_digest(tuple(changed), profile, binding, 2)
    assert digest != _authorization_digest(CASES, profile, binding, 1)


def test_stale_digest_stops_before_evaluation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root, trace_db, eval_db = eval_cli_fixture(tmp_path)
    monkeypatch.setattr("agc_runtime.eval_cli._capture_cases", lambda **_values: CASES)
    monkeypatch.setattr("agc_runtime.eval_cli._judge_binding", fixed_judge_binding)

    def forbidden(**_values: object):
        raise AssertionError("stale authorization must stop before evidence or Judge")

    monkeypatch.setattr("agc_runtime.eval_cli._evaluate_cases", forbidden)
    assert main(
        [
            "capture",
            "--root",
            str(root),
            "--trace-db",
            str(trace_db),
            "--eval-db",
            str(eval_db),
            "--max-items",
            "2",
            "--authorization-digest",
            "0" * 64,
        ]
    ) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"]["code"] == "capture_eval_authorization_stale"


def test_authorized_run_returns_only_result_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root, trace_db, eval_db = eval_cli_fixture(tmp_path)
    profile = _load_profile()
    binding = fixed_judge_binding(None)
    monkeypatch.setattr("agc_runtime.eval_cli._capture_cases", lambda **_values: CASES)
    monkeypatch.setattr("agc_runtime.eval_cli._judge_binding", fixed_judge_binding)
    digest = _authorization_digest(CASES, profile, binding, 2)
    monkeypatch.setattr(
        "agc_runtime.eval_cli._evaluate_cases",
        lambda **_values: (PASS_RESULT, INSUFFICIENT_RESULT),
    )
    assert main(
        [
            "capture",
            "--root",
            str(root),
            "--trace-db",
            str(trace_db),
            "--eval-db",
            str(eval_db),
            "--max-items",
            "2",
            "--authorization-digest",
            digest,
        ]
    ) == 0
    data = json.loads(capsys.readouterr().out)["data"]
    assert data["status_counts"] == {"insufficient_evidence": 1, "pass": 1}
    assert data["result_ids"] == [PASS_RESULT["result_id"], INSUFFICIENT_RESULT["result_id"]]
    assert data["usage"] == {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12}
    assert "trace_snapshot" not in json.dumps(data)
    assert "capsule" not in json.dumps(data)
    assert "command" not in data


def test_missing_optional_runtime_returns_fixed_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root, trace_db, eval_db = eval_cli_fixture(tmp_path)
    profile = _load_profile()
    binding = fixed_judge_binding(None)
    monkeypatch.setattr("agc_runtime.eval_cli._capture_cases", lambda **_values: CASES)
    monkeypatch.setattr("agc_runtime.eval_cli._judge_binding", fixed_judge_binding)
    monkeypatch.setattr(
        "agc_runtime.eval_cli._evaluate_cases",
        lambda **_values: (_ for _ in ()).throw(ModuleNotFoundError("private package path")),
    )
    digest = _authorization_digest(CASES, profile, binding, 2)
    assert main(
        [
            "capture",
            "--root",
            str(root),
            "--trace-db",
            str(trace_db),
            "--eval-db",
            str(eval_db),
            "--max-items",
            "2",
            "--authorization-digest",
            digest,
        ]
    ) == 1
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "eval_runtime_unavailable"


@pytest.mark.parametrize(
    "arguments",
    (
        [],
        ["prepare-capture", "--root", "x"],
        ["prepare-capture", "--root", "x", "--trace-db", "y", "--max-items", "0"],
        ["capture", "--root", "x", "--trace-db", "y", "--eval-db", "z", "--max-items", "1"],
    ),
)
def test_cli_rejects_every_non_exact_form(arguments, capsys) -> None:
    assert main(arguments) == 2
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "invalid_input"
