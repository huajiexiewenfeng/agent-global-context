# Auto Capture Policy

## Goal

Auto capture implements the `observe` stage. It lets an agent notice signals that may have long-term value and write candidate entries to staging.

Auto capture does not create long-term memory. Anything that becomes long-term memory must still pass through commit.

## Default

Auto capture is enabled by default.

When enabled, it only creates candidates.

Users can disable it with:

```yaml
auto_capture:
  enabled: false
```

## Capture Triggers

Capture candidates only when these signals appear:

- The user states a preference or habit.
- The user makes a durable decision.
- The user corrects agent behavior.
- The user shares stable identity-level context such as background, role, or work environment.

Do not capture:

- one-off task details
- temporary state
- exploratory ideas that are not decided
- small talk, greetings, or unrelated discussion
- unconfirmed psychological, personality, motivation, or emotional-state inferences

## Candidate Entry Format

Entries in `staging/inbox.md` should include at least:

- `source`: conversation excerpt or behavior description that triggered the candidate
- `proposed_priority`: proposed `P0-P4`
- `proposed_confidence`: confidence value
- `rationale`: why this may be worth remembering
- `created_at`: capture time
- `status`: `pending | promoted | rejected | expired`

## Confidence Rules

- `confirmed` can only come from explicit user action: commit skill, "remember this", or user approval.
- Auto capture confidence is capped at `observed`.
- Default auto capture confidence is `inferred`.
- Weak evidence uses `tentative`.
- Confidence upgrades require explicit events and should record the upgrade source.
- Do not silently rewrite confidence.

## Sensitive Filtering

Sensitive memory rules apply during `observe`, not only during `commit`.

Never write secrets, credentials, private keys, tokens, passwords, or recovery codes to `staging/inbox.md` or `pending-review.md`.

Personal sensitive context should not go to `inbox.md`. If it may be legitimate to remember, route it to `pending-review.md` and ask the user.

Unconfirmed psychological, personality, motivation, or emotional-state inferences should be dropped by default. Do not stage them unless the user explicitly asks.

## Review and Decay

Candidates need an exit path:

- At the start of a session, if pending candidates exist, the agent may give a short notice such as "You have N pending memory candidates."
- After adding a candidate, if pending count or oldest pending age crosses configured review thresholds, suggest review.
- Candidates older than the configured retention period should be marked `expired`.
- `expired` candidates do not enter long-term memory.
- Review, promotion, rejection, and cleanup are handled by `agent-global-context-review`.

## Recall Behavior

`staging/inbox.md` is not part of default recall.

Exceptions:

- The user explicitly asks to review candidates.
- A candidate is highly relevant to the current task.

Even then, candidates must not be treated as confirmed long-term facts.

## Configuration

```yaml
auto_capture:
  enabled: true
  categories:
    preferences: true
    corrections: true
    identity: true
    project_decisions: true
  retention_days: 14
  recall_inbox: false
review:
  session_start_notice: true
  prompt_when_pending_count_gte: 5
  prompt_when_oldest_pending_days_gte: 7
  max_candidates_per_review: 10
```

## Operating Principle

Auto capture may notice.
Staging may hold.
Review may approve.
Commit may remember.
Recall must not trust unconfirmed candidates.
