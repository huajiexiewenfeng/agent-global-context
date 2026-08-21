# Bug Brief: Extractor rejects current Codex CLI help

- bug_id: `2026-08-21-extractor-help-read-only-token`
- status: verified-preinstall
- symptom: AGC selected the PATH-first npm Codex CLI `0.142.0`, which cannot invoke the Codex App model `gpt-5.6-sol`; the App actually runs its own `0.149.0-alpha.4` Runtime, whose successful usage event added `cache_write_input_tokens` that the pre-fix AGC parser rejected.
- expected: capability probing and extraction work with the current documented `codex exec --json` and Structured Outputs contracts without weakening fail-closed boundaries.
- evidence: live reduction found six initial compatibility gaps. Follow-up process inspection proved Codex App is running `C:\Users\admin\AppData\Local\OpenAI\Codex\bin\f022bde1137dbb75\codex.exe` version `0.149.0-alpha.4`, while PATH resolves the npm `0.142.0` first. An exact App Runtime probe with `gpt-5.6-sol` succeeded and returned schema-valid empty drafts plus usage fields `input_tokens`, `cached_input_tokens`, `cache_write_input_tokens`, `output_tokens`, and `reasoning_output_tokens`.
- reproduction_status: executable-selection mismatch and five-field usage were reproduced live; no related promoted Session Digest was found. App Runtime model invocation succeeds, the five-field parser regression is green, and the exact `codex-app` selector resolves the bounded App Runtime without PATH fallback.
- likely_scope: `agc_runtime/codex_app_runtime.py`, `agc_runtime/codex_extractor.py`, `agc_runtime/capture_cli.py`, focused tests, operations documentation, and this Bug Brief.
- active_scope: same as likely scope, plus Pilot and production extractor configuration during the installed verification stage.
- read_only_scope: installed Runtime, current Codex CLI help, isolated Pilot data under `D:\tmp_test`.
- excluded_scope: Scanner semantics, Runner semantics, Session parsing, formal Memory Items, Hook, production Capture state.
- fix_plan: completed in source. The five-field usage parser validates `cache_write_input_tokens`; the exact `codex-app` selector resolves one ordinary non-reparse App Runtime candidate below the fixed LocalAppData root and fails closed for missing or ambiguous candidates.
- verification_plan: focused Extractor suite; adjacent backfill/Runner/E2E/CLI suites; `git diff --check`; install the immutable Runtime; rerun installed smoke and verify the production root is unchanged.

## Context Handoff

- lifecycle_session: `agc-history-pilot-20260821`
- user_intent: Import a few historical Sessions into AGC for an isolated test.
- active_sources: installed Codex CLI `0.142.0`, official non-interactive/Structured Outputs contracts, live capability output, current extractor source and tests.
- active_scope: Extractor/Structured Outputs compatibility and regression coverage.
- read_only_scope: installed Runtime and isolated Pilot state.
- candidate_scope: local Runtime reinstall after verification.
- excluded_scope: unrelated Capture or Memory behavior.
- current_gate: source implementation and focused verification passed; installed verification pending.
- requested_stage_or_bridge: systematic-debugging followed by test-driven-development.
- constraints: preserve strict capability checks; do not expose Session content; keep all test artifacts under `D:\tmp_test`.

## Flow Record

- intake: completed; live Pilot failure captured.
- design: completed; compatibility gaps were isolated individually and kept within the Extractor boundary.
- plan: completed; regression-first minimal changes.
- implementation: usage support commit `e5c2022`; bounded resolver commit `817cdf7`; selector integration commit `3f1c28a`.
- verification: resolver TDD RED was observed before implementation; resolver suite `9 passed`; selector TDD RED was observed before integration; combined resolver/CLI/Extractor suite `79 passed`. App Runtime `0.149.0-alpha.4` directly invoked `gpt-5.6-sol` successfully. Full related regression, immutable Runtime installation, dynamic selector live preparation, representative historical Session observation, and production invariant checks remain pending.
