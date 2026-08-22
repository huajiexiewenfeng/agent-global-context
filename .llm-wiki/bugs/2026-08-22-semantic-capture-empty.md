# Bug Brief: semantic Capture candidates are dropped before extraction

- bug_id: `2026-08-22-semantic-capture-empty`
- status: verified-installed
- symptom: three authorized historical Codex App backfill items completed with `zero_reason=extractor_empty`, three Extractor calls, and zero observations even though at least one source contained durable compound Chinese project decisions.
- expected: keep the existing deterministic direct lane strict, admit bounded scrubbed assertive plain-language user context to a separate semantic lane, allow that broader evidence to persist only as atomic `agent_inferred` plus `tentative` observations, and complete genuinely empty Capsules locally without budget reservation or a model call.
- reproduction_status: reproduced by `test_compound_chinese_project_decision_reaches_tentative_semantic_lane`, which failed with an empty `user_signals` tuple before implementation and passed after the bounded semantic lane was added.
- likely_scope: `agc_runtime/capture_safety.py`, `agc_runtime/codex_extractor.py`, `agc_runtime/capture_capsule.py`, `agc_runtime/capture_runner.py`, their focused tests, and isolated Pilot evidence under `D:\tmp_test`.
- active_scope: bounded semantic user-input admission, mode-aware provenance validation, semantic Extractor instruction, empty-Capsule short-circuit, source/package/installed-runtime verification, and one separately authorized isolated Pilot.
- read_only_scope: production Capture configuration, receipts, formal memory count, prior installed Runtime, and the single historical Session selected for the isolated Pilot.
- excluded_scope: automatic promotion, production backfill, Hook enablement, continuous Runner enablement, taxonomy redesign, general unrestricted semantic parsing, secret/code filter relaxation, and unrelated baseline failures.
- root_cause: current `_user_has_high_signal()` delegates exclusively to deterministic fixed-grammar proposition parsing, so colloquial or compound Chinese user decisions are removed before the model sees the Capsule; the Runner also reserves budget and invokes the Extractor before checking whether the resulting Capsule contains any durable semantic field.
- hypothesis: a second bounded semantic-input predicate, paired with `agent_inferred`/`tentative`-only persistence and a pre-reservation no-signal branch, will recover reviewable candidates without weakening direct-memory guarantees or wasting model calls.
- fix_plan: execute `docs/superpowers/plans/2026-08-22-agc-semantic-capture-candidates.md` task-by-task using RED/GREEN tests.
- verification_plan: focused Capture suites; full repository suite with no new failures over the recorded `1289 passed, 3 failed` baseline; clean wheel inspection; immutable Runtime install; one exact-digest authorized `gpt-5.6-sol` Pilot; production formal memory remains 24.

## Context Handoff

- lifecycle_session: `2026-08-22-semantic-capture-empty`
- user_intent: fix semantic Capture loss, verify the installed AGC Runtime, and merge the verified result into `main`.
- active_sources: current branch source, production receipt metadata, and the confirmed design specification.
- active_scope: files listed above.
- candidate_scope: none.
- current_gate: TDD reproduction.
- requested_stage_or_bridge: systematic debugging and test-driven development.
- constraints: no Session text in tracked documentation; no model call without a fresh exact authorization; no automatic promotion.

## Flow Record

- intake: completed; three authorized historical items produced three `extractor_empty` receipts and zero observations, with no safety, policy, or over-limit filtering recorded.
- design: completed; two-lane design A was confirmed, preserving deterministic direct claims and confining broader semantic evidence to tentative agent inferences.
- plan: completed; implementation plan committed as `08c5200`.
- implementation: completed in `63ee802`, `82bc361`, and `9c6a32e`; the final semantic predicate admits assertive Chinese context and context-prefixed first-person English while preserving all prior negative safety cases.
- testing: completed through source/package verification; focused Capture/App Runtime regression passed 761 tests, the full repository suite passed 1293 tests with only the two known CRLF byte-idempotence failures, and the prior long-path baseline failure passed under the required short basetemp.
- installed_verification: completed; immutable Runtime `af38109dbbbca0608ed42d2206cc4ed0ac2e5e3f3b0080109153581e8cda5bc0` is active, four core installed file hashes match branch source, production remains `scanner_only`, Hook is absent, and formal memory remains 24.
- pilot: completed under exact authorization digest `35835b95fb0356e2ea9ee617ec41cd1f4aa374be55cad6f851233e5733b93e89`; one installed Runtime call to `gpt-5.6-sol` completed with two collected tentative inferred observations, zero failures, zero silent loss, and no promotion. Production formal memory remained 24 and no Pilot path leaked into production state.
- archive: completed through `.llm-wiki/handoff/2026-08-22-semantic-capture-empty-handoff.md` with evidence-backed implementation, test-integrity, installed Runtime, Pilot, and residual-risk state.
- merge: completed by fast-forwarding `codex/fix-semantic-capture-empty` into `main` at `da27dd6`; the merged relevant suite passed 761 tests and installed Runtime files exactly match the authoritative `main` Git blobs.
