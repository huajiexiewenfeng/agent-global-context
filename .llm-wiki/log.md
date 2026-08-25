# LLM Wiki Log

## 2026-08-25 — AGC project-aware Observation context

- Added deterministic opaque project scopes derived from validated Session cwd metadata without persisting or exposing the source path.
- Propagated exact scopes through Capsule and Observation persistence while preserving explicit caller scopes and schema v1.
- Strengthened extractor instructions for grounded self-contained project referents while retaining atomic predicates and prohibiting inference from opaque scope hashes.
- Updated quality-first formalization to group same-receipt observations, expand exact non-null project scopes to at most 20 items, and keep null/different scopes conservative.
- Agent-local verification passed 582 focused adjacent tests in the feature worktree and again after local fast-forward merge to `main`; compileall, diff, UTF-8/no-BOM, and test-integrity checks passed.
- No install, release, production replay/model call, historical rewrite, formal-memory promotion, or GitHub push was performed.

## 2026-08-22 — semantic Capture candidates

- Fixed historical `extractor_empty` results by adding a bounded semantic input lane while preserving exact deterministic direct-memory validation.
- Broader user evidence can persist only as atomic `agent_inferred` plus `tentative` observations; direct evidence cannot be semantically rewritten.
- Empty Capsules now complete as `no_durable_signal` before token reservation or Extractor invocation.
- Agent-local verification passed 761 relevant tests; the full suite passed 1293 tests with only two pre-existing Windows CRLF byte-idempotence failures and no new regression.
- Built and isolated-tested wheel `1B9405A...7249B8`, then installed immutable Runtime `af38109d...a5bc0`; installed core hashes match source.
- The exact-digest authorized `gpt-5.6-sol` Pilot processed one revision, produced two collected tentative inferred observations, reported zero failure and zero silent loss, and left production formal memory at 24 with no automatic promotion.
- Final handoff and artifact registrations were created. The verified branch was fast-forward merged into `main`; the merged relevant suite passed 761 tests and installed core files exactly matched authoritative main Git blobs.

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
## 2026-08-23 — task-aware Census catalog 0.4.1

- Replaced repeated frozen-member hot reads with an atomically published packed v2 Census catalog and concurrent one-time cold rebuild.
- Added transactional catalog invalidation/recovery for scan and Hard Forget paths, while keeping the derived catalog out of backups.
- Added deterministic local Capsule ranking, round-robin task selection, a three-per-task invocation cap, and selected-Capsule reuse without changing the model or persistence boundary.
- Agent-local evidence: 1334 full-suite tests before the final Capture-only packed layout, then 1064 Capture tests after it; package and installed/source hash gates passed.
- Production read-only acceptance found 915 unique revisions, cold rebuild 26.172 seconds, hot reads 8.370/6.122 seconds, zero hot member reads, and zero formal-memory/observation/token/Extractor deltas.
- Installed immutable Runtime 0.4.1 at `4f63831e...96bcf`. Codex config is updated; the current App task still holds the previous MCP process and requires restart before live-route closure.
- On 2026-08-24 the user restarted Codex App. The live MCP returned Runtime 0.4.1 with the expected production binding, enabled `scanner_only`, paused false, 946/946 accounted keys, zero pending keys, and zero silent loss; the archive gate is closed.
