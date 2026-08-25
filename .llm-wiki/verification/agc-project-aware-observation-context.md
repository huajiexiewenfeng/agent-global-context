# Verification: AGC project-aware Observation context

- verification_id: `agc-project-aware-observation-context`
- branch: `codex/task-aware-census-catalog`
- merged_main_head: `d552951`
- status: passed-agent-local
- executor: agent-local
- authority: agent-local; no CI or independent reviewer claim
- limitation_acceptor: none; no verification limitation was accepted

## Regression Evidence

- Feature-worktree focused adjacent suite: 582 passed in 33.01 seconds, exit 0.
- Merged-`main` focused adjacent suite: 582 passed in 36.90 seconds, exit 0.
- Scope: project-scope resolver, Capsule safety, Extractor, manual backfill E2E, Capture read service, and Skill adapter.
- `python -m compileall -q agc_runtime tests`: exit 0.
- `git diff --check`: exit 0.
- Strict tracked-file text gate: 228 files decoded as UTF-8 with no BOM.
- Raw output provenance: current Codex task terminal output on 2026-08-25; this page is the durable summary, not an independent review authority.
- All pytest temporary artifacts were routed beneath `D:\tmp_test`.

## TDD Evidence

- Resolver test first failed because `agc_runtime.capture_project_scope` did not exist; 11 tests passed after implementation.
- Adapter test first observed a null Capsule scope and the E2E persistence gate accepted zero observations; boundary tests and the E2E passed after propagation.
- Extractor contract first failed because the three project-referent clauses were absent; the complete extractor suite then passed 53 tests.
- Formalization contract first failed because same-receipt/exact-scope rules and the X-publishing golden case were absent; the complete Skill adapter suite then passed 20 tests.

## Test Integrity

- production_changes: yes — pure scope resolver, Codex Source Adapter propagation, and extractor instruction contract.
- test_changes: yes — unit, adapter boundary, real JSONL source, subprocess CLI E2E, and Skill contract assertions.
- mocks_or_fixtures_changed: yes — the existing fake extractor fixture is parameterized to return the derived opaque scope; real adapter, Capsule, persistence gate, filesystem transaction, and CLI behavior remain exercised.
- assertions_added_or_removed: assertions were added for normalization, confidentiality, caller precedence, two-Session persistence, prompt safety, project grouping, and the golden case; no safety assertion was removed.
- expected_behavior_changed: new Sessions with valid absolute cwd metadata now share a stable opaque project scope, while invalid or absent cwd remains null.
- over_mocking_risk: low — the fake model boundary is isolated, while the propagation and acceptance path is exercised end to end with real runtime components.

## Residual Risk

- Project moves or path aliases can conservatively split scopes.
- Unrelated work sharing one cwd enters the same candidate boundary, but semantic review and explicit confirmation still control synthesis.
- Existing historical null-scope Observations are not rewritten by this change.
- Installation, release, production replay/model calls, and GitHub push were not performed.
