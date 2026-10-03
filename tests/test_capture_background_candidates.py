from agc_runtime.capture_runner import CaptureRunner
from agc_runtime.capture_ledger import receipt_for_revision
from agc_runtime.capture_capsule import CapsulePolicy
from tests.test_capture_manual_runner import FakeAdapter, _revision, NOW


def test_background_capsule_loading_is_bounded_and_deterministic():
    revisions = tuple(_revision(f'rev-{i:03}', task_id=f'task-{i:03}') for i in range(100))
    receipts = tuple(receipt_for_revision(r, discovered_at=NOW, status='discovered', exclusion_reason=None) for r in revisions)
    results = []
    for ordered in (receipts, tuple(reversed(receipts))):
        adapter = FakeAdapter(revisions=revisions)
        descriptor = adapter.describe()
        selected = CaptureRunner._ranked_ready_receipts(
            ordered, {r.key: r for r in revisions},
            {(descriptor.adapter_id, descriptor.source_root_id): adapter},
            CapsulePolicy(target_token_limit=1200, hard_token_limit=3000),
            max_items=1, candidate_limit=32,
        )
        assert adapter.load_calls == 32
        assert len(selected) == 1
        assert len(receipts) == 100  # no receipt is consumed by candidate selection
        results.append(selected[0].receipt.receipt_id)
    assert results[0] == results[1]
