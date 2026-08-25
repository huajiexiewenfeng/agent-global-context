# Handoff: AGC 0.4.2 automatic Capture rollout

## Result

AGC 0.4.2 is installed and live in Codex App. Automatic Capture runs every 15 minutes against new and pending safe Capsules through the Codex App `gpt-5.6-sol` boundary, with a 500000-token incremental ceiling, one worker, and no automatic formal-memory promotion.

## Production State

- Runtime: 0.4.2, immutable id `451b84dc62f34677755ec256683eed5d78e6a5a0041037ca942c31976a03fdd1`.
- Memory Root: enabled, unpaused, mode `runner`.
- Scheduler: enabled, LogonTrigger plus 15-minute TimeTrigger, `--max-items 10`, `IgnoreNew`; automatic start was observed at 16:41:44.
- Hook: disabled.
- First cycle: 10 settlements, one new Observation, formal Memory unchanged at 26.
- Accounting: 1214/1214 accounted, pending 0, silent loss 0.

## Verification

- Record: `.llm-wiki/verification/agc-0.4.2-auto-capture-rollout.md`.
- Local commits: release `b1c9629`, scheduler fail-closed fix `1563396`, active-session TimeTrigger fix `e83fdb9`.
- Final activation reports `continuous_runner_ready=true` with no conflicts.
- Host configurator fixes passed 14/14 tests after two observed RED cases.
- Verification authority remains agent-local.

## Residual Risk

- Current full Census/candidate preparation can consume most of a 15-minute interval; `IgnoreNew` prevents overlap.
- The existing scheduler ACL required one UAC-assisted Action update. Future registration denial now fails and rolls back transactionally.
- GitHub push and GitHub Release were excluded and remain undone.

## Next Action

Let the automatic Runner operate and review new Observations for quality. A later performance change should make recurring cycles incremental before increasing concurrency or lowering the interval.
