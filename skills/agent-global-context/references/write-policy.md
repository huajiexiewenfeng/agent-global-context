# Write Policy

## Goal

Write durable context, not transcripts.

## Commit Conditions

A memory can be committed when at least one is true:

- The user explicitly asks to remember it.
- It will likely be useful in future sessions.
- It affects agent collaboration, technical choices, coding style, or project work.
- It comes from a reliable source such as files, command output, or repeated user behavior.

Committed `P0-P2` memory must include a rationale. `P3-P4` rationale is recommended but optional when the value is obvious from project commands, decisions, or task state.

## Write Destinations

- `P0`: `user/profile.md`
- `P1`: `user/preferences.md`
- `P2`: `user/coding-style.md`
- `P3` environment: `environment/*.md`
- `P3` project: `projects/<project-id>/*.md`
- `P4`: `projects/<project-id>/active.md` and `sessions/`

## Explicit Remember

If the user says "remember this", "write this to memory", or similar:

1. Classify priority.
2. Check sensitive policy.
3. Resolve project id if the memory is project-scoped.
4. Deduplicate against existing entries.
5. Write or update the best target file.
6. Update `index.md` if the new memory changes recall behavior.
7. Report the file changed.

## Project-Scoped Writes

For project-scoped memory, resolve `<project-id>` in this order:

1. Use any explicit project binding confirmed by the user.
2. Use `index.md` `Project Map`.
3. Use the Git remote repository slug.
4. Use the current directory name slug.
5. Ask the user if the project id is new or ambiguous.

## Dedupe and Update

Before appending, scan the target file for an existing memory with the same meaning.

Update an existing memory when the new information clarifies or refreshes the same fact, preference, habit, or decision.

Append only when the new information is distinct.

If new information replaces old information, mark the old item as `status: superseded` and add `supersedes` to the new item when useful.

## Session Compression

When compressing a session:

1. Create a session summary.
2. Update `active.md` with current state and next actions.
3. Promote only clear durable `P0-P3` context.
4. Leave noisy details out.

## Staging

If useful but unconfirmed, write to `staging/inbox.md`.

If sensitive or high-impact, write to `staging/pending-review.md` and ask the user.

Auto capture is enabled by default. It may write candidates to staging, but those candidates are not long-term memory. Use commit before promoting anything durable.
