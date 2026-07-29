---
name: agent-global-context-recall
description: Use when starting or resuming substantial agent work, when the user asks to continue from memory or global context, or when a task depends on user background, preferences, coding habits, project context, environment facts, or cross-session continuity.
---

# Agent Global Context Recall

## Purpose

Load the smallest useful set of global context files for the current task.

## Default Memory Root

```text
~/.agent-global-context/
```

## Windows Encoding Safety

Memory Markdown is UTF-8. On Windows PowerShell 5.1, never inspect these files
with a bare `Get-Content`, because UTF-8 without a BOM may be decoded as the
legacy system code page and valid Chinese will appear as mojibake. Read with
`Get-Content -Raw -Encoding UTF8` or strict .NET UTF-8 decoding. Before
repairing apparently garbled text, verify the raw bytes; preserve valid UTF-8
and the existing BOM state when writing, then validate with explicit UTF-8.

## Workflow

1. Locate the memory root.
2. Read `config.yaml` if present.
3. Read `index.md`.
4. Load `P0` recall summary for substantial work.
5. Classify the current task:
   - technical decision or planning
   - code implementation, review, testing, or refactoring
   - environment or command work
   - project-specific work
   - continuation of recent work
6. Read only the relevant files.
7. Briefly tell the user which memory areas were loaded.

For project work, resolve the project id using explicit user bindings and `index.md` `Project Map` first, then Git remote slug, then current directory slug. Ask before relying on a new or ambiguous project id.

When multiple priorities match, load summaries first. Preserve active project context and directly relevant user preferences before old session details.

## Priority Loading

- `P0`: load summary by default for substantial work.
- `P1`: load for technical choices, planning, tools, architecture, and collaboration flow.
- `P2`: load for code work.
- `P3`: load for matching project or environment tasks.
- `P4`: load only for continuation requests such as "continue", "resume", or "last time".

If project-specific context conflicts with general user preferences, project conventions win inside that project unless the current user request says otherwise.

## Important Rules

- Prefer `Recall Summary` sections before full files.
- Do not load all sessions by default.
- Do not treat inferred or tentative memory as confirmed.
- If memory conflicts with the user's current request, follow the current request and mention the conflict briefly.

## When Memory Is Missing

If the memory root or files are missing, say so briefly and offer to initialize from the project template. Do not invent memory.
