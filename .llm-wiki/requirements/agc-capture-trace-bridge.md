# Change Brief: agc-capture-trace-bridge

## Summary

- flow_id: `agc-capture-trace-bridge`
- status: design-confirmed
- why: Observe scheduled Capture batch health in Trace without coupling AGC memory behavior to Trace availability or exporting memory content.
- original_path: `docs/superpowers/specs/2026-08-29-agc-capture-trace-bridge-design.md`

## Change

Add an optional, metadata-only, failure-open Trace bridge at the `agc-capture run/cycle` CLI boundary. Enable it only through `AGENT_TRACE_DB`; suppress successful empty cycles.

## Active Scope

- new `agc_runtime/capture_trace.py`
- `agc_runtime/capture_cli.py`
- focused Capture Trace and CLI tests
- optional dependency metadata and Capture operations documentation

## Read-Only Scope

- Capture Runner/Scanner report contracts
- Trace Runtime v0.1 public API and schemas
- sanitized AGC Recall smoke evidence

## Excluded Scope

- Capture selection, extraction, storage, scheduling, and memory behavior
- Recall and formal memory operations
- per-item spans and content payloads
- AGC configuration migration
- production install, scheduled-task mutation, publishing, GitHub push, and Eval

## Acceptance Criteria

1. Absent Trace opt-in reports disabled without importing Trace.
2. Significant success records a completed metadata-only root; empty success is suppressed.
3. Sanitized Runner failure records a failed root when available.
4. Missing package or store failure never changes the AGC result or exit code.
5. Only allowlisted numeric/status metadata is persisted.
6. Existing and new AGC tests plus a local cross-repository smoke pass.

## External Dependencies

- project_id: `agent-runtime-modules`
- edge_id: none; register only after this optional integration proves useful
- dependency_type: optional runtime library
- required_contract: Trace Runtime `0.1.x` exports `EventStore`, `PrincipalRef`, `TraceService`, `create_event`, and `resolve_db_path`, and accepts runtime-sourced `trace.root.*` events
- evidence: source-verified against the current Trace Runtime public exports, event validation, store, and service implementation
- verification_status: source-verified
- impact_on_change: supplies optional event persistence only; AGC remains functional without it
- fallback_or_handoff: return `trace_status: unavailable` and preserve the original Capture result

## Verification Plan

- Demonstrate RED for each bridge and CLI boundary behavior.
- Run focused bridge/CLI tests, full AGC suite, package checks, Ruff, and LLM Wiki Doctor.
- Install both local packages into an isolated test environment and inspect one content-safe Trace Snapshot.

## Flow Record

| Step | Status | Evidence | Updated |
|---|---|---|---|
| source | done | current Capture CLI/Runner reports and source-verified Trace v0.1 API | 2026-08-29 |
| design | done | user-confirmed optional failure-open design; linked specification | 2026-08-29 |
| plan | pending | implementation plan not yet written | 2026-08-29 |
| development | pending | implementation not started | 2026-08-29 |
| testing | pending | TDD and cross-repository smoke not started | 2026-08-29 |
| archive | pending | handoff not written | 2026-08-29 |

## Open Questions

- Production installation and scheduled-task environment activation require later explicit confirmation.
