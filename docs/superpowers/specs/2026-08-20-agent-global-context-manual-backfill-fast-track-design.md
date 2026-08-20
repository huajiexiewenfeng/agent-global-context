# Agent Global Context Manual Backfill Fast Track Design

**Date:** 2026-08-20
**Status:** Approved design; implementation planning pending
**Parent plans:**

- `2026-08-13-agent-global-context-capture-extractor-runner.md`
- `2026-08-13-agent-global-context-capture-host-rollout.md`

## Purpose

Make the existing Capture foundation useful sooner by delivering an explicit,
manual seven-day batch-capture workflow before background automation. The final
Capture architecture, acceptance criteria, privacy boundaries, Host rollout,
and human authorization gates remain unchanged. This design changes delivery
order, not the final product.

The first usable release must collect and classify many durable memories while
remaining bounded, inspectable, repeatable, and off by default.

## Delivery order

### Phase A: Manual batch-capture MVP

Move the minimum required pieces of Extractor/Runner Tasks 3–5 and Host route
diagnosis forward:

1. Durable actual-or-reserved Token accounting.
2. Read-only backfill preparation and an authorization digest.
3. An explicit, single-concurrency, one-shot backfill command.
4. Existing Capsule, isolated Extractor, persistence gate, Receipt,
   Observation, classification, deduplication, transaction, backup, and Hard
   Forget integration.
5. Installed-wheel verification against synthetic roots.

This phase does not install a service, register a scheduler, merge a Hook, or
activate a real profile automatically.

### Phase B: Runner reliability completion

Complete the original Runner design: retry/backoff, pause, backlog,
single-concurrency leasing, crash recovery, replay convergence, complete E2E
coverage, backup, and Forget regression.

### Phase C: Host automation

Complete inert installation, full route diagnosis, Windows supervision,
optional Hook merge, latency gates, Scanner-only fallback, operator actions,
and rollback.

### Phase D: Release and human-gated rollout

Complete the AC-01..20 release verifier, obtain explicit Scanner-only and
Shadow Backfill authorization, inspect samples, and separately authorize
continuous incremental Capture.

## Operator workflow

### Prepare

```text
agc-capture prepare-backfill --root <memory-root>
```

Preparation is read-only with respect to semantic model processing. It may
perform deterministic Source discovery and freeze the configured seven-day
Census, but it must not invoke the Extractor or spend model Tokens. Its single
content-free response reports:

- frozen Census identity and Revision counts;
- ready, completed, deferred, failed, and excluded counts;
- configured Extractor, model, and Provider boundary;
- the fixed backfill Token ceiling and current actual-or-reserved charge;
- a bounded batch recommendation; and
- an authorization digest.

The digest binds the Memory Root identity, frozen Census, Source bindings,
effective Capture configuration, Extractor identity/version/schema, model and
Provider boundary, and Token ceiling. Any bound change invalidates it.

### Run one batch

```text
agc-capture backfill --root <memory-root> \
  --authorization-digest <digest> \
  --max-items 20 \
  --once
```

The command validates the digest before any model call. It processes at most
`max-items` ready Revisions sequentially and returns a content-free batch
report. Repeating the command continues the same frozen Census. Completed,
excluded, quarantined, failed, deferred, and suppressed Revisions remain
visible and are never silently dropped.

## Per-Revision data flow

```text
frozen Census Revision
  -> acquire existing fenced Capture lease
  -> load only the target completed turn
  -> build the privacy-filtered Task Capsule in memory
  -> persist conservative Token reservation
  -> invoke the isolated Semantic Extractor exactly once
  -> validate strict extractor JSON
  -> apply persistence safety, relevance, atomicity, classification, and dedupe
  -> atomically commit 0..8 Observations, terminal Receipt, Ledger, and settlement
  -> release the lease and discard all content buffers
```

Classification uses the existing reviewed fields: `primary_category`, `kind`,
`scopes`, `project_scope`, `confidence`, `signal_type`, and `priority`. No new
taxonomy is introduced by the fast track.

## Token accounting

The frozen seven-day Census owns a fixed backfill pool capped at 100,000 model
Tokens. Before starting an Extractor process, the system durably reserves the
conservative maximum input plus output for that attempt under the Capture root
lock.

- Known complete Provider usage settles as `actual`.
- Missing, partial, invalid, timed-out, or crash-unknown usage consumes the
  reservation as `reserved`.
- Retries are separate attempts and remain charged.
- Active reservations survive restart and continue counting.
- Exact repeated settlement is idempotent; conflicting or duplicate settlement
  fails closed.
- Insufficient remaining budget causes no model call and leaves the Revision as
  `deferred_budget`.
- The incremental pool remains separate and disabled while its configured total
  is null.

Deterministic scanning, hashing, schema validation, and local reads are reported
separately and never counted as model Tokens.

## Failure behavior

A single Revision failure does not abort unrelated items in the same manual
batch. Each attempted Revision receives a truthful Receipt state and a fixed,
content-free error. Root integrity, budget corruption, stale authorization, or
an invalid frozen Census stops the batch before another model call.

No transcript excerpt, Capsule, prompt, raw stdout/stderr, invalid model output,
code, diff, log, stack trace, or rejected draft may be persisted or logged.
Existing managed backup, restore, revision/observation Hard Forget, and ordinary
Recall/Catalog isolation contracts remain in force.

## Safety scope

The fast track retains the already implemented safety floor:

- known-secret and sensitive-label pre-scrubbing;
- in-memory Capsule construction;
- isolated, schema-constrained Extractor subprocess;
- strict 0..8 draft validation;
- persistence safety, relevance, atomicity, and deduplication gates;
- content-free errors and diagnostics;
- Capture transactions, backup/restore, and Hard Forget; and
- the hard Token ceiling.

The following work is deferred, not removed:

- broader adversarial-corpus expansion beyond current reviewed gates;
- automatic background scheduling and full retry orchestration;
- Windows supervision and transactional Hook activation;
- installed Hook latency gating;
- complete Host readiness and activation-digest surfaces beyond manual
  backfill;
- the AC-01..20 release verifier; and
- real-profile Shadow/continuous rollout.

## Verification strategy

Development follows RED -> GREEN. Phase A requires:

1. AC-15 tests for concurrency, boundary, refusal, actual/reserved usage,
   invalid output, retry, crash/restart, and double settlement.
2. Manual preparation tests proving zero model calls and digest invalidation.
3. Manual backfill tests for 0, 1, 8, and over-8 drafts, classification,
   duplicate suppression, replay, item failure isolation, and budget deferral.
4. A persistence sentinel sweep proving no Capsule or forbidden content reaches
   managed storage.
5. Focused and adjacent regression suites during implementation.
6. One natural-order full suite and a clean-wheel installed synthetic
   `prepare-backfill -> backfill -> inspect` proof at the Phase A exit gate.

Full-suite execution is reserved for the phase exit unless a cross-cutting
change or failure requires it. Review scope is frozen to the approved design;
blocking correctness, privacy, data-loss, and authorization findings must be
fixed, while unrelated hardening is recorded for later phases.

## Phase A exit gate

Phase A is usable when all of the following are demonstrated from the installed
artifact against synthetic data:

- preparation invokes no model and returns a stable digest;
- stale or mismatched authorization invokes no model;
- a valid batch classifies and commits 0..8 Observations per Revision;
- exact replay creates no duplicate Observation or Token charge;
- crash-unknown calls remain conservatively charged after restart;
- total actual-or-reserved backfill usage never exceeds 100,000;
- Capture search/overview can inspect category, kind, scope, confidence, and
  processing state;
- forbidden persistence sentinel hits are zero;
- ordinary Recall and Catalog bytes remain unchanged; and
- no live Codex profile is accessed during development verification.

Running a real backfill remains a separate explicit user action using the
displayed authorization digest.
