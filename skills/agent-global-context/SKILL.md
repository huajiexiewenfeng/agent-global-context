---
name: agent-global-context
description: Use when designing, configuring, auditing, or modifying an AI agent global context system, especially when the task involves cross-session user context, priority-based recall, Markdown memory files, or long-term agent continuity.
---

# Agent Global Context

## Purpose

Agent Global Context is a Markdown-first context layer for AI agents. It preserves only key information that should influence future behavior across sessions.

Use this skill as the shared policy reference for the recall and commit skills.

## Core Principle

Store context that changes future decisions. Do not store everything.

Good global context helps an agent answer:

- Who is the user, at a durable and useful level?
- How does the user prefer to work?
- What technical and coding habits should guide implementation?
- What project and environment facts should not be rediscovered every session?
- What recent task state is needed to continue work?

## Memory Root

Default memory root:

```text
~/.agent-global-context/
```

On Windows:

```text
C:\Users\<user>\.agent-global-context\
```

## Priority Model

- `P0`: user background and identity-level context.
- `P1`: technical and collaboration preferences.
- `P2`: coding habits and engineering style.
- `P3`: project and work-environment knowledge.
- `P4`: temporary session state.

## Memory Item Format

Long-term memory items should be Markdown entries:

```markdown
## memory-id

- type: preference
- priority: P1
- confidence: confirmed
- source: user_explicit
- scope: global
- status: active
- created_at: YYYY-MM-DD
- updated_at: YYYY-MM-DD

Memory content.

Rationale:
Why this should influence future agent behavior.
```

## Write Rules

Write long-term memory only when the information:

- Is likely to be reused in future sessions.
- Affects collaboration, technical choices, code style, or project work.
- Comes from the user explicitly, reliable project files, command output, or repeated observation.
- Has a clear rationale for `P0-P2`; `P3-P4` rationale is recommended but optional when obvious.

Do not write:

- Full chat transcripts.
- Ordinary small talk.
- One-off logs or already-solved errors with no future value.
- Sensitive data without confirmation.
- Unconfirmed psychological, personality, or motivation judgments.

## Recall Rules

Recall starts with `index.md`, then loads only relevant context:

- Always prefer `Recall Summary` sections before full files.
- Read `P0` summary by default for substantial work.
- Read `P1` for technical decisions or workflow choices.
- Read `P2` for code work.
- Read `P3` when a project or environment is relevant.
- Read `P4` only when continuing recent work.

## References

Read these references only when needed:

- `references/directory-layout.md`
- `references/schema.md`
- `references/auto-capture-policy.md`
- `references/priority-policy.md`
- `references/project-resolution.md`
- `references/recall-budget-policy.md`
- `references/recall-policy.md`
- `references/write-policy.md`
- `references/dedupe-policy.md`
- `references/confidence-policy.md`
- `references/conflict-policy.md`
- `references/index-schema.md`
- `references/lifecycle-policy.md`
- `references/review-policy.md`
- `references/sensitive-policy.md`
