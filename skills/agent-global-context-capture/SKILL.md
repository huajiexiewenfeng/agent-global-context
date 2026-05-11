---
name: agent-global-context-capture
description: Use when auto capture is enabled, when the agent notices durable user preferences, corrections, identity context, work environment facts, or project decisions that may be worth preserving as candidate global context.
---

# Agent Global Context Capture

## Purpose

Capture possible long-term context as candidates. Do not create long-term memory.

## Default Memory Root

```text
~/.agent-global-context/
```

## Workflow

1. Read `config.yaml`.
2. Stop if `auto_capture.enabled` is false.
3. Identify only strong capture signals:
   - user preferences or habits
   - durable project or workflow decisions
   - user corrections to agent behavior
   - stable identity-level context such as background, role, language, or work environment
4. Reject non-signals:
   - one-off task details
   - temporary state
   - undecided exploratory ideas
   - small talk or unrelated discussion
   - unconfirmed psychological, personality, motivation, or emotional-state inferences
5. Apply sensitive filtering during observe.
6. Write ordinary candidates to `staging/inbox.md`.
7. Write legitimate high-impact candidates requiring confirmation to `staging/pending-review.md`.
8. Never write secrets, tokens, passwords, private keys, or recovery codes.
9. If pending candidate count or age crosses review thresholds, suggest review without blocking normal work.

## Candidate Format

Use this template:

```markdown
## candidate-YYYYMMDD-HHMM-short-id

- source: conversation excerpt or behavior description
- proposed_priority: P1
- proposed_confidence: inferred
- category: preferences
- status: pending
- created_at: YYYY-MM-DD HH:mm

Candidate:
Candidate memory content.

Rationale:
Why this may be worth remembering.
```

## Confidence

- `confirmed` can only come from explicit user action.
- Auto capture confidence is capped at `observed`.
- Default to `inferred`.
- Use `tentative` for weak or ambiguous evidence.

## Recall Boundary

Candidates are not long-term facts. Do not use staged candidates as authoritative memory during normal work.

## Reporting

If a candidate is captured during normal work, keep the report minimal. Prefer a short note only when useful:

```text
Captured 1 global context candidate for later review.
```

If review thresholds are crossed, use:

```text
You have N pending global context candidates. Review now, later, or ignore for this session?
```
