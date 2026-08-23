from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CapturePaths:
    root: Path
    schema_version: Path
    cursor_hmac_key: Path
    receipts: Path
    observations: Path
    reviews: Path
    ledger: Path
    census: Path
    census_catalog: Path
    tombstones: Path
    quarantines: Path
    conflicts: Path
    dirty: Path
    journals: Path
    staging: Path
    leases: Path
    indexes: Path
    scan_state: Path
    budgets: Path

    @classmethod
    def from_runtime(cls, runtime: Path) -> "CapturePaths":
        root = runtime / "capture"
        return cls(
            root=root, schema_version=root / "schema-version", cursor_hmac_key=root / "cursor-hmac-key",
            receipts=root / "receipts",
            observations=root / "observations", reviews=root / "reviews",
            ledger=root / "ledger", census=root / "census",
            census_catalog=root / "census-catalog",
            tombstones=root / "tombstones", quarantines=root / "quarantines", conflicts=root / "conflicts",
            dirty=root / "dirty", journals=root / "journals", staging=root / "staging",
            leases=root / "leases", indexes=root / "indexes", scan_state=root / "scan-state",
            budgets=root / "budgets",
        )

    def directories(self) -> tuple[Path, ...]:
        return (
            self.receipts, self.observations, self.reviews, self.ledger, self.census,
            self.census_catalog, self.tombstones,
            self.quarantines, self.conflicts, self.dirty, self.journals, self.staging,
            self.leases, self.indexes, self.scan_state, self.budgets,
        )


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
    migrations: Path
    capture: CapturePaths

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
            migrations=runtime / "migrations",
            capture=CapturePaths.from_runtime(runtime),
        )

    def resolve_managed(self, relative_path: str | Path) -> Path:
        target = (self.root / relative_path).resolve()
        if target != self.root and self.root not in target.parents:
            raise ValueError("path is outside memory root")
        return target
