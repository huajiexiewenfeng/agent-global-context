from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MemoryPaths:
    root: Path
    catalog_md: Path
    catalog_json: Path
    memories: Path
    contexts: Path
    candidates: Path
    events: Path
    archive: Path
    queue: Path
    receipts: Path
    locks: Path
    cache: Path
    backups: Path
    tombstones: Path

    @classmethod
    def from_root(cls, root: Path) -> "MemoryPaths":
        resolved = root.resolve()
        runtime = resolved / ".runtime"
        return cls(
            root=resolved,
            catalog_md=resolved / "catalog.md",
            catalog_json=resolved / "catalog.json",
            memories=resolved / "memories",
            contexts=resolved / "contexts",
            candidates=resolved / "candidates",
            events=resolved / "events",
            archive=resolved / "archive",
            queue=runtime / "queue",
            receipts=runtime / "receipts",
            locks=runtime / "locks",
            cache=runtime / "cache",
            backups=runtime / "backups",
            tombstones=runtime / "tombstones",
        )

    def resolve_managed(self, relative_path: str | Path) -> Path:
        target = (self.root / relative_path).resolve()
        if target != self.root and self.root not in target.parents:
            raise ValueError("path is outside memory root")
        return target
