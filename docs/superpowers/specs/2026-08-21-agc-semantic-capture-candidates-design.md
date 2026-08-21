# AGC Semantic Capture Candidates Design

## Context

Production backfill processed three historical Codex App turns with `gpt-5.6-sol`, but all three receipts completed with `zero_reason=extractor_empty`. At least one source turn contained reusable project decisions. Current pre-Capsule filtering admits only a bounded fixed grammar of atomic user propositions, so colloquial or compound Chinese decisions can be removed before semantic extraction.

The product priority is to collect and classify useful candidate memories early. Safety hardening may continue later, but candidate collection must remain reviewable and must not automatically change formal memory.

## Goals

- Preserve the existing strict path for direct, deterministic memory propositions.
- Let bounded, scrubbed, plain-language user context reach semantic extraction.
- Store semantic interpretations only as tentative candidate observations.
- Bind every candidate to verbatim evidence and the originating project scope.
- Avoid model calls and token reservations when a Capsule has no extractable context.
- Distinguish pre-Capsule emptiness, extractor emptiness, and post-extraction filtering in diagnostics.
- Keep automatic promotion out of scope.

## Non-goals

- General natural-language truth verification.
- Automatic promotion into formal P0-P4 memory files.
- Relaxing secret, credential, code, private-path, subagent, or target-turn isolation controls.
- Retrying or rewriting already completed production receipts without a separate explicit operation.
- Changing the memory taxonomy beyond using the existing project/work categories and tentative confidence.

## Selected Architecture: Two Capture Lanes

### Direct lane

The existing controlled proposition grammar remains authoritative for direct candidates. Evidence must match a deterministic proposition, and the persisted statement must represent the same canonical proposition. Existing confidence and assertion-mode rules remain unchanged.

### Semantic tentative lane

The pre-Capsule gate may retain a user message unit when it:

- belongs to the target main-task turn;
- survives existing secret and prohibited-content scrubbing;
- is bounded by the existing codepoint and token limits; and
- is assertive plain language rather than a question, hypothetical, log, command payload, or serialized/code structure.

Such context remains transient Capsule input. A model-derived candidate using this context must:

- use `assertion_mode=agent_inferred`;
- use `confidence=tentative`;
- contain one atomic, personally or project-relevant statement accepted by the existing persisted-statement grammar;
- cite verbatim evidence that exists in the Capsule;
- preserve the exact Capsule `project_scope`; and
- pass the existing safety, sensitivity, deduplication, and observation-count gates.

Semantic candidates are observations only. They are not formal memories and are never promoted automatically.

## Data Flow

1. The Codex App source adapter isolates one completed main-task turn.
2. The pre-Capsule gate removes untrusted structure, secrets, private paths, code-like payloads, non-target turns, and subagent content.
3. Controlled atomic propositions enter the direct lane. Other bounded assertive plain-language user units enter the semantic tentative lane.
4. If the resulting Capsule has no user signals, decisions, reusable methods, or next steps, the runner completes it locally as `no_durable_signal` without reserving model budget or invoking the extractor.
5. Otherwise, the Codex App bundled runtime invokes `gpt-5.6-sol` with the schema-constrained extractor.
6. The persistence gate validates direct candidates with exact proposition equivalence. It validates semantic candidates only when they are `agent_inferred`, `tentative`, atomic, scope-bound, safe, and backed by verbatim Capsule evidence.
7. Accepted drafts are stored as candidate observations; formal memory remains unchanged.

## Diagnostics and Budget Accounting

Zero-observation outcomes must be distinguishable:

- `no_durable_signal`: no eligible Capsule context; no extractor call and no model budget charge.
- `extractor_empty`: eligible context reached the model, but the model returned no drafts.
- `all_filtered_safety` or `all_filtered_policy`: drafts were returned but rejected after extraction.
- `all_duplicates_within_revision`: valid drafts duplicated another draft in the same revision.

The one-shot/backfill response must continue reporting extractor call count, charged/reserved usage, observation count, and filtering counts so acceptance can verify where loss occurs.

## Failure Handling

- Source identity or target-turn ambiguity remains fail-closed.
- Unsafe or structurally untrusted content remains excluded before the model call.
- Invalid model output remains retryable extractor failure under existing behavior.
- A semantic draft that violates tentative-mode, evidence, atomicity, scope, or safety rules is filtered rather than promoted or silently rewritten.
- Empty Capsules complete locally and deterministically; they do not consume a retry or model reservation.

## Test Strategy

TDD must cover:

1. A real-style compound Chinese project decision reaches the semantic Capsule lane.
2. The same input previously produces no semantic context, proving RED before implementation.
3. A tentative `agent_inferred` atomic draft backed by the compound verbatim evidence passes persistence.
4. The same draft marked `direct` or non-tentative is rejected.
5. Questions, hypotheticals, secrets, code, paths, subagent records, and cross-turn records remain excluded.
6. An empty Capsule completes as `no_durable_signal` with zero extractor calls and zero charged tokens.
7. A non-empty semantic Capsule still reports `extractor_empty` when the extractor deliberately returns no drafts.
8. Focused Capture tests, the broader Capture regression suite, package build, immutable runtime install, and a bounded isolated live Pilot all pass.
9. The live Pilot produces at least one tentative observation, zero silent loss, and no formal-memory promotion.

## Rollout and Acceptance

1. Implement and verify in `codex/fix-semantic-capture-empty`.
2. Build a new wheel and install it into a new immutable runtime venv.
3. Run an isolated Pilot against a copied, hash-verified historical Session; do not replay production receipts during source validation.
4. Confirm at least one `agent_inferred`/`tentative` observation and verify production formal memory remains unchanged.
5. Update the Bug Brief and verification record.
6. Merge the verified branch into `main` with a non-destructive fast-forward or merge commit as repository state permits.

## Compatibility

Existing direct candidates, schemas, formal memory, Hard Forget behavior, and review/promotion workflows remain compatible. The behavioral expansion is limited to additional tentative observations and local no-signal short-circuiting.
