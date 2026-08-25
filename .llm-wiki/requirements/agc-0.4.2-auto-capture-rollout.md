# Change Brief: agc-0.4.2-auto-capture-rollout

## Summary

- title: AGC 0.4.2 release, immutable install, and automatic Capture rollout
- flow_id: agc-0.4.2-auto-capture-rollout
- status: complete
- change: Release the merged project-aware Capture implementation as Runtime 0.4.2, install it immutably, and enable the scheduled Runner with a 500000-token incremental ceiling every 15 minutes.
- authorization: explicit user authorization on 2026-08-25 to send safe Capsules from new and pending Codex Sessions to OpenAI `gpt-5.6-sol`; no automatic formal-memory promotion.

## Scope

- active:
  - Runtime/package version declarations and exact version contract tests
  - version-specific Capture operations documentation
  - focused/full regression, wheel/sdist build, isolated artifact checks
  - immutable local Runtime installation and Codex App MCP route update
  - content-free activation evidence and exact activation digest
  - `EnableRunner` with `IncrementalTokenBudget=500000` and 15-minute schedule
  - post-install and post-activation status/zero-promotion verification
- reference-only:
  - production Memory Root formal memories and existing Capture evidence
  - installer/configurator scripts and prior 0.4.1 verification artifacts
- excluded:
  - GitHub push or GitHub Release
  - automatic formal-memory promotion
  - Hook activation
  - deletion, Hard Forget, historical rewrite, or budget bypass
  - changing model away from `gpt-5.6-sol`

## Acceptance

1. Source, package metadata, CLI, MCP, and installer probes report exactly `0.4.2`.
2. Project-aware Capture regressions and release gates pass with artifacts under `D:\tmp_test`.
3. Wheel contains required Runtime assets and no tests; wheel and sdist contain no Session data, production memory, or Census data.
4. Installer publishes a new content-addressed Runtime without mutating/removing the previous Runtime and updates the Codex App route transactionally.
5. Installed source hashes match committed source and `pip check` passes.
6. Live App status reports Runtime 0.4.2 after process reload; if the current App process remains on 0.4.1, Runner activation stops until restart.
7. Activation evidence truthfully reports route, Recall, Extractor, Census, scheduler, and Hook facts without content or paths.
8. Runner is enabled only with the exact current activation digest, 500000 incremental tokens, one worker, and 15-minute scheduling.
9. Formal-memory count and hashes are unchanged by installation/activation; Capture observations remain review-only.

## Verification Plan

- TDD RED/GREEN for the exact 0.4.2 version contract.
- Focused project-aware and complete repository regression.
- `compileall`, `git diff --check`, strict UTF-8/no-BOM, build, wheel inspection, and isolated install/import/entrypoint checks.
- Pre/post production snapshots limited to content-free counts/hashes/status.
- Configurator transaction backup and post-action `capture_status` verification.

## Flow Record

| Step | Status | Evidence | Updated |
|---|---|---|---|
| source | done | explicit user release/install/Runner authorization | 2026-08-25 |
| design | done | staged immutable install and exact-digest activation sequence | 2026-08-25 |
| plan | done | `.llm-wiki/working-context/agc-0.4.2-auto-capture-rollout.md` | 2026-08-25 |
| development | done | release `b1c9629`; scheduler fixes `1563396`, `e83fdb9`, `fc00887` | 2026-08-25 |
| testing | passed-agent-local | 1349 full-suite tests; 582 focused tests; 15/15 Host configurator tests; installed/live/automatic-trigger evidence | 2026-08-25 |
| archive | done | verification and handoff records for `agc-0.4.2-auto-capture-rollout` | 2026-08-25 |

## Risks And Controls

- Codex App was restarted and the live MCP route reports Runtime 0.4.2.
- Enabling Runner exposes safe Capsules to the configured provider: explicit authorization and a 500000-token ceiling are recorded.
- Existing backlog is large: task-aware bounded selection and one-worker concurrency remain unchanged.
- Installation/config changes are transactional and retain the prior immutable Runtime and before-image backup.
- The first Runner cycle spent about ten minutes in local Census/candidate preparation before model calls; the task keeps a 15-minute trigger but now permits 30 minutes for one cycle and uses `IgnoreNew`.
- The existing Windows task required one UAC-assisted Action update because its ACL used the legacy local principal. Future registration failures now terminate and roll back instead of reporting false success.
- A standalone TimeTrigger is required for activation inside an already logged-on session; production now has a LogonTrigger plus a 15-minute TimeTrigger with a non-null next run.
- The original 15-minute execution limit orphaned child processes at the trigger boundary. Production was quiesced, stale children were terminated after content-free health checks, and the limit was raised to 30 minutes before re-enabling.

## Open Questions

- none
