# Change Brief: agc-v2-local-upgrade

## Summary

- title: Agent Global Context v2 Local Upgrade
- status: complete
- flow_id: agc-v2-local-upgrade
- parent_flow_id: agc-v2-runtime-foundation
- why: The v2 Runtime source is complete, but Codex still loads five alpha P0–P4 Skills, no AGC MCP tools are registered, the Runtime is not installed, and the active personal memory root is still v1.
- changes: Deliver the thin v2 Skill and three-tool MCP adapter, deterministic parallel v1 migration, repeatable local installation, validated cutover, and rollback evidence.
- does_not_change: Codex side-channel capture, recent-task backfill, Trace/Eval/Loop, LLM Wiki Runtime, or the original Codex task archive.

## Sources

- `docs/superpowers/specs/2026-07-28-agent-global-context-v2-design.md`
- `.llm-wiki/handoff/agc-v2-runtime-foundation-handoff.md`
- User confirmation on 2026-07-29: directly upgrade the local AGC and continue on `main`.

## Scope

- active:
  - `skills/agent-global-context/`
  - retirement of the four public alpha companion Skills
  - `agc_runtime/mcp_server.py`
  - Runtime migration support
  - migration, MCP, Skill contract, and installation tests
  - local installation and Codex MCP registration
  - parallel v2 memory root, validation, and cutover
- read-only:
  - the current v1 personal memory root before backup and migration
  - the stable Runtime read/write/admin semantics
- excluded:
  - Codex task capture and seven-day backfill
  - Trace/Eval/Loop
  - LLM Wiki Runtime integration
  - vector search, databases, and semantic matching inside Runtime

## Acceptance

- Codex is presented with one thin `agent-global-context` Skill rather than five public alpha Skills.
- The always-visible capability description contains no personal fact and stays within the approximately 80-token design budget.
- Recall remains an LLM decision; no P0/P1 rule automatically injects personal memory.
- The local MCP server exposes only `agc.read`, `agc.write`, and `agc.admin`, bound to one configured memory root.
- Runtime and MCP failure never block an otherwise-completable main task.
- Migration builds a separate schema-v2 root and never rewrites the v1 source in place.
- A migration request supplies semantic decisions; Runtime validates and persists them but does not infer matches or classifications.
- Normal/personal v1 sources are recoverably snapshotted; sensitive/secret content is excluded without copying its body.
- Migration is idempotent, validates all migrated Memory Items, rebuilds Catalog, and records a content-free migration receipt.
- Local Runtime installation, Skill synchronization, Codex MCP registration, v1 backup, v2 validation, and cutover are repeatable.
- The active local memory root passes `agc.admin validate`, the MCP smoke test, strict UTF-8/no-BOM checks, and full project tests.

## Plan

- active_plan: `docs/superpowers/plans/2026-07-29-agent-global-context-v2-local-upgrade.md`
- status: confirmed
- execution: Subagent-Driven Development in the current session.
- evidence: The user explicitly said to continue with the direct local upgrade.

## External Dependencies

- dependency: official MCP Python SDK 2.0.0
- required_contract: v2 `MCPServer` stdio server and tool decorators
- verification_status: primary-source-checked
- evidence: official `modelcontextprotocol/python-sdk` documentation
- impact_on_change: optional `mcp==2.0.0` package extra and local stdio server entry point
- fallback_or_handoff: the deterministic CLI remains available if Codex MCP startup fails

## Flow Record

| Step | Status | Evidence | Updated |
|---|---|---|---|
| source | done | approved v2 design and Runtime handoff | 2026-07-29 |
| design | done | thin Skill, LLM-owned semantics, parallel migration, three tools | 2026-07-29 |
| plan | done | confirmed local-upgrade implementation plan | 2026-07-29 |
| development | done | Skill/MCP, migration/forget, and installer commits through `88f8ea7` | 2026-07-29 |
| testing | passed-agent-local | 186 tests plus local CLI, MCP stdio, UTF-8, backup, and cutover gates | 2026-07-29 |
| archive | done | verification and handoff artifacts recorded | 2026-07-29 |

## Risks

- Codex requires a restart or new task before a newly registered MCP server appears.
- The v1 store may contain mixed-sensitivity prose; migration must exclude uncertain content rather than copy it.
- A rollback copy remains AGC-managed and must be included in later hard-forget scope.
- Editing the active Codex configuration requires a timestamped backup and exact-scope patch.

## Completion

- one active `agent-global-context` Skill; four alpha companions retired to a timestamped backup
- Runtime `0.2.0` and MCP SDK `2.0.0` installed in a dedicated venv
- Codex registered to `C:\Users\admin\.agent-global-context-v2`
- 19 formal Memory Items and one candidate validated
- v1 retained as rollback material with capture disabled
- capture/backfill, Trace/Eval/Loop, and LLM Wiki Runtime remain excluded
