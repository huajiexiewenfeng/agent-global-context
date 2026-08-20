from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import sys

import pytest

from agc_runtime.paths import MemoryPaths
import tests.test_capture_scanner as scanner_fixtures
from tests.test_capture_scanner import _revision


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
NOW = "2026-08-13T12:00:00Z"


@pytest.fixture(scope="module", autouse=True)
def _load_and_unload_deferred_backfill_modules():
    global BackfillPreparation, CapabilityProbe, EXTRACTOR_SCHEMA_VERSION
    global EXTRACTOR_VERSION, ExtractorDescriptor, TAXONOMY_VERSION
    global authorization_digest_for, prepare_backfill, root_fingerprint

    before = set(sys.modules)
    from agc_runtime.capture_backfill import (
        BackfillPreparation as _BackfillPreparation,
        authorization_digest_for as _authorization_digest_for,
        prepare_backfill as _prepare_backfill,
    )
    from agc_runtime.capture_extractor import (
        EXTRACTOR_SCHEMA_VERSION as _EXTRACTOR_SCHEMA_VERSION,
        EXTRACTOR_VERSION as _EXTRACTOR_VERSION,
        TAXONOMY_VERSION as _TAXONOMY_VERSION,
        CapabilityProbe as _CapabilityProbe,
        ExtractorDescriptor as _ExtractorDescriptor,
    )
    from agc_runtime.capture_store import root_fingerprint as _root_fingerprint

    BackfillPreparation = _BackfillPreparation
    authorization_digest_for = _authorization_digest_for
    prepare_backfill = _prepare_backfill
    root_fingerprint = _root_fingerprint
    CapabilityProbe = _CapabilityProbe
    ExtractorDescriptor = _ExtractorDescriptor
    EXTRACTOR_SCHEMA_VERSION = _EXTRACTOR_SCHEMA_VERSION
    EXTRACTOR_VERSION = _EXTRACTOR_VERSION
    TAXONOMY_VERSION = _TAXONOMY_VERSION
    yield
    for name in set(sys.modules) - before:
        if name.startswith("agc_runtime.capture_") or name in {
            "agc_runtime.codex_source_adapter",
            "agc_runtime.codex_extractor",
            "agc_runtime.project_identity",
        }:
            sys.modules.pop(name, None)


def _adapter() -> object:
    from agc_runtime.capture_source import (
        AdapterDescriptor,
        DiscoveryBatch,
        ScanHint,
        SourceBindingKey,
        SourceProbe,
    )

    scanner_fixtures.AdapterDescriptor = AdapterDescriptor
    scanner_fixtures.DiscoveryBatch = DiscoveryBatch
    scanner_fixtures.ScanHint = ScanHint
    scanner_fixtures.SourceBindingKey = SourceBindingKey
    scanner_fixtures.SourceProbe = SourceProbe
    return scanner_fixtures.SyntheticAdapter((_revision("ready"),))


@dataclass
class FakeExtractor:
    extract_calls: int = 0
    probe_calls: int = 0

    def describe(self) -> ExtractorDescriptor:
        return ExtractorDescriptor(
            "codex", EXTRACTOR_VERSION, EXTRACTOR_SCHEMA_VERSION, TAXONOMY_VERSION
        )

    def probe_capabilities(self) -> CapabilityProbe:
        self.probe_calls += 1
        return CapabilityProbe(
            True,
            "a" * 64,
            "1",
            "gpt-5",
            "openai",
            True,
            True,
            True,
            None,
        )

    def extract(self, capsule: object, reservation: object) -> object:
        del capsule, reservation
        self.extract_calls += 1
        raise AssertionError("prepare-backfill must not extract")


def _write_config(memory_root: Path, source_root: Path, *, total: int = 100_000) -> None:
    memory_root.mkdir(parents=True, exist_ok=True)
    default = (REPOSITORY_ROOT / "agc_runtime" / "default_config.yaml").read_text(
        encoding="utf-8"
    )
    configured = (
        default.replace("enabled: false", "enabled: true", 1)
        .replace("mode: off", "mode: scanner_only", 1)
        .replace("sources: []", f"sources:\n    - {source_root.as_posix()}", 1)
        .replace("backfill_total_tokens: 100000", f"backfill_total_tokens: {total}", 1)
    )
    (memory_root / "config.yaml").write_text(configured, encoding="utf-8")


def test_prepare_backfill_scans_probes_and_never_extracts(tmp_path: Path) -> None:
    memory_root = tmp_path / "memory"
    source_root = tmp_path / "source"
    source_root.mkdir()
    _write_config(memory_root, source_root)
    paths = MemoryPaths.from_root(memory_root)
    adapter = _adapter()
    extractor = FakeExtractor()

    preparation = prepare_backfill(
        paths=paths,
        adapters=(adapter,),
        extractor=extractor,
        now=NOW,
    )

    assert isinstance(preparation, BackfillPreparation)
    assert adapter.discover_count == 1
    assert extractor.probe_calls == 1
    assert extractor.extract_calls == 0
    assert preparation.memory_root_fingerprint == root_fingerprint(paths)
    assert preparation.frozen_revision_count == 1
    assert preparation.ready_revision_count == 1
    assert preparation.backfill_total_tokens == 100_000
    assert preparation.charged_tokens == 0
    assert preparation.remaining_tokens == 100_000
    assert len(preparation.authorization_digest) == 64
    encoded = json.dumps(preparation.to_mapping(), sort_keys=True)
    assert str(source_root) not in encoded
    assert "sessions/" not in encoded


def test_prepare_backfill_is_deterministic_for_exact_replay(tmp_path: Path) -> None:
    memory_root = tmp_path / "memory"
    source_root = tmp_path / "source"
    source_root.mkdir()
    _write_config(memory_root, source_root)
    paths = MemoryPaths.from_root(memory_root)
    adapter = _adapter()
    extractor = FakeExtractor()

    first = prepare_backfill(
        paths=paths, adapters=(adapter,), extractor=extractor, now=NOW
    )
    second = prepare_backfill(
        paths=paths, adapters=(adapter,), extractor=extractor, now=NOW
    )

    assert first.authorization_digest == second.authorization_digest
    assert first.census_id == second.census_id
    assert extractor.extract_calls == 0


@pytest.mark.parametrize(
    "field",
    (
        "memory_root_fingerprint",
        "census_id",
        "source_binding_digest",
        "capture_config_digest",
        "extractor_identity",
        "extractor_version",
        "extractor_schema_version",
        "model_boundary",
        "provider_boundary",
        "backfill_total_tokens",
    ),
)
def test_authorization_digest_binds_every_execution_boundary(field: str) -> None:
    value: dict[str, object] = {
        "memory_root_fingerprint": "a" * 64,
        "census_id": "census-" + "b" * 32,
        "source_binding_digest": "c" * 64,
        "capture_config_digest": "d" * 64,
        "extractor_identity": "e" * 64,
        "extractor_version": "1",
        "extractor_schema_version": "1",
        "model_boundary": "gpt-5",
        "provider_boundary": "openai",
        "backfill_total_tokens": 100_000,
    }
    changed = dict(value)
    changed[field] = 100_001 if field == "backfill_total_tokens" else "changed"

    assert authorization_digest_for(value) != authorization_digest_for(changed)


def test_prepare_backfill_rejects_unavailable_capability_without_extracting(
    tmp_path: Path,
) -> None:
    memory_root = tmp_path / "memory"
    source_root = tmp_path / "source"
    source_root.mkdir()
    _write_config(memory_root, source_root)
    extractor = FakeExtractor()
    extractor.probe_capabilities = lambda: CapabilityProbe.from_mapping(
        {
            "available": False,
            "executable_identity": "",
            "executable_version": "",
            "model_boundary": None,
            "provider_boundary": None,
            "auth_available": False,
            "sandbox_read_only": False,
            "usage_available": False,
            "error": {"stage": "probe", "code": "unavailable", "retryable": False},
        }
    )

    with pytest.raises(RuntimeError, match="capture_extractor_unavailable"):
        prepare_backfill(
            paths=MemoryPaths.from_root(memory_root),
            adapters=(_adapter(),),
            extractor=extractor,
            now=NOW,
        )

    assert extractor.extract_calls == 0


def test_prepare_backfill_cli_form_is_exact_and_content_safe(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from agc_runtime.capture_cli import _parse, main

    root = tmp_path / "memory"
    assert _parse(["prepare-backfill", "--root", str(root)]) == (
        "prepare-backfill",
        root,
        None,
    )
    assert _parse(["prepare-backfill", str(root)]) is None

    exit_code = main(["prepare-backfill", "--root", str(root)])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert output["action"] == "prepare-backfill"
    assert output["error"]["code"] == "capture_disabled"
    assert str(root) not in json.dumps(output)
