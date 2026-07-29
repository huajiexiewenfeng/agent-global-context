# Handoff: agc-v2-runtime-foundation

## Result

The independent Agent Global Context v2 Runtime Foundation is implemented on `main`.

## Implemented

- Strict Schema v2 Markdown objects with temporal, recall, sensitivity, provenance, and content budgets.
- Strict UTF-8/no-BOM I/O, atomic replacement, cross-platform root locking, transaction journals, and recovery.
- Sensitive/secret pre-persistence rejection, deterministic observation policy, evidence thresholds, and legal lifecycle transitions.
- Exact `source.ref + source.revision + source.content_hash` idempotency without semantic matching.
- `agc.write` observation, candidate, confirm/update/reinforce/conflict, supersede/archive/reject, batch, and authorized Hard Forget paths.
- `agc.read` progressive overview/search/get/history/evidence access with bounded overview cards.
- `agc.admin` init/validate/rebuild/backup/restore plus explicit deferred migration.
- Host CLI adapters, package metadata, wheel/sdist build, end-to-end tests, and updated English/Chinese boundary documentation.

## Boundaries Preserved

- The five alpha Skills remain the active compatibility layer.
- Runtime does not infer semantic equality or invent `match_memory_id`.
- Sensitive persistence remains disabled; secrets are never stored.
- Codex side-channel capture, recent-task backfill, and v1 migration are not activated.
- Trace/Eval/Loop and LLM Wiki Runtime integration remain outside scope.

## Verification

- evidence: `.llm-wiki/verification/agc-v2-runtime-foundation.md`
- result: 94 tests passed; wheel/sdist built; CLI contract, strict UTF-8/no-BOM, and diff checks passed
- trust_level: agent-local
- residual_risk: no CI-backed run or external code review yet

## Important Commits

- `1ab7ba0` package and stable tool contract
- `0fd4c82` Schema v2
- `49da895` idempotent Markdown Store
- `e7663b9` write service
- `e41f35e` progressive reads
- `c43747a` Hard Forget
- `8743332` admin, backup, and recovery
- `4a01076` CLI, end-to-end gate, and documentation

## Next Action

Design and implement the v2 Recall/Skill Adapter against the three stable Runtime tools without enabling Codex capture or migration.
