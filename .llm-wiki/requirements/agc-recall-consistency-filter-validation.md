# Change Brief: agc-recall-consistency-filter-validation

## Summary

- title: AGC Recall consistency and search filter validation
- status: active
- flow_id: agc-recall-consistency-filter-validation
- why: Post-deployment evidence shows that two equivalent "related to my research" requests route inconsistently, and an invalid `scope` filter is silently ignored, returning unrelated cards.
- changes: Add one explicit research-relevance Recall trigger and reject unknown Search filter keys.
- does_not_change: Memory content, ranking, query semantics, progressive read actions, automatic capture, Trace/Eval Runtime, and unrelated-task silence.

## Sources

- `docs/superpowers/specs/2026-08-08-agent-global-context-recall-activation-design.md`
- 2026-08-11 three-day read-only usage audit: reverse-skill recalled AGC while the equivalent vLLM research-relevance request did not; `filters.scope` was accepted and ignored.
- User confirmation on 2026-08-11: implement the two minimal improvements.

## Scope

- active: `skills/agent-global-context/SKILL.md`, `agc_runtime/read_service.py`, focused tests, this Flow documentation
- read-only: existing 22 formal memories and the active local installation until repository verification passes
- excluded: memory mutation, semantic/vector retrieval, ranking, capture/backfill, Trace/Eval loop, unrelated refactoring

## Acceptance

- The Skill explicitly treats requests that evaluate whether a project, repository, tool, or technology fits the user's research, learning, or long-term goals as Recall candidates.
- A generic factual explanation of a project or technology remains a no-Recall task.
- Search accepts only `kind`, `scopes`, `decision_impact`, `sensitivity`, `exposure`, and `confidence`; every value remains a list of strings.
- Unknown filter keys such as `scope` return the standard `invalid_request` envelope instead of being ignored.
- Focused RED/GREEN evidence and the complete test suite pass.
- No AGC memory event is created or updated by this change.

## Plan

- active_plan: `docs/superpowers/plans/2026-08-11-agent-global-context-recall-consistency-filter-validation.md`
- status: confirmed
- evidence: The user approved both audit recommendations and asked the agent to implement them.

## External Dependencies

- project-id: none
- edge_id: none
- dependency_type: none
- required_contract: none
- verification_status: source-verified
- impact_on_change: none

## Flow Record

| Step | Status | Evidence | Updated |
|---|---|---|---|
| source | done | 2026-08-11 three-day AGC audit | 2026-08-11 |
| design | done | two-layer minimal fix approved by user | 2026-08-11 |
| plan | done | linked implementation plan | 2026-08-11 |
| development | active | TDD execution in isolated worktree | 2026-08-11 |
| testing | pending | focused and full verification | 2026-08-11 |
| archive | pending | final verification/handoff | 2026-08-11 |

## Open Questions

- None blocking implementation.
