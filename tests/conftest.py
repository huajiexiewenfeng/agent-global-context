import json
import subprocess
import sys
from pathlib import Path

import pytest

from agc_runtime.capture_contracts import (
    CaptureKey,
    CaptureReceipt,
    CollectedObservation,
    TokenUsage,
    observation_fingerprint_for,
    observation_id_for,
    receipt_id_for,
)
from agc_runtime.capture_store import CaptureStore
from agc_runtime.paths import MemoryPaths


@pytest.fixture
def run_cli():
    def invoke(*args: str, stdin: str = "") -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "agc_runtime.cli", *args],
            input=stdin,
            text=True,
            capture_output=True,
            check=False,
        )

    return invoke


@pytest.fixture
def cli(run_cli):
    def invoke(tool: str, root: Path, payload: dict) -> dict:
        result = run_cli(
            tool,
            "--root",
            str(root),
            "--input",
            "-",
            stdin=json.dumps(payload, ensure_ascii=False),
        )
        assert result.returncode == 0, result.stderr or result.stdout
        return json.loads(result.stdout)

    return invoke


@pytest.fixture
def visible_capture_observations():
    def create(paths: MemoryPaths, statements: list[str]):
        if not 1 <= len(statements) <= 8:
            raise ValueError("test factory supports one Capture extraction batch")
        now = "2026-08-23T12:00:00Z"
        key = CaptureKey("synthetic_adapter", "1" * 64, "review-task", "review-revision")
        base = {
            "schema_version": 1,
            "receipt_id": receipt_id_for(key),
            **key.to_mapping(),
            "adapter_version": "1",
            "source_schema_version": "1",
            "identity_quality": "session_id",
            "source_fingerprint": "a" * 64,
            "source_hash_schema_version": "source-v1",
            "capsule_hash": "b" * 64,
            "capsule_schema_version": "capsule-v1",
            "settled_at": now,
            "discovered_at": now,
            "updated_at": now,
            "status": "extracting",
            "attempt_count": 1,
            "next_retry_at": None,
            "extractor_id": "synthetic_extractor",
            "extractor_version": "1",
            "extractor_schema_version": "1",
            "taxonomy_version": "taxonomy-v1",
            "observation_count": None,
            "filtered_counts": None,
            "duplicate_suppression_count": None,
            "token_usage": TokenUsage(1, 1, 2).to_mapping(),
            "usage_quality": "actual",
            "redacted_by_forget": False,
            "forgotten_observation_count": 0,
            "zero_reason": None,
            "sanitized_error": None,
            "coalesced_to": None,
            "exclusion_reason": None,
        }
        receipt = CaptureReceipt.from_mapping(base)
        observations = []
        for ordinal, statement in enumerate(statements):
            value = {
                "schema_version": 1,
                "observation_id": "co_" + "0" * 64,
                "receipt_id": receipt.receipt_id,
                "source": {**key.to_mapping(), "locator": "sessions/review.jsonl"},
                "ordinal": ordinal,
                "observation_fingerprint": "0" * 64,
                "statement": statement,
                "assertion": {"subject": "user", "mode": "direct", "modality": "asserted"},
                "primary_category": "work",
                "taxonomy_version": "taxonomy-v1",
                "kind": "preference",
                "scopes": ["testing"],
                "project_scope": None,
                "confidence": "observed",
                "sensitivity": "normal",
                "signal_type": "decision_or_constraint",
                "observed_at": now,
                "captured_at": now,
                "extractor_version": "1",
                "processing_state": "collected",
            }
            value["observation_fingerprint"] = observation_fingerprint_for(value)
            value["observation_id"] = observation_id_for(
                receipt.receipt_id, value["observation_fingerprint"]
            )
            observations.append(CollectedObservation.from_mapping(value))
        terminal = CaptureReceipt.from_mapping(
            {
                **base,
                "status": "complete",
                "observation_count": len(observations),
                "filtered_counts": {"safety": 0, "policy": 0, "over_limit": 0},
                "duplicate_suppression_count": 0,
            }
        )
        store = CaptureStore(paths, clock=lambda: now)
        store.register_extraction(receipt)
        lease = store.acquire_lease(key, owner_id="review-worker", now=now, ttl_seconds=60)
        assert lease is not None
        store.commit_extraction(lease, tuple(observations), terminal)
        return store, tuple(observations)

    return create
