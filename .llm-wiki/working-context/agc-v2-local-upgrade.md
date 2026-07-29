# Working Context: agc-v2-local-upgrade

## Context Handoff

- lifecycle_session: agc-v2-local-upgrade
- user_intent: Upgrade the locally active AGC to the complete v2 design.
- active_sources: approved v2 design, Runtime Foundation handoff, current alpha Skills, local v1 store inventory.
- active_scope: thin Skill, MCP adapter, deterministic migration, local install, parallel v2 root, verified cutover.
- read_only_scope: v1 memory content until migration execution.
- candidate_scope: compatibility references retained inside the single public Skill.
- excluded_scope: Codex capture/backfill, Trace/Eval/Loop, LLM Wiki Runtime.
- current_gate: Scope Lock Gate.
- requested_stage_or_bridge: writing-plans, TDD, subagent-driven-development.
- constraints: direct `main` work authorized; backup before mutation; strict UTF-8; no personal data in repository; LLM owns semantic relevance; Runtime failure releases the main task.

## Scope Lock

- locked_active_scope: repository Skill/MCP/migration/install code and the explicitly named local AGC installation.
- locked_read_only_scope: original v1 root before the cutover transaction.
- locked_candidate_scope: none after the plan is confirmed by the user's continue instruction.
- locked_excluded_scope: capture/backfill and external runtimes.
- accepted_assumptions: Python 3.10+, official MCP Python SDK 1.x, current Codex `config.toml` supports stdio MCP servers.
- escalation_rule: stop before any deletion that is not a verified replacement step with a recoverable backup.

## Local Baseline

- repository: clean `main`, synchronized with `origin/main`
- tests: `94 passed` with pytest basetemp redirected to a writable `D:\tmp` directory
- active Skills: five alpha P0–P4 packages
- active memory root: 16 v1 files, all valid UTF-8; one project file contains a UTF-8 BOM
- global `agc` command: absent
- Runtime package: source present, not installed in the test venv

## Verification Plan

- Run RED/GREEN pressure scenarios for the Skill behavior.
- Run RED/GREEN pytest cycles for MCP and migration contracts.
- Run the complete suite with a writable basetemp after each implementation task.
- Build wheel and sdist with the MCP optional dependency metadata.
- Install into a dedicated local virtual environment and register one Codex MCP server.
- Back up v1, build v2 in parallel, validate, then switch the configured tool root.
- Verify one no-recall task, one overview/search/get path, and one idempotent write path.
- Validate strict UTF-8 without BOM for repository and v2 managed text.

