from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from agc_runtime import admin_service, managed_backup
from agc_runtime.admin_service import dispatch_admin
from agc_runtime.paths import MemoryPaths


def test_production_scale_archive_round_trip(tmp_path: Path):
    # More than the observed primary + unique-Census archive population;
    # realistic path lengths also cross the former 1 MiB manifest ceiling.
    files = [
        (f"contexts/evidence-{index:064x}.json", f'{{"ordinal":{index}}}\n'.encode())
        for index in range(24000)
    ]
    value = managed_backup.manifest(files)
    encoded_manifest = json.dumps(value, indent=2).encode()
    assert len(encoded_manifest) > 1024 * 1024
    archive = tmp_path / "large.zip"
    archive.write_bytes(managed_backup.archive_bytes(files, value))

    restored, restored_manifest = managed_backup.read_verified_archive(archive)

    assert restored == dict(files)
    assert restored_manifest == value


def test_production_scale_archive_restores_through_admin(tmp_path: Path):
    source = MemoryPaths.from_root(tmp_path / "source")
    assert dispatch_admin(source, {"action": "init"}).status == "accepted"
    files = managed_backup.backup_files(source)
    extra = [
        (f"contexts/item-{index:064x}.txt", f"Bounded synthetic evidence {index}\n".encode())
        for index in range(5000)
    ]
    files.extend(extra)
    archive = tmp_path / "restore-large.zip"
    archive.write_bytes(managed_backup.archive_bytes(files, managed_backup.manifest(files)))
    target = MemoryPaths.from_root(tmp_path / "restored")

    response = dispatch_admin(target, {"action": "restore", "backup_path": str(archive)})

    assert response.status == "accepted", response
    assert all((target.root / name).read_bytes() == data for name, data in extra)
    assert dispatch_admin(target, {"action": "validate"}).status == "accepted"


@pytest.mark.parametrize("excluded", ["capture", "backups", "locks"])
def test_strict_decode_prunes_excluded_subtrees_before_scan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, excluded: str,
):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    ignored = paths.root / ".runtime" / excluded
    (ignored / "nested").mkdir(parents=True)
    (ignored / "nested" / "ignored.bin").write_bytes(b"\xff\x80")
    paths.contexts.mkdir(parents=True)
    bad_text = paths.contexts / "invalid.txt"
    bad_text.write_bytes(b"\xff")
    unsupported = paths.contexts / "retained.bin"
    unsupported.write_bytes(b"binary")
    paths.contexts.joinpath("transient.tmp").write_bytes(b"\xff")
    real_scandir = os.scandir
    real_is_file = Path.is_file

    def forbid_excluded_scan(path):
        if Path(path).is_relative_to(ignored):
            raise AssertionError("generic UTF-8 pass descended into an excluded subtree")
        return real_scandir(path)

    def forbid_excluded_stat(path: Path, *args, **kwargs):
        # pathlib's glob implementation can retain its own scandir reference.
        if path != ignored and path.is_relative_to(ignored):
            raise AssertionError("generic UTF-8 pass inspected an excluded descendant")
        return real_is_file(path, *args, **kwargs)

    monkeypatch.setattr(os, "scandir", forbid_excluded_scan)
    monkeypatch.setattr(Path, "is_file", forbid_excluded_stat)
    issues: list[dict[str, str]] = []
    admin_service._strict_decode_managed(paths, issues)

    assert {item["path"] for item in issues} == {str(bad_text), str(unsupported)}
    assert any("invalid UTF-8" in item["message"] for item in issues)
    assert any("unsupported binary" in item["message"] for item in issues)


def test_production_scale_keeps_existing_payload_guards():
    assert managed_backup._MAX_FILE_SIZE == 16 * 1024 * 1024
    assert managed_backup._MAX_TOTAL_SIZE == 64 * 1024 * 1024
    assert managed_backup._MAX_COMPRESSION_RATIO == 200
    assert 24000 <= managed_backup._MAX_ARCHIVE_FILES <= 32768
    assert managed_backup._MAX_MANIFEST_SIZE <= 8 * 1024 * 1024


@pytest.mark.parametrize(
    "relative", ["census/oversized.json", "census-runs/run-cold/members/oversized.json"]
)
def test_production_scale_still_rejects_oversize_cold_census(tmp_path: Path, relative: str):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    oversized = paths.capture.root / relative
    oversized.parent.mkdir(parents=True)
    with oversized.open("wb") as stream:
        stream.truncate(managed_backup._MAX_FILE_SIZE + 1)

    with pytest.raises(ValueError, match="file size.*limit"):
        managed_backup.backup_files(paths)
