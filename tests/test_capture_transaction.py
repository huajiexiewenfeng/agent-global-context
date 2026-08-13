from __future__ import annotations

from pathlib import Path

import pytest

from agc_runtime.capture_store import CaptureStore
from tests.test_capture_store import _complete_receipt, _key, _observation, _receipt
from agc_runtime.paths import MemoryPaths


@pytest.mark.parametrize(
    "crash_point",
    [
        f"{side}:{point}"
        for point in ("journal", "stage", "observation:0", "observation:1", "ledger", "receipt", "cleanup")
        for side in ("before", "after")
    ],
)
def test_ac_09_crash_recovery_never_exposes_partial_or_duplicate_batches(
    tmp_path: Path, crash_point: str
):
    store = CaptureStore(
        MemoryPaths.from_root(tmp_path / "memory"), crash_at=crash_point,
        clock=lambda: "2026-08-13T12:00:00Z",
    )
    receipt = _receipt()
    store.register_extraction(receipt)
    lease = store.acquire_lease(_key(), owner_id="worker", now="2026-08-13T12:00:00Z", ttl_seconds=60)
    assert lease is not None
    observations = (_observation("User prefers crash-safe commits.", 0), _observation("User values retryable transactions.", 1))
    with pytest.raises(RuntimeError, match="injected crash"):
        store.commit_extraction(lease, observations, _complete_receipt(receipt, 2))

    recovered = CaptureStore(MemoryPaths.from_root(tmp_path / "memory"))
    report = recovered.recover_transactions(now="2026-08-13T12:01:30Z")
    visible = recovered.visible_observations(receipt.receipt_id)
    current = recovered.read_receipt(receipt.receipt_id)
    assert len(visible) in {0, 2}
    assert (current.status == "complete") == (len(visible) == 2)
    if not visible:
        assert current.status == "retryable"
    assert report.orphan_count == report.partial_count == report.duplicate_count == 0
