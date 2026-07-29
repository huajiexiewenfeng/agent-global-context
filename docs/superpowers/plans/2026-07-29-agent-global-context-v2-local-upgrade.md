# Agent Global Context v2 Local Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the locally active alpha AGC with one thin v2 Skill, three Codex-visible Runtime tools, a deterministic parallel v1 migration, and a verified local cutover.

**Architecture:** The existing deterministic Runtime remains the only data engine. A tiny FastMCP stdio adapter binds one configured memory root and forwards exactly three tools; one public Skill tells the LLM when to use them without injecting personal facts. Migration accepts an LLM-authored semantic plan, builds a separate v2 root, snapshots only approved normal/personal v1 sources, records content-free exclusions, validates the result, and leaves v1 untouched for rollback until the tool root is switched.

**Tech Stack:** Python 3.10+, PyYAML 6.x, official MCP Python SDK 2.0.0, pytest 9.1.1, PowerShell 7/Windows, Markdown, TOML.

## Global Constraints

- The current user instruction and current facts always outrank memory.
- LLM owns semantic relevance, `disposition`, `match_memory_id`, classification, and whether recalled memory is applied.
- Runtime owns deterministic validation, persistence, exact source-key idempotency, lifecycle legality, backup, recovery, and hard forget.
- Only `agc.read`, `agc.write`, and `agc.admin` are exposed to the Agent.
- The static capability hint contains no personal facts and targets at most approximately 80 tokens.
- No P0/P1 rule or Catalog card is injected by default; a task can consume zero personal-memory tokens when the LLM does not call `agc.read`.
- `sensitive_storage` remains fixed to `disabled`; sensitive/secret bodies never enter Memory, Candidate, Event, log, retry data, migration receipt, or repository.
- `agc.read` or normal/personal `agc.write` failure never blocks the main task; the Agent must not claim a failed write succeeded.
- Migration never rewrites v1 in place. Build and validate a separate v2 root, then switch the configured tool root.
- Migration is idempotent and never performs semantic matching inside Runtime.
- All repository and Runtime-managed text is strict UTF-8 without BOM.
- Codex side-channel capture/backfill, Trace/Eval/Loop, and LLM Wiki Runtime remain out of scope.
- Direct development on `main` is explicitly authorized for this change.

---

### Task 1: Thin Skill and Three-Tool MCP Adapter

**Files:**

- Modify: `skills/agent-global-context/SKILL.md`
- Create: `skills/agent-global-context/references/tool-contract.md`
- Create: `skills/agent-global-context/references/application-policy.md`
- Delete: `skills/agent-global-context-recall/SKILL.md`
- Delete: `skills/agent-global-context-capture/SKILL.md`
- Delete: `skills/agent-global-context-review/SKILL.md`
- Delete: `skills/agent-global-context-commit/SKILL.md`
- Create: `agc_runtime/mcp_server.py`
- Modify: `agc_runtime/__init__.py`
- Modify: `pyproject.toml`
- Create: `tests/test_skill_adapter.py`
- Create: `tests/test_mcp_server.py`
- Modify: `tests/test_cli_contract.py`

**Interfaces:**

- Consumes: `dispatch_read(paths, request)`, `dispatch_write(paths, request)`, `dispatch_admin(paths, request)`, `MemoryPaths.from_root(path)`.
- Produces:
  - MCP tools named exactly `agc.read`, `agc.write`, and `agc.admin`.
  - `create_server(memory_root: Path) -> FastMCP`.
  - console entry point `agc-mcp = agc_runtime.mcp_server:main`.
  - Runtime package version `0.2.0`.

- [ ] **Step 1: Preserve the RED Skill baseline**

Use `D:\tmp\agc-skill-red-baseline-report.md` as evidence. The existing Skills fail because they expose five public choices, force P0/P1 file reads, bypass Runtime, lack `adapt|continue|grow`, and lack failure-open behavior.

- [ ] **Step 2: Write failing Skill contract tests**

Create `tests/test_skill_adapter.py` with repository-level assertions:

```python
from pathlib import Path


ROOT = Path(__file__).parents[1]
SKILLS = ROOT / "skills"
PUBLIC = SKILLS / "agent-global-context" / "SKILL.md"


def test_only_one_public_agc_skill_remains():
    names = sorted(path.parent.name for path in SKILLS.glob("agent-global-context*/SKILL.md"))
    assert names == ["agent-global-context"]


def test_capability_hint_is_thin_and_contains_no_personal_fact():
    text = PUBLIC.read_text(encoding="utf-8")
    description = text.split("---", 2)[1]
    assert len(description.split()) <= 80
    assert all(token not in text for token in ("P0", "P1", "index.md"))
    assert all(name in text for name in ("agc.read", "agc.write", "agc.admin"))


def test_skill_preserves_llm_choice_and_failure_open():
    text = PUBLIC.read_text(encoding="utf-8")
    assert "LLM decides" in text
    assert "Do not call" in text
    assert "continue the main task" in text
    assert all(mode in text for mode in ("adapt", "continue", "grow"))
```

- [ ] **Step 3: Run Skill tests and verify RED**

Run:

```powershell
python -m pytest tests/test_skill_adapter.py -q --basetemp D:\tmp\agc-skill-red
```

Expected: FAIL because five public Skills remain and the main Skill still contains P0/P1/index instructions.

- [ ] **Step 4: Write failing MCP adapter tests**

Create `tests/test_mcp_server.py`:

```python
from pathlib import Path

from agc_runtime.admin_service import dispatch_admin
from agc_runtime.mcp_server import create_server
from agc_runtime.paths import MemoryPaths


def test_mcp_exposes_exactly_three_agc_tools(tmp_path: Path):
    root = tmp_path / "memory"
    dispatch_admin(MemoryPaths.from_root(root), {"action": "init"})
    server = create_server(root)
    tools = server._tool_manager.list_tools()
    assert sorted(tools) == ["agc.admin", "agc.read", "agc.write"]


def test_mcp_root_is_bound_by_host_not_llm(tmp_path: Path):
    server = create_server(tmp_path / "memory")
    schemas = {
        name: tool.parameters
        for name, tool in server._tool_manager.list_tools().items()
    }
    assert all("root" not in schema.get("properties", {}) for schema in schemas.values())
```

If the official SDK exposes an async public tool-list API instead of `_tool_manager`, use that public API while preserving the exact assertions.

- [ ] **Step 5: Run MCP tests and verify RED**

Run:

```powershell
python -m pytest tests/test_mcp_server.py -q --basetemp D:\tmp\agc-mcp-red
```

Expected: collection FAIL because `agc_runtime.mcp_server` does not exist.

- [ ] **Step 6: Implement the minimal MCP adapter**

Create `agc_runtime/mcp_server.py`:

```python
import os
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from agc_runtime.admin_service import dispatch_admin
from agc_runtime.paths import MemoryPaths
from agc_runtime.read_service import dispatch_read
from agc_runtime.write_service import dispatch_write


def create_server(memory_root: Path) -> FastMCP:
    paths = MemoryPaths.from_root(memory_root)
    server = FastMCP(
        name="Agent Global Context",
        instructions=(
            "Personal memory is optional. The LLM decides whether it is relevant. "
            "Current instructions win and Runtime failure must not block the main task."
        ),
    )

    @server.tool(name="agc.read")
    def agc_read(request: dict[str, Any]) -> dict[str, Any]:
        """Read optional personal memory progressively; relevance remains an LLM decision."""
        return dispatch_read(paths, request).to_dict()

    @server.tool(name="agc.write")
    def agc_write(request: dict[str, Any]) -> dict[str, Any]:
        """Persist an LLM-authored semantic decision through deterministic policy."""
        return dispatch_write(paths, request).to_dict()

    @server.tool(name="agc.admin")
    def agc_admin(request: dict[str, Any]) -> dict[str, Any]:
        """Validate, review, migrate, back up, restore, or rebuild AGC state."""
        return dispatch_admin(paths, request).to_dict()

    return server


def main() -> None:
    root = os.environ.get("AGC_MEMORY_ROOT")
    if not root:
        raise SystemExit("AGC_MEMORY_ROOT is required")
    create_server(Path(root)).run(transport="stdio")
```

The server must not log request bodies to stdout or add a fourth health/version tool.

- [ ] **Step 7: Replace the public Skill surface**

Keep one short `skills/agent-global-context/SKILL.md`. Its positive contract must state:

1. Personal memory exists but is optional.
2. LLM decides whether memory can materially improve the result.
3. Small/self-contained tasks do not call Recall.
4. Progressive read is `overview → search → get → history/evidence`.
5. Application is exactly `adapt`, `continue`, or guarded `grow`.
6. Explicit durable non-sensitive user changes may call `agc.write`.
7. Current instructions win; failures continue the main task; never claim a failed save.
8. `agc.admin` is for maintenance/migration, not ordinary Recall.

Move detailed tool schemas and application rules to the two reference files. Remove the four companion public Skill packages only after the single-Skill test is in place.

- [ ] **Step 8: Update packaging and version**

Set:

```toml
version = "0.2.0"

[project.optional-dependencies]
mcp = ["mcp==2.0.0"]
test = ["pytest==9.1.1", "build>=1.2,<2", "mcp==2.0.0"]

[project.scripts]
agc = "agc_runtime.cli:main"
agc-mcp = "agc_runtime.mcp_server:main"
```

Set `agc_runtime.__version__` and the CLI contract test to `0.2.0`.

- [ ] **Step 9: Run GREEN tests and a pressure re-test**

Run:

```powershell
python -m pytest tests/test_skill_adapter.py tests/test_mcp_server.py tests/test_cli_contract.py -q --basetemp D:\tmp\agc-task1-green
```

Then dispatch a fresh Skill pressure-test agent with the same A–D scenarios used for RED. It must report:

- A: no Recall;
- B: optional overview first, no forced identity read;
- C: `agc.write` with evolving interest semantics;
- D: main task continues without memory.

- [ ] **Step 10: Commit**

```powershell
git add skills agc_runtime/mcp_server.py agc_runtime/__init__.py pyproject.toml tests/test_skill_adapter.py tests/test_mcp_server.py tests/test_cli_contract.py
git commit -m "feat: add agc v2 skill and mcp adapter"
```

---

### Task 2: Deterministic Parallel v1 Migration and Legacy Forget Scope

**Files:**

- Create: `agc_runtime/migration_service.py`
- Modify: `agc_runtime/paths.py`
- Modify: `agc_runtime/admin_service.py`
- Modify: `agc_runtime/forget_service.py`
- Create: `tests/test_migration_service.py`
- Modify: `tests/test_admin_service.py`
- Modify: `tests/test_forget_service.py`

**Interfaces:**

- Consumes: strict UTF-8 I/O, `MemoryItem.from_markdown`, `validate_memory_item`, `MemoryStore.create_memory`, `rebuild_catalog`, root write lock.
- Produces:
  - `migrate_v1(paths: MemoryPaths, request: dict[str, Any]) -> ToolResponse`.
  - `MemoryPaths.migrations == root/.runtime/migrations`.
  - migration request:

```json
{
  "action": "migrate",
  "migration_id": "v1-20260729",
  "source_root": "<absolute-v1-root>",
  "sources": [
    {
      "path": "user/preferences.md",
      "sha256": "<64-lower-hex>",
      "disposition": "snapshot"
    },
    {
      "path": "staging/rejected.md",
      "sha256": "<64-lower-hex>",
      "disposition": "ignored"
    },
    {
      "path": "opaque/source/ref",
      "sha256": "<64-lower-hex>",
      "disposition": "excluded_sensitive"
    }
  ],
  "memories": [
    {
      "source_path": "user/preferences.md",
      "memory_markdown": "<complete-schema-v2-memory>"
    }
  ]
}
```

- [ ] **Step 1: Replace the deferred migration test with failing contract tests**

Create focused tests proving:

- migration requires a separate source root and rejects `source_root == target root`;
- source paths cannot escape the v1 root;
- every source SHA-256 is verified before writing;
- `snapshot` copies strict UTF-8 normal/personal source bytes into `.runtime/migrations/<id>/snapshot/`;
- `excluded_sensitive` writes only opaque path/hash/disposition metadata and never reads/copies the body into target files;
- `ignored` records metadata but no body;
- every memory is schema-v2-valid and references a declared `snapshot` source;
- Runtime does not derive Memory Items or semantic matches;
- exact request retry is idempotent;
- a different request with the same `migration_id` is rejected;
- Catalog is rebuilt and the final receipt contains counts only.

- [ ] **Step 2: Run migration tests and verify RED**

Run:

```powershell
python -m pytest tests/test_migration_service.py tests/test_admin_service.py::test_migrate_is_explicitly_deferred -q --basetemp D:\tmp\agc-migrate-red
```

Expected: FAIL because `migration_service` does not exist and admin returns `migration_adapter_not_installed`.

- [ ] **Step 3: Add migration paths**

Add `migrations: Path` to `MemoryPaths`, initialized as:

```python
migrations=runtime / "migrations"
```

Include it in managed initialization. Validation must accept migration manifests/snapshots as strict UTF-8 text but continue excluding locks, backups, and temporary files.

- [ ] **Step 4: Implement request validation before persistence**

`migration_service.py` must:

- enforce exact top-level and entry fields;
- require `migration_id` to match the existing safe ID grammar;
- resolve `source_root` and require it differ from `paths.root`;
- resolve every relative source path under `source_root`;
- validate lowercase SHA-256 and compare raw source bytes;
- strict-decode only `snapshot` and `ignored` text sources;
- avoid decoding or copying `excluded_sensitive` bodies after hash verification;
- parse and validate every `memory_markdown` before acquiring the write lock;
- reject target roots that already contain non-migration Memory Items unless the exact completed receipt exists.

- [ ] **Step 5: Implement idempotent migration persistence**

Under one root lock:

1. initialize the empty v2 target if needed;
2. copy `snapshot` sources with `atomic_write_text`;
3. create each Memory Item using unique source ref `migration:v1:<source_path>#<memory_id>`, revision `<migration_id>`, and the verified source SHA;
4. rebuild Catalog;
5. validate the resulting root;
6. write a content-free canonical `manifest.json` containing request digest, source metadata, migrated IDs, counts, source root, and completion status.

On exact retry, return the stored counts. On partial retry, rely on exact source-key idempotency and rebuild before completing the receipt. Never put `memory_markdown` or source bodies in the receipt.

- [ ] **Step 6: Extend hard forget to registered legacy material**

When a confirmed `agc.write forget` matches a migrated Memory ID, use the migration receipt to include:

- the copied v1 snapshot file;
- the registered v1 source file;
- migration metadata referencing that Memory ID;
- ordinary current-root Event, Candidate, Archive, Cache, Receipt, Catalog, and backup copies.

Keep the existing precise authorization and verification-term requirements. Tombstones still contain no original text, content hash, or evidence excerpt. Tests must prove an explicitly forgotten migrated term cannot be found in either the snapshot or registered legacy root, while unrelated v1 content remains.

- [ ] **Step 7: Run focused and full GREEN tests**

Run:

```powershell
python -m pytest tests/test_migration_service.py tests/test_admin_service.py tests/test_forget_service.py -q --basetemp D:\tmp\agc-task2-focused
python -m pytest -q --basetemp D:\tmp\agc-task2-full
```

- [ ] **Step 8: Commit**

```powershell
git add agc_runtime/migration_service.py agc_runtime/paths.py agc_runtime/admin_service.py agc_runtime/forget_service.py tests/test_migration_service.py tests/test_admin_service.py tests/test_forget_service.py
git commit -m "feat: add safe parallel v1 migration"
```

---

### Task 3: Repeatable Local Installer and Codex Registration

**Files:**

- Create: `scripts/install-local.ps1`
- Create: `tests/test_local_install.py`
- Modify: `docs/install.md`
- Modify: `README.md`
- Modify: `README.zh.md`

**Interfaces:**

- Produces PowerShell parameters:

```powershell
param(
  [Parameter(Mandatory=$true)][string]$RepositoryRoot,
  [Parameter(Mandatory=$true)][string]$SkillsRoot,
  [Parameter(Mandatory=$true)][string]$CodexConfig,
  [Parameter(Mandatory=$true)][string]$MemoryRoot,
  [string]$InstallRoot = "$env:USERPROFILE\.agent-global-context-runtime",
  [switch]$SkipRuntimeInstall
)
```

- Installer results:
  - dedicated venv under `<InstallRoot>\venv`;
  - exact MCP executable path in Codex config;
  - one installed public AGC Skill;
  - timestamped backups of config and retired Skill directories;
  - UTF-8/no-BOM writes;
  - idempotent rerun.

- [ ] **Step 1: Write a failing installer integration test**

Use temporary Skills/config/install roots and `-SkipRuntimeInstall` to prove:

- one public Skill is copied;
- four alpha Skill directories are backed up then absent from active Skills;
- a marked `[mcp_servers.agent_global_context]` block is added once;
- rerun replaces only the marked block and does not duplicate it;
- config and copied Markdown are strict UTF-8 without BOM;
- unrelated config text is byte-for-byte preserved after newline normalization.

- [ ] **Step 2: Run installer test and verify RED**

Run:

```powershell
python -m pytest tests/test_local_install.py -q --basetemp D:\tmp\agc-install-red
```

Expected: FAIL because `scripts/install-local.ps1` does not exist.

- [ ] **Step 3: Implement safe installation**

The script must:

1. resolve all paths and reject missing repository/Skill/config inputs;
2. create a timestamped backup before modifying active Skills or config;
3. create `<InstallRoot>\venv` and install `"<RepositoryRoot>[mcp]"` unless skipped;
4. copy only `skills\agent-global-context` to the active Skills root;
5. move the four retired alpha Skill directories into the timestamped backup;
6. write a launcher under `<InstallRoot>\bin`;
7. insert or replace this exact marked TOML block:

```toml
# BEGIN agent-global-context
[mcp_servers.agent_global_context]
enabled = true
command = "<absolute-agc-mcp-executable>"
args = []

[mcp_servers.agent_global_context.env]
AGC_MEMORY_ROOT = "<absolute-v2-memory-root>"
# END agent-global-context
```

8. use strict UTF-8 without BOM for all writes;
9. print a JSON result containing paths and `restart_required: true`, without personal memory.

- [ ] **Step 4: Document deployment boundaries**

Document that:

- Runtime is independent and MCP is an optional Host Adapter;
- a Codex restart/new task is required after MCP registration;
- the active tool root can be a parallel `~/.agent-global-context-v2`;
- v1 remains read-only rollback material until a later explicit retirement;
- Codex capture/backfill remains disabled.

- [ ] **Step 5: Run GREEN tests**

Run:

```powershell
python -m pytest tests/test_local_install.py -q --basetemp D:\tmp\agc-task3-green
```

- [ ] **Step 6: Commit**

```powershell
git add scripts/install-local.ps1 tests/test_local_install.py docs/install.md README.md README.zh.md
git commit -m "feat: add repeatable local agc installer"
```

---

### Task 4: Migrate and Cut Over the Actual Local AGC

**Files:**

- Do not commit personal migration payloads.
- Update: `.llm-wiki/requirements/agc-v2-local-upgrade.md`
- Update: `.llm-wiki/working-context/agc-v2-local-upgrade.md`
- Create: `.llm-wiki/verification/agc-v2-local-upgrade.md`
- Create: `.llm-wiki/handoff/agc-v2-local-upgrade-handoff.md`
- Update: `.llm-wiki/artifacts/index.md`

**Local paths:**

- v1 source: `C:\Users\admin\.agent-global-context`
- parallel v2 target: `C:\Users\admin\.agent-global-context-v2`
- Runtime install: `C:\Users\admin\.agent-global-context-runtime`
- active Skill root: `C:\Users\admin\.agents\skills`
- active Codex config: `C:\Users\admin\.codex-clean-20260710\config.toml`

- [ ] **Step 1: Build the LLM-authored migration request in memory**

Use the redacted inventory report at `D:\tmp\agc-v1-migration-inventory-report.md` plus strict reads of only the approved normal/personal sources. Produce complete v2 `MemoryItem` Markdown for:

- durable principles and collaboration/writing preferences;
- evolving AI/Agent/LLM interests;
- professional capabilities and current role with scoped recall;
- explicit active goals only when confirmed;
- project/environment context only when it changes future work.

Do not persist the migration request to the repository. Exclude templates, empty examples, obsolete task state, psychological inference, sensitive details, and secrets.

- [ ] **Step 2: Install Runtime and MCP into the dedicated local venv**

Run the installer initially with the parallel v2 root. It may synchronize the new Skill and register MCP, but the server will not be considered ready until migration validation passes.

- [ ] **Step 3: Initialize and migrate the parallel v2 root**

Invoke:

```text
agc.admin init
agc.admin migrate
agc.admin validate
agc.admin rebuild_catalog
agc.admin backup
```

Use stdin or process memory for the migration request so no personal payload is written to a temporary request file.

- [ ] **Step 4: Verify local data invariants**

Prove:

- `schema-version` is exactly `2`;
- all migrated Memory files validate;
- Catalog count matches the approved migration inventory;
- no template/empty example is cataloged;
- sensitive exclusion count matches the semantic inventory and no excluded body appears under v2;
- every managed text file is strict UTF-8 without BOM;
- exact migration retry returns the same counts and creates no duplicate evidence.

- [ ] **Step 5: Verify MCP end to end**

Start the installed MCP server using the exact Codex configuration environment and use the official in-memory/stdio MCP client to:

1. list exactly three tools;
2. call `agc.read` overview;
3. search then get one high-impact principle;
4. call `agc.admin` validate;
5. confirm a self-contained task can be completed without any `agc.read` call.

Do not create a synthetic persistent personal memory merely for smoke testing.

- [ ] **Step 6: Run release gates**

Run:

```powershell
python -m pytest -q --basetemp D:\tmp\agc-v2-release
python -m build
python -m agc_runtime.cli version
git diff --check
```

Also run:

- strict UTF-8/no-BOM scan over tracked text;
- installed package version check (`0.2.0`);
- installed Skill equality check;
- Codex config marked-block check;
- v2 Runtime validation and backup check.

- [ ] **Step 7: Record verification without personal content**

The verification page may contain only counts, IDs when non-sensitive, commands, exit codes, checksums of build artifacts, and backup paths. It must not contain memory bodies, personal details, source excerpts, or migration request payloads.

- [ ] **Step 8: Commit project evidence**

```powershell
git add .llm-wiki
git commit -m "docs: verify agc v2 local cutover"
```

- [ ] **Step 9: Final review and synchronize main**

Run a whole-change review against the pre-upgrade base. Fix every Critical/Important finding, rerun the complete release gate, then push verified `main`. Confirm local `HEAD`, `origin/main`, and GitHub `main` are identical.

## Self-Review

- Spec coverage: thin Skill, LLM choice, three tools, failure-open, parallel migration, sensitive exclusion, idempotency, hard-forget legacy scope, local installation, rollback, and verification are each assigned to a task.
- Placeholder scan: no TBD/TODO/implement-later instructions remain.
- Type consistency: `create_server(Path)`, `migrate_v1(MemoryPaths, request)`, tool names, migration fields, and local paths are consistent across tasks.
- Scope check: Codex side-channel capture and seven-day backfill remain a separate independently testable delivery and are not activated here.

