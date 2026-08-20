# AGC Tool Contract

The Host binds the memory root once. The LLM supplies only a `request` mapping;
no action accepts a filesystem root parameter. Only `agc.read`, `agc.write`,
and `agc.admin` are public.

The LLM chooses whether to recall, semantic relevance, `disposition`,
`match_memory_id`, and whether memory applies. Runtime performs deterministic
validation, policy, persistence, lifecycle, idempotency, backup, and recovery.

## Response Envelope

Every tool returns a schema-v2 mapping:

```yaml
schema_version: 2
tool: agc.read | agc.write | agc.admin
action: <action>
status: accepted | deferred | rejected_policy | needs_adjudication | failed
data: {}
warnings: []
error: null | {code: <stable-code>, message: <safe-message>}
```

Malformed requests and unsupported actions return a failure envelope rather
than raising across the tool boundary.

## `agc.read`

`overview` has no fields beyond `action`. `search` accepts optional `query`
(non-empty string), `filters` (mapping), and `limit` (integer, 1–100; default
20). Every filter value is a list of strings. Supported filters are `kind`,
`scopes`, `decision_impact`, `sensitivity`, `exposure`, and `confidence`.
Unknown filter names are rejected rather than ignored.
`get`, `history`, and `evidence` require an exact non-empty `id`.

| Action | Example request |
| --- | --- |
| `overview` | `{"action":"overview"}` |
| `search` | `{"action":"search","query":"planning","filters":{"kind":["preference"],"scopes":["work"],"decision_impact":["high"],"sensitivity":["normal","personal"],"exposure":["core_card","scoped_card"],"confidence":["confirmed"]},"limit":20}` |
| `get` | `{"action":"get","id":"memory-id"}` |
| `history` | `{"action":"history","id":"memory-id"}` |
| `evidence` | `{"action":"evidence","id":"memory-id"}` |
| `capture_overview` | `{"action":"capture_overview"}` |
| `capture_search` | `{"action":"capture_search","filters":{"project":["project-id"],"category":["preference"]},"limit":20}` |
| `capture_get` | `{"action":"capture_get","observation_id":"co_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}` |

Recall progressively: `overview → search → get → history/evidence`. Stop when
the current task has enough context.

The Capture read actions use the same `agc.read` tool. Capture does not add a fourth MCP tool.
Capture observations are reviewable evidence, not formal Memory
Items. `capture_search` accepts strict filters (`task`, `project`, `category`,
`kind`, `scope`, `state`, `sensitivity`, and a `time` range), a limit from 1
to 100, and an opaque cursor. `capture_get` accepts exactly one
`observation_id` or `receipt_id`.

## Reusable `agc.write` Schemas

### Observation Envelope

`observation` is a strict mapping: every path below is required, and unknown
fields at these nested levels are rejected.

| Field path | Type and contract |
| --- | --- |
| `observation_id` | non-empty string; stable observation/candidate id |
| `source.ref` | non-empty source reference |
| `source.revision` | non-empty source revision |
| `source.content_hash` | lowercase 64-character SHA-256 hex string |
| `source.observed_at` | non-empty observation timestamp |
| `assertion.subject` | non-empty string; use `user` for user assertions |
| `assertion.mode` | `direct`, `behavior_observed`, `agent_inferred`, or `quoted` |
| `assertion.modality` | `asserted`, `hypothetical`, `question`, or `example` |
| `proposal.disposition` | `ignore`, `new`, `reinforce`, `update`, `conflict`, or `need_more_evidence` |
| `proposal.match_memory_id` | non-empty string or null; required semantically for reinforce/update/conflict |
| `proposal.kind` | non-empty kind; persistent items use identity/principle/preference/interest/capability/goal/pattern/context |
| `proposal.scopes` | list of non-empty scope strings |
| `proposal.temporal_type` | non-empty temporal type; persistent items use durable/evolving/goal_bound/contextual/derived/episodic |
| `proposal.sensitivity` | `normal`, `personal`, `sensitive`, or `secret`; sensitive/secret persistence is rejected |
| `proposal.rationale` | non-empty rationale |
| `proposal.requested_confidence` | `tentative`, `observed`, `confirmed`, or `disputed` |
| `evidence.count` | non-negative integer |
| `evidence.distinct_sessions` | non-negative integer |
| `evidence.time_span_days` | non-negative integer |

Example:

```json
{
  "observation_id": "confirm-before-change-observation",
  "source": {
    "ref": "codex-task:example",
    "revision": "r1",
    "content_hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "observed_at": "2026-07-29T00:00:00Z"
  },
  "assertion": {
    "subject": "user",
    "mode": "direct",
    "modality": "asserted"
  },
  "proposal": {
    "disposition": "new",
    "match_memory_id": null,
    "kind": "principle",
    "scopes": ["work"],
    "temporal_type": "durable",
    "sensitivity": "normal",
    "rationale": "May improve future high-impact decisions.",
    "requested_confidence": "confirmed"
  },
  "evidence": {
    "count": 1,
    "distinct_sessions": 1,
    "time_span_days": 0
  }
}
```

### Memory Item Markdown

`memory_markdown` is a non-empty string containing a complete schema-v2 Memory
Item. It is required for `new`/`update` persistence, `confirm`, and `update`.
Its id, kind, scopes, temporal type, sensitivity, and confidence must agree
with the Observation Envelope and action.

Every item uses the common lifecycle, confidence, temporal, recall,
sensitivity, provenance, and four body-section fields shown in the complete
examples below. Add these top-level fields when the condition applies:

| Condition | Required fields and enums |
| --- | --- |
| `kind: interest` | `topic`; `intensity` = `emerging`, `low`, `medium`, or `high`; `trend` = `rising`, `stable`, `declining`, or `dormant`; `motivation` |
| `kind: capability` | `domain`; `polarity` = `strength` or `growth_area`; `current_level` |
| capability `polarity: growth_area` with `recall.exposure: core_card` or `scoped_card` | non-empty `goal_refs` identifying active goals |
| `kind: identity`, `sensitivity: personal`, and `recall.exposure: core_card` | non-empty `policy_reason` |

#### Complete principle Memory Item

```markdown
---
schema_version: 2
id: confirm-before-irreversible-change
kind: principle
subkind: decision_standard
lifecycle:
  status: active
confidence:
  level: confirmed
temporal:
  type: durable
  valid_from: "2026-07-29"
  last_observed: "2026-07-29"
  review_after:
recall:
  prior: medium
  decision_impact: high
  exposure: scoped_card
  scopes: [work]
  applies_when: [irreversible_change]
  not_when: [trivial_task]
  freshness_policy: event_driven
sensitivity: normal
provenance:
  created_at: "2026-07-29"
  updated_at: "2026-07-29"
  confirmed_at: "2026-07-29"
  evidence_refs: [codex-task:example]
---
## Memory Card

Confirm before irreversible changes.

## Full Meaning

Use an explicit confirmation boundary for high-impact irreversible work.

## Application Boundary

Do not add friction to trivial or safely reversible work.

## Rationale

This can prevent unintended high-impact changes.
```

#### Complete interest Memory Item

```markdown
---
schema_version: 2
id: reliable-ai-systems-interest
kind: interest
subkind: research_topic
topic: reliable AI systems
intensity: high
trend: rising
motivation: Improve correctness in agent workflows.
lifecycle:
  status: active
confidence:
  level: observed
temporal:
  type: evolving
  valid_from: "2026-07-01"
  last_observed: "2026-07-29"
  review_after: "2026-10-29"
recall:
  prior: medium
  decision_impact: medium
  exposure: scoped_card
  scopes: [learning, research]
  applies_when: [research_planning]
  not_when: [unrelated_task]
  freshness_policy: periodic
sensitivity: normal
provenance:
  created_at: "2026-07-01"
  updated_at: "2026-07-29"
  confirmed_at:
  evidence_refs: [codex-task:example-interest]
---
## Memory Card

Interest in reliable AI systems.

## Full Meaning

Research interest currently emphasizes correctness and reliability in agent workflows.

## Application Boundary

Apply to relevant learning or research planning, not unrelated tasks.

## Rationale

This can improve topic and example selection.
```

#### Complete capability Memory Item

```markdown
---
schema_version: 2
id: distributed-debugging-growth
kind: capability
subkind: engineering_skill
domain: distributed systems debugging
polarity: growth_area
current_level: developing
goal_refs: [goal-improve-distributed-debugging]
lifecycle:
  status: active
confidence:
  level: observed
temporal:
  type: goal_bound
  valid_from: "2026-07-01"
  last_observed: "2026-07-29"
  review_after: "2026-09-29"
recall:
  prior: medium
  decision_impact: medium
  exposure: scoped_card
  scopes: [work, learning]
  applies_when: [debugging_plan]
  not_when: [unrelated_task]
  freshness_policy: goal_bound
sensitivity: normal
provenance:
  created_at: "2026-07-01"
  updated_at: "2026-07-29"
  confirmed_at:
  evidence_refs: [codex-task:example-capability]
---
## Memory Card

Developing distributed-systems debugging.

## Full Meaning

Current growth work focuses on diagnosing failures across distributed components.

## Application Boundary

Offer support only when it advances the linked active goal.

## Rationale

The linked goal guards proactive growth suggestions.
```

## `agc.write` Actions

In the compact examples, `"<ObservationEnvelope object>"` and
`"<v2 Memory Item Markdown>"` mean values matching the complete reusable
schemas above.

| Action | Example request |
| --- | --- |
| `observe` | `{"action":"observe","observation":"<ObservationEnvelope object>","memory_markdown":"<v2 Memory Item Markdown>"}` |
| `observe_batch` | `{"action":"observe_batch","items":[{"observation":"<ObservationEnvelope object>","memory_markdown":"<v2 Memory Item Markdown>"}]}` |
| `propose` | `{"action":"propose","observation":"<ObservationEnvelope object>"}` |
| `confirm` | `{"action":"confirm","observation":"<ObservationEnvelope object>","memory_markdown":"<v2 Memory Item Markdown>"}` |
| `update` | `{"action":"update","observation":"<ObservationEnvelope object>","memory_markdown":"<v2 Memory Item Markdown>"}` |
| `supersede` | `{"action":"supersede","observation":"<ObservationEnvelope object>","memory_id":"memory-id"}` |
| `archive` | `{"action":"archive","observation":"<ObservationEnvelope object>","memory_id":"memory-id"}` |
| `reject` | `{"action":"reject","candidate_id":"candidate-id"}` |
| `forget` | `{"action":"forget","memory_id":"memory-id","authorization":"explicit_user_request","suppression_scope":"precise_scope","verification_terms":["exact managed-content term"]}` |
| `capture_forget` | `{"action":"capture_forget","authorization":"explicit_user_request","target":{"type":"observation","observation_id":"co_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}}` |

Action-specific rules:

- An accepted formal-memory mutation refreshes `catalog.json` and `catalog.md`
  automatically. Ordinary callers do not invoke `agc.admin rebuild_catalog`
  after `agc.write`.
- If the source-of-truth Memory, Event, and Receipt commit succeeds but the
  derived Catalog refresh fails, the write remains `accepted` and includes the
  stable warning `catalog_refresh_failed`. Use `agc.admin validate` and
  `rebuild_catalog` for repair; do not report the accepted memory as lost.
- `observe`: `memory_markdown` is required only when disposition is `new` or
  `update`; omit it for `reinforce`, `conflict`, `need_more_evidence`, and
  `ignore`.
- `observe_batch`: `items` is a list of observe request mappings; Runtime sets
  each nested action to `observe` and returns one envelope per item.
- `propose`: records a policy-eligible candidate; it does not need
  `memory_markdown`.
- `confirm`: Runtime forces disposition `new` and requested confidence
  `confirmed`; supply matching Memory Item Markdown.
- `update`: Runtime forces disposition `update`; `proposal.match_memory_id`
  and the Memory Item id must match.
- `supersede`/`archive`: `observation.proposal.match_memory_id` is always
  required. The optional request-level `memory_id` is only a locator alias; if
  present it must equal the proposal match and never substitutes for a missing
  proposal match.
- `reject`: requires the exact candidate id.
- `forget`: requires exact `memory_id`, authorization equal to
  `explicit_user_request`, and a precise lowercase `suppression_scope`;
  `verification_terms` is an optional list of non-empty strings (default `[]`).
- `capture_forget`: requires `explicit_user_request` and exactly one Capture
  target: an observation id, or a complete adapter/source/task/revision key.
  It removes matching managed Capture copies and rewrites managed backups; it
  never means provider-side deletion.

#### Complete supersede request

```json
{
  "action": "supersede",
  "memory_id": "confirm-before-irreversible-change",
  "observation": {
    "observation_id": "supersede-confirm-before-change",
    "source": {
      "ref": "doc-example:supersede",
      "revision": "r1",
      "content_hash": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
      "observed_at": "2026-07-30T00:00:00Z"
    },
    "assertion": {
      "subject": "user",
      "mode": "direct",
      "modality": "asserted"
    },
    "proposal": {
      "disposition": "update",
      "match_memory_id": "confirm-before-irreversible-change",
      "kind": "principle",
      "scopes": ["work"],
      "temporal_type": "durable",
      "sensitivity": "normal",
      "rationale": "A newer confirmed standard replaces this item.",
      "requested_confidence": "confirmed"
    },
    "evidence": {
      "count": 1,
      "distinct_sessions": 1,
      "time_span_days": 0
    }
  }
}
```

#### Complete archive request

```json
{
  "action": "archive",
  "memory_id": "confirm-before-irreversible-change",
  "observation": {
    "observation_id": "archive-confirm-before-change",
    "source": {
      "ref": "doc-example:archive",
      "revision": "r1",
      "content_hash": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
      "observed_at": "2026-07-31T00:00:00Z"
    },
    "assertion": {
      "subject": "user",
      "mode": "direct",
      "modality": "asserted"
    },
    "proposal": {
      "disposition": "update",
      "match_memory_id": "confirm-before-irreversible-change",
      "kind": "principle",
      "scopes": ["work"],
      "temporal_type": "durable",
      "sensitivity": "normal",
      "rationale": "The superseded item is retained only as history.",
      "requested_confidence": "confirmed"
    },
    "evidence": {
      "count": 1,
      "distinct_sessions": 1,
      "time_span_days": 0
    }
  }
}
```

## `agc.admin`

The Host-bound root is never present in these requests. `restore.backup_path`
is optional: omit it to use the latest managed backup; when supplied, it must
be a non-empty path string. `migrate` currently returns a deterministic
deferred envelope because the migration adapter is outside this package.

| Action | Example request |
| --- | --- |
| `init` | `{"action":"init"}` |
| `validate` | `{"action":"validate"}` |
| `rebuild_catalog` | `{"action":"rebuild_catalog"}` |
| `backup` | `{"action":"backup"}` |
| `restore` | `{"action":"restore","backup_path":"D:/managed/agc-backup.zip"}` |
| `migrate` | `{"action":"migrate"}` |
| `capture_status` | `{"action":"capture_status"}` |

`agc.admin` is maintenance and migration, not a Recall shortcut.
`capture_status` is content-free operational evidence for the Host-bound root.
