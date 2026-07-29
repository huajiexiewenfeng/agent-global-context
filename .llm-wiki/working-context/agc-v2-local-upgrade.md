# Working Context: agc-v2-local-upgrade

## Context Handoff

- lifecycle_session: agc-v2-local-upgrade
- user_intent: Upgrade the locally active AGC to the complete v2 design.
- active_sources: approved v2 design, Runtime Foundation handoff, current alpha Skills, local v1 store inventory.
- active_scope: thin Skill, MCP adapter, deterministic migration, local install, parallel v2 root, verified cutover.
- read_only_scope: retained v1 rollback root after migration; auto capture is disabled.
- candidate_scope: compatibility references retained inside the single public Skill.
- excluded_scope: Codex capture/backfill, Trace/Eval/Loop, LLM Wiki Runtime.
- current_gate: Release Gate complete.
- requested_stage_or_bridge: project finish and handoff.
- constraints: direct `main` work authorized; backup before mutation; strict UTF-8; no personal data in repository; LLM owns semantic relevance; Runtime failure releases the main task.

## Scope Lock

- locked_active_scope: repository Skill/MCP/migration/install code and the explicitly named local AGC installation.
- locked_read_only_scope: original v1 root before the cutover transaction.
- locked_candidate_scope: none after the plan is confirmed by the user's continue instruction.
- locked_excluded_scope: capture/backfill and external runtimes.
- accepted_assumptions: Python 3.10+, official MCP Python SDK 2.0.0, current Codex `config.toml` supports stdio MCP servers.
- escalation_rule: stop before any deletion that is not a verified replacement step with a recoverable backup.

## Local Baseline

- repository: clean `main`, synchronized with `origin/main`
- tests: `94 passed` with pytest basetemp redirected to a writable `D:\tmp` directory
- active Skills: five alpha P0–P4 packages
- active memory root: 16 v1 files, all valid UTF-8; one project file contains a UTF-8 BOM
- global `agc` command: absent
- Runtime package: source present, not installed in the test venv

## Completed Local State

- Runtime: content-addressed venv
  `C:\Users\admin\.agent-global-context-runtime\venvs\753035ae1f47ac63d11544f62a3992dccc726183fc77d88a0a3cd70041815f87`,
  package `0.2.0`
- MCP: exactly `agc.read`, `agc.write`, and `agc.admin`
- Codex config: one marked `agent_global_context` server bound to the parallel v2 root
- active Skill root: one `agent-global-context` directory
- Skill/config backup: `C:\Users\admin\.agent-global-context-runtime\backups\20260730-033200-562-ccbe4d2edc7a4536a947db8ea82c35f7`
- content-addressed Runtime switch backup: `C:\Users\admin\.agent-global-context-runtime\backups\20260730-043855-668-1c788d0c5f8847a9beddac4d9810e727`
- v1 configuration backup: `C:\Users\admin\.agent-global-context-v1-backups\20260729T192524374Z-226c14fce34848bbaea3ced7078ba214`
- v1: 16 files retained; frozen manifest SHA-256 `a9efe4fb81c9ff899bf2822f41af058a5b65640d99b299f12978b27090cb341f`
- v2: 19 formal memories, one candidate, one completed v1 migration receipt, and one validated ZIP backup
- exposure: one core card, 14 scoped cards, three discoverable-only, one history-only
- privacy: four personal memories, none core; no sensitive or secret persistent item
- restart boundary: this existing task cannot gain newly registered MCP tools; use a new task or restart Codex
- deferred: Codex capture/backfill, Trace/Eval/Loop, and LLM Wiki Runtime

## Verification Plan

- Run RED/GREEN pressure scenarios for the Skill behavior.
- Run RED/GREEN pytest cycles for MCP and migration contracts.
- Run the complete suite with a writable basetemp after each implementation task.
- Build wheel and sdist with the MCP optional dependency metadata.
- Install into a dedicated local virtual environment and register one Codex MCP server.
- Back up v1, build v2 in parallel, validate, then switch the configured tool root.
- Verify one no-recall task, one overview/search/get path, and one idempotent write path.
- Validate strict UTF-8 without BOM for repository and v2 managed text.

## Verification Result

- repository implementation gate: 188 tests passed after final review fixes
- `agc.admin validate`: accepted, zero issues
- CLI overview/search: 19 memories; relevant scoped result returned; unrelated query returned zero
- MCP 2.0 stdio: initialized, listed exactly three tools, and executed `agc.read overview`
- v2 backup ZIP: `testzip()` passed
- installed config/Skill/launcher and v2 managed text: strict UTF-8 without BOM
- installer no-op rerun: `backup_path: null`
