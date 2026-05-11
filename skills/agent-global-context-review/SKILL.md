---
name: agent-global-context-review
description: Use when reviewing, approving, rejecting, expiring, promoting, auditing, cleaning, or deduplicating staged global context candidates, pending review items, or stale temporary memory.
---

# Agent Global Context Review

## Purpose

Review candidate memories and move them toward `promoted`, `rejected`, or `expired`.

This skill does not bypass commit. Promotion means applying commit rules to write a formal memory item.

## Default Memory Root

```text
~/.agent-global-context/
```

## Workflow

1. Read `config.yaml`, `index.md`, `staging/inbox.md`, and `staging/pending-review.md`.
2. List pending candidates by priority, confidence, and category.
3. Expire candidates older than `auto_capture.retention_days`.
4. For each candidate:
   - promote if it is confirmed or reliably observed and non-sensitive
   - ask the user before promoting `inferred`, `tentative`, sensitive, or high-impact candidates
   - reject low-value, one-off, duplicate, or unsafe candidates
5. For promoted candidates:
   - classify final `P0-P4`
   - choose destination
   - dedupe/update existing memory
   - write formal memory item using commit rules
   - update candidate status to `promoted`
6. For rejected or expired candidates, update status and reason.

## Promotion Rules

- `confirmed`: can be promoted.
- `observed`: can be promoted when source is reliable and non-sensitive.
- `inferred`: requires user confirmation.
- `tentative`: do not promote unless confirmed or upgraded.

Secrets, tokens, passwords, private keys, and recovery codes are never promoted.

## Candidate Status Updates

Promoted:

```markdown
- status: promoted
- reviewed_at: YYYY-MM-DD
- promoted_to: path/to/file.md#memory-id
```

Rejected:

```markdown
- status: rejected
- reviewed_at: YYYY-MM-DD
- rejection_reason: short reason
```

Expired:

```markdown
- status: expired
- reviewed_at: YYYY-MM-DD
- expiration_reason: exceeded retention period
```

## User Interaction

When user confirmation is needed, ask concise questions. Do not batch too many ambiguous candidates into one question.

Suggest review when pending candidate count or oldest pending age crosses configured thresholds. Keep the prompt non-blocking unless sensitive/high-impact confirmation or expiration is required.

Example:

```text
This candidate looks like a long-term technical preference. Should I promote it to global context, keep it pending, or reject it?
```

## Reporting

After review, summarize:

- promoted count and destinations
- rejected count
- expired count
- candidates still pending
