# Agent Global Context v2 Runtime Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the independent Python AGC v2 Runtime foundation that can safely initialize, validate, read, write, rebuild, back up, restore, and forget Markdown-first personal memory without changing the public Skills yet.

**Architecture:** A dependency-light Python package owns deterministic behavior only: schemas, UTF-8 I/O, source-key idempotency, lifecycle transitions, sensitivity gates, Markdown storage, generated catalogs, and JSON CLI envelopes. LLMs remain responsible for semantic relevance, `disposition`, and `match_memory_id`; the Runtime never performs semantic merging or automatic promotion. This is the first of four independently testable delivery plans: Runtime Foundation, Recall and Skill Adapter, Codex Side-Channel Capture, and v1 Migration and Rollout.

**Tech Stack:** Python 3.10+, `PyYAML>=6.0.2,<7`, `pytest==9.1.1`, standard-library `argparse`, `dataclasses`, `hashlib`, `json`, `pathlib`, and atomic `os.replace`.

## Global Constraints

- The Runtime is independent and must not import or invoke `llm-wiki-runtime`.
- Do not add a database, vector store, knowledge graph, Trace Runtime, Eval Runtime, or Loop Runtime.
- Markdown is the source of truth; `catalog.md` and `catalog.json` are rebuildable.
- New text files use strict UTF-8 without BOM and `\n` line endings.
- `sensitive_storage` is fixed to `disabled`; sensitive and secret content is rejected before any persistent or temporary Runtime write.
- Exact idempotency key: `source.ref + source.revision + source.content_hash`.
- Runtime never infers semantic equality or invents `match_memory_id`.
- Evidence thresholds produce `eligible_for_adjudication`, never automatic promotion.
- This plan does not modify the five current public Skills. Skill consolidation begins only after the Runtime end-to-end gate passes.
- Every task follows red-green TDD and ends in one focused commit.

## Program Boundary

The design contains four independently reviewable systems, so implementation is split:

1. **Runtime Foundation — this plan:** deterministic storage, policy, read/write/admin, recovery, and hard forget.
2. **Recall and Skill Adapter:** 50–80 Token capability hint, three host tools, application modes, and alpha Skill compatibility.
3. **Codex Side-Channel Capture:** discovery, in-memory Task Capsules, extractor, budgets, watermarks, and Receipts.
4. **v1 Migration and Rollout:** sensitive preflight, parallel v2 build, seven-day fill, validation, cutover, and rollback.

## File Structure

```text
pyproject.toml
agc_runtime/
  __init__.py
  cli.py
  contracts.py
  errors.py
  paths.py
  utf8_io.py
  locking.py
  frontmatter.py
  models.py
  schema.py
  policy.py
  store.py
  events.py
  catalog.py
  read_service.py
  write_service.py
  forget_service.py
  admin_service.py
tests/
  conftest.py
  fixtures/
    active-principle.md
    evolving-interest.md
  test_cli_contract.py
  test_paths_and_io.py
  test_schema.py
  test_policy.py
  test_store_and_events.py
  test_write_service.py
  test_catalog_and_read.py
  test_forget_service.py
  test_admin_service.py
  test_runtime_end_to_end.py
```

---

### Task 1: Package Skeleton and Stable JSON Contract

**Files:**
- Create: `pyproject.toml`
- Create: `agc_runtime/__init__.py`
- Create: `agc_runtime/errors.py`
- Create: `agc_runtime/contracts.py`
- Create: `agc_runtime/cli.py`
- Create: `tests/conftest.py`
- Test: `tests/test_cli_contract.py`

**Interfaces:**
- Produces: `SourceKey(ref, revision, content_hash)`.
- Produces: `ToolResponse(tool, action, status, data, warnings, error)`.
- Statuses: `accepted`, `deferred`, `rejected_policy`, `needs_adjudication`, `failed`.

- [ ] **Step 1: Write the failing CLI tests**

```python
def test_version_is_a_stable_json_envelope(run_cli):
    result = run_cli("version")
    assert result.returncode == 0
    assert json.loads(result.stdout) == {
        "schema_version": 2,
        "tool": "agc.admin",
        "action": "version",
        "status": "accepted",
        "data": {"runtime_version": "0.1.0"},
        "warnings": [],
        "error": None,
    }


def test_unknown_tool_is_machine_readable(run_cli):
    result = run_cli("unknown")
    assert result.returncode == 2
    assert json.loads(result.stdout)["error"]["code"] == "invalid_tool"
```

- [ ] **Step 2: Verify red**

Run: `python -m pytest tests/test_cli_contract.py -q`

Expected: collection fails because `agc_runtime` does not exist.

- [ ] **Step 3: Implement package and response contracts**

Use this project metadata:

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "agent-global-context-runtime"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = ["PyYAML>=6.0.2,<7"]

[project.optional-dependencies]
test = ["pytest==9.1.1", "build>=1.2,<2"]

[project.scripts]
agc = "agc_runtime.cli:main"

[tool.setuptools.packages.find]
include = ["agc_runtime*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
```

Define exact contracts:

```python
Status = Literal[
    "accepted", "deferred", "rejected_policy", "needs_adjudication", "failed"
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
```

`cli.main()` emits one `json.dumps(..., ensure_ascii=False) + "\n"` envelope. Invalid CLI shape exits 2.

Create the test runner fixture in this task so RED failures come from missing
Runtime behavior rather than missing test infrastructure:

```python
# tests/conftest.py
import subprocess
import sys

import pytest


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
```

- [ ] **Step 4: Verify green**

Run: `python -m pytest tests/test_cli_contract.py -q`

Expected: `2 passed`.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml agc_runtime tests/conftest.py tests/test_cli_contract.py
git commit -m "feat: scaffold agc runtime contract"
```

### Task 2: Safe Root, UTF-8, Atomic Writes, and Locking

**Files:**
- Create: `agc_runtime/paths.py`
- Create: `agc_runtime/utf8_io.py`
- Create: `agc_runtime/locking.py`
- Test: `tests/test_paths_and_io.py`

**Interfaces:**
- Produces: `MemoryPaths.from_root(root)`.
- Produces: `strict_read_text(path)`, `atomic_write_text(path, text)`.
- Produces: `root_write_lock(paths)`.

- [ ] **Step 1: Write failing safety tests**

```python
def test_memory_paths_reject_escape(tmp_path):
    paths = MemoryPaths.from_root(tmp_path / "memory")
    with pytest.raises(ValueError, match="outside memory root"):
        paths.resolve_managed("../escape.md")

def test_atomic_write_is_utf8_without_bom(tmp_path):
    target = tmp_path / "记忆.md"
    atomic_write_text(target, "做难而正确的事情\n")
    raw = target.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert b"\r\n" not in raw
    assert strict_read_text(target) == "做难而正确的事情\n"

def test_strict_read_rejects_invalid_utf8(tmp_path):
    target = tmp_path / "broken.md"
    target.write_bytes(b"\xff")
    with pytest.raises(UnicodeDecodeError):
        strict_read_text(target)
```

- [ ] **Step 2: Verify red**

Run: `python -m pytest tests/test_paths_and_io.py -q`

Expected: missing-module import failure.

- [ ] **Step 3: Implement fixed paths and atomic I/O**

`MemoryPaths` exposes `catalog_md`, `catalog_json`, `memories`, `contexts`, `candidates`, `events`, `archive`, `queue`, `receipts`, `locks`, `cache`, and `backups`. Resolve the root and reject paths outside it.

```python
def strict_read_text(path: Path) -> str:
    return path.read_bytes().decode("utf-8", errors="strict")

def atomic_write_text(path: Path, text: str) -> None:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(normalized.encode("utf-8"))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        if os.path.exists(temporary):
            os.unlink(temporary)
        raise
```

The write lock uses exclusive creation, records PID/host/time, reclaims only a same-host dead-PID lock, and always releases its own file.

- [ ] **Step 4: Verify green**

Run: `python -m pytest tests/test_paths_and_io.py -q`

Expected: all path, encoding, atomicity, and stale-lock tests pass.

- [ ] **Step 5: Commit**

```bash
git add agc_runtime/paths.py agc_runtime/utf8_io.py agc_runtime/locking.py tests/test_paths_and_io.py
git commit -m "feat: add safe agc storage primitives"
```

### Task 3: Schema v2 and Canonical Markdown

**Files:**
- Create: `agc_runtime/models.py`
- Create: `agc_runtime/frontmatter.py`
- Create: `agc_runtime/schema.py`
- Create: `tests/fixtures/active-principle.md`
- Create: `tests/fixtures/evolving-interest.md`
- Test: `tests/test_schema.py`

**Interfaces:**
- Produces: `MemoryItem.from_markdown(text)`, `MemoryItem.to_markdown()`.
- Produces: `validate_memory_item(item)`.

- [ ] **Step 1: Write failing schema tests**

```python
def test_principle_round_trips_canonically(fixture_text):
    item = MemoryItem.from_markdown(fixture_text("active-principle.md"))
    assert item.id == "difficult-but-correct"
    assert item.kind == "principle"
    validate_memory_item(item)
    assert MemoryItem.from_markdown(item.to_markdown()) == item

def test_content_budgets_are_enforced(fixture_text):
    item = MemoryItem.from_markdown(
        fixture_text("active-principle.md").replace(
            "做难而正确的事情", "难" * 61, 1
        )
    )
    with pytest.raises(ValueError, match="Memory Card exceeds 60"):
        validate_memory_item(item)
```

- [ ] **Step 2: Verify red**

Run: `python -m pytest tests/test_schema.py -q`

Expected: missing `MemoryItem`.

- [ ] **Step 3: Implement typed models and strict frontmatter**

Use frozen dataclasses for `Lifecycle`, `Confidence`, `Temporal`, `Recall`, `Provenance`, and `MemoryItem`. Use only `yaml.safe_load`; reject unknown fields, YAML tags, duplicate body headings, missing fixed sections, and IDs outside `^[a-z0-9][a-z0-9-]{0,79}$`.

Allowed values:

```python
KINDS = {"identity", "principle", "preference", "interest",
         "capability", "goal", "pattern", "context"}
LIFECYCLES = {"candidate", "active", "challenged", "dormant",
              "superseded", "historical", "rejected"}
TEMPORAL_TYPES = {"durable", "evolving", "goal_bound",
                  "contextual", "derived", "episodic"}
EXPOSURES = {"core_card", "scoped_card", "discoverable_only", "history_only"}
```

Canonical body headings are `Memory Card`, `Full Meaning`, `Application Boundary`, and `Rationale`; budgets are 60, 300, 150, and 100 Unicode code points. A personal identity record cannot become `core_card` without an explicit policy reason. A `growth_area` requires active `goal_refs` before proactive use.

- [ ] **Step 4: Verify green**

Run: `python -m pytest tests/test_schema.py -q`

Expected: round-trip, unknown-field, enum, and budget tests pass.

- [ ] **Step 5: Commit**

```bash
git add agc_runtime/models.py agc_runtime/frontmatter.py agc_runtime/schema.py tests/fixtures tests/test_schema.py
git commit -m "feat: define agc v2 memory schema"
```

### Task 4: Observation, Sensitivity, and Lifecycle Policy

**Files:**
- Modify: `agc_runtime/contracts.py`
- Create: `agc_runtime/policy.py`
- Test: `tests/test_policy.py`

**Interfaces:**
- Produces: `ObservationEnvelope.from_mapping(value)`.
- Produces: `evaluate_observation(envelope)`.
- Produces: `validate_transition(old, new)`.

- [ ] **Step 1: Write failing policy tests**

```python
def test_sensitive_is_rejected_before_persistence(envelope):
    decision = evaluate_observation(envelope(sensitivity="sensitive"))
    assert decision.status == "rejected_policy"
    assert decision.code == "sensitive_persistence_disabled"
    assert "rationale" not in decision.persistable_metadata

def test_reinforce_requires_match_memory_id(envelope):
    decision = evaluate_observation(envelope(disposition="reinforce"))
    assert decision.status == "needs_adjudication"
    assert decision.code == "match_memory_id_required"

def test_hypothetical_cannot_auto_confirm(envelope):
    value = envelope(requested_confidence="confirmed").to_mapping()
    value["assertion"]["modality"] = "hypothetical"
    assert evaluate_observation(
        ObservationEnvelope.from_mapping(value)
    ).code == "assertion_not_confirmable"
```

- [ ] **Step 2: Verify red**

Run: `python -m pytest tests/test_policy.py -q`

Expected: missing Observation contract.

- [ ] **Step 3: Implement the deterministic policy matrix**

```python
PERSISTABLE_SENSITIVITY = {"normal", "personal"}
NON_PERSISTABLE_SENSITIVITY = {"sensitive", "secret"}
CONFIRMABLE_ASSERTIONS = {("direct", "asserted")}
MATCH_REQUIRED = {"reinforce", "update", "conflict"}
EVIDENCE_THRESHOLD = {
    "minimum_evidence": 3,
    "minimum_distinct_sessions": 2,
    "minimum_time_span_days": 7,
}
```

Quoted, hypothetical, question, example, third-party, and role-play assertions cannot use A3. Behavior observations remain Candidates. Threshold satisfaction returns `eligible_for_adjudication`; it cannot create active memory. Use an explicit lifecycle transition table and reject silent `active -> rejected`, `superseded -> active`, and `historical -> active`.

- [ ] **Step 4: Verify green**

Run: `python -m pytest tests/test_policy.py -q`

Expected: all sensitivity, source-mode, evidence, and transition cases pass.

- [ ] **Step 5: Commit**

```bash
git add agc_runtime/contracts.py agc_runtime/policy.py tests/test_policy.py
git commit -m "feat: enforce agc observation policy"
```

### Task 5: Markdown Store, Events, and Exact Idempotency

**Files:**
- Create: `agc_runtime/store.py`
- Create: `agc_runtime/events.py`
- Test: `tests/test_store_and_events.py`

**Interfaces:**
- Produces: `MemoryStore(paths)`.
- Produces: `create_memory(item, source_key)`, `add_evidence(...)`.

- [ ] **Step 1: Write failing store tests**

```python
def test_same_source_is_idempotent(store, principle):
    source = SourceKey("codex-task:t1", "r1", "a" * 64)
    assert store.create_memory(principle, source).created is True
    duplicate = store.create_memory(principle, source)
    assert duplicate.created is False
    assert duplicate.code == "duplicate_source"

def test_new_revision_is_independent(store, principle):
    store.create_memory(principle, SourceKey("codex-task:t1", "r1", "a" * 64))
    result = store.add_evidence(
        principle.id,
        SourceKey("codex-task:t1", "r2", "b" * 64),
        "2026-07-29T00:00:00Z",
    )
    assert result.independent_evidence_count == 2

def test_event_does_not_copy_memory_body(store, principle):
    store.create_memory(principle, SourceKey("codex-task:t1", "r1", "a" * 64))
    assert "做难而正确的事情" not in store.read_all_events_text()
```

- [ ] **Step 2: Verify red**

Run: `python -m pytest tests/test_store_and_events.py -q`

Expected: missing store module.

- [ ] **Step 3: Implement one recoverable mutation order**

Every mutation acquires the root lock, rechecks the exact source key, writes the Memory/Candidate atomically, appends a sanitized event, updates `.runtime/receipts/source-keys.json`, and releases the lock. Events contain opaque object ID, old/new lifecycle, timestamp, and source reference only. Formal paths are deterministic by kind. Semantic similarity without `match_memory_id` returns `needs_adjudication` without body scanning.

- [ ] **Step 4: Verify green**

Run: `python -m pytest tests/test_store_and_events.py -q`

Expected: idempotency, new revision, atomic failure, and sanitized event tests pass.

- [ ] **Step 5: Commit**

```bash
git add agc_runtime/store.py agc_runtime/events.py tests/test_store_and_events.py
git commit -m "feat: add idempotent markdown store"
```

### Task 6: Write Service

**Files:**
- Create: `agc_runtime/write_service.py`
- Test: `tests/test_write_service.py`

**Interfaces:**
- Produces: `dispatch_write(paths, request) -> ToolResponse`.
- Supports: `observe`, `observe_batch`, `propose`, `confirm`, `update`, `supersede`, `archive`, `reject`.

- [ ] **Step 1: Write failing action tests**

```python
def test_direct_normal_can_create_confirmed(runtime_paths, direct_request):
    response = dispatch_write(runtime_paths, direct_request)
    assert response.status == "accepted"
    assert response.data["lifecycle"] == "active"
    assert response.data["confidence"] == "confirmed"

def test_behavior_threshold_requests_adjudication(runtime_paths, observations):
    responses = [dispatch_write(runtime_paths, item) for item in observations]
    assert responses[-1].data["candidate_status"] == "eligible_for_adjudication"
    assert not list(runtime_paths.memories.rglob("*.md"))

def test_update_without_match_does_not_merge(runtime_paths, update_request):
    update_request["proposal"].pop("match_memory_id")
    assert dispatch_write(
        runtime_paths, update_request
    ).status == "needs_adjudication"
```

- [ ] **Step 2: Verify red**

Run: `python -m pytest tests/test_write_service.py -q`

Expected: missing service.

- [ ] **Step 3: Implement explicit handlers**

Each action has a separate handler. `observe_batch` evaluates each envelope independently and returns status counts. Existing-object actions require exact IDs and legal transitions. High-impact conflict returns `needs_adjudication`. Never generate a semantic match, auto-promote an evidence-eligible Candidate, persist rejected content, or claim a failed write succeeded.

- [ ] **Step 4: Verify green**

Run: `python -m pytest tests/test_write_service.py -q`

Expected: action, lifecycle, batch, and failure-reporting tests pass.

- [ ] **Step 5: Commit**

```bash
git add agc_runtime/write_service.py tests/test_write_service.py
git commit -m "feat: implement agc write service"
```

### Task 7: Catalog and Progressive Read Service

**Files:**
- Create: `agc_runtime/catalog.py`
- Create: `agc_runtime/read_service.py`
- Test: `tests/test_catalog_and_read.py`

**Interfaces:**
- Produces: `rebuild_catalog(paths)`.
- Produces: `dispatch_read(paths, request)`.
- Supports: `overview`, `search`, `get`, `history`, `evidence`.

- [ ] **Step 1: Write failing progressive-read tests**

```python
def test_overview_returns_metadata_not_full_meaning(populated_paths):
    response = dispatch_read(populated_paths, {"action": "overview"})
    encoded = json.dumps(response.to_dict(), ensure_ascii=False)
    assert response.data["estimated_tokens"] <= 250
    assert "长期价值" not in encoded

def test_search_filters_before_loading_bodies(populated_paths):
    response = dispatch_read(populated_paths, {
        "action": "search",
        "filters": {"kind": ["principle"], "scopes": ["architecture"],
                    "decision_impact": ["high"], "sensitivity": ["normal"]},
        "limit": 10,
    })
    assert [item["id"] for item in response.data["items"]] == [
        "difficult-but-correct"
    ]

def test_discoverable_and_history_are_not_default(populated_paths):
    response = dispatch_read(populated_paths, {"action": "overview"})
    ids = {item["id"] for item in response.data.get("cards", [])}
    assert "family-structure" not in ids
    assert "old-role" not in ids
```

- [ ] **Step 2: Verify red**

Run: `python -m pytest tests/test_catalog_and_read.py -q`

Expected: missing catalog module.

- [ ] **Step 3: Implement deterministic cards and reads**

Sort Catalog by UTF-8 bytes of ID. Cards contain only ID, kind, scopes, updated time, confidence, impact, exposure, sensitivity, and Memory Card. `overview` returns counts and high-impact scopes; cards are included only below the small-catalog budget. Estimate tokens as `(len(serialized) + 2) // 3`. `search` filters metadata first. `get`, `history`, and `evidence` require explicit IDs. `discoverable_only` and `history_only` never enter overview cards.

- [ ] **Step 4: Verify green**

Run: `python -m pytest tests/test_catalog_and_read.py -q`

Expected: ordering, exposure, filters, token budgets, and rebuild tests pass.

- [ ] **Step 5: Commit**

```bash
git add agc_runtime/catalog.py agc_runtime/read_service.py tests/test_catalog_and_read.py
git commit -m "feat: add progressive agc reads"
```

### Task 8: Authorized Hard Forget

**Files:**
- Create: `agc_runtime/forget_service.py`
- Modify: `agc_runtime/write_service.py`
- Test: `tests/test_forget_service.py`

**Interfaces:**
- Produces: `forget(paths, request)`.
- Requires: `authorization == "explicit_user_request"`.

- [ ] **Step 1: Write failing forget tests**

```python
def test_forget_requires_authorization(populated):
    response = forget(populated.paths, {"memory_id": "family-structure"})
    assert response.error["code"] == "forget_authorization_required"

def test_forget_removes_all_managed_copies(populated):
    response = forget(populated.paths, {
        "memory_id": "family-structure",
        "suppression_scope": "family_structure",
        "authorization": "explicit_user_request",
        "verification_terms": ["妻子和儿子"],
    })
    assert response.status == "accepted"
    assert all("妻子和儿子" not in path.read_text(encoding="utf-8")
               for path in populated.all_text_files)
    assert set(response.data["tombstone"]) == {
        "memory_id", "status", "forgotten_at", "suppression_scope"
    }

def test_restore_cannot_resurrect_forgotten(populated):
    forget(populated.paths, populated.authorized_request)
    restore_latest(populated.paths)
    assert dispatch_read(
        populated.paths, {"action": "get", "id": "family-structure"}
    ).status == "failed"
```

- [ ] **Step 2: Verify red**

Run: `python -m pytest tests/test_forget_service.py -q`

Expected: missing forget service.

- [ ] **Step 3: Implement scoped erase under one lock**

Require exact Memory ID; ambiguous scope returns `needs_adjudication`. Remove formal Memory/Candidate, sanitize matching Event payloads, remove Catalog/source registry/Cache/Queue/Receipt/Archive/migration-staging references, rewrite AGC backups, write a content-free Tombstone, rebuild Catalog, and scan managed copies using ephemeral `verification_terms`. Never delete Codex source tasks. Return `managed_agc_copies_deleted: true` and `source_task_deleted: false`.

- [ ] **Step 4: Verify green**

Run: `python -m pytest tests/test_forget_service.py -q`

Expected: authorization, scope, backup rewrite, non-resurrection, and Tombstone tests pass.

- [ ] **Step 5: Commit**

```bash
git add agc_runtime/forget_service.py agc_runtime/write_service.py tests/test_forget_service.py
git commit -m "feat: implement agc hard forget"
```

### Task 9: Admin Services and Recovery

**Files:**
- Create: `agc_runtime/admin_service.py`
- Test: `tests/test_admin_service.py`

**Interfaces:**
- Produces: `dispatch_admin(paths, request)`.
- Supports: `init`, `validate`, `rebuild_catalog`, `backup`, `restore`.
- `migrate` returns `deferred` with `migration_adapter_not_installed`.

- [ ] **Step 1: Write failing admin tests**

```python
def test_init_creates_v2_layout_and_fixed_policy(tmp_path):
    paths = MemoryPaths.from_root(tmp_path)
    assert dispatch_admin(paths, {"action": "init"}).status == "accepted"
    assert (tmp_path / "schema-version").read_text(encoding="utf-8") == "2\n"
    assert "sensitive_storage: disabled" in (
        tmp_path / "config.yaml"
    ).read_text(encoding="utf-8")

def test_validate_excludes_invalid_memory(invalid_root):
    response = dispatch_admin(invalid_root, {"action": "validate"})
    assert response.status == "failed"
    assert response.data["invalid_count"] == 1

def test_backup_excludes_locks(populated_paths):
    manifest = dispatch_admin(
        populated_paths, {"action": "backup"}
    ).data["manifest"]
    assert all(".runtime/locks" not in item["path"]
               for item in manifest["files"])
```

- [ ] **Step 2: Verify red**

Run: `python -m pytest tests/test_admin_service.py -q`

Expected: missing admin service.

- [ ] **Step 3: Implement admin actions**

`init` writes schema version 2, fixed sensitive policy, Recall budgets 250/600, and evidence thresholds 3/2/7. `validate` strict-decodes every managed file, validates objects, source-key uniqueness, legal transitions, and Catalog reproducibility. `backup` writes deterministic ZIP and SHA-256 manifest while excluding locks and temp files. `restore` verifies the manifest, applies Tombstone suppression, replaces files atomically, and rebuilds Catalog.

- [ ] **Step 4: Verify green**

Run: `python -m pytest tests/test_admin_service.py -q`

Expected: init, validation, corrupted backup rejection, restore, and suppression tests pass.

- [ ] **Step 5: Commit**

```bash
git add agc_runtime/admin_service.py tests/test_admin_service.py
git commit -m "feat: add agc administration services"
```

### Task 10: Three CLI Tools and End-to-End Gate

**Files:**
- Modify: `agc_runtime/cli.py`
- Modify: `tests/conftest.py`
- Test: `tests/test_runtime_end_to_end.py`
- Modify: `README.md`
- Modify: `README.zh.md`

**Interfaces:**
- `agc read --root <path> --input <json-file|->`
- `agc write --root <path> --input <json-file|->`
- `agc admin --root <path> --input <json-file|->`

- [ ] **Step 1: Write the failing vertical-slice test**

```python
def test_init_write_rebuild_read_forget(tmp_path, cli):
    assert cli("admin", tmp_path, {"action": "init"})["status"] == "accepted"
    assert cli("write", tmp_path, direct_preference_request())[
        "status"
    ] == "accepted"
    assert cli("admin", tmp_path, {"action": "rebuild_catalog"})[
        "data"
    ]["memory_count"] == 1
    assert cli("read", tmp_path, {
        "action": "search", "filters": {"kind": ["preference"]}
    })["data"]["items"][0]["id"] == "implementation-plan-first"
    removed = cli("write", tmp_path, {
        "action": "forget",
        "memory_id": "implementation-plan-first",
        "suppression_scope": "collaboration_preferences",
        "authorization": "explicit_user_request",
        "verification_terms": ["先确认实施计划"],
    })
    assert removed["status"] == "accepted"
```

- [ ] **Step 2: Verify red**

Run: `python -m pytest tests/test_runtime_end_to_end.py -q`

Expected: CLI rejects unwired read/write/admin dispatch.

- [ ] **Step 3: Wire dispatch and document boundaries**

Parse only `read`, `write`, `admin`, and `version`. Read one JSON object, resolve an explicit `--root`, dispatch, and emit one response. Invalid input exits 2; handled policy rejection exits 0; I/O failure exits 1 and never reports acceptance.

README must state that the Runtime is independent, the five alpha Skills remain active during this phase, the CLI is a host adapter rather than a human workflow, semantic matching remains with the LLM, sensitive persistence is disabled, and Codex capture/migration are not activated.

- [ ] **Step 4: Run the release gate**

```bash
python -m pytest -q
python -m build
python -m agc_runtime.cli version
git diff --check
```

Expected: tests pass, wheel and source distribution build, version emits the stable accepted envelope, and diff check is clean.

Run strict Windows encoding verification:

```powershell
$strict = New-Object System.Text.UTF8Encoding($false, $true)
$files = rg --files -g '*.md' -g '*.py' -g '*.toml' -g '*.yaml' -g '*.json'
foreach ($file in $files) {
  $bytes = [IO.File]::ReadAllBytes((Resolve-Path $file))
  $null = $strict.GetString($bytes)
  if ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and
      $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) {
    throw "Unexpected UTF-8 BOM: $file"
  }
}
```

Expected: exit 0 without decoding or BOM failure.

- [ ] **Step 5: Commit**

```bash
git add agc_runtime/cli.py tests/conftest.py tests/test_runtime_end_to_end.py README.md README.zh.md
git commit -m "feat: complete agc runtime foundation"
```

## Self-Review

### Spec Coverage

- Three-tool deterministic contract: Tasks 1, 6, 7, 9, and 10.
- Markdown source, Schema v2, temporal metadata, and UTF-8: Tasks 2 and 3.
- Sensitive persistence disabled before writes: Task 4.
- Exact idempotency, evidence thresholds, and no semantic merging: Tasks 4–6.
- Progressive data access without prompt injection: Task 7.
- Catalog rebuild, recovery, and hard forget: Tasks 7–9.
- Recall capability hint and `adapt/continue/grow`: assigned to the Recall and Skill Adapter plan.
- Task Capsule, watermarks, Receipts, and Token budgets: assigned to the Codex Side-Channel Capture plan.
- v1 preflight, parallel migration, seven-day fill, cutover, and rollback: assigned to the v1 Migration and Rollout plan.

### Placeholder Scan

Every foundation task has exact paths, interfaces, tests, commands, expected results, and commit boundaries. The uninstalled migration adapter has an explicit deterministic response instead of an undefined behavior.

### Type Consistency

- All services consume `MemoryPaths`.
- Every dispatcher returns `ToolResponse`.
- Exact evidence identity always uses `SourceKey`.
- Every CLI request contains `action`.
- Hard forget uses the same Memory ID used by Store, Catalog, Events, and Read Service.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-29-agent-global-context-v2-runtime-foundation.md`. Two execution options:

1. **Subagent-Driven (recommended):** a fresh subagent per task with specification and code-quality review between tasks.
2. **Inline Execution:** execute tasks in this session using `executing-plans`, in batches with review checkpoints.
