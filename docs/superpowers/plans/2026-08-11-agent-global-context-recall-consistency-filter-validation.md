# Agent Global Context Recall Consistency and Filter Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make personal research-relevance requests trigger AGC consistently and make Search fail closed on unknown filter keys.

**Architecture:** Keep Recall controlled by the LLM and preserve the existing progressive read path. Add one narrow intent rule to the public Skill, while the deterministic Read Service validates the fixed Search filter vocabulary before catalog matching.

**Tech Stack:** Markdown Agent Skill, Python 3.10+, pytest 9.1.1.

## Global Constraints

- Do not change memory data, catalog ranking, literal query semantics, or public MCP actions.
- Do not broaden Recall to generic repository or technology explanations.
- Supported Search filters remain `kind`, `scopes`, `decision_impact`, `sensitivity`, `exposure`, and `confidence`, with list-of-string values.
- Preserve the schema-v2 failure envelope and failure-open main-task behavior.

---

### Task 1: Reject Unknown Search Filter Keys

**Files:**
- Modify: `tests/test_catalog_and_read.py`
- Modify: `agc_runtime/read_service.py`

**Interfaces:**
- Consumes: `dispatch_read(paths, request)` and the existing Search filter mapping.
- Produces: deterministic `invalid_request` responses for unsupported filter keys.

- [ ] **Step 1: Add a failing test**

Add a test that sends `{"action":"search","filters":{"scope":["research"]}}` and expects `status == "failed"`, `error.code == "invalid_request"`, and a message naming `scope`.

- [ ] **Step 2: Verify RED**

Run:

```powershell
& 'D:\tmp\github\agent-global-context\.venv\Scripts\python.exe' -m pytest tests/test_catalog_and_read.py::test_search_rejects_unknown_filter_keys -q --basetemp 'C:\tmp\agc-filter-red'
```

Expected: FAIL because the current Runtime silently ignores `scope` and accepts the request.

- [ ] **Step 3: Implement minimal validation**

Define the supported filter-key set in `agc_runtime/read_service.py`. Before matching the catalog, compute unknown keys deterministically and raise `ValueError("unsupported search filter: <keys>")` when any exist.

- [ ] **Step 4: Verify GREEN**

Run the focused test and then all of `tests/test_catalog_and_read.py`.

---

### Task 2: Make Research-Relevance Recall Explicit

**Files:**
- Modify: `tests/test_skill_adapter.py`
- Modify: `skills/agent-global-context/SKILL.md`
- Modify: `docs/superpowers/specs/2026-08-08-agent-global-context-recall-activation-design.md`

**Interfaces:**
- Consumes: the existing LLM-owned Recall value gate.
- Produces: one explicit positive trigger and one explicit generic-factual exclusion, plus the exact Search filter recipe.

- [ ] **Step 1: Add a failing Skill regression test**

Require the Skill description/body to cover projects or technologies evaluated against the user's research, learning, or long-term goals, and to retain a generic factual exclusion. Require the inline Search guidance to name `scopes` and all supported keys.

- [ ] **Step 2: Verify RED**

Run:

```powershell
& 'D:\tmp\github\agent-global-context\.venv\Scripts\python.exe' -m pytest tests/test_skill_adapter.py::test_research_relevance_is_an_explicit_recall_trigger tests/test_skill_adapter.py::test_ordinary_recall_is_small_and_value_gated -q --basetemp 'C:\tmp\agc-skill-red'
```

Expected: FAIL because the current Skill has only broad research wording and no exact filter recipe.

- [ ] **Step 3: Implement the smallest Skill wording change**

Add one concrete research-relevance trigger, state that generic explanations remain no-Recall, and show filters as list-valued keys with `scopes` rather than `scope`. Correct the matching typo in the approved design document.

- [ ] **Step 4: Verify GREEN and complete gates**

Run focused tests, Skill validation, the full pytest suite, strict UTF-8/no-BOM checks on changed text files, and `git diff --check`.

- [ ] **Step 5: Update Flow evidence and finish**

Record exact verification evidence in the Change Brief/working context, commit the scoped changes, merge to `main`, deploy with the existing installer, verify repository/active Skill hashes, validate the unchanged 22-memory store, and push `main`.
