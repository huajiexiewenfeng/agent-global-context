# Recall Budget Policy

## Goal

Control how much memory is loaded when multiple priority levels match the task.

## Principle

Priority decides importance. Relevance decides inclusion. Budget decides depth.

Do not fill the context window just because more memory exists.

## Default Budget Order

For substantial work:

1. Load `index.md`.
2. Load `P0` `Recall Summary`.
3. Load task-relevant summaries in this order:
   - project `P3`
   - user `P1`
   - user `P2`
   - continuation `P4`
4. Load detailed entries only when summaries are insufficient.

## Per-Level Depth

- `P0`: summary only by default. Do not load sensitive details unless explicitly needed.
- `P1`: summary first; load specific entries for technical choices.
- `P2`: summary first; load specific entries for implementation, review, testing, or refactoring.
- `P3`: load project summaries for matching projects; load detailed commands or decisions only when relevant.
- `P4`: load `active.md` and at most the configured number of recent session summaries.

## Tight Budget Order

When context budget is tight:

1. Keep the current user request.
2. Keep project-specific `P3` context for the active project.
3. Keep directly relevant `P1/P2` preferences.
4. Drop old `P4` session details first.
5. Drop unrelated global preferences next.

## Future Work

The MVP does not enforce token counting. Agents should follow this as a qualitative loading policy. A future version may add hard per-level limits.

