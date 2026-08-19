import json
import os
import shutil
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
        ("enabled: true", "enabled capture.mode must be scanner_only or runner"),
        ("mode: runner", "disabled capture.mode must be off"),
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


def test_capture_config_enforces_mode_source_and_schema_v1_subagent_invariants(tmp_path: Path):
    paths = initialized_paths(tmp_path)
    config_file = paths.root / "config.yaml"
    source = tmp_path / "codex-home"
    source.mkdir()
    base = config_file.read_text(encoding="utf-8")

    enabled = base.replace("enabled: false", "enabled: true").replace(
        "mode: off", "mode: scanner_only"
    ).replace("sources: []", f"sources:\n    - {source.as_posix()}")
    atomic_write_text(config_file, enabled)
    assert load_runtime_config(paths).capture.mode == "scanner_only"

    runner = enabled.replace("mode: scanner_only", "mode: runner")
    atomic_write_text(config_file, runner)
    assert load_runtime_config(paths).capture.mode == "runner"

    invalid_cases = (
        (base.replace("mode: off", "mode: scanner_only"), "disabled capture.mode must be off"),
        (enabled.replace("enabled: true", "enabled: false"), "disabled capture.mode must be off"),
        (enabled.replace("include_subagents: false", "include_subagents: true"), "include_subagents must be false"),
        (enabled.replace(source.as_posix(), "relative/profile"), "absolute directory"),
    )
    for text, message in invalid_cases:
        atomic_write_text(config_file, text)
        with pytest.raises(ValueError, match=message):
            load_runtime_config(paths)


def test_disabled_capture_rejects_lexical_duplicate_sources_without_touching_them(
    tmp_path: Path,
):
    paths = initialized_paths(tmp_path)
    config_file = paths.root / "config.yaml"
    source = tmp_path / "does-not-need-to-exist"
    configured = config_file.read_text(encoding="utf-8").replace(
        "sources: []",
        f"sources:\n    - {source.as_posix()}\n    - {str(source).upper()}",
    )
    atomic_write_text(config_file, configured)

    with pytest.raises(ValueError, match="duplicate roots"):
        load_runtime_config(paths)

    assert not source.exists()


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
    repository_artifacts_before = {
        path.relative_to(repository): (path.stat().st_mtime_ns, path.stat().st_size)
        for pattern in ("build/**/*", "dist/**/*", "*.egg-info/**/*")
        for path in repository.glob(pattern)
        if path.is_file()
    }
    source = tmp_path / "source"
    excluded = {
        "build",
        "dist",
        ".venv",
        ".git",
        ".pytest_cache",
        "__pycache__",
    }
    shutil.copytree(
        repository,
        source,
        ignore=lambda _directory, names: [
            name
            for name in names
            if name in excluded or name.endswith(".egg-info")
        ],
    )
    assert not (source / "build").exists()
    assert not (source / "dist").exists()
    assert not (source / ".venv").exists()
    assert not list(source.glob("*.egg-info"))

    wheel_dir = tmp_path / "wheel"
    environment = os.environ.copy()
    environment.update(
        {
            "PIP_NO_INDEX": "1",
            "PIP_DISABLE_PIP_VERSION_CHECK": "1",
            "PIP_NO_INPUT": "1",
        }
    )
    backend = subprocess.run(
        [
            sys.executable,
            "-c",
            "import setuptools.build_meta, wheel; print('offline backend ready')",
        ],
        cwd=source,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert backend.returncode == 0, backend.stdout + backend.stderr
    assert backend.stdout.strip() == "offline backend ready"
    build = subprocess.run(
        [
            sys.executable,
            "-m",
            "build",
            "--wheel",
            "--no-isolation",
            "--outdir",
            str(wheel_dir),
        ],
        cwd=source,
        env=environment,
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
    source_modules = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import json; "
                "import agc_runtime.capture_source as source; "
                "import agc_runtime.project_identity as identity; "
                "print(json.dumps({'source': source.__file__, 'identity': identity.__file__}))"
            ),
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert source_modules.returncode == 0, source_modules.stdout + source_modules.stderr
    module_paths = json.loads(source_modules.stdout)
    for module_path in module_paths.values():
        assert Path(module_path).resolve().is_relative_to(install_dir.resolve())
    repository_artifacts_after = {
        path.relative_to(repository): (path.stat().st_mtime_ns, path.stat().st_size)
        for pattern in ("build/**/*", "dist/**/*", "*.egg-info/**/*")
        for path in repository.glob(pattern)
        if path.is_file()
    }
    assert repository_artifacts_after == repository_artifacts_before
