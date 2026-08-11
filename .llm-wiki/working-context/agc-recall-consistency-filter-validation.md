# Working Context: agc-recall-consistency-filter-validation

## Context Handoff

- lifecycle_session: agc-recall-consistency-filter-validation
- user_intent: Implement the two minimal improvements identified by the 2026-08-11 AGC audit.
- active_sources: current Skill, Read Service, focused tests, approved Change Brief.
- active_scope: Skill trigger wording, Search filter-key validation, regression tests, exact supporting documentation.
- read_only_scope: existing memories and active installed AGC until verification passes.
- candidate_scope: none.
- excluded_scope: retrieval ranking, query semantics, Capture, memory mutation, Trace/Eval, broad Recall redesign.
- current_gate: Scope Lock Gate.
- requested_stage_or_bridge: executing-plans plus test-driven-development.
- constraints: work from failing tests; keep unrelated tasks quiet; preserve failure-open reads and the schema-v2 envelope.

## Scope Lock

- locked_active_scope: `skills/agent-global-context/SKILL.md`, `agc_runtime/read_service.py`, focused tests, exact docs.
- locked_read_only_scope: formal memory root and active installation before deployment.
- locked_candidate_scope: none.
- locked_excluded_scope: all broader memory-system work.
- escalation_rule: stop before expanding Recall triggers beyond personal research relevance or changing Search matching/ranking.

## Verification Plan

- Establish focused RED for the missing trigger and unknown filter rejection.
- Implement the smallest Skill and Runtime changes.
- Run focused GREEN tests, Skill validation, complete pytest suite, UTF-8/BOM check, and `git diff --check`.

## Execution Status

- current_batch: tests-first implementation
- baseline: `192 passed` with an explicit writable pytest base directory
- implementation_head: pending
- verification: pending
