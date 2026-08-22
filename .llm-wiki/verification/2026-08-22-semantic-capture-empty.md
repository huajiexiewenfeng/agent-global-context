# Verification: semantic Capture candidates

- verification_id: `2026-08-22-semantic-capture-empty`
- source_branch: `codex/fix-semantic-capture-empty`
- source_head_before_verification_docs: `9c6a32e`
- design: `docs/superpowers/specs/2026-08-21-agc-semantic-capture-candidates-design.md`
- plan: `docs/superpowers/plans/2026-08-22-agc-semantic-capture-candidates.md`
- status: source-package-installed-verified; isolated live Pilot pending fresh authorization.

## TDD Evidence

- Semantic Capsule RED: the real-style compound Chinese decision produced `user_signals == ()` and failed the new regression test.
- Semantic Capsule GREEN: `tests/test_capture_capsule_safety.py` passed `464` tests after the semantic input predicate was narrowed to keep all prior negative cases.
- Persistence/Prompt RED: the tentative inferred draft was policy-filtered and the Extractor instruction lacked semantic-mode rules.
- Persistence/Prompt GREEN: Capsule safety plus Extractor passed `518` tests. A neighboring regression first exposed and then verified that direct-lane evidence cannot be semantically rewritten.
- Empty Capsule RED: the Runner reported `reserved_attempt_count=1` for an empty Capsule.
- Empty Capsule GREEN: Runner/Store/transaction/end-to-end suites passed `73` tests; the final exact regression test also passed independently.

## Regression Evidence

- Relevant command: pytest with `-p no:cacheprovider --basetemp D:\tmp_test\sc-rel` over Capsule safety, Extractor, manual Runner, manual backfill end-to-end, Store, transaction, contracts, CLI, backfill, Codex source adapter, and Codex App Runtime tests.
- Relevant result: `761 passed in 78.73s`.
- Full command: pytest with `-p no:cacheprovider --basetemp D:\tmp_test\sf -q`.
- Full result: `1293 passed, 2 failed, 1 warning in 450.01s`.
- Known baseline failures only:
  - `tests/test_capture_host_config.py::test_enable_scanner_is_digest_gated_transactional_and_idempotent`
  - `tests/test_runtime_config.py::test_built_wheel_contains_default_and_installed_admin_init_works`
- Both remaining failures compare CRLF and LF bytes. The baseline long-path failure passed with the short basetemp. No new failure was introduced.

## Package Evidence

- Clean committed-source export: `D:\tmp_test\agc-semantic-capture-release-20260822\source`
- Wheel: `D:\tmp_test\agc-semantic-capture-release-20260822\dist\agent_global_context_runtime-0.3.0-py3-none-any.whl`
- Wheel SHA-256: `1B9405A39D09F7DC236569E6271968C822E2CEF937E31F4DC893ED7F7D7249B8`
- Isolated install: `D:\tmp_test\agc-semantic-capture-release-20260822\installed`
- Isolated imports resolved to the installed `capture_safety.py`, `capture_runner.py`, and `codex_extractor.py` with exit code 0.
- Installed wheel contents include the semantic prompt, `capsule_has_durable_signal`, and the `no_durable_signal` Runner branch.

## Installed Runtime Evidence

- Active immutable venv: `C:\Users\admin\.agent-global-context-runtime\venvs\af38109dbbbca0608ed42d2206cc4ed0ac2e5e3f3b0080109153581e8cda5bc0`
- Installer exit: 0.
- Stable `agc-capture.cmd` and `agc-mcp.cmd` launchers both target that venv.
- Backup: `C:\Users\admin\.agent-global-context-runtime\backups\20260822-100050-809-eb882752d04f4ea889a7b89a0c6048f8`
- Source and installed SHA-256 values match exactly:
  - `capture_safety.py`: `4471E551793B64E1B25749A0FBDB6F14EF5089B43B18B94332B377DCFC9BCEEE`
  - `codex_extractor.py`: `7B32FE569DF3301990A2A7647EAA4C47AB2E12C44CF1841C9FCF3F5203DE3F29`
  - `capture_capsule.py`: `27F26BB218777666A3A71B69046B20D50479CCA0A0F4A56C40AB557A8191DD2B`
  - `capture_runner.py`: `8DC0ACDFBA046759D0A501A1189D600A92A3055048B2D3B6FF78B3F6F0BD15F9`
- Production Capture configuration: enabled, `scanner_only`, not paused, executable `codex-app`, model `gpt-5.6-sol`.
- Capture Hook: disabled; no `hooks.json` exists and Codex config contains only the AGC MCP registration.
- Formal catalog: `memory_count=24`, `cards_count=24`.

## Pending Acceptance

- Prepare one hash-verified isolated historical Session copy under `D:\tmp_test` without a model call.
- Obtain fresh authorization bound to its exact digest, `gpt-5.6-sol`, `max-items 1`, and maximum 6,000 tokens.
- Verify at least one collected `agent_inferred`/`tentative` observation, zero silent loss, no automatic promotion, and unchanged production formal memory.
- Re-run branch completion checks and relevant tests, then fast-forward merge into `main` and verify authoritative main.
