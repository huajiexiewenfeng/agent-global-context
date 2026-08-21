# LLM Wiki Log

## 2026-08-13 — agc-capture-coverage-mvp

- Locked the next milestone to provable Codex main-task Revision coverage rather
  than the complete automatic-learning loop.
- Revised the written design so Phase 1 stops at truthful Capture Receipt plus
  zero to eight Recall-isolated Collected Observations; aggregation, Candidate,
  and Formal Memory mutation remain deferred.
- Defined active-profile scope, completed-turn Revision identity, Hook/Scanner
  separation, two-level idempotency, transaction recovery, Source Health,
  backup/restore, Hard Forget, token accounting, and foreground latency gates.
- Registered the Change Brief and design for user written-spec review. Planning,
  production implementation, deployment, and Capture activation have not started.
- The user approved continuation after written-spec review. Split implementation
  into four dependency-ordered TDD plans: deterministic core, Codex source/Census,
  Extractor/Runner, and Windows host rollout.
- Mapped AC-01 through AC-20 to independently runnable tests and preserved four
  later human gates: real Scanner enablement, Hook trust, Shadow Backfill, and
  continuous Runner activation.
- Corrected rollback compatibility: released 0.2.0 cannot retroactively reject a
  future Capture schema, so post-data rollback disables processing while retaining
  a Capture-capable Runtime for read/status/forget instead of binary downgrade.
- Production code, tests, installation, and real-profile Capture remain unchanged.
- Implemented and independently hardened Capture Core, Source Census, safe
  Capsule/Extractor/Runner, inert Host installation, transactional supervision,
  Hook latency gate, explicit operations, and Runtime-bound activation digest.
- Agent-local AC-01..20 release verification passed: 1255 full-suite tests, one
  expected adversarial ZIP warning, wheel/sdist build, isolated installed
  four-entrypoint provenance, pip check, diff, and strict UTF-8/no-BOM.
- Capture remains off. Live Scanner, Hook trust, Shadow Backfill, sample review,
  and continuous Runner are still separate explicit human gates.
- On 2026-08-21 the user-authorized inert upgrade installed commit `8a8f75a`
  as immutable Runtime `97cda42d...a622e9`; version, four entry points,
  committed-source hashes, exact three-tool MCP surface, Codex binding, and
  default-off Capture state passed. A stable-Python selector and Python-bound
  deployment key prevent reuse of venvs built by a different interpreter.
- The user then authorized Scanner-only activation for the active Codex Home.
  Config migration retained 23 formal memories; Census and replay converged at
  38/38 known/accounted keys with zero silent loss. The 15-minute Windows task
  completed with result 0, Hook/Runner/model remained off, and a live-found
  Scanner/Runner argument bug was fixed in `47f5325` with 28 focused tests.
  Source health remains explicitly degraded by one `unknown_source_shape`
  quarantine, so Shadow Backfill and Runner are not authorized.

## 2026-08-11 — agc-recall-consistency-filter-validation

- Added an explicit Recall trigger for evaluating whether a project, repository,
  tool, or technology fits the user's research, learning, or long-term goals.
- Restricted Search filters to the six documented names and changed unknown names
  from silent ignore to the standard `invalid_request` response.
- Agent-local release gate passed twice at 195 tests, plus Skill validation,
  strict UTF-8/no-BOM, diff, deployed Runtime, and active Skill hash checks.
- Local deployment reports all 22 memories valid and unchanged; the current Codex
  process requires a new task or restart to load the new Skill and MCP process.

## 2026-07-29 — agc-v2-runtime-foundation

- Flow Record moved from execution to archived completion.
- Runtime Foundation implemented in commits `1ab7ba0` through `4a01076`.
- Agent-local release gate passed: 94 tests, wheel/sdist build, CLI version, strict UTF-8/no-BOM scan, and `git diff --check`.
- Verification and handoff registered under `.llm-wiki/verification/` and `.llm-wiki/handoff/`.
- No dashboard was created because this repository has no enabled or registered progress dashboard.
- Next independent deliverable: v2 Recall/Skill Adapter.

## 2026-07-29 — agc-v2-local-upgrade

- Flow Record moved from implementation to archived completion.
- One public Skill and the three-tool MCP adapter replaced the five alpha Skill surface.
- Deterministic v1 migration, manifest integrity, path containment, shared-source Hard
  Forget, retry recovery, and repeatable local installation were independently reviewed.
- Agent-local release gate passed: 188 tests, wheel/sdist build, CLI, MCP 2.0 stdio,
  strict UTF-8/no-BOM, backup ZIP, no-op installer, and local cutover checks.
- Local v2 contains 19 formal memories and one candidate; exposure is limited to one
  core card, with no personal core cards.
- v1 remains rollback material with auto capture disabled.
- Capture/backfill, Trace/Eval/Loop, and LLM Wiki Runtime remain deferred.
- No dashboard was updated because this repository has no enabled or registered progress dashboard.

## 2026-08-01 — 2026-08-01-catalog-stale-after-write

- Reproduced a write-to-recall consistency defect: one persisted formal memory
  was available by exact ID but absent from stale overview/search catalogs.
- The write dispatcher now refreshes derived catalogs for accepted formal-memory
  results and reports `catalog_refresh_failed` without contradicting a committed write.
- Agent-local verification passed: 190 tests, diff check, installed Runtime smoke
  test without manual rebuild, and live validation/search of all 20 formal memories.
- Codex configuration now points to content-addressed Runtime `0918faf6...6145ee`;
  the previous Runtime and installer rollback backup remain available.
- Verification and handoff artifacts were registered. No dashboard was updated
  because this repository has no enabled or registered progress dashboard.
