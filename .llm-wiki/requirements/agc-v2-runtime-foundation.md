# Change Brief: agc-v2-runtime-foundation

## Summary

- title: Agent Global Context v2 Runtime Foundation
- status: executing
- why: The current alpha Skills have no deterministic Runtime for Schema v2, sparse Recall, safe persistence, idempotency, lifecycle evolution, recovery, or hard forget.
- changes: Add an independent Python Runtime with Markdown as source of truth and stable `read`, `write`, and `admin` JSON adapters.
- does_not_change: The five public alpha Skills, Codex task capture, v1 memory data, Trace/Eval/Loop Runtime, and LLM Wiki Runtime remain unchanged in this delivery.

## Sources

- `docs/superpowers/specs/2026-07-28-agent-global-context-v2-design.md`
- `docs/superpowers/plans/2026-07-29-agent-global-context-v2-runtime-foundation.md`
- User confirmation on 2026-07-29: execute inline and allow direct development on `main`.

## Scope

- active: `agc_runtime/`, `tests/`, `pyproject.toml`, Runtime sections of `README.md` and `README.zh.md`
- reference-only: five existing `skills/agent-global-context*` packages, v2 design, existing alpha templates
- excluded: Skill consolidation, Codex side-channel capture, recent-task backfill, v1 migration/cutover, Trace/Eval/Loop, LLM Wiki Runtime integration

## Acceptance

- Three deterministic JSON adapters exist for `agc.read`, `agc.write`, and `agc.admin`.
- Markdown remains the formal source of truth and generated Catalog files are rebuildable.
- Strict UTF-8 without BOM is enforced for Runtime-managed text.
- Sensitive persistence is fixed off and secret/sensitive payloads are rejected before Runtime writes.
- Exact source-key retries are idempotent; Runtime does not perform semantic matching.
- Evidence thresholds request LLM adjudication rather than automatic promotion.
- Legal lifecycle operations, progressive reads, backup/restore, and authorized hard forget are covered by tests.
- Full test, package build, CLI version, encoding, and `git diff --check` gates pass.

## Plan

- active_plan: `docs/superpowers/plans/2026-07-29-agent-global-context-v2-runtime-foundation.md`
- status: confirmed
- evidence: User selected Inline Execution (`2`) and explicitly authorized direct implementation on `main`.

## External Dependencies

- project-id: none
- edge_id: none
- dependency_type: none
- required_contract: none
- evidence: Runtime is intentionally independent.
- verification_status: source-verified
- derived_staleness: fresh
- impact_on_change: none
- fallback_or_handoff: none

## Flow Record

| Step | Status | Evidence | Updated |
|---|---|---|---|
| source | done | v2 approved design | 2026-07-29 |
| design | done | `docs/superpowers/specs/2026-07-28-agent-global-context-v2-design.md` | 2026-07-29 |
| plan | done | confirmed Runtime Foundation plan | 2026-07-29 |
| development | active | Inline execution authorized on `main` | 2026-07-29 |
| testing | pending | Task-level RED/GREEN and release gates | 2026-07-29 |
| archive | pending | finish handoff after verification | 2026-07-29 |

## Open Questions

- None blocking Runtime Foundation.

## Notes

- Implementation is split into four deliverables so the current Skills are not switched to tools that do not exist yet.
- Scope expansion requires explicit user confirmation.
