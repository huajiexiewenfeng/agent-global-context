# Artifact Registry

| id | type | path | owner | related_session | status | last_checked | notes |
|---|---|---|---|---|---|---|---|
| agc-v2-design | design | `docs/superpowers/specs/2026-07-28-agent-global-context-v2-design.md` | project | agc-v2-runtime-foundation | active | 2026-07-29 | Approved v2 design and delivery boundaries. |
| agc-v2-runtime-plan | plan | `docs/superpowers/plans/2026-07-29-agent-global-context-v2-runtime-foundation.md` | project | agc-v2-runtime-foundation | complete | 2026-07-29 | Ten-task Runtime Foundation implementation plan. |
| agc-v2-runtime-verification | verification | `.llm-wiki/verification/agc-v2-runtime-foundation.md` | agent-local | agc-v2-runtime-foundation | passed-agent-local | 2026-07-29 | 94 tests, package build, CLI, encoding, and diff gates. |
| agc-v2-runtime-handoff | handoff | `.llm-wiki/handoff/agc-v2-runtime-foundation-handoff.md` | project | agc-v2-runtime-foundation | active | 2026-07-29 | Completion and continuation entry point. |
| agc-v2-local-upgrade-plan | plan | `docs/superpowers/plans/2026-07-29-agent-global-context-v2-local-upgrade.md` | project | agc-v2-local-upgrade | complete | 2026-07-29 | Thin Skill, MCP, migration, installer, and cutover plan. |
| agc-v2-local-upgrade-verification | verification | `.llm-wiki/verification/agc-v2-local-upgrade.md` | agent-local | agc-v2-local-upgrade | passed-agent-local | 2026-07-29 | Repository, local install, migration, MCP, encoding, backup, and noise gates. |
| agc-v2-local-upgrade-handoff | handoff | `.llm-wiki/handoff/agc-v2-local-upgrade-handoff.md` | project | agc-v2-local-upgrade | superseded | 2026-08-01 | Historical upgrade handoff; current Runtime and memory state continue in the catalog-consistency handoff. |
| agc-catalog-consistency-bug | bug | `.llm-wiki/bugs/2026-08-01-catalog-stale-after-write.md` | project | 2026-08-01-catalog-stale-after-write | verified | 2026-08-01 | Source-of-truth diagnosis, bounded fix, Flow Record, and residual risk. |
| agc-catalog-consistency-verification | verification | `.llm-wiki/verification/2026-08-01-catalog-stale-after-write.md` | agent-local | 2026-08-01-catalog-stale-after-write | passed-agent-local | 2026-08-01 | 190 tests, installed-artifact smoke test, live 20-memory validation, and test-integrity record. |
| agc-catalog-consistency-handoff | handoff | `.llm-wiki/handoff/2026-08-01-catalog-stale-after-write-handoff.md` | project | 2026-08-01-catalog-stale-after-write | active | 2026-08-01 | Current Runtime paths, behavior, memory state, rollback material, and next action. |
