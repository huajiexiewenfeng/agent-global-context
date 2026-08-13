import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
import yaml

from agc_runtime.admin_service import dispatch_admin
from agc_runtime.paths import MemoryPaths
from agc_runtime.runtime_config import load_runtime_config
from agc_runtime.utf8_io import atomic_write_text


def initialized_paths(tmp_path: Path) -> MemoryPaths:
    paths = MemoryPaths.from_root(tmp_path / "memory")
    assert dispatch_admin(paths, {"action": "init"}).status == "accepted"
    return paths


def test_load_runtime_config_exposes_strict_typed_runtime_values(tmp_path: Path):
    config = load_runtime_config(initialized_paths(tmp_path))

    assert config.schema_version == 3
    assert config.sensitive_storage == "disabled"
    assert config.recall.overview_token_budget == 250
    assert config.recall.compact_card_token_budget == 600
    assert config.recall.default_lifecycle == "active"
    assert config.capture.enabled is False
    assert config.capture.mode == "off"
    assert config.capture.paused is False
    assert config.capture.include_subagents is False
    assert config.capture.sources == ()
    assert config.capture.hook.enabled is False
    assert config.capture.runner.concurrency == 1
    assert config.capture.runner.max_attempts == 5
    assert config.capture.runner.backoff_seconds == (60, 300, 1800, 7200, 21600)
    assert config.capture.capsule.target_tokens == 1200
    assert config.capture.capsule.max_tokens == 3000
    assert config.capture.budgets.backfill_window_days == 7
    assert config.capture.budgets.backfill_total_tokens == 100000
    assert config.capture.budgets.incremental_total_tokens is None
    assert config.capture.extractor.kind == "codex_exec"
    assert config.capture.extractor.executable == "codex"
    assert config.capture.extractor.model is None
    assert config.capture.exclude.task_ids == ()
    assert config.capture.exclude.project_ids == ()


@pytest.mark.parametrize(
    ("replacement", "message"),
    [
        ("unknown_key: true\n", "unknown runtime config field: unknown_key"),
        ("overview_token_budget: invalid", "recall.overview_token_budget must be a positive integer"),
        ("enabled: true", "capture.enabled must be false while capture is unavailable"),
        ("mode: runner", "capture.mode must be off while capture is unavailable"),
    ],
)
def test_load_runtime_config_rejects_unknown_invalid_and_unsafe_values(
    tmp_path: Path, replacement: str, message: str
):
    paths = initialized_paths(tmp_path)
    text = (paths.root / "config.yaml").read_text(encoding="utf-8")
    if replacement.startswith("unknown_key"):
        text += replacement
    elif replacement.startswith("overview_token_budget"):
        text = text.replace("overview_token_budget: 250", replacement)
    else:
        key, value = replacement.split(": ", 1)
        text = text.replace(f"{key}: false" if key == "enabled" else f"{key}: off", replacement)
    atomic_write_text(paths.root / "config.yaml", text)

    with pytest.raises(ValueError, match=message):
        load_runtime_config(paths)


@pytest.mark.parametrize(
    ("duplicate", "key"),
    [
        ("schema_version: 3\n", "schema_version"),
        ("  overview_token_budget: 251\n", "overview_token_budget"),
        ("    concurrency: 2\n", "concurrency"),
    ],
)
def test_load_runtime_config_rejects_duplicate_keys_at_every_depth(
    tmp_path: Path, duplicate: str, key: str
):
    paths = initialized_paths(tmp_path)
    config_file = paths.root / "config.yaml"
    text = config_file.read_text(encoding="utf-8")
    if key == "schema_version":
        text = duplicate + text
    elif key == "overview_token_budget":
        text = text.replace(
            "  compact_card_token_budget",
            duplicate + "  compact_card_token_budget",
        )
    else:
        text = text.replace("    max_attempts", duplicate + "    max_attempts")
    atomic_write_text(config_file, text)

    with pytest.raises(ValueError, match=f"duplicate YAML key: {key}"):
        load_runtime_config(paths)


def test_runtime_loader_does_not_change_pyyaml_safe_loader():
    assert yaml.safe_load("value: off\n") == {"value": False}


def test_installed_default_and_template_are_byte_identical():
    package_default = Path(__file__).parents[1] / "agc_runtime" / "default_config.yaml"
    template = Path(__file__).parents[1] / "templates" / "memory" / "config.yaml"

    assert package_default.read_bytes() == template.read_bytes()


def test_admin_validate_parses_valid_non_default_config(tmp_path: Path):
    paths = initialized_paths(tmp_path)
    config_file = paths.root / "config.yaml"
    atomic_write_text(
        config_file,
        config_file.read_text(encoding="utf-8").replace(
            "overview_token_budget: 250", "overview_token_budget: 251"
        ),
    )

    assert dispatch_admin(paths, {"action": "validate"}).status == "accepted"


def test_built_wheel_contains_default_and_installed_admin_init_works(tmp_path: Path):
    repository = Path(__file__).parents[1]
    wheel_dir = tmp_path / "wheel"
    build = subprocess.run(
        [
            sys.executable,
            "-m",
            "build",
            "--wheel",
            "--outdir",
            str(wheel_dir),
        ],
        cwd=repository,
        capture_output=True,
        text=True,
        check=False,
    )
    assert build.returncode == 0, build.stdout + build.stderr
    wheel = next(wheel_dir.glob("*.whl"))
    with zipfile.ZipFile(wheel) as archive:
        assert "agc_runtime/default_config.yaml" in archive.namelist()

    install_dir = tmp_path / "installed"
    install = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--no-deps",
            "--target",
            str(install_dir),
            str(wheel),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert install.returncode == 0, install.stdout + install.stderr

    memory_root = tmp_path / "memory"
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(install_dir)
    environment["PYTHONNOUSERSITE"] = "1"
    initialized = subprocess.run(
        [
            sys.executable,
            "-m",
            "agc_runtime.cli",
            "admin",
            "--root",
            str(memory_root),
            "--input",
            "-",
        ],
        cwd=tmp_path,
        env=environment,
        input=json.dumps({"action": "init"}),
        capture_output=True,
        text=True,
        check=False,
    )

    assert initialized.returncode == 0, initialized.stdout + initialized.stderr
    assert json.loads(initialized.stdout)["status"] == "accepted"
    assert (memory_root / "config.yaml").read_bytes() == (
        install_dir / "agc_runtime" / "default_config.yaml"
    ).read_bytes()
