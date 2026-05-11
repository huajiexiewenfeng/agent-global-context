# Memory Schema

Use Markdown entries with small metadata blocks.

## Required Fields

- `type`: `profile | preference | coding_style | environment | project | decision | task | session`
- `priority`: `P0 | P1 | P2 | P3 | P4`
- `confidence`: `confirmed | inferred | observed | tentative`
- `source`: `user_explicit | conversation | repo_scan | command_output | agent_inference`
- `scope`: `global | project:<project-id> | session`
- `status`: `active | superseded | rejected | archived`
- `created_at`: `YYYY-MM-DD`
- `updated_at`: `YYYY-MM-DD`

## Optional Fields

- `review_after`: `YYYY-MM-DD`
- `supersedes`: memory id
- `related`: memory ids
- `expires_after`: `YYYY-MM-DD` for temporary `P4` state

## Entry Template

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

Content goes here.

Rationale:
Why this information matters for future agent behavior.
```

`Rationale` is required for `P0-P2`. It is recommended but optional for `P3-P4`, where the value may be obvious from project commands, decisions, or task state.

## Session Summary Template

```markdown
# Session YYYY-MM-DD HH:mm

## Goal

## Key Decisions

## Updated Memories

## Current State

## Next Actions
```
