# Bug Brief: Extractor rejects current Codex CLI help

- bug_id: `2026-08-21-extractor-help-read-only-token`
- status: verified-installed
- symptom: AGC selected the PATH-first npm Codex CLI `0.142.0`, which cannot invoke the Codex App model `gpt-5.6-sol`; the App actually runs its own `0.149.0-alpha.4` Runtime, whose successful usage event added `cache_write_input_tokens` that the pre-fix AGC parser rejected.
- expected: capability probing and extraction work with the current documented `codex exec --json` and Structured Outputs contracts without weakening fail-closed boundaries.
- evidence: live reduction found six initial compatibility gaps. Follow-up process inspection proved Codex App is running `C:\Users\admin\AppData\Local\OpenAI\Codex\bin\f022bde1137dbb75\codex.exe` version `0.149.0-alpha.4`, while PATH resolves the npm `0.142.0` first. An exact App Runtime probe with `gpt-5.6-sol` succeeded and returned schema-valid empty drafts plus usage fields `input_tokens`, `cached_input_tokens`, `cache_write_input_tokens`, `output_tokens`, and `reasoning_output_tokens`.
- reproduction_status: executable-selection mismatch and five-field usage were reproduced live; no related promoted Session Digest was found. App Runtime model invocation succeeds, the five-field parser regression is green, and the exact `codex-app` selector resolves the bounded App Runtime without PATH fallback.
- likely_scope: `agc_runtime/codex_app_runtime.py`, `agc_runtime/codex_extractor.py`, `agc_runtime/capture_cli.py`, focused tests, operations documentation, and this Bug Brief.
- active_scope: same as likely scope, plus the two confirmed Codex App turn events (`patch_apply_end` and `turn_aborted`), Pilot configuration, and production extractor configuration during installed verification.
- read_only_scope: installed Runtime, current Codex CLI help, isolated Pilot data under `D:\tmp_test`.
- excluded_scope: Scanner semantics, Runner semantics, general or speculative Session-format expansion, formal Memory Items, Hook, and production Capture mutation.
- fix_plan: completed in source. The five-field usage parser validates `cache_write_input_tokens`; the exact `codex-app` selector resolves one ordinary non-reparse App Runtime candidate below the fixed LocalAppData root and fails closed for missing or ambiguous candidates.
- verification_plan: completed. Focused and adjacent suites passed; the immutable Runtime was installed; installed historical and synthetic Pilots exercised the App Runtime; production was checked read-only and remained unchanged.

## Context Handoff

- lifecycle_session: `agc-history-pilot-20260821`
- user_intent: Import a few historical Sessions into AGC for an isolated test.
- active_sources: installed Codex CLI `0.142.0`, official non-interactive/Structured Outputs contracts, live capability output, current extractor source and tests.
- active_scope: Extractor/Structured Outputs compatibility and regression coverage.
- read_only_scope: installed Runtime and isolated Pilot state.
- candidate_scope: local Runtime reinstall after verification.
- excluded_scope: unrelated Capture or Memory behavior.
- current_gate: verified installed. The App selector and five-field usage path work with `gpt-5.6-sol`; production remains Scanner-only and unchanged.
- requested_stage_or_bridge: systematic-debugging followed by test-driven-development.
- constraints: preserve strict capability checks; do not expose Session content; keep all test artifacts under `D:\tmp_test`.

## Flow Record

- intake: completed; live Pilot failure captured.
- design: completed; compatibility gaps were isolated individually and kept within the Extractor boundary.
- plan: completed; regression-first minimal changes.
- implementation: usage support commit `e5c2022`; bounded resolver commit `817cdf7`; selector integration commit `3f1c28a`; confirmed App turn-event compatibility commit `04b2365`.
- verification: resolver and selector TDD RED states were observed before implementation. The final related regression passed `129` tests. Runtime `0.3.0` was installed into immutable venv `4ff51fb219b78df90b72c6a235f32f60a6577d1de23f9ae486fd4a24e409512d`. Installed `prepare-backfill` resolved Codex App Runtime `0.149.0-alpha.4` with model boundary `gpt-5.6-sol`. A real 45-turn App Session initially exposed the `patch_apply_end`/`turn_aborted` compatibility bug, then rescanned as 45 receipts after the fix with a healthy 50/50 Census and zero silent loss. Real historical Chinese Sessions completed without protocol failures but produced zero observations because the pre-existing safety gate accepts only narrow English atomic propositions. A separate one-turn, content-safe English diagnostic produced one Pilot observation, proving non-empty Structured Output, policy validation, and observation persistence. Nothing was promoted. Production read-only verification reported formal `memory_count=24`, Scanner-only mode, Hook disabled, degraded pre-existing source health, and no Pilot path leakage.
