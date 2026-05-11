# Dedupe and Update Policy

## Goal

Prefer updating durable memory over creating duplicates.

## Stable Memory IDs

Each long-term memory item uses a stable heading id:

```markdown
## markdown-first-memory
```

Use short lowercase ASCII ids:

- topic-oriented
- stable over time
- unique within the file

## Match Existing Memory

Before writing a new item, scan the target file for existing entries with:

- the same or similar heading id
- the same `type` and `scope`
- overlapping content
- the same user preference, project fact, decision, or coding habit

## Update Instead of Append

Update an existing memory when the new information:

- clarifies the same fact or preference
- changes confidence or source
- adds rationale or scope
- refreshes `updated_at`

Append a new memory only when it represents a distinct durable fact, preference, habit, decision, or task state.

## Supersede Instead of Delete

If a new memory replaces an old one:

1. Mark the old memory `status: superseded`.
2. Add `supersedes: <old-memory-id>` to the new memory when useful.
3. Keep both entries unless the user asks to delete history.

## Session State

For `P4` active state, update `active.md` rather than appending repeated task-state entries.

Session summaries may be appended as dated files under `sessions/`.

## Guardrails

- Do not create a new preference entry for every rephrasing.
- Do not split one coherent project decision across many tiny memories.
- Do not silently overwrite a confirmed memory with an inferred one.
- If new information conflicts with confirmed memory, ask or mark the conflict clearly.

