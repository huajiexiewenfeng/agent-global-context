# Review Policy

## Goal

Move candidate memories through a controlled review path so staging does not become long-term noise.

## Review Outcomes

Each candidate should end in one of these states:

- `pending`: waiting for review.
- `promoted`: accepted and committed to long-term memory.
- `rejected`: rejected by the user or agent policy.
- `expired`: not reviewed within the retention period.

## Promotion Rules

Promote a candidate only when it has clear future value and passes write policy.

Default behavior by confidence:

- `confirmed`: can be promoted and committed directly.
- `observed`: may be promoted if the source is reliable and non-sensitive.
- `inferred`: requires user confirmation before promotion.
- `tentative`: do not promote unless confirmed by the user or upgraded through repeated evidence.

Sensitive candidates require sensitive policy. Secrets, tokens, passwords, private keys, and recovery codes must never be promoted.

## Review Workflow

1. Read `staging/inbox.md` and `staging/pending-review.md`.
2. Group candidates by status and priority.
3. Expire old `pending` candidates beyond `auto_capture.retention_days`.
4. For each candidate worth keeping:
   - confirm or ask the user when required
   - classify final `P0-P4`
   - choose destination
   - dedupe against existing memory
   - commit through write policy
   - mark candidate `promoted`
5. Mark rejected candidates `rejected` with a short reason.

## Candidate Promotion Metadata

When a candidate is promoted, update its staging entry:

```markdown
- status: promoted
- reviewed_at: YYYY-MM-DD
- promoted_to: path/to/file.md#memory-id
```

When rejected:

```markdown
- status: rejected
- reviewed_at: YYYY-MM-DD
- rejection_reason: short reason
```

When expired:

```markdown
- status: expired
- reviewed_at: YYYY-MM-DD
- expiration_reason: exceeded retention period
```

## Session Start Notice

At the start of substantial work, if pending candidates exist, the agent may say:

```text
You have N pending global context candidates.
```

Do not load candidate details unless the user asks to review them or they are directly relevant to the task.

## Review Prompt Thresholds

The agent should suggest review when:

- pending candidate count is greater than or equal to `review.prompt_when_pending_count_gte`
- oldest pending candidate age is greater than or equal to `review.prompt_when_oldest_pending_days_gte`
- `staging/pending-review.md` contains sensitive or high-impact candidates
- a pending candidate is directly relevant before a commit

Use a short, non-blocking prompt:

```text
You have N pending global context candidates. Review now, later, or ignore for this session?
```

Review should not block normal work unless sensitive/high-impact candidates require confirmation or retention policy requires expiration.

## Guardrails

- Do not treat pending candidates as facts.
- Do not promote sensitive memory without confirmation.
- Do not promote low-value or one-off task details.
- Do not keep an ever-growing inbox; expire old candidates.
