# Agent Global Context Minimal Recall Activation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Codex reliably discover AGC for high-value personal-context tasks, apply recalled memory only when it changes the result, and keep unrelated tasks quiet.

**Architecture:** Keep the Runtime and memory store unchanged. Improve the always-visible Skill description, place the minimal read path and value gate directly in `SKILL.md`, and load the large tool contract only for write/admin work. Deploy the verified repository Skill with the existing repeatable installer.

**Tech Stack:** Markdown Agent Skill, Python 3.10+, pytest 9.1.1, PowerShell local installer, MCP `agc.admin` validation.

## Global Constraints

- Do not modify `agc_runtime/`, the memory Schema, Search behavior, Capture, Trace, or Eval.
- Preserve LLM ownership of whether to recall, what to read, and whether a recalled item applies.
- Preserve failure-open behavior: Recall failure must not block the main task.
- Keep the frontmatter description free of personal facts and at no more than 80 words.
- Use the existing `overview → search → get → history/evidence` actions; use filters and `limit <= 5`, and do not send long natural-language `query` values to the current literal matcher.
- Do not mutate the 22 existing formal memories while deploying this change.
- Forward-testing with subagents is not part of this plan because the current session does not have user authorization to dispatch them; the existing usage audit is the RED behavioral baseline, and post-deployment verification uses real future tasks.

---

### Task 1: Make Recall Discovery and Application Explicit

**Files:**
- Modify: `tests/test_skill_adapter.py`
- Modify: `skills/agent-global-context/SKILL.md`

**Interfaces:**
- Consumes: the existing public Skill name `agent-global-context` and existing MCP actions `agc.read`, `agc.write`, and `agc.admin`.
- Produces: an always-visible high-value trigger description and an inline ordinary-Recall contract that requires no Runtime change.

- [ ] **Step 1: Add failing tests for the missing trigger and value-gate behavior**

Add these tests after `test_capability_description_is_thin_and_contains_no_personal_fact`:

```python
def test_capability_description_names_recall_triggers_and_exclusions():
    description = _frontmatter_description(_skill_text()).casefold()
    expected_triggers = (
        "important decision",
        "personalized writing",
        "collaboration",
        "learning",
        "research",
        "growth review",
        "cross-task continuation",
    )

    assert all(trigger in description for trigger in expected_triggers)
    assert re.search(
        r"skip.*(?:self-contained|factual|mechanical)", description
    )


def test_ordinary_recall_is_small_and_value_gated():
    raw = _skill_text()
    text = _normalized_skill_text()

    assert re.search(r'\{\s*"action"\s*:\s*"overview"\s*\}', raw)
    assert re.search(r"search.*filters.*limit.*5", text)
    assert "literal substring" in text
    assert re.search(
        r"tool-contract\.md.*(?:write|admin)", text
    )
    assert "decision, expression, continuity, or growth support" in text
    assert re.search(r"no material change.*discard", text)
```

- [ ] **Step 2: Run the focused test file and verify RED**

Run:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_skill_adapter.py -q
```

Expected: the two new tests fail because the current description is generic and the current body does not contain the compact read contract or explicit value gate. Existing tests remain passing.

- [ ] **Step 3: Replace `SKILL.md` with the minimal implementation**

Use this complete content:

```markdown
---
name: agent-global-context
description: Use when personal long-term memory may materially improve an important decision, personalized writing or collaboration, learning or research planning, growth review, or cross-task continuation; when the user requests durable personal recall or storage; or when AGC maintenance is requested. Skip self-contained factual or mechanical tasks.
---

# Agent Global Context

AGC is optional personal long-term memory. Memory enters context only through an explicit tool read.

## Decide

Read only when missing personal context could materially worsen decision, expression, continuity, or growth support. Complexity alone is not a trigger. Self-contained tasks and tasks governed by current evidence do not call `agc.read`. Current instructions and facts always outrank memory.

## Recall and Apply

Use `overview → search → get → history/evidence`; stop as soon as enough context is available.

1. Start with `{"action":"overview"}`.
2. Search with relevant `filters` and `limit` at most `5`. The current `query` is a literal substring match; omit it unless an exact short term is known.
3. Use `get` only when a card is insufficient; use history/evidence only for change, conflict, or provenance.

Apply memory only when it materially changes decision, expression, continuity, or growth support. Choose exactly one mode: `adapt`, `continue`, or `grow`. If there is no material change, discard the recalled item without surfacing it.

## Write, Admin, and Failure

Explicit durable non-sensitive changes may call `agc.write`; sensitive persistence stays disabled. `agc.admin` is for maintenance and migration, not ordinary Recall. Read [the tool contract](references/tool-contract.md) only for write/admin or an exact schema. Read [the application policy](references/application-policy.md) only for `grow`, conflicts, or ambiguous boundaries.

If `agc.read` fails, continue the main task. A failed write is not saved and must not be reported as saved.
```

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_skill_adapter.py -q
```

Expected: all tests in `tests/test_skill_adapter.py` pass.

- [ ] **Step 5: Validate the Skill and run the full test suite**

Run:

```powershell
$env:PYTHONUTF8='1'
& '.\.venv\Scripts\python.exe' 'C:\Users\admin\.codex-clean-20260710\skills\.system\skill-creator\scripts\quick_validate.py' 'skills\agent-global-context'
& '.\.venv\Scripts\python.exe' -m pytest -q
git diff --check
```

Expected:

- Skill validation reports success.
- The complete pytest suite passes.
- `git diff --check` produces no output.

- [ ] **Step 6: Commit the tested Skill change**

Run:

```powershell
git add -- skills/agent-global-context/SKILL.md tests/test_skill_adapter.py
git commit -m "feat: improve agc recall activation"
```

Expected: one commit containing only the Skill and its tests.

---

### Task 2: Deploy and Verify the Active Codex Skill

**Files:**
- Deploy from: `skills/agent-global-context/SKILL.md`
- Replace through installer: `C:/Users/admin/.agents/skills/agent-global-context/SKILL.md`
- Preserve: `C:/Users/admin/.agent-global-context-v2/`
- Preserve or update only through installer: `C:/Users/admin/.codex-clean-20260710/config.toml`

**Interfaces:**
- Consumes: the tested repository Skill and existing repeatable `scripts/install-local.ps1` installer.
- Produces: an active Codex Skill byte-identical to the repository version while retaining the same memory root and three-tool MCP registration.

- [ ] **Step 1: Run the repeatable installer with explicit paths**

Run:

```powershell
& '.\scripts\install-local.ps1' `
  -RepositoryRoot 'D:\tmp\github\agent-global-context' `
  -SkillsRoot 'C:\Users\admin\.agents\skills' `
  -CodexConfig 'C:\Users\admin\.codex-clean-20260710\config.toml' `
  -MemoryRoot 'C:\Users\admin\.agent-global-context-v2' `
  -InstallRoot 'C:\Users\admin\.agent-global-context-runtime'
```

Expected: installer succeeds, retains the same memory root, backs up replaced active files when needed, and leaves exactly one public AGC Skill.

- [ ] **Step 2: Verify the deployed Skill and UTF-8 content**

Run:

```powershell
$repositorySkill = 'D:\tmp\github\agent-global-context\skills\agent-global-context\SKILL.md'
$activeSkill = 'C:\Users\admin\.agents\skills\agent-global-context\SKILL.md'
$repositoryHash = (Get-FileHash -LiteralPath $repositorySkill -Algorithm SHA256).Hash
$activeHash = (Get-FileHash -LiteralPath $activeSkill -Algorithm SHA256).Hash
if ($repositoryHash -ne $activeHash) { throw 'Active AGC Skill differs from repository Skill.' }
$strictUtf8 = New-Object System.Text.UTF8Encoding($false, $true)
[System.IO.File]::ReadAllText($activeSkill, $strictUtf8) | Out-Null
```

Expected: hashes match and strict UTF-8 decoding succeeds.

- [ ] **Step 3: Validate the unchanged memory store**

Call `agc.admin` with:

```json
{"action":"validate"}
```

Expected: `status: accepted`, `invalid_count: 0`, and the formal memory count remains `22`.

- [ ] **Step 4: Verify repository state and push `main`**

Run:

```powershell
git status --short
git log -3 --oneline
git push origin main
```

Expected: worktree is clean before push; `main` contains the design, plan, and tested Skill commits; push succeeds without a force update.

- [ ] **Step 5: Start post-deployment observation**

Restart Codex and use a new task so Skill metadata is reloaded. Over the next 10 tasks where personal context could materially change the result, later audit:

1. whether AGC was called when relevant;
2. whether recalled memory changed decision, expression, continuity, or growth support; and
3. whether unrelated tasks remained quiet.

Expected: this step creates no new Runtime, Capture, Trace, or Eval subsystem. It supplies the real-usage evidence for deciding whether Search needs a later change.
