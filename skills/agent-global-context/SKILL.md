---
name: agent-global-context
description: Use when personal long-term memory may materially improve an important decision, personalized writing or collaboration, learning or research planning, growth review, or cross-task continuation; when evaluating whether a project or technology fits the user's research direction; when the user requests durable personal recall or storage; or when AGC maintenance is requested. Skip self-contained factual or mechanical tasks.
---

# Agent Global Context

AGC is optional personal long-term memory. Memory enters context only through an explicit tool read.

## Decide

Read only when missing personal context could materially worsen decision, expression, continuity, or growth support. The LLM decides relevance and application; Runtime only provides deterministic data and persistence. Complexity alone is not a trigger. Self-contained tasks and tasks governed by current evidence do not call `agc.read`. Current instructions and facts always outrank memory.

Treat requests that evaluate whether a project, repository, tool, or technology fits the user's research, learning, or long-term goals as Recall cases. For a generic explanation or overview with no personal relevance, do not call `agc.read`.

## Recall and Apply

Use `overview → search → get → history/evidence`; stop as soon as enough context is available.

1. Start with `{"action":"overview"}`.
2. Search with relevant `filters` and `limit` at most `5`. Filters use only `kind`, `scopes`, `decision_impact`, `sensitivity`, `exposure`, and `confidence`; every value is a list of strings, for example `{"scopes":["research"]}`. The current `query` is a literal substring match; omit it unless an exact short term is known.
3. Use `get` only when a card is insufficient; use history/evidence only for change, conflict, or provenance.

Apply memory only when it materially changes decision, expression, continuity, or growth support. Choose exactly one mode: `adapt`, `continue`, or `grow`. If there is no material change, discard the recalled item without surfacing it.

Capture observations are evidence, not formal memory. They are not automatically injected into context or automatically promoted. Use `capture_overview`, then a narrow `capture_search`, and `capture_get` only when task history is materially relevant. See the [Capture operations guide](../../docs/capture-operations.md) for activation, status, exclusions, cost, rollback, and hard-forget procedures.

## Write, Admin, and Failure

Explicit durable non-sensitive changes may call `agc.write`; sensitive persistence stays disabled. `agc.admin` is for maintenance and migration, not ordinary Recall. Read [the tool contract](references/tool-contract.md) only for write/admin or an exact schema. Read [the application policy](references/application-policy.md) only for `grow`, conflicts, or ambiguous boundaries.

If `agc.read` fails, continue the main task. A failed write is not saved and must not be reported as saved.
