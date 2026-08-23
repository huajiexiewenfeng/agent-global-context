# Verification: task-aware Census catalog 0.4.1

- verification_id: `2026-08-23-census-catalog-task-aware-backfill`
- branch: `codex/task-aware-census-catalog`
- source_head: `3ed1089`
- status: passed-agent-local; live Codex App reload pending
- authority: local agent execution; no CI or independent reviewer claim

## Regression Evidence

- Full repository suite before the final packed catalog layout: `1334 passed, 1 warning in 799.08s`.
- Complete Capture regression after the packed catalog layout: latest completion gate `1064 passed, 1 warning in 243.14s`; the preceding run also passed in 231.76s.
- Focused final store test: `24 passed in 5.64s`.
- The warning is the expected adversarial duplicate-ZIP-name safety case.
- `python -m compileall -q agc_runtime tests`: exit 0.
- `git diff --check`: exit 0.
- Production code and tests changed together. Assertions cover canonical deduplication, packed generation shape, hot-path member avoidance, invalidation, corruption and recovery, Hard Forget/backup behavior, deterministic ranking, per-task fairness, and Capsule reuse. The packed-layout test failed against the prior per-member layout before the implementation was changed.

## Package Evidence

- wheel: `D:\tmp_test\agc041_packed_dist\agent_global_context_runtime-0.4.1-py3-none-any.whl`
- wheel SHA-256: `340F09E1DBF0060097B39642AC9D59D54EE2E04528D90BCAA50E62A650EAA3CF`
- sdist SHA-256: `C94CAB40B332E2431CAB858783E530A3CE52B7895172263F7BB0E0CD378DB33B`
- wheel members: 63; required default config and Capture schema present; no tests, Session, production-memory, or Census catalog data present.

## Production Read-Only Acceptance

- evidence file: `D:\tmp_test\agc041_catalog_acceptance.json`
- memory-root fingerprint: `25e9201ae2f5c7883dab58e6597833da81b5c319db5f9a786692b9a0f8ecf9a6`
- cold catalog rebuild: 26.172 seconds
- two hot snapshots: 8.370 and 6.122 seconds
- frozen unique revisions: 915
- catalog unique revisions: 915
- hot member JSON reads: 0
- formal-memory files: 28; acceptance hash unchanged
- observations: 7 before and after
- charged tokens: 120000 before and after
- Extractor calls delta: 0
- No Session content, memory statement, model request, backfill, or formal-memory promotion was performed.

## Installed Runtime Evidence

- immutable venv: `C:\Users\admin\.agent-global-context-runtime\venvs\4f63831e70d0c6dea92dabf6096f477c15c6a7ace84719483cd4f3eb35c96bcf`
- installer exit: 0; installer backup: `C:\Users\admin\.agent-global-context-runtime\backups\20260823-222322-997-ecfe2417f317466b97ce19fb118351ed`
- `agc-mcp --version`: `0.4.1`
- `pip check`: `No broken requirements found.`
- installed/source SHA-256 equality passed for `capture_store.py`, `capture_runner.py`, `capture_forget_service.py`, `capture_forget_transaction.py`, and `runtime_config.py`.
- Installed probe: exit 0 in 3.718 seconds; Runtime 0.4.1; memory-root fingerprint matched; enabled `scanner_only`; paused false; model configured; 915 known/accounted keys and zero pending/silent-loss keys.
- Post-probe formal fingerprint `f5991dc4...c4ae`, observation count 7, and budget fingerprint `bf990789...a883` matched their pre-probe values.

## Residual Risk

- The current Codex task retained the old MCP process after the config update. Its `capture_status` call still exceeded 60 seconds and was terminated. Restarting Codex App is required to prove the in-app process is the newly installed 0.4.1 route.
- Scanner source health remains degraded and the Runner reports 837 discovered backlog items. This release does not process that backlog and no model authorization is implied.
- Existing frozen evidence remains on disk; the catalog removes hot-read amplification but does not compact historical run files.
