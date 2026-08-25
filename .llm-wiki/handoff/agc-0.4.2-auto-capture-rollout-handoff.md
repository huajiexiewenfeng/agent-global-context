# Handoff: AGC 0.4.2 automatic Capture rollout

## Result

AGC 0.4.2 is installed and live in Codex App. Automatic Capture runs every 15 minutes against new and pending safe Capsules through the Codex App `gpt-5.6-sol` boundary, with a 500000-token incremental ceiling, one worker, and no automatic formal-memory promotion.

## Production State

- Runtime: 0.4.2, immutable id `451b84dc62f34677755ec256683eed5d78e6a5a0041037ca942c31976a03fdd1`.
- Memory Root: enabled, unpaused, mode `runner`.
- Scheduler: enabled, LogonTrigger plus 15-minute TimeTrigger, 30-minute execution limit, `--max-items 10`, `IgnoreNew`.
- Hook: disabled.
- First cycle: 10 settlements, one new Observation, formal Memory unchanged at 26.
- Accounting: 1214/1214 accounted, pending 0, silent loss 0.

## Verification

- Record: `.llm-wiki/verification/agc-0.4.2-auto-capture-rollout.md`.
- Local commits: release `b1c9629`; scheduler fixes `1563396`, `e83fdb9`, and `fc00887`.
- Final activation reports `continuous_runner_ready=true` with no conflicts.
- Host configurator fixes passed 15/15 tests after three observed RED cases.
- Verification authority remains agent-local.

## Residual Risk

- Current full Census/candidate preparation can exceed a 15-minute interval; `IgnoreNew` prevents a new registered instance while the 30-minute task remains active.
- The existing scheduler ACL required one UAC-assisted Action update. Future registration denial now fails and rolls back transactionally.
- GitHub push and GitHub Release were excluded and remain undone.

## Next Action

Let the automatic Runner operate and review new Observations for quality. A later performance change should make recurring cycles incremental before increasing concurrency or lowering the interval.
