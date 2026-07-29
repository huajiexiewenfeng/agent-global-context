from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Status = Literal[
    "accepted",
    "deferred",
    "rejected_policy",
    "needs_adjudication",
    "failed",
]


@dataclass(frozen=True)
class SourceKey:
    ref: str
    revision: str
    content_hash: str

    @property
    def stable_id(self) -> str:
        return f"{self.ref}\x1f{self.revision}\x1f{self.content_hash}"


@dataclass(frozen=True)
class ToolResponse:
    tool: str
    action: str
    status: Status
    data: dict[str, Any] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()
    error: dict[str, str] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["warnings"] = list(self.warnings)
        return {"schema_version": 2, **payload}
