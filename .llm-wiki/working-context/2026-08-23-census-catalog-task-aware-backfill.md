# Working Context: Census Catalog and Task-Aware Backfill

## Context Handoff

- lifecycle_session: `2026-08-23-census-catalog-task-aware-backfill`
- user_intent: finish the approved design and development so historical Capture becomes fast enough to use and prioritizes correct, useful, low-noise memory candidates
- active_sources:
  - `../bugs/2026-08-23-census-catalog-task-aware-backfill.md`
  - `../../docs/superpowers/specs/2026-08-23-agc-task-aware-census-catalog-design.md`
  - current Capture source and focused tests
- active_scope:
  - store/path/catalog implementation
  - task-aware runner selection
  - Hard Forget and backup handling for derived catalog state
  - focused tests, package version, operations documentation, implementation plan, verification and handoff records
- read_only_scope:
  - Capture schema/state machine, Capsule safety and Extractor behavior, Source Adapter contract, production Capture data and installed configuration
- candidate_scope:
  - installer/release scripts only if package verification proves they require adjustment
- excluded_scope:
  - model/prompt changes, safety-gate relaxation, automatic formal-memory promotion, raw Session persistence, live backfill, Hook/continuous Runner activation, unrelated refactoring
- current_gate: installed verification complete; Codex App reload gate pending
- requested_stage_or_bridge: restart Codex App, then verify the live MCP reports Runtime 0.4.1
- constraints:
  - all test temporary output is rooted under `D:\tmp_test`
  - zero new Extractor/model calls without a fresh exact authorization
  - production formal memories remain unchanged
  - existing frozen Census runs remain untouched except through existing user-authorized Hard Forget

## Scope Lock

- locked_active_scope: files and behaviors listed under active_scope
- locked_read_only_scope: existing contracts, safety/extractor logic, production state and configuration
- locked_candidate_scope: release/install scripts only on direct build or install evidence
- locked_excluded_scope: all content-policy expansion, auto-promotion, live egress, and unrelated modules
- accepted_assumptions:
  - the catalog is derived and can be deleted/rebuilt without changing Capture truth
  - the three-per-task limit is per runner invocation, not a permanent exclusion
  - local Capsule construction is permitted before authorization because it performs no external transfer
  - explicit full audit and backup verification retain cold-evidence validation responsibility
- escalation_rule: any change to Capture schemas, model boundary, formal-memory mutation, external transfer, or irreversible receipt disposition requires a new design decision

## Verification Plan

- RED/GREEN focused tests for catalog deduplication, hot-path member avoidance, invalidation, corruption, staging recovery, Hard Forget, backup exclusion, signal ranking, fairness, determinism, and pending status.
- Full Capture regression with `TEMP`, `TMP`, and pytest `--basetemp` under `D:\tmp_test`.
- Build wheel/sdist and install into a new immutable content-addressed runtime.
- Read-only cold/hot benchmark against production-scale Capture data with zero Extractor calls.
- Compare formal-memory count/hashes and Capture token/egress receipts before and after installation.

## Current State

- branch: `codex/task-aware-census-catalog`
- head: `3ed1089`
- installed_runtime: `4f63831e70d0c6dea92dabf6096f477c15c6a7ace84719483cd4f3eb35c96bcf`
- installed_version: `0.4.1`
- production_acceptance: cold 26.172 seconds; hot 8.370 and 6.122 seconds; 915/915 unique revision match; zero hot member JSON reads
- zero_mutation_check: formal-memory, observation count, and budget fingerprints unchanged
- pending: restart Codex App because the current task still holds the previous MCP process
