from pathlib import Path

import pytest

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
    assert config.capture.hook.enabled is False


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
