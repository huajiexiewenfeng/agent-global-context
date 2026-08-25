# Verification: AGC 0.4.2 automatic Capture rollout

- verification_id: `agc-0.4.2-auto-capture-rollout`
- branch: `codex/task-aware-census-catalog`
- release_commit: `b1c9629`
- scheduler_fix_commit: `1563396`
- scheduler_time_trigger_commit: `e83fdb9`
- status: passed-agent-local
- executor: agent-local plus user-approved Windows UAC for the existing task ACL
- authority: agent-local; no CI or independent reviewer claim
- limitation_acceptor: none; no verification limitation was accepted

## Release Evidence

- Version/installer contracts: 71 passed in 168.28 seconds after an observed RED against 0.4.1.
- Project-aware focused regression: 582 passed in 33.16 seconds.
- Full repository regression: 1349 passed with one expected duplicate-ZIP adversarial warning in 486.61 seconds.
- Compileall, `git diff --check`, and strict UTF-8/no-BOM checks passed for 232 tracked files.
- Installed wheel SHA-256: `ad8ebeec910aadc8084d100b69cca74db5856c0e7533177739176de811793247`.
- Final rebuilt wheel/sdist under `D:\tmp_test\agc042-dist-final-1563396`: `beb96c12074b6bc00a6e44be1d285ad44c3b7784cffda83c80e54981f932d9ed` / `48b996ad2588c864fa3ef8f5ca56a5d5d165d60e4d9ff1866d7fa191ddf78e22`.
- Isolated wheel install reported Runtime/MCP 0.4.2 and `pip check` reported no broken requirements.

## Production Evidence

- Immutable Runtime id: `451b84dc62f34677755ec256683eed5d78e6a5a0041037ca942c31976a03fdd1`.
- Installer backup: `20260825-152815-429-6c7f9ca9f7584174b5cb5494a7e023bd`.
- Live MCP reports 0.4.2 after the user restarted Codex App.
- Activation evidence: `D:\tmp_test\agc042-activation-evidence-20260825.json`, SHA-256 `ff280a62fad48b2a68fe42f499a3eb202fd48f88bc7aa41687c07e1e8c52be0f`.
- Final activation digest: `dc7e0e096eaa2e9ebf33e1a63b5ff83ffe9313f6cac39dec1179734bc66318af`.
- Final activation: route/scanner/backfill/continuous Runner ready, no conflicts, Hook disabled.
- Runner configuration: enabled/unpaused, mode `runner`, one worker, 500000 incremental tokens, LogonTrigger plus 15-minute TimeTrigger, maximum 10 items, `IgnoreNew`.
- Extractor process evidence used the Codex App Runtime with `gpt-5.6-sol`, ephemeral/read-only sandbox, and the v1 output schema.
- First verification cycle created 10 incremental settlements and charged 60000 reserved tokens; one Observation was added.
- Formal Memory stayed byte-identical at 26 files with combined fingerprint `41b92a78473d58600dc1d3876a927c6edda82cce014950cb526bf128ee749c17`.
- Post-cycle Census: 1214 known/accounted, pending 0, silent loss 0.

## Scheduler Regression

- Reproduced Windows `Register-ScheduledTask` access denial followed by a false accepted envelope.
- Root cause: the scheduler cmdlet emitted a non-terminating error without explicit `-ErrorAction Stop`; the legacy task principal also required one UAC-assisted Action update.
- TDD RED: `test_windows_scheduler_registration_errors_are_terminating` failed against the original script.
- GREEN: the same test passed after the one-line fix.
- A second observed RED proved the scheduler XML lacked an active-session TimeTrigger. Production then reported `NextRunTime=16:41:44`, Windows automatically started the task at that time, and scheduled the following run for 16:56:44.
- The complete Host configurator file passed 14/14 in 48.32 seconds after both fixes.
- Test integrity: one exact error-contract assertion was added; no safety assertion, fixture, mock, or expected success behavior was weakened.

## Residual Risk

- Verification authority is agent-local, not CI or an independent review.
- A Runner cycle spent roughly ten minutes in local Census/candidate preparation before model calls; the 15-minute task uses `IgnoreNew`, preventing overlap but potentially reducing effective cadence.
- Model charges were reserved-usage settlements because the App Runtime did not expose accepted actual-usage metadata for these calls.
- Host configurator PowerShell scripts are repository deployment assets and are not members of the Runtime wheel; production was updated explicitly through the verified UAC transaction.
