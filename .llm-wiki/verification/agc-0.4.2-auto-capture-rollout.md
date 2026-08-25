# Verification: AGC 0.4.2 automatic Capture rollout

- verification_id: `agc-0.4.2-auto-capture-rollout`
- branch: `codex/task-aware-census-catalog`
- release_commit: `b1c9629`
- scheduler_fix_commit: `1563396`
- scheduler_time_trigger_commit: `e83fdb9`
- scheduler_timeout_commit: `fc00887`
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
- Runner configuration: enabled/unpaused, mode `runner`, one worker, 500000 incremental tokens, LogonTrigger plus 15-minute TimeTrigger, 30-minute execution limit, maximum 10 items, `IgnoreNew`.
- Extractor process evidence used the Codex App Runtime with `gpt-5.6-sol`, ephemeral/read-only sandbox, and the v1 output schema.
- First verification cycle created 10 incremental settlements and charged 60000 reserved tokens; one Observation was added.
- Formal Memory stayed byte-identical at 26 files with combined fingerprint `41b92a78473d58600dc1d3876a927c6edda82cce014950cb526bf128ee749c17`.
- Final exact-consent activation diagnosis again reported `continuous_runner_ready=true`, no conflicts, and digest `dc7e0e096eaa2e9ebf33e1a63b5ff83ffe9313f6cac39dec1179734bc66318af`.

## Live Scheduled Acceptance

- Windows started the repaired task automatically at 17:11:45 on 2026-08-25. One Runner root (PID 27820, created 17:11:46) remained the only registered cycle process throughout the run.
- At the next 15-minute trigger, 17:26:45, Task Scheduler attempted another launch but `IgnoreNew` preserved the original single process tree; no second Runner or orphan appeared.
- The original cycle reached the Codex App Runtime boundary at 17:29:00. Every observed Extractor child used `codex.exe exec --ephemeral`, read-only sandboxing, the v1 output schema, and model `gpt-5.6-sol`.
- The cycle exited naturally at 17:32:24, before the 30-minute limit. The task returned to `Ready`, `LastTaskResult=0`, the next run was 17:41:44, and no Runner or Extractor process remained.
- The cycle added five isolated Observations, taking the total to 22. It advanced complete receipts from 104 to 111 and settled tokens from 288000 to 336000; three receipts remained retryable under the existing bounded retry policy.
- Final accounting was 1238 known / 1238 accounted, pending 0, silent loss 0, and dirty markers 0. Formal Memory remained byte-identical at 26 files with the same combined fingerprint `41b92a78473d58600dc1d3876a927c6edda82cce014950cb526bf128ee749c17`.

## Scheduler Regression

- Reproduced Windows `Register-ScheduledTask` access denial followed by a false accepted envelope.
- Root cause: the scheduler cmdlet emitted a non-terminating error without explicit `-ErrorAction Stop`; the legacy task principal also required one UAC-assisted Action update.
- TDD RED: `test_windows_scheduler_registration_errors_are_terminating` failed against the original script.
- GREEN: the same test passed after the one-line fix.
- A second observed RED proved the scheduler XML lacked an active-session TimeTrigger. Production then reported `NextRunTime=16:41:44`, Windows automatically started the task at that time, and scheduled the following run for 16:56:44.
- A third observed RED proved the 15-minute task execution limit was shorter than a real scheduled cycle. The limit is now 30 minutes; the complete Host configurator file passed 15/15 in 57.44 seconds.
- During containment the task was disabled, a naturally exited second attempt was confirmed, and the remaining stale orphan was terminated by exact PID. Post-recovery status reported 1228/1228 accounted, pending 0, silent loss 0.
- The subsequent real 20-minute-39-second scheduled cycle crossed a second trigger with exactly one process tree and then completed with result 0, providing live evidence for both `IgnoreNew` and the 30-minute limit.
- Test integrity: one exact error-contract assertion was added; no safety assertion, fixture, mock, or expected success behavior was weakened.

## Residual Risk

- Verification authority is agent-local, not CI or an independent review.
- A Runner cycle can exceed the 15-minute trigger interval. The task now allows 30 minutes and uses `IgnoreNew`, so effective cadence can be 30 minutes when a prior cycle is still active.
- Model charges were reserved-usage settlements because the App Runtime did not expose accepted actual-usage metadata for these calls.
- Host configurator PowerShell scripts are repository deployment assets and are not members of the Runtime wheel; production was updated explicitly through the verified UAC transaction.
