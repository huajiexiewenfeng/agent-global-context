# AGC Quality-First Memory Formalization Design

## Context

AGC Capture now produces safe, reviewable `CollectedObservation` records from historical Codex App sessions. Those records are intentionally atomic and bounded, so some are short, ambiguous in isolation, or useful only when combined with adjacent observations and existing formal memory.

The current runtime stops at candidate observation storage. It does not yet consolidate observations into useful Memory Items. Treating every observation as a memory would create noise; simply lengthening observations would weaken Capture's evidence boundary. The next phase therefore formalizes a small number of observations into complete, decision-relevant Memory Items while keeping the user confirmation boundary already required for durable writes.

The product priority is content quality and early usefulness. Automatic background promotion, a large proposal subsystem, and broader security redesign are deliberately deferred.

## Goals

- Turn a small batch of related Capture observations into self-contained formal-memory drafts.
- Preserve exact grounding: every claim in a draft must be supported by selected observations or by an existing formal Memory Item being updated.
- Prefer one coherent memory or an update to an existing memory over several short duplicates.
- Separate useful drafts, insufficient-context observations, and noise.
- Show the exact draft in Codex App and require explicit user confirmation before changing formal memory.
- Prevent terminally reviewed observations from appearing in ordinary future review batches.
- Reuse the current Codex App model and the existing three-tool AGC surface.

## Non-goals

- Changing the `CollectedObservation` schema or making observations longer.
- Automatically promoting observations in the background.
- Adding a fourth public MCP tool, a vector database, embeddings, or a proposal database.
- Persisting full draft text, model reasoning, raw session text, or new copies of evidence in runtime review records.
- Reopening raw Codex Session files or sending additional raw Session content to a provider.
- Building proposal version chains, scheduled consolidation, or a new UI.
- Expanding Hard Forget semantics beyond the existing managed Capture and formal-memory boundaries.
- Solving every ambiguous observation by guessing from surrounding conversation.

## Selected Architecture

Formalization is a Codex App review workflow, not a second extraction pipeline.

The Codex App AGC review workflow orchestrates the flow. In this v2 repository it is packaged inside the single public `agent-global-context` skill; the retired standalone `agent-global-context-review` skill is not reintroduced. The workflow uses `agc.read` to retrieve a small set of unreviewed Capture observations and a compact set of relevant active Memory Cards. The active Codex App model performs semantic grouping, deduplication, and drafting. The rollout model boundary is `gpt-5.6-sol`, resolved by Codex App rather than by an npm-installed Codex CLI. Runtime remains responsible for deterministic validation, persistence, idempotency, and the existing `agc.write` commit rules.

The public tool surface remains exactly:

- `agc.read`
- `agc.write`
- `agc.admin`

No separate Codex CLI subprocess or extractor model call is introduced. The review uses only content already exposed to the active Codex App turn through bounded AGC reads.

## Minimal Tool Contract Changes

The MCP surface remains three tools, but their strict request schemas gain the minimum fields needed to close the review loop:

- `agc.read capture_search` excludes terminally reviewed observations by default and accepts `include_reviewed: true` for an explicit audit search. Exact `capture_get` remains available regardless of review outcome.
- Existing formal-memory write actions accept an optional `capture_observation_ids` list. It contains 1–20 duplicate-free existing observation IDs that contributed to the confirmed write. Runtime validates the entire list before mutation.
- `agc.write capture_review` records only `needs_context` or `discard` for 1–20 duplicate-free existing observation IDs. Its exact request shape is `{"action":"capture_review","observation_ids":["co_<sha256>"],"outcome":"needs_context"}`. It accepts no Memory Item body, free-form reason, or raw evidence.

`draft` is never recorded through `capture_review`. It is recorded only as part of a successful existing `confirm`, `update`, or reinforce-compatible `observe` request carrying `capture_observation_ids`. This prevents a previewed or failed proposal from becoming terminal.

## Review Outcomes

Every selected observation receives exactly one review outcome:

- `draft`: the observation contributed to a complete formal-memory draft. This outcome becomes terminal only after the user confirms the exact draft and the corresponding `agc.write` succeeds.
- `needs_context`: the observation may be useful, but its current wording cannot support a self-contained memory without guessing.
- `discard`: the observation is a duplicate, one-off detail, temporary fact, or otherwise lacks future decision value.

Preview alone is non-mutating. If the user postpones a draft, the contributing observations remain eligible for a later review. If the user rejects it permanently, the workflow records `discard`. A failed formal-memory write records no terminal review outcome.

## Quality Contract

A draft is eligible to show to the user only when all of these conditions hold:

1. **Grounded:** every factual or preference claim is traceable to selected observations or to the existing formal Memory Item being updated. No missing subject, object, scope, or purpose is invented.
2. **Self-contained:** the draft can be understood in a future session without the source transcript. Dangling references such as “该 skill”, “这个方案”, “最终目标”, or “上面的设置” are forbidden unless resolved by explicit evidence already present in a matched formal memory.
3. **Decision-relevant:** the memory can change a future answer, implementation choice, workflow, or continuation decision. Mere historical narration does not qualify.
4. **Deduplicated:** the workflow searches relevant active memories before proposing a new ID. It updates or reinforces the best semantic match instead of appending a rephrasing.
5. **Bounded:** one draft represents one coherent durable idea. Related observations may be merged, but unrelated preferences or facts are not bundled merely to make a longer memory.
6. **Policy-valid:** sensitivity, confidence, lifecycle, scope, rationale, and destination comply with the existing AGC write and review policies.

Draft body sections remain the existing schema-v2 sections: `Memory Card`, `Full Meaning`, `Application Boundary`, and `Rationale`. Length is determined by completeness, not by a minimum word count.

## Data Flow

1. The user starts a review in Codex App.
2. `agc.read capture_search` returns a small page of eligible observations. The default review path excludes observations with terminal review receipts; an explicit audit search may include them.
3. `agc.read capture_get` retrieves the selected observation records. No raw Session is reopened.
4. Progressive formal-memory recall loads only relevant active Memory Cards: overview, search, then exact items when needed.
5. The Codex App model groups related observations and assigns `draft`, `needs_context`, or `discard`.
6. Local structural checks reject drafts with unsupported observation IDs, missing required Memory Item fields, forbidden dangling references, invalid sensitivity, or an invalid update target.
7. Codex App shows the user the exact proposed Memory Item, its source observation IDs, and whether the write is new, update, or reinforce.
8. Only explicit confirmation authorizes the existing `agc.write confirm`, `agc.write update`, or `agc.write observe` with `reinforce` disposition. The request carries the contributing `capture_observation_ids`.
9. After a successful formal-memory write, Runtime stores content-free terminal review receipts for every contributing observation. `needs_context` and `discard` receipts are stored through `agc.write capture_review` only after the user accepts those classifications.
10. The next default review skips observations with terminal receipts.

## Minimal Review Receipt

Runtime stores one small JSON receipt per observation at `.runtime/capture/reviews/<observation-id>.json`. The logical schema is:

```json
{
  "schema_version": 1,
  "observation_id": "co_<sha256>",
  "outcome": "draft | needs_context | discard",
  "target_memory_id": "memory-id or null",
  "reviewed_at": "RFC 3339 UTC timestamp"
}
```

Rules:

- The filename is derived from the validated observation ID.
- `target_memory_id` is required for a terminal `draft` outcome and must identify the successfully written formal memory.
- `target_memory_id` is `null` for `needs_context` and `discard`.
- The receipt contains no observation statement, Memory Item body, raw evidence, prompt, or model output.
- Receipt publication is idempotent. An existing conflicting receipt fails closed rather than being overwritten.
- Runtime validates all contributing observations before a formal-memory mutation. A successful memory write is authoritative even if a later receipt publication step reports a repairable warning; a failed memory write never publishes `draft` receipts.
- Managed backup, restore, validation, and exact observation Hard Forget include the receipt using their existing all-managed-copies rules.

This is deliberately not a persisted proposal system. The exact proposal exists only in the active Codex App review until the user confirms it.

## User Interaction

The review should be compact and content-first. For each draft, show:

- a one-line explanation of why the observations belong together;
- whether it creates, updates, or reinforces a formal memory;
- the complete proposed Memory Item content; and
- the source observation IDs.

Ask for confirmation on a small number of drafts at a time. Do not mix an ambiguous `needs_context` item into a broader confirmation question. For `needs_context`, state exactly which referent or scope is missing; do not ask the user to validate guessed content.

## Failure Handling

- A missing or unreadable observation is omitted and reported without affecting other review candidates.
- An ambiguous reference produces `needs_context`, never a guessed draft.
- A formal-memory match that is uncertain is shown as unresolved rather than silently treated as new.
- Invalid or policy-rejected Memory Item Markdown returns to preview; it is never marked reviewed.
- If `agc.write` fails, Codex App must say that the memory was not saved and must not write a terminal review receipt.
- If the formal-memory write succeeds but receipt publication fails, the memory remains committed. The response carries a stable warning and a later repair pass may create the missing content-free receipt after verifying the target memory.
- Preview, cancellation, and deferred confirmation leave the formal-memory catalog and review receipts unchanged.

## Security and Privacy Boundary

- Review reads only already-managed Capture observations and formal-memory cards through host-bound AGC tools.
- It does not reopen historical Session JSONL, bypass Capture redaction, or broaden source access.
- It does not launch a second Codex CLI process or silently switch models.
- Existing secret and sensitive-memory policies remain authoritative.
- Proposal text and model reasoning are not persisted before confirmation.
- Formal memory changes remain visible, explicit, and user-confirmed.

## Golden Acceptance Batch

The current six production observations are the first acceptance fixture. Before any confirmation, the active formal-memory count remains 24.

| Observation content | Required result |
| --- | --- |
| “Codex 自动完成发布” plus “人工只确认发布” | Merge into one self-contained publishing-workflow draft with an explicit final human confirmation boundary. Do not create two memories. |
| “使用 1Panel” | Produce one bounded environment-context draft. Do not invent server identity, topology, version, or deployment details. |
| “最终目标保持不变” | Match and update the existing AGC goal only when that formal memory resolves the referent. Do not create a new vague goal. |
| “Docker Desktop 数据放在 D 盘” | `discard` for this batch as a temporary/local setup detail, unless the user explicitly reclassifies it as durable. |
| “该 skill 调用当前本地 harness” | `needs_context`; the skill identity is absent, so no draft may guess it. |

Acceptance also requires:

- no draft contains a dangling reference;
- preview creates or updates zero formal memories;
- only user-confirmed drafts call the formal write path;
- confirmed updates reuse the matched stable memory ID;
- each terminally handled observation receives one content-free review receipt;
- ordinary later review does not resurface terminally handled observations;
- Capture observation content and count remain unchanged by formalization.

## Test Strategy

Implementation follows TDD and covers:

1. Receipt schema validation, canonical paths, atomic publication, idempotent replay, and conflicting replay.
2. Default Capture search exclusion for terminal review receipts, `include_reviewed` audit behavior, and exact `capture_get` access.
3. Preview purity: no formal Memory Item, catalog entry, event, or review receipt changes.
4. Successful new/update/reinforce writes with one or several `capture_observation_ids`, followed by terminal receipt publication.
5. `capture_review` acceptance for `needs_context` and `discard`, plus rejection of `draft`, free-form content, duplicates, and unknown observation IDs.
6. Write failure and receipt-publication failure ordering.
7. Local rejection of missing observation IDs, invalid target IDs, incomplete Memory Item Markdown, sensitive proposals, and forbidden dangling references.
8. Exact backup, restore, validate, and observation-forget handling for review receipts.
9. The six-observation golden acceptance fixture and the unchanged pre-confirmation count of 24 formal memories.
10. Focused tests, the full pytest suite, package build, immutable runtime install, and an isolated live Codex App review using `gpt-5.6-sol`.

Windows tests must use a short child path under `D:\tmp_test` because deep Capture paths can exceed the host's legacy path limit. Tests that compare repository resource bytes must run from an LF-preserving checkout or explicitly account for the host's `core.autocrlf=true` setting.

## Rollout

1. Implement and verify on `codex/formalization-quality-first` in the isolated worktree.
2. Run the golden batch as a non-mutating preview against an isolated Memory Root copied from production state.
3. Verify all three outcome classes, proposed dedupe targets, complete draft content, and formal-memory count of 24.
4. Present the preview to the user.
5. Apply only explicitly confirmed writes, then verify target memory IDs, catalog consistency, and content-free review receipts.
6. Build and install a new immutable AGC runtime only after automated and isolated acceptance passes.
7. Sync the verified commit to GitHub through the existing release workflow.

## Deferred Work

- Background or scheduled consolidation.
- Automatic promotion without user confirmation.
- Persisted proposal bodies, proposal histories, or multi-stage approval databases.
- Semantic vector search and embeddings.
- Rich review UI.
- Cross-provider deletion guarantees or broader Hard Forget redesign.
- Automatic recovery of ambiguous pronouns from raw Session history.

These can be added only when real review volume demonstrates a need. They are not prerequisites for collecting and using high-quality memory now.
