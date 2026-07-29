# Working Context: agc-v2-runtime-foundation

## Context Handoff

- lifecycle_session: agc-v2-runtime-foundation
- user_intent: Execute the confirmed Runtime Foundation plan inline.
- active_sources: v2 design and Runtime Foundation implementation plan.
- active_scope: `agc_runtime/`, `tests/`, `pyproject.toml`, Runtime README sections.
- read_only_scope: existing Skills and alpha templates.
- candidate_scope: none.
- excluded_scope: Skill consolidation, Codex capture, v1 migration, Trace/Eval/Loop, LLM Wiki Runtime integration.
- current_gate: Scope Lock Gate.
- requested_stage_or_bridge: executing-plans plus test-driven-development.
- constraints: direct work on `main` explicitly authorized; strict UTF-8; Markdown source of truth; no sensitive persistence; no semantic inference in Runtime.

## Scope Lock

- locked_active_scope: Runtime package, Runtime tests, packaging metadata, Runtime documentation.
- locked_read_only_scope: existing public Skills, v2 design, alpha templates.
- locked_candidate_scope: none.
- locked_excluded_scope: capture, migration, Skill cutover, external runtimes.
- accepted_assumptions: Python 3.10+, PyYAML 6.x, pytest 9.1.1, local CLI adapter.
- escalation_rule: Stop and ask before editing excluded scope or changing public Skill behavior.

## Verification Plan

- Run every new behavior through RED then GREEN.
- Run focused tests after each task and the complete suite at batch checkpoints.
- Validate strict UTF-8 without BOM.
- Build wheel and source distribution at Task 10.
- Run `git diff --check` and inspect exact changed-file scope.

## Execution Status

- current_batch: complete
- completed_tasks: Tasks 1–10
- implementation_head: `4a01076`
- verification: `94 passed`; wheel and sdist built; CLI version contract passed; all 89 tracked text files strict UTF-8 without BOM; `git diff --check` passed
- verification_trust: agent-local
- handoff: `.llm-wiki/handoff/agc-v2-runtime-foundation-handoff.md`
- next_deliverable: v2 Recall and Skill Adapter
- excluded_work_still_not_started: Codex side-channel capture, v1 migration/cutover, Trace/Eval/Loop integration
