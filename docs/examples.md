# Examples

## Remember a Preference

User:

```text
Remember that I prefer Markdown-first memory with only small YAML config files.
```

Expected action:

- Classify as `P1`.
- Write to `user/preferences.md`.
- Include source, confidence, and rationale.

## Continue Previous Work

User:

```text
Continue from my global context.
```

Expected action:

- Read `index.md`.
- Load `P0` recall summary.
- Identify the current project if possible.
- Load relevant `P3` project files and `P4` active state if continuation is requested.

## Compress a Session

User:

```text
Compress this session into global context.
```

Expected action:

- Write a dated session summary under the current project.
- Update `active.md`.
- Promote only durable `P0-P3` facts that meet the write policy.

## Capture a Candidate

User:

```text
I usually want design discussion before implementation.
```

Expected action:

- If `auto_capture.enabled` is true, write a candidate to `staging/inbox.md`.
- Use `proposed_priority: P1`.
- Use `proposed_confidence: inferred` or `observed`, depending on evidence.
- Do not write to `user/preferences.md` yet.

## Promote a Candidate

User:

```text
Review my staged global context candidates and promote the useful ones.
```

Expected action:

- Read `staging/inbox.md` and `staging/pending-review.md`.
- Promote confirmed or reliable observed candidates.
- Ask before promoting inferred, tentative, sensitive, or high-impact candidates.
- Commit promoted candidates to the correct long-term memory file.
- Mark promoted candidates with `promoted_to` and `reviewed_at`.

## Review Prompt

When pending candidates reach the configured threshold:

```text
You have 6 pending global context candidates. Review now, later, or ignore for this session?
```

Expected action:

- If the user chooses review, use `agent-global-context-review`.
- If the user chooses later, continue the current task.
- If the user ignores for the session, do not prompt again during the same session unless sensitive/high-impact candidates require confirmation.
