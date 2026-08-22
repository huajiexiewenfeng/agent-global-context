# Handoff: semantic Capture candidates

## Result

The fix is implemented, package-verified, installed in an immutable Runtime, and validated by one explicitly authorized isolated `gpt-5.6-sol` Pilot. The integration target is a fast-forward merge from `codex/fix-semantic-capture-empty` into `main` after the final branch test gate.

## Implementation

- `capture_safety.py` keeps the deterministic direct lane strict and adds a bounded semantic lane for assertive Chinese context and context-prefixed first-person English.
- Semantic evidence is accepted only for atomic `agent_inferred` drafts with `confidence=tentative`; deterministic direct evidence cannot use that exception to change meaning.
- `codex_extractor.py` instructs the model to split colloquial or compound signals into atomic tentative inferences backed by verbatim Capsule evidence.
- `capture_capsule.py` identifies whether a Capsule has a durable semantic field.
- `capture_runner.py` commits an empty Capsule as zero-token `no_durable_signal` before reservation or model invocation.

## Verification

- verification record: `.llm-wiki/verification/2026-08-22-semantic-capture-empty.md`
- focused relevant result: 761 passed, exit 0
- full result: 1293 passed, 2 known baseline CRLF failures, no new failures
- clean wheel: SHA-256 `1B9405A39D09F7DC236569E6271968C822E2CEF937E31F4DC893ED7F7D7249B8`
- installed Runtime: `af38109dbbbca0608ed42d2206cc4ed0ac2e5e3f3b0080109153581e8cda5bc0`
- installed/source core hashes: exact matches
- Pilot: one completed call, two collected observations, zero failure, zero silent loss, no promotion, production memory count 24
- trust level: passed-agent-local plus user-authorized live Pilot; no CI or independent reviewer claim

## Test Integrity

- Production code and tests changed together, so assertion strength was inspected before closure.
- The changed pre-Capsule expectation now permits two bounded context-prefixed statements into the semantic lane but still asserts that the same evidence is rejected as a direct claim.
- New tests first failed for the missing semantic Capsule, missing tentative persistence and prompt behavior, and wasteful empty-Capsule model call, then passed after minimal production changes.
- Existing adversarial Capsule tests exposed an over-broad first predicate and an inferred/direct provenance leak; both were fixed without deleting or weakening those tests.
- `FakeAdapter` gained only a configurable `user_signals` tuple to exercise the real Runner branch; the test asserts persisted receipt fields, report accounting, and zero Extractor calls rather than mock call behavior alone.

## Runtime State

- Production Capture: enabled, `scanner_only`, not paused.
- Extractor boundary: Codex App bundled runtime, `gpt-5.6-sol`.
- Hook: disabled.
- Production formal memories: 24.
- Pilot artifacts remain isolated under `D:\tmp_test` and do not appear in production configuration or receipts.

## Residual Risk

- Two unrelated Windows CRLF byte-idempotence tests remain red from the recorded baseline.
- Provider usage was unavailable in the Pilot response, so accounting conservatively charged the full 6,000-token reservation.
- The semantic predicate is intentionally bounded; future languages or discourse forms require reviewed regression cases.

## Next Action

Run the final relevant suite and Git completion audit, fast-forward merge into `main`, verify the merged suite and installed hashes, then record authoritative merge completion.
