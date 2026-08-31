# AGC Proactive Capture Review Notification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use `executing-plans` for inline execution. Do not delegate unless the user explicitly requests delegation.

**Goal:** Notify the user in Codex App when a bounded Capture batch is ready, generate complete non-mutating memory previews, and preserve explicit confirmation as the only formal-write gate.

**Architecture:** A pure review-status module derives readiness from unreviewed Capture observations and terminal receipts. A tiny content-free cache under `.runtime/cache` records the latest notification digest and time; it is deliberately operational rather than durable memory. `agc.read` exposes status, `agc.admin` records delivery, and the public Skill defines the scheduled Codex App interaction.

**Tech Stack:** Python 3.10+, existing Capture Store and MCP tools, SHA-256 canonical JSON, pytest, Markdown Skill contracts, Codex App Scheduled Tasks.

## Global Constraints

- Review readiness performs no model call and reads no raw Codex Session.
- The status response contains observation IDs and aggregate counts, never statements, evidence, Capsule text, source paths, or model output.
- Thresholds are fixed for Runtime 0.4.5: 10 unreviewed observations, 24-hour oldest age, 10 observations per proposed batch, and 24-hour notification cooldown.
- The oldest eligible observations are selected first to prevent starvation.
- The notice cache is content-free and non-authoritative; deleting it can only permit a repeated notification.
- A scheduled run may generate at most three previews and may never write formal memory without a later explicit user confirmation.
- Preserve Capture schema version 1 and Memory schema version 2.
- Keep tests under the user-designated centralized test root; do not create new repository-root temporary directories.

---

### Task 1: Deterministic review readiness and notice cache

**Files:**
- Create: `agc_runtime/capture_review_notification.py`
- Create: `tests/test_capture_review_notification.py`

**Interfaces:**
- Consumes: `CaptureStore(paths).read_snapshot()` and `paths.cache`.
- Produces: `capture_review_status(paths, now=None) -> dict[str, Any]`.
- Produces: `record_capture_review_notice(paths, batch_digest, now=None) -> dict[str, Any]`.

- [ ] **Step 1: Write failing readiness tests**

Create synthetic complete observations and terminal review receipts using the existing Capture fixtures. Assert:

```python
status = capture_review_status(paths, now="2026-08-31T12:00:00Z")
assert status["ready"] is True
assert status["should_notify"] is True
assert status["ready_reason"] == "count_threshold"
assert status["unreviewed_count"] == 10
assert len(status["batch_observation_ids"]) == 10
assert status["batch_observation_ids"] == oldest_first_ids
assert set(status["category_counts"]) <= {"project", "work", "learning", "research", "personal_growth"}
assert "statement" not in repr(status)
```

Also cover empty, nine fresh observations, one observation older than 24 hours, reviewed observations excluded, integrity degraded, invalid notice cache, same-digest cooldown, cooldown expiry, and new-batch digest behavior.

- [ ] **Step 2: Run tests and verify RED**

```powershell
$env:AGC_TEST_TMP_ROOT='D:\tmp_test\agc-review-notification'
& '.\.venv\Scripts\python.exe' -m pytest tests/test_capture_review_notification.py -q -p no:cacheprovider --basetemp (Join-Path $env:AGC_TEST_TMP_ROOT 'status-red')
```

Expected: collection fails because `agc_runtime.capture_review_notification` does not exist.

- [ ] **Step 3: Implement the minimal status model**

Use these public constants and signatures:

```python
REVIEW_COUNT_THRESHOLD = 10
REVIEW_MAX_AGE_SECONDS = 24 * 60 * 60
REVIEW_BATCH_LIMIT = 10
REVIEW_NOTICE_COOLDOWN_SECONDS = 24 * 60 * 60
REVIEW_NOTICE_POLICY = "capture-review-notification-v1"
```

The exact public signatures are `capture_review_status(paths: MemoryPaths, *, now: str | None = None) -> dict[str, Any]` and `record_capture_review_notice(paths: MemoryPaths, batch_digest: str, *, now: str | None = None) -> dict[str, Any]`.

Sort eligible observations by parsed `captured_at` ascending and `observation_id`. Compute the digest from canonical JSON containing only `policy` and the selected batch IDs. Store the notice at `paths.cache / "capture-review-notice.json"` with exact fields:

```json
{"schema_version":1,"policy":"capture-review-notification-v1","batch_digest":"<sha256>","notified_at":"<UTC>"}
```

Invalid cache content is treated as missing. If Capture integrity is not `healthy`, return `ready=false`, `should_notify=false`, and `ready_reason="integrity_degraded"`.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run the Step 2 command with basetemp suffix `status-green`.

Expected: every test in `tests/test_capture_review_notification.py` passes.

- [ ] **Step 5: Commit Task 1**

```powershell
git add agc_runtime/capture_review_notification.py tests/test_capture_review_notification.py
git commit -m "feat: derive capture review readiness"
```

---

### Task 2: Expose exact read/admin/MCP contracts

**Files:**
- Modify: `agc_runtime/read_service.py`
- Modify: `agc_runtime/admin_service.py`
- Modify: `tests/test_capture_read_service.py`
- Modify: `tests/test_admin_service.py`
- Modify: `tests/test_mcp_server.py`

**Interfaces:**
- Consumes: Task 1 status and notice functions.
- Produces: `agc.read {"action":"capture_review_status"}`.
- Produces: `agc.admin {"action":"capture_review_notice","batch_digest":"<sha256>"}`.

- [ ] **Step 1: Add failing dispatch and MCP tests**

Assert exact successful requests and strict rejection:

```python
read = dispatch_read(paths, {"action": "capture_review_status"})
assert read.status == "accepted"
assert read.data["policy"] == "capture-review-notification-v1"

notice = dispatch_admin(paths, {
    "action": "capture_review_notice",
    "batch_digest": read.data["batch_digest"],
})
assert notice.status == "accepted"
assert notice.data["code"] == "capture_review_notice_recorded"
```

Reject missing/uppercase/non-hex digests and unknown request fields. Verify MCP binds the configured Memory Root and never accepts a caller-provided root.

- [ ] **Step 2: Run focused tests and verify RED**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_capture_read_service.py tests/test_admin_service.py tests/test_mcp_server.py -q -p no:cacheprovider --basetemp (Join-Path $env:AGC_TEST_TMP_ROOT 'contracts-red') -k 'review_status or review_notice'
```

Expected: actions are rejected as unsupported.

- [ ] **Step 3: Register strict handlers**

Add `_handle_capture_review_status` to `read_service.py` and the action to `_CAPTURE_ACTIONS`. Add `_handle_capture_review_notice` to `admin_service.py`; require exactly `action` and `batch_digest`, then return:

```python
ToolResponse(
    tool="agc.admin",
    action="capture_review_notice",
    status="accepted",
    data={"code": "capture_review_notice_recorded", **result},
)
```

Do not change the three public MCP tool names.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run the Step 2 command without `-k`, using basetemp suffix `contracts-green`.

Expected: all selected read, admin, and MCP tests pass.

- [ ] **Step 5: Commit Task 2**

```powershell
git add agc_runtime/read_service.py agc_runtime/admin_service.py tests/test_capture_read_service.py tests/test_admin_service.py tests/test_mcp_server.py
git commit -m "feat: expose capture review notification status"
```

---

### Task 3: Codex App scheduled review workflow

**Files:**
- Create: `skills/agent-global-context/references/review-notification-workflow.md`
- Modify: `skills/agent-global-context/SKILL.md`
- Modify: `skills/agent-global-context/references/tool-contract.md`
- Modify: `docs/capture-operations.md`
- Modify: `tests/test_skill_adapter.py`

**Interfaces:**
- Consumes: Task 2 tool actions and the existing quality-first formalization workflow.
- Produces: a scheduled-task prompt contract that stays quiet unless `should_notify=true`.

- [ ] **Step 1: Write failing Skill contract tests**

Assert the packaged Skill requires all of these literals:

```python
required = (
    "capture_review_status",
    "capture_review_notice",
    "should_notify",
    "at most three",
    "complete Memory Item",
    "explicit user confirmation",
    "never write formal memory",
)
for value in required:
    assert value in review_notification_workflow_text
```

- [ ] **Step 2: Run Skill tests and verify RED**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_skill_adapter.py -q -p no:cacheprovider --basetemp (Join-Path $env:AGC_TEST_TMP_ROOT 'skill-red') -k 'review_notification'
```

Expected: the workflow reference is absent.

- [ ] **Step 3: Add the bounded workflow**

The workflow must instruct a scheduled Codex App run to:

1. Call `capture_review_status`.
2. Return no user-facing result when `should_notify` is false.
3. Fetch only `batch_observation_ids` with `capture_get`; never reopen raw Sessions.
4. Apply the existing formalization quality gates and compare only relevant active memories.
5. Present at most three complete previews with disposition and contributing IDs.
6. Call `capture_review_notice` only after the preview is ready to show.
7. End in a user-input-required state and perform no formal-memory write.

Document that Codex App owns scheduling/notifications while AGC owns readiness, safe data selection, and memory-domain behavior.

- [ ] **Step 4: Run Skill and adjacent formalization tests**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_skill_adapter.py tests/test_capture_review.py tests/test_capture_read_service.py -q -p no:cacheprovider --basetemp (Join-Path $env:AGC_TEST_TMP_ROOT 'skill-green')
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit Task 3**

```powershell
git add skills/agent-global-context/SKILL.md skills/agent-global-context/references/review-notification-workflow.md skills/agent-global-context/references/tool-contract.md docs/capture-operations.md tests/test_skill_adapter.py
git commit -m "docs: add proactive capture review workflow"
```

---

### Task 4: Runtime 0.4.5 verification and deployment handoff

**Files:**
- Modify: `pyproject.toml`
- Modify: `agc_runtime/__init__.py`
- Modify: `README.md`
- Modify: `README.zh.md`
- Modify: `README.en.md`
- Modify: version-sensitive tests
- Create after verification: `.llm-wiki/verification/agc-proactive-review-notification.md`

**Interfaces:**
- Consumes: Tasks 1-3.
- Produces: a locally verified AGC 0.4.5 candidate and an explicit production-deployment handoff.

- [ ] **Step 1: Update version and release documentation**

Set both authoritative version declarations to `0.4.5`. Describe proactive review readiness as opt-in through a Codex App scheduled task; installation alone must not create the task or promote memory.

- [ ] **Step 2: Run full verification**

```powershell
$env:AGC_TEST_TMP_ROOT='D:\tmp_test\agc-review-notification'
& '.\.venv\Scripts\python.exe' -m pytest -q -p no:cacheprovider --basetemp (Join-Path $env:AGC_TEST_TMP_ROOT 'full')
& '.\.venv\Scripts\python.exe' -m compileall -q agc_runtime tests
git diff --check
```

Expected: full suite and compile pass; diff check prints nothing.

- [ ] **Step 3: Build and inspect the package**

```powershell
& '.\.venv\Scripts\python.exe' -m build --outdir (Join-Path $env:AGC_TEST_TMP_ROOT 'dist')
& '.\.venv\Scripts\python.exe' -m pip check
& '.\.venv\Scripts\python.exe' -m agc_runtime.cli --version
```

Expected: wheel and sdist build, dependency check passes, and CLI reports `0.4.5`.

- [ ] **Step 4: Record verification without deploying**

Create the verification page with exact test counts, package hashes, commands, and remaining deployment gate. Update the Change Brief Flow Record to development/testing done and archive pending.

- [ ] **Step 5: Commit the release candidate**

```powershell
git add pyproject.toml agc_runtime/__init__.py README.md README.zh.md README.en.md tests .llm-wiki/requirements/agc-proactive-review-notification.md .llm-wiki/working-context/agc-proactive-review-notification.md .llm-wiki/verification/agc-proactive-review-notification.md .llm-wiki/log.md
git commit -m "release: prepare AGC 0.4.5 review notifications"
```

After this commit, request explicit authorization before installing 0.4.5, creating the Codex App scheduled task, running the first production preview, or pushing GitHub.
