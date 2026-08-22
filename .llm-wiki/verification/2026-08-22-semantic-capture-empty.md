# Verification: semantic Capture candidates

- verification_id: `2026-08-22-semantic-capture-empty`
- source_branch: `codex/fix-semantic-capture-empty`
- source_head_before_verification_docs: `9c6a32e`
- design: `docs/superpowers/specs/2026-08-21-agc-semantic-capture-candidates-design.md`
- plan: `docs/superpowers/plans/2026-08-22-agc-semantic-capture-candidates.md`
- status: source-package-installed-pilot-verified; final branch audit and merge pending.

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

## Isolated Pilot Evidence

- Pilot root: `D:\tmp_test\agc-semantic-capture-pilot-20260822`.
- Historical source and isolated copy SHA-256: `0005246AA78F6988D908CCF41237DFAAE084A3EF8D76A133A8EC9D8F1B2E4349`.
- Census: healthy, two accounted revisions, zero quarantine, zero silent loss, and zero charged tokens before authorization.
- Local preflight: the first ready revision contained two semantic user signals; the second contained no durable signal. No Session text was written to tracked verification records.
- Exact authorization digest: `35835b95fb0356e2ea9ee617ec41cd1f4aa374be55cad6f851233e5733b93e89`.
- Authorized boundary: OpenAI `gpt-5.6-sol`, `max-items 1`, maximum 6,000 tokens, no automatic promotion.
- Installed backfill result: exit 0; attempted 1, completed 1, Extractor calls 1, observations 2, failures 0, silent loss 0, charged tokens 6,000.
- Usage quality is `reserved`: the provider response did not report complete usage, so the safety budget charged the full authorized reservation rather than claiming a lower measured value.
- Collected observations:
  - `co_74699b46873bd5286b9b9dcba9d417bbb3ffdc75c758d83572d615d8313cb303`
  - `co_a106f5129f62cd64b4cff77d7714c22ab4c518448ee4dc3f1a28a38b672897f0`
- Both observations are atomic, `assertion.mode=agent_inferred`, `confidence=tentative`, `processing_state=collected`, normal sensitivity, and preserve the Capsule project scope (`null` for this source).
- The persistence gate accepted each draft only after validating verbatim Capsule evidence. The durable Observation schema stores the source Session locator rather than duplicating evidence text.
- Pilot formal memory count remained 0; no observation was promoted.
- Production invariants after Pilot: formal `memory_count=24`, `cards_count=24`, Capture enabled in `scanner_only`, paused false, Hook disabled, `codex-app` plus `gpt-5.6-sol`, and zero Pilot-path matches in production config/Capture state.
- The four installed core file hashes still match branch source after Pilot.

## Residual Risks

- The semantic input predicate intentionally remains bounded rather than acting as a general natural-language classifier; new languages or discourse forms may need additional reviewed cases.
- Two pre-existing Windows CRLF byte-idempotence tests remain red and are unrelated to this Capture behavior.
- Provider token usage was unavailable for the Pilot, so accounting conservatively charged the full 6,000-token reservation.

## Remaining Acceptance

- Re-run the relevant Capture suite and branch completion checks.
- Fast-forward merge into `main`, verify authoritative main, and confirm installed Runtime hashes match merged source.
