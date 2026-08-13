# Working Context: agc-capture-coverage-mvp

## Context Handoff

- lifecycle_session: agc-capture-coverage-mvp
- user_intent: Continue from the approved Capture Coverage written specification into dependency-ordered implementation plans, then pause for an execution-mode decision before production or test changes.
- active_sources:
  - `../requirements/agc-capture-coverage-mvp.md`
  - `../../docs/superpowers/specs/2026-07-28-agent-global-context-v2-design.md`
  - `../../docs/superpowers/specs/2026-08-13-agent-global-context-high-coverage-capture-design.md`
  - `../../docs/superpowers/plans/2026-08-13-agent-global-context-capture-core.md`
  - `../../docs/superpowers/plans/2026-08-13-agent-global-context-codex-source-census.md`
  - `../../docs/superpowers/plans/2026-08-13-agent-global-context-capture-extractor-runner.md`
  - `../../docs/superpowers/plans/2026-08-13-agent-global-context-capture-host-rollout.md`
- active_scope:
  - `.llm-wiki/requirements/agc-capture-coverage-mvp.md`
  - `.llm-wiki/working-context/agc-capture-coverage-mvp.md`
  - `.llm-wiki/artifacts/index.md`
  - `.llm-wiki/log.md`
  - `docs/superpowers/specs/2026-08-13-agent-global-context-high-coverage-capture-design.md`
  - `docs/superpowers/plans/2026-08-13-agent-global-context-capture-core.md`
  - `docs/superpowers/plans/2026-08-13-agent-global-context-codex-source-census.md`
  - `docs/superpowers/plans/2026-08-13-agent-global-context-capture-extractor-runner.md`
  - `docs/superpowers/plans/2026-08-13-agent-global-context-capture-host-rollout.md`
- read_only_scope:
  - `agc_runtime/`
  - `tests/`
  - `scripts/`
  - `skills/agent-global-context/`
  - `README.md`
  - `README.zh.md`
  - current Codex Host configuration and task-source metadata
- candidate_scope:
  - exact Runtime, Source Adapter, Scanner/Runner, host, installer, documentation, and test files named by the four proposed implementation plans
- excluded_scope:
  - production and test edits before plan confirmation
  - Observation aggregation, Candidate/Formal Memory mutation, semantic Recall changes, Trace/Eval/Loop, external memory engines, and full-history replay
- current_gate: Capture Core Task 1 implementation
- requested_stage_or_bridge: Subagent-Driven Development directly on `main`, with per-task TDD and independent review
- constraints:
  - current task behavior remains failure-open
  - foreground Hook performs no LLM, network, transcript parsing, or formal-memory work
  - collected observations remain outside ordinary Recall
  - no sensitive or secret persistence
  - Capture data is included in safe backup/restore and user-authorized Hard Forget
  - seven-day backfill and `100,000` total model-token ceiling

## Scope Lock

- locked_active_scope: planning and lifecycle documentation files listed under `active_scope`
- locked_read_only_scope: existing Runtime, tests, installers, Skills, README, and Host evidence
- locked_candidate_scope: implementation files and tests named by the four proposed plans
- locked_excluded_scope: production implementation in the written-spec revision; Phase 2 aggregation/promotion; Phase 3 application evaluation
- accepted_assumptions:
  - Hook delivery is an optimization and Scanner reconciliation is the coverage authority.
  - Main task is the capture unit; subagent work is evidence inside the parent task, not an independent memory source.
  - Short or irrelevant tasks legitimately produce zero observations but still produce truthful Receipt state.
- escalation_rule: Any change that lets Capture block a foreground task, automatically mutate formal memory, persist sensitive/raw transcript content, or expand beyond the seven-day window requires a new user decision and Change Brief scope update.

## Verification Plan

- Written-spec self-review: unresolved-marker scan, phase-boundary check, schema/state-machine consistency, and acceptance-to-design traceability.
- Source-contract review: main-task/revision identity, active/archive reconciliation, transcript-format drift, and Hook/Scanner separation.
- Documentation integrity: strict UTF-8/no-BOM scan for changed Markdown, `git diff --check`, and link/path existence checks.
- Implementation planning gate: every acceptance criterion must map to one independently testable plan task before execution can be confirmed.
- Future implementation gate: focused TDD per Capture contract, complete existing suite, package build, installer checks, deployed-profile diagnostics, synthetic seven-day census, crash/replay tests, sensitive-content tests, and foreground-latency measurement.

## Execution Status

- requirement: planned
- written_spec: approved
- implementation_plan: confirmed
- development: active on Capture Core Task 1
- testing: not started
- next_gate: Capture Core Task 1 RED/GREEN, task review, and focused commit
