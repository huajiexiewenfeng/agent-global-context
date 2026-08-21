# Bug Brief: 2026-08-21-census-window-subagent-health

## Summary

- title: Production Census is degraded by stale formats and embedded parent metadata
- status: executing
- flow_id: 2026-08-21-census-window-subagent-health
- severity: high
- owner: Codex
- updated_at: 2026-08-21

## Routing

- intent: restore a healthy production Census so manual backfill can start
- primary_stage: project-fix
- secondary_bridges: systematic-debugging, test-driven-development
- confidence: confirmed
- reason: reproduced against the installed Codex App Session corpus and current adapter
- next_gate: production install and verification
- routed_at: 2026-08-21

## Source

- path/url/log/user_report: production `agc-capture scan` and content-free adapter diagnostics
- source_proxy: counts and structural metadata only; no transcript content retained
- sensitivity: normal

## Symptom

Production Census reads 3,034 Session files (about 5.48 GB), discovers 685 recent turns, but remains degraded and blocks backfill preparation.

## Expected

Malformed or obsolete files outside the configured seven-day window must not degrade the current-window Census. A subagent rollout that embeds parent-task metadata must be excluded as a subagent, not treated as a conflicting main-task identity.

## Evidence

- Production Census: 685 known/accounted, zero silent loss, one durable source quarantine.
- Latest Census recorded three diagnostic classes.
- Content-free diagnostic scan found 267 historical problem files: 153 `conflicting_source_identity`, 113 `unknown_completion_shape`, and one `unknown_source_shape`.
- Correct seven-day path filter found 15 `conflicting_source_identity` files.
- Structural inspection showed those files begin with subagent metadata and then embed repeated parent main-task metadata.

## Reproduction

- status: reproduced
- command_or_steps: run `CodexSourceAdapter.discover` against a stale malformed file and against a subagent-first rollout containing embedded parent metadata
- observed: stale diagnostics degrade the current window; embedded parent metadata produces `conflicting_source_identity`
- expected: stale diagnostic excluded from current health; subagent rollout safely ignored
- limitation: production transcript content was not inspected or retained

## Scope

- active: `agc_runtime/codex_source_adapter.py`, `tests/test_codex_source_adapter.py`, this Bug Brief
- read_only: production Capture metadata and content-free Session structural fields
- candidate: Capture incremental performance/indexing
- excluded: Capture Store, Hard Forget, formal-memory promotion, production observation extraction
- escalation_history: none

## Diagnosis

`discover` adds every file diagnostic before applying the configured time window. `_scan_file` also requires every repeated `session_meta` identity to equal the first, even when a subagent rollout embeds its parent task metadata. Together these turn irrelevant historical formats and valid subagent packaging into a binding-wide health failure.

## Fix Plan

1. Add failing regression coverage for stale diagnostics and embedded parent metadata.
2. Scope file diagnostics to files whose filesystem modification time can overlap the requested window; continue parsing valid historical files so cross-window revision conflicts remain fail-closed.
3. Treat the first valid subagent metadata as authoritative for exclusion while keeping main-first identity conflicts fail-closed.
4. Run focused and full Capture regressions, reinstall, rescan, and verify production state before any backfill.

## Verification

- status: partial
- commands_or_checks: TDD RED/GREEN; full 597-test Capture regression; content-free discovery against the real Codex App Session root
- result_summary: 597 tests passed; real seven-day discovery returned 689 revisions and no diagnostic codes
- limitation:
- residual_risk: the adapter still performs a full historical read; safe incremental indexing remains candidate scope

## Flow Record

| Step | Status | Evidence | Updated |
|---|---|---|---|
| source | done | production Census and content-free structural diagnostics | 2026-08-21 |
| design | done | root cause confirmed in current adapter and real App Session structure | 2026-08-21 |
| plan | done | narrow adapter/test fix plan above | 2026-08-21 |
| development | done | adapter window diagnostics, subagent exclusion, legacy identity upgrade, and benign event compatibility | 2026-08-21 |
| testing | active | 597 tests passed; production installation and Census pending | 2026-08-21 |
| archive | pending |  |  |

## Artifacts

- This Bug Brief

## Open Questions

- Whether a later phase should add a cryptographically bound per-file scan cache to avoid repeated full-history reads.

## Residual Risk

This fix restores current-window health without relaxing validation of recent malformed files or valid cross-window revision conflicts. It does not yet optimize full-history scan latency.
