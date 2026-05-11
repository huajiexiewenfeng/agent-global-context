# Write Policy

## Goal

Write durable context, not transcripts.

## Commit Conditions

A memory can be committed when at least one is true:

- The user explicitly asks to remember it.
- It will likely be useful in future sessions.
- It affects agent collaboration, technical choices, coding style, or project work.
- It comes from a reliable source such as files, command output, or repeated user behavior.

Every committed memory must include a rationale.

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
3. Deduplicate against existing entries.
4. Write or update the best target file.
5. Update `index.md` if the new memory changes recall behavior.
6. Report the file changed.

## Session Compression

When compressing a session:

1. Create a session summary.
2. Update `active.md` with current state and next actions.
3. Promote only clear durable `P0-P3` context.
4. Leave noisy details out.

## Staging

If useful but unconfirmed, write to `staging/inbox.md`.

If sensitive or high-impact, write to `staging/pending-review.md` and ask the user.

