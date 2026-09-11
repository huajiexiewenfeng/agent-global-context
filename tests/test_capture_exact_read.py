"""Exact reads must not pay the global Census validation cost."""

import pytest

from agc_runtime.capture_store import CaptureStore
from agc_runtime.capture_read_service import capture_get
from agc_runtime.capture_transaction import atomic_write_json, read_json
from agc_runtime.paths import MemoryPaths
from agc_runtime.read_service import dispatch_read


def test_exact_read_does_not_build_global_snapshot(tmp_path, visible_capture_observations, monkeypatch):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    _, (observation,) = visible_capture_observations(paths, ["Synthetic preference."])

    def forbidden(*args, **kwargs):
        pytest.fail("exact read must not scan Census or all receipts")

    monkeypatch.setattr(CaptureStore, "read_snapshot", forbidden)
    assert capture_get(paths, {"observation_id": observation.observation_id})["observation"]["statement"] == observation.statement
    assert len(capture_get(paths, {"receipt_id": observation.receipt_id})["observations"]) == 1


@pytest.mark.parametrize("corrupt", ["ledger", "review", "member", "count"])
def test_exact_read_rejects_corrupt_binding(tmp_path, visible_capture_observations, corrupt):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    _, observations = visible_capture_observations(paths, ["Synthetic first.", "Synthetic second."])
    item = observations[0]
    if corrupt == "ledger":
        path = paths.capture.ledger / (item.receipt_id + ".json")
        data = read_json(path)
        data["status"] = "queued"
    elif corrupt == "review":
        path = paths.capture.reviews / (item.observation_id + ".json")
        data = {"invalid": True}
    elif corrupt == "member":
        path = paths.capture.observations / (item.observation_id + ".json")
        data = {"invalid": True}
    else:
        path = paths.capture.receipts / (item.receipt_id + ".json")
        data = read_json(path)
        data["observation_count"] += 1
    atomic_write_json(path, data)
    result = dispatch_read(paths, {"action": "capture_get", "observation_id": item.observation_id})
    assert result.status == "failed"
    assert result.error["code"] == "capture_integrity_degraded"
    assert "Synthetic" not in str(result.to_dict())


def test_exact_read_after_removal_has_no_cached_content(tmp_path, visible_capture_observations):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    _, (item,) = visible_capture_observations(paths, ["Synthetic removable."])
    capture_get(paths, {"observation_id": item.observation_id})
    (paths.capture.observations / (item.observation_id + ".json")).unlink()
    result = dispatch_read(paths, {"action": "capture_get", "observation_id": item.observation_id})
    assert result.status == "failed"
    assert "Synthetic removable" not in str(result.to_dict())
