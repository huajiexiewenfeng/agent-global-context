# Change Brief: agc-capture-eval-pilot

## Summary

- title: AGC Capture Eval Pilot
- status: executing
- flow_id: `agc-capture-eval-pilot`
- parent_flow_id: `agc-capture-trace-bridge`
- why: Evaluate whether completed Capture observations are faithful, durable, atomic, correctly classified, and low-noise while keeping Trace generic and preventing Eval from mutating AGC memory.

## Sources

- `docs/superpowers/plans/2026-08-30-agc-capture-eval-pilot.md`
- source-verified public contracts and implementation plan from the Agent Runtime Modules repository

## Active Scope

- AGC-owned safe Capture evidence and content-free item reports
- one item-level Trace event per immutable completed receipt
- AGC EvidenceResolver and Trace-to-EvalCase adapter
- packaged `agc.capture-quality:1` Profile
- manual prepare/authorized Capture Eval CLI
- focused/full tests, docs, and 0.4.4 release candidate metadata

## Read-Only Scope

- Capture Store snapshots, Source Adapter Capsule reconstruction, existing Runner/CLI behavior
- Trace v0.1 public read/write APIs
- Eval Runtime v0.1 public contracts, protocols, store, and optional Codex Judge adapter
- installed production Trace database for a preparation-only preview after local verification

## Excluded Scope

- automatic Eval scheduling
- formal-memory create/merge evaluation
- Recall evaluation
- automatic memory promotion, merge, deletion, policy mutation, or prompt changes
- live Judge calls, production installation, scheduled-task mutation, publication, release tags, and GitHub push without separate authorization

## Acceptance Criteria

1. Capture emits one content-free `agc.capture.item.completed` event only after a receipt is durably complete.
2. Trace contains opaque evidence references and aggregates, never Session, Capsule, Observation, or Memory text.
3. AGC resolves evidence from one consistent Capture snapshot and rejects missing, stale, changed, or digest-mismatched evidence.
4. Deterministic sampling builds at most one EvalCase per completed evidence reference.
5. Preparation computes a digest over exact cases, Profile, provider, model, executable identity, and limits without resolving evidence or calling a model.
6. Authorized evaluation is manual, bounded, immutable, and unable to mutate AGC state.
7. Base AGC remains functional without Trace/Eval optional packages, and existing Capture behavior stays failure-open.

## Verification Plan

- Follow every red-green-refactor checkpoint in the confirmed implementation plan.
- Run focused evidence, bridge, resolver, case, CLI, and synthetic cross-runtime tests.
- Run the complete AGC suite, package build, contract tests, and content-absence checks.
- Keep all test artifacts under the user-designated global test root and use a short Windows path where required.

## Plan

- active_plan: `docs/superpowers/plans/2026-08-30-agc-capture-eval-pilot.md`
- status: confirmed
- execution_mode: inline on the current `main` branch by explicit user choice

## External Dependencies

- project_id: `agent-runtime-modules`
- edge_id: pending registration after the Pilot proves the integration
- dependency_type: optional local runtime packages
- required_contract: Contracts 0.1.1, Trace Runtime 0.1.x, Eval Runtime 0.1.x, and optional Codex Eval Adapter 0.1.x public APIs defined by the confirmed runtime plan
- verification_status: source verification required against the implemented runtime packages before AGC code begins
- impact_on_change: AGC imports remain lazy and failure-open; no runtime dependency may affect Capture truth
- fallback_or_handoff: report optional integration unavailable and preserve the original Capture result

## Flow Record

| Step | Status | Evidence | Updated |
|---|---|---|---|
| source | done | existing Capture Runner/Store/Trace bridge and confirmed architecture | 2026-08-30 |
| design | done | confirmed mixed TraceSnapshot plus AGC evidence design | 2026-08-30 |
| plan | done | `docs/superpowers/plans/2026-08-30-agc-capture-eval-pilot.md`; commit `7402eb9` | 2026-08-30 |
| development | active | waiting for source-verified Eval Runtime implementation | 2026-08-30 |
| testing | active | clean pre-change baseline: 1372 tests, one existing warning | 2026-08-30 |
| archive | pending | final handoff after verified implementation | 2026-08-30 |

## Open Questions

- Live evidence transmission, production installation, scheduled execution, formal-memory Eval, publication, release tag, and GitHub push remain later explicit decisions.
