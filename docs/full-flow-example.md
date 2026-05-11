# Full Flow Example

This example shows how a candidate moves from auto capture to long-term memory.

## 1. User Signal

User says:

```text
I usually want design discussion before implementation.
```

## 2. Auto Capture

Because `auto_capture.enabled` is true, the agent writes a candidate to:

```text
staging/inbox.md
```

Candidate:

```markdown
## candidate-20260511-0930-design-before-implementation

- source: User said "I usually want design discussion before implementation."
- proposed_priority: P1
- proposed_confidence: inferred
- category: preferences
- status: pending
- created_at: 2026-05-11 09:30

Candidate:
The user usually prefers design discussion before implementation.

Rationale:
This may affect whether the agent should propose a design and wait for confirmation before editing files.
```

## 3. Review

Later, the user says:

```text
Review my pending global context candidates.
```

The review skill sees that this candidate is `inferred`, so it asks for confirmation:

```text
This candidate looks like a long-term collaboration preference. Should I promote it to global context, keep it pending, or reject it?
```

User confirms:

```text
Promote it.
```

## 4. Commit

The candidate is committed to:

```text
user/preferences.md
```

Formal memory:

```markdown
## prefers-design-before-implementation

- type: preference
- priority: P1
- confidence: confirmed
- source: user_explicit
- scope: global
- status: active
- created_at: 2026-05-11
- updated_at: 2026-05-11

The user prefers design discussion before implementation for substantial work.

Rationale:
This affects whether the agent should propose a design and wait for confirmation before making changes, especially for architecture, workflow, or larger code changes.
```

## 5. Candidate Status Update

The staging entry is updated:

```markdown
- status: promoted
- reviewed_at: 2026-05-11
- promoted_to: user/preferences.md#prefers-design-before-implementation
```

## 6. Future Recall

On future substantial work, `agent-global-context-recall` may load:

```text
user/profile.md          # P0 summary
user/preferences.md      # P1 when planning or technical decisions are relevant
```

The promoted memory can now influence behavior. The original candidate no longer acts as an unconfirmed fact.

