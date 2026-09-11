import importlib
import json
from pathlib import Path

import pytest


def module():
    return importlib.import_module("agc_runtime.capture_experiment_preflight")


@pytest.fixture
def checkout(tmp_path):
    package = tmp_path / "agc_runtime"
    (package / "schemas").mkdir(parents=True)
    (package / "eval_profiles").mkdir()
    (package / "codex_extractor.py").write_text(
        '_EXTRACTION_INSTRUCTION = ("Extract " "durable signals")\n'
        'raise RuntimeError("must never import checkout")\n', encoding="utf-8"
    )
    (package / "capture_capsule.py").write_text("VERSION = 1\n", encoding="utf-8")
    (package / "schemas/capture-extractor-v1.schema.json").write_text('{}', encoding="utf-8")
    (package / "eval_profiles/agc-capture-quality.v1.json").write_text('{}', encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "0.4.5"\n', encoding="utf-8")
    return tmp_path


def prepare(root, **kwargs):
    return module().prepare_identity(root, model="gpt-5.6-sol", model_config={"reasoning_effort": "medium"}, **kwargs)


def test_read_only_snapshot_does_not_import_checkout(checkout):
    before = {p.relative_to(checkout): p.read_bytes() for p in checkout.rglob('*') if p.is_file()}
    result = prepare(checkout)
    assert result == prepare(checkout)
    assert result["execution_verified"] is False
    assert result["model_called"] is False
    assert result["identity"]["model"] == "gpt-5.6-sol"
    assert set(result["identity"]) == {"model", "model_config", "schema", "profile", "agc_version", "prompt"}
    assert str(checkout) not in json.dumps(result)
    assert before == {p.relative_to(checkout): p.read_bytes() for p in checkout.rglob('*') if p.is_file()}


def test_candidate_changes_only_prompt_identity(checkout):
    baseline = prepare(checkout)
    candidate = prepare(checkout, prompt="Consider scoped project evidence")
    assert [k for k in baseline["identity"] if baseline["identity"][k] != candidate["identity"][k]] == ["prompt"]


@pytest.mark.parametrize("relative, field", [
    ("agc_runtime/capture_capsule.py", "agc_version"),
    ("agc_runtime/schemas/capture-extractor-v1.schema.json", "schema"),
    ("agc_runtime/eval_profiles/agc-capture-quality.v1.json", "profile"),
])
def test_actual_artifact_change_is_detected(checkout, relative, field):
    before = prepare(checkout)
    path = checkout / relative
    path.write_text('{"changed": true}' if path.suffix == '.json' else 'VERSION = 2\n', encoding="utf-8")
    assert prepare(checkout)["identity"][field] != before["identity"][field]


def test_missing_prompt_is_not_silently_defaulted(checkout):
    (checkout / "agc_runtime/codex_extractor.py").write_text("x = 1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="experiment_prompt_unavailable"):
        prepare(checkout)


def test_invalid_profile_is_rejected(checkout):
    (checkout / "agc_runtime/eval_profiles/agc-capture-quality.v1.json").write_text('not json', encoding="utf-8")
    with pytest.raises(ValueError, match="experiment_artifact_invalid"):
        prepare(checkout)


def test_empty_override_is_rejected(checkout):
    with pytest.raises(ValueError, match="experiment_prompt_unavailable"):
        prepare(checkout, prompt=" ")


def test_real_checkout_prepares_without_models():
    result = prepare(Path(__file__).resolve().parents[1])
    assert "agc_runtime/codex_extractor.py" in result["artifacts"]
    assert result["identity"]["schema"].startswith("sha256:")
