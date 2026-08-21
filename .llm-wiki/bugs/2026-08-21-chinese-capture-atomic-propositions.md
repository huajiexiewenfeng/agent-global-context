# Bug Brief: Chinese atomic Capture propositions are dropped

- bug_id: `2026-08-21-chinese-capture-atomic-propositions`
- status: verified-installed
- symptom: real Chinese Codex App Sessions complete extraction successfully but produce empty Capsules or policy-filtered drafts, while an equivalent narrow English proposition can persist a Pilot observation.
- expected: explicit, first-person Chinese atomic preferences, goals, methods, principles, and constraints pass the same bounded pre-Capsule and persistence gates as their English equivalents without accepting hypotheticals, quotations, code, secrets, or arbitrary natural-language claims.
- reproduction_status: reproduced with installed Runtime on real historical Sessions. A content-safe English diagnostic produced one observation. The Chinese architecture-diagram constraint initially failed the pre-Capsule gate; after the source fix, a live non-persistent `gpt-5.6-sol` call produced one schema-valid draft whose exact evidence and canonical Chinese proposition pass the persistence policy.
- likely_scope: `agc_runtime/capture_safety.py`, `agc_runtime/codex_extractor.py`, focused safety/Extractor tests, this Bug Brief, and isolated Pilot evidence under `D:\tmp_test`.
- active_scope: fixed Chinese subject/predicate forms, bounded Chinese object validation, exact bilingual extractor transformations, and real historical Pilot acceptance.
- excluded_scope: general Chinese semantic parsing, automatic promotion, relaxed secret/code filtering, production backfill, Hook, continuous Runner, and unrelated taxonomy changes.
- fix_plan: add explicit anchored Chinese proposition grammars on both evidence and persisted-statement sides; keep one canonical object binding; add a static prompt envelope that treats Capsule values as untrusted data and requires verbatim evidence plus exact statement transformations.
- verification_plan: observe TDD RED/GREEN; run full Capsule safety and Extractor suites; run the full App Runtime/backfill regression set; install a new immutable Runtime; process a bounded real historical Chinese Session in an isolated Pilot; verify at least one observation and zero silent loss; verify production formal memory remains 24.

## Flow Record

- intake: completed; real historical Chinese zero-observation behavior reduced to the English-only fixed grammar.
- design: conservative fixed grammar selected instead of broad language acceptance.
- implementation: commits `5bbe4db`, `1750bb1`, `03d1e57`, and `5f2857f` add bounded Chinese propositions, exact prompt transformations, deterministic direct-evidence statement normalization, and the confirmed App `item_completed` event.
- verification: focused RED/GREEN cycles were observed for the Chinese proposition, three-part contrast, prompt, deterministic normalization, and App event changes. Final combined source regression passed `593` tests. Changed files are valid UTF-8 without BOM. Runtime `0.3.0` was installed in immutable venv `bc2eab4548b3bc6a2f4702b0237e82d25bbb3fbe2d497229cda6d73156f46950`. The final isolated Pilot used a SHA-256-matched real Codex App Session, reported healthy 7/7 accounting, seven complete receipts, zero failures, zero silent loss, full inspection completion, and one collected Chinese observation. The observation remains Pilot-only and was not promoted. Final production read-only verification reported formal `memory_count=24`, `scanner_only`, Hook disabled, the configured `codex-app`/`gpt-5.6-sol` boundary, no Pilot path leakage, and unchanged pre-existing degraded source health; no production backfill was run.
