# Bug Brief: Extractor rejects current Codex CLI help

- bug_id: `2026-08-21-extractor-help-read-only-token`
- status: verified-installed
- symptom: `agc-capture prepare-backfill` returns `extractor_capability_unavailable` with Codex CLI `0.142.0` despite a healthy isolated three-Session census.
- expected: capability probing and extraction work with the current documented `codex exec --json` and Structured Outputs contracts without weakening fail-closed boundaries.
- evidence: live reduction found six compatibility gaps: punctuated help values; missing `--skip-git-repo-check` in the empty working directory; unsupported Structured Outputs keywords and missing explicit types; current four-field usage plus nonfatal error items and duplicate identical final messages; a Windows temporary-directory cleanup race; and omission of a valid absolute `CODEX_HOME` needed for CLI authentication/model metadata. The minimal probe also needed an explicit empty-drafts instruction to prevent content extraction during capability testing.
- reproduction_status: every gap was reproduced either with a focused RED test or the installed CLI. The repaired source completed `prepare-backfill` against the isolated Pilot with Codex CLI `0.142.0` and model `gpt-5.4-mini`.
- likely_scope: `agc_runtime/codex_extractor.py`, `agc_runtime/schemas/capture-extractor-v1.schema.json`, `tests/fixtures/fake_codex_exec.py`, `tests/test_capture_extractor.py`, this Bug Brief.
- active_scope: same as likely scope.
- read_only_scope: installed Runtime, current Codex CLI help, isolated Pilot data under `D:\tmp_test`.
- excluded_scope: Scanner semantics, Runner semantics, Session parsing, formal Memory Items, Hook, production Capture state.
- fix_plan: preserve strict argv, schema, event, environment, model, provider, and sandbox boundaries while adding only the compatibility cases proven by current CLI behavior.
- verification_plan: focused Extractor suite; adjacent backfill/Runner/E2E/CLI suites; `git diff --check`; install the immutable Runtime; rerun installed smoke and verify the production root is unchanged.

## Context Handoff

- lifecycle_session: `agc-history-pilot-20260821`
- user_intent: Import a few historical Sessions into AGC for an isolated test.
- active_sources: installed Codex CLI `0.142.0`, official non-interactive/Structured Outputs contracts, live capability output, current extractor source and tests.
- active_scope: Extractor/Structured Outputs compatibility and regression coverage.
- read_only_scope: installed Runtime and isolated Pilot state.
- candidate_scope: local Runtime reinstall after verification.
- excluded_scope: unrelated Capture or Memory behavior.
- current_gate: installed Runtime verification passed.
- requested_stage_or_bridge: systematic-debugging followed by test-driven-development.
- constraints: preserve strict capability checks; do not expose Session content; keep all test artifacts under `D:\tmp_test`.

## Flow Record

- intake: completed; live Pilot failure captured.
- design: completed; compatibility gaps were isolated individually and kept within the Extractor boundary.
- plan: completed; regression-first minimal changes.
- implementation: completed.
- verification: focused Extractor `48 passed`; adjacent Capture suites `98 passed`; live source and installed Runtime both accepted `prepare-backfill`; first isolated backfill attempted three, completed two, retained one retryable, and reported zero silent loss. Installed immutable venv is `8c1cf6084dae21af4db01f08ad383aa90852bfdbbb195f7a87643640b02ba885`; production overview remains 24 formal memories and production Capture remains Scanner-only with no Runner or Hook activation.
