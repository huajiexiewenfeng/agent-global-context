"""Content-free terminal review receipts for Capture observations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
from typing import Any

from agc_runtime.models import MemoryItem


MAX_REVIEW_OBSERVATIONS = 20
REVIEW_OUTCOMES = frozenset({"draft", "needs_context", "discard"})
_OBSERVATION_ID = re.compile(r"^co_[0-9a-f]{64}$")
_MEMORY_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,79}$")
_DANGLING_REFERENCES = (
    "该 skill",
    "该技能",
    "这个方案",
    "上述方案",
    "上面的设置",
    "最终目标保持不变",
)


def _utc(value: Any) -> str:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("reviewed_at must be an RFC 3339 UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise ValueError("reviewed_at must be an RFC 3339 UTC timestamp") from error
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise ValueError("reviewed_at must be an RFC 3339 UTC timestamp")
    return value


def parse_capture_observation_ids(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list) or not 1 <= len(value) <= MAX_REVIEW_OBSERVATIONS:
        raise ValueError("capture_observation_ids must contain between 1 and 20 items")
    if any(
        not isinstance(item, str) or not _OBSERVATION_ID.fullmatch(item)
        for item in value
    ):
        raise ValueError("capture_observation_ids must contain canonical observation ids")
    if len(value) != len(set(value)):
        raise ValueError("capture_observation_ids must not contain duplicates")
    return tuple(value)


@dataclass(frozen=True)
class CaptureReviewReceipt:
    schema_version: int
    observation_id: str
    outcome: str
    target_memory_id: str | None
    reviewed_at: str

    @classmethod
    def from_mapping(cls, value: Any) -> "CaptureReviewReceipt":
        fields = {
            "schema_version",
            "observation_id",
            "outcome",
            "target_memory_id",
            "reviewed_at",
        }
        if not isinstance(value, dict) or set(value) != fields:
            raise ValueError("CaptureReviewReceipt must contain the exact fields")
        if type(value["schema_version"]) is not int or value["schema_version"] != 1:
            raise ValueError("CaptureReviewReceipt.schema_version must be 1")
        observation_id = parse_capture_observation_ids([value["observation_id"]])[0]
        outcome = value["outcome"]
        if outcome not in REVIEW_OUTCOMES:
            raise ValueError("CaptureReviewReceipt.outcome is unsupported")
        target = value["target_memory_id"]
        if outcome == "draft":
            if not isinstance(target, str) or not _MEMORY_ID.fullmatch(target):
                raise ValueError("draft review receipt requires target_memory_id")
        elif target is not None:
            raise ValueError("non-draft review receipt forbids target_memory_id")
        return cls(1, observation_id, outcome, target, _utc(value["reviewed_at"]))

    def _to_mapping_unchecked(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "observation_id": self.observation_id,
            "outcome": self.outcome,
            "target_memory_id": self.target_memory_id,
            "reviewed_at": self.reviewed_at,
        }

    def to_mapping(self) -> dict[str, Any]:
        return CaptureReviewReceipt.from_mapping(
            self._to_mapping_unchecked()
        )._to_mapping_unchecked()


def validate_formalization_item(item: MemoryItem) -> None:
    if not isinstance(item, MemoryItem):
        raise ValueError("formalization item must be a MemoryItem")
    body = "\n".join(
        (item.memory_card, item.full_meaning, item.application_boundary, item.rationale)
    )
    folded = body.casefold()
    found = next(
        (phrase for phrase in _DANGLING_REFERENCES if phrase.casefold() in folded),
        None,
    )
    if found is not None:
        raise ValueError(f"formalization memory contains dangling reference: {found}")
