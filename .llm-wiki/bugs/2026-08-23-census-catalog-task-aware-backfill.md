# Bug Brief: Census replay amplification and fragment-first backfill

## Summary

- title: Repeated frozen Census reads amplify I/O and fragment-first scheduling wastes bounded backfill capacity
- status: verified-installed; Codex App process reload pending
- flow_id: `2026-08-23-census-catalog-task-aware-backfill`
- severity: high operational latency and low candidate yield; no formal-memory corruption observed
- owner: Codex
- updated_at: 2026-08-23

## Routing

- intent: design, implement, test, package, and install the approved quality-first Capture optimization
- primary_stage: project-fix
- secondary_bridges: brainstorming, writing-plans, test-driven-development, verification-before-completion
- confidence: high
- reason: current source and production metadata directly reproduce repeated Census member decoding and discovery-order revision selection
- next_gate: Scope Lock Gate followed by TDD execution
- routed_at: 2026-08-23

## Source

- path/url/log/user_report: user report that small AGC backfills take abnormally long and produce very few useful memories
- source_proxy: production metadata counts and current source inspection; no raw Session content persisted here
- sensitivity: content-free operational metadata only

## Symptom

The production Capture root accumulated highly overlapping frozen runs. Before the fix, `CaptureStore.read_snapshot()` decoded repeated members on every read and the runner sorted ready receipts by discovery time and receipt id, so a bounded batch could consume several slots on weak turns from one task. The final production acceptance found 116 frozen runs and 915 unique revisions.

## Expected

Normal reads should scale with frozen run manifests plus unique revisions. A manual batch should distribute work across tasks and select locally stronger Capsules, with no more than three selected revisions from one task per invocation. Existing authorization, privacy, review, budget, and formal-memory boundaries remain unchanged.

## Evidence

- Current `capture_store.py` calls `frozen_revision_records()` from `read_snapshot()`, which visits every member directory, then calls `_read_frozen_run()` again while collecting `census_runs`.
- Current `capture_runner.py` selects `ready_revisions()` by `(discovered_at, receipt_id)` and slices before any task grouping or local signal ranking.
- Production metadata: 110 run directories, 74,175 member JSON files, 852 unique revision filenames, 70 unique tasks.
- Recent bounded runs spent 15.5 to 19.7 minutes for five attempted revisions and produced zero or one observation.

## Reproduction

- status: reproduced
- command_or_steps: current-source inspection plus production member/run/unique-key counts; regression tests will encode member-decode counts and deterministic selection behavior before implementation
- observed: repeated member decoding is proportional to run count multiplied by overlapping membership; selection has no per-task cap or signal rank
- expected: one-time full validation followed by a canonical hot catalog; deterministic task-aware selection
- limitation: production performance acceptance must remain read-only and perform zero model calls

## Scope

- active:
  - `agc_runtime/paths.py`
  - `agc_runtime/capture_store.py`
  - `agc_runtime/capture_runner.py`
  - `agc_runtime/capture_forget_service.py`
  - `agc_runtime/capture_forget_transaction.py`
  - `agc_runtime/admin_service.py`
  - focused Capture tests, release version, Capture operations documentation, spec, plan, and lifecycle records
- read_only:
  - Capture contracts, schema, ledger, Capsule/safety/extractor implementation, Source Adapter contract, existing production Capture root, installed Runtime configuration
- candidate:
  - installer/release scripts if the existing immutable-runtime path requires a version-only adjustment
- excluded:
  - Extractor prompt or model changes, pre-Capsule/persistence policy relaxation, automatic promotion, raw Session persistence, Hook enablement, continuous Runner enablement, live historical backfill, and unrelated repository refactors
- escalation_history: none

## Diagnosis

The latency is structural local I/O amplification, not primarily model latency. Frozen runs intentionally overlap seven-day windows, but the hot read path treats every run member as fresh unique truth on every snapshot. Low yield is amplified by revision-level discovery ordering before local semantic availability is known.

## External Findings

None. The fix does not depend on another project or remote contract.

## Fix Plan

Implement the approved `census-catalog` derived namespace with atomic rebuild and hot validation against run manifests; invalidate it transactionally during Hard Forget and exclude it from backup. Add deterministic local Capsule ranking and round-robin task selection capped at three per task per invocation. Execute `docs/superpowers/plans/2026-08-23-agc-task-aware-census-catalog.md` using RED/GREEN tests.

## Verification

- status: passed-agent-local
- commands_or_checks: full repository suite before the final packed-layout optimization; complete Capture regression after it; package build and inspection; immutable local install; installed/source hashes; read-only production cold/hot benchmark and zero-delta formal-memory/observation/budget checks
- result_summary: 1334 full-suite tests passed before the final Capture-only packed-layout change; 1064 Capture tests then passed after it; wheel/sdist built; Runtime 0.4.1 installed; production cold rebuild took 26.172 seconds and hot reads took 8.370 and 6.122 seconds with zero hot member JSON reads
- limitation: no external model call is authorized for this implementation acceptance
- residual_risk: cold-member tampering after a valid catalog build is detected by explicit full audit/backup verification rather than every hot status read

## Flow Record

| Step | Status | Evidence | Updated |
|---|---|---|---|
| source | done | production metadata counts and current source call paths | 2026-08-23 |
| design | done | `docs/superpowers/specs/2026-08-23-agc-task-aware-census-catalog-design.md` | 2026-08-23 |
| plan | done | `docs/superpowers/plans/2026-08-23-agc-task-aware-census-catalog.md` | 2026-08-23 |
| development | done | commits `5e9b61a` through `3ed1089` | 2026-08-23 |
| testing | passed-agent-local | `.llm-wiki/verification/2026-08-23-census-catalog-task-aware-backfill.md` | 2026-08-23 |
| archive | active | handoff created; current Codex App process must restart to load the new MCP route | 2026-08-23 |

## Artifacts

- `docs/superpowers/specs/2026-08-23-agc-task-aware-census-catalog-design.md`
- `docs/superpowers/plans/2026-08-23-agc-task-aware-census-catalog.md`
- `.llm-wiki/verification/2026-08-23-census-catalog-task-aware-backfill.md`
- `.llm-wiki/handoff/2026-08-23-census-catalog-task-aware-backfill-handoff.md`

## Open Questions

None. The user approved the recommended per-invocation cap of three locally high-signal completed turns per task and requested design plus development completion.

## Residual Risk

The first catalog construction remains a full cold validation. Existing frozen evidence remains unchanged, so disk file count is not reduced. The installed route is 0.4.1, but the Codex App process that was already running retained the previous MCP process and must be restarted before in-app verification can close the archive gate.
