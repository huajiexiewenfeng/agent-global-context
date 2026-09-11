"""Read-only checkout fingerprints, not execution attestation or authorization.

No checkout imports, subprocesses, model calls, production roots or writes.
The execution bridge must later bind these artifacts to the actual request.
"""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

from agc_runtime.capture_experiment import _digest, _text


def prepare_identity(
    checkout: Path, *, model: str, model_config: dict, prompt: str | None = None
) -> dict:
    """Fingerprint explicit source artifacts; model settings remain declared only."""
    if not _text(model) or not isinstance(model_config, dict):
        raise ValueError("experiment_invalid_identity")
    config_digest = _digest(model_config)
    root = Path(checkout).resolve(strict=True)
    package = root / "agc_runtime"
    schema_name = "agc_runtime/schemas/capture-extractor-v1.schema.json"
    profile_name = "agc_runtime/eval_profiles/agc-capture-quality.v1.json"
    paths = sorted(package.rglob("*.py")) + [
        root / "pyproject.toml", root / schema_name, root / profile_name
    ]
    contents = {}
    try:
        for path in paths:
            if not path.resolve(strict=True).is_relative_to(root):
                raise ValueError("experiment_artifact_invalid")
            contents[path.relative_to(root).as_posix()] = path.read_bytes()
        for name in (schema_name, profile_name):
            if not isinstance(json.loads(contents[name]), dict):
                raise ValueError("experiment_artifact_invalid")
    except (OSError, ValueError) as error:
        raise ValueError("experiment_artifact_invalid") from error
    if prompt is None:
        try:
            tree = ast.parse(contents["agc_runtime/codex_extractor.py"])
            values = [
                ast.literal_eval(node.value)
                for node in tree.body
                if isinstance(node, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "_EXTRACTION_INSTRUCTION" for t in node.targets)
            ]
            if len(values) != 1:
                raise ValueError("missing or duplicate instruction")
            prompt = values[0]
        except (KeyError, SyntaxError, ValueError, TypeError) as error:
            raise ValueError("experiment_prompt_unavailable") from error
    if not _text(prompt):
        raise ValueError("experiment_prompt_unavailable")
    artifacts = {
        name: "sha256:" + hashlib.sha256(content).hexdigest()
        for name, content in sorted(contents.items())
    }
    identity = {
        "model": model,
        "model_config": config_digest,
        "schema": artifacts[schema_name],
        "profile": artifacts[profile_name],
        "agc_version": _digest({k: v for k, v in artifacts.items() if k not in (schema_name, profile_name)}),
        "prompt": _digest(prompt),
    }
    record = {
        "schema": "agc.experiment.preflight.v1",
        "identity": identity,
        "artifacts": artifacts,
        "execution_verified": False,
        "model_called": False,
    }
    record["snapshot_digest"] = _digest(record)
    return record
