---
name: agent-global-context-commit
description: Use when the user asks an agent to remember something, write to global context, update memory, compress the current session, save durable preferences, record project decisions, or preserve cross-session context.
---

# Agent Global Context Commit

## Purpose

Write durable, useful context into the global context system.

## Default Memory Root

```text
~/.agent-global-context/
```

## Workflow

1. Locate the memory root.
2. Read `config.yaml`, `index.md`, and the relevant target file.
3. Classify the information as `P0-P4`.
4. Check whether it is sensitive or high-impact.
5. Resolve project id for project-scoped memory.
6. Deduplicate or update an existing entry when possible.
7. Write a Markdown memory item with metadata and rationale when required.
8. Update `index.md` when recall behavior changes.
9. Report changed files.

## Classification

- `P0`: user background and identity-level context -> `user/profile.md`
- `P1`: technical or collaboration preference -> `user/preferences.md`
- `P2`: coding habit or engineering style -> `user/coding-style.md`
- `P3`: project or environment knowledge -> `environment/` or `projects/<project-id>/`
- `P4`: current task state -> project `active.md` or `sessions/`

## Project Resolution

For project-scoped memory, use explicit user bindings and `index.md` `Project Map` first, then Git remote slug, then current directory slug. Ask the user before creating memory for a new or ambiguous project id.

## Dedupe and Update

Before appending, scan the target file for an existing memory with the same meaning. Update the existing memory when the new information clarifies or refreshes the same fact, preference, habit, or decision. Append only when the information is distinct.

If a new memory replaces an old one, mark the old memory `status: superseded` and use `supersedes` on the new entry when useful.

## Confidence

Use `confirmed` for explicit user statements or approvals. Use `observed` for reliable files, command output, configuration, or repeated visible behavior. Use `inferred` for agent-derived context that is not directly confirmed. Use `tentative` for weak, ambiguous, or likely temporary context.

## Sensitive Gate

Ask before committing sensitive context. Never store secrets, tokens, passwords, private keys, or recovery codes.

Use this prompt:

```text
This may be sensitive long-term context. Should I write it to the global context, stage it for review, or skip it?
```

## Session Compression

When asked to compress a session:

1. Write a dated summary under `projects/<project-id>/sessions/`.
2. Update `projects/<project-id>/active.md`.
3. Promote only durable `P0-P3` information that has clear future value.
4. Do not save the full transcript.

Treat `P4` active state as temporary. Remove completed next actions and avoid carrying stale blockers into unrelated tasks.

## Memory Item Template

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

## Reporting

After writing, summarize:

- What was written.
- Which file changed.
- Whether anything was staged or skipped.
