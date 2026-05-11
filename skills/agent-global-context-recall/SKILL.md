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

## Priority Loading

- `P0`: load summary by default for substantial work.
- `P1`: load for technical choices, planning, tools, architecture, and collaboration flow.
- `P2`: load for code work.
- `P3`: load for matching project or environment tasks.
- `P4`: load only for continuation requests such as "continue", "resume", or "last time".

## Important Rules

- Prefer `Recall Summary` sections before full files.
- Do not load all sessions by default.
- Do not treat inferred or tentative memory as confirmed.
- If memory conflicts with the user's current request, follow the current request and mention the conflict briefly.

## When Memory Is Missing

If the memory root or files are missing, say so briefly and offer to initialize from the project template. Do not invent memory.

