# Bug Brief: Scanner scheduler invokes Runner cycle

- bug_id: `2026-08-21-scanner-scheduler-runs-runner-cycle`
- status: fixed-verified-live
- symptom: Scanner-only Host activation registers `cycle --root ... --once --max-items 10`; the CLI parses that exact shape as `runner-cycle` and rejects it while mode is `scanner_only`.
- expected: Scanner-only scheduling uses `cycle --root ... --once`; Runner scheduling retains the bounded `--max-items 10` form.
- evidence: live Scanner activation succeeded, but the registered argument shape maps to `runner-cycle` in `capture_cli._parse`; the same command returns a mode error before any model work.
- active_scope: `scripts/configure-capture-host.ps1`, `tests/test_capture_host_config.py`, this Bug Brief, Capture MVP verification/handoff/log.
- excluded_scope: Hook, Extractor, model/provider, task content, Memory Items, Capture data deletion.
- fix_plan: add a failing Host-config test that distinguishes Scanner and Runner scheduler arguments; pass an explicit scheduler mode into `Set-SchedulerState`.
- verification_plan: focused Host test RED/GREEN, complete Host/CLI focused tests, PowerShell 5/7 parse, live task re-registration, one incremental replay, status and rollback evidence.

## TDD evidence

- Live RED: the registered command returned `capture_mode_unsupported` because
  it was parsed as Runner while configuration was `scanner_only`.
- Automated RED: Scanner Host regression failed while the existing Runner
  assertion passed (`1 failed, 1 passed`).
- GREEN: `Set-SchedulerState` now takes explicit `scanner|runner` mode;
  Scanner emits `cycle --root ... --once`, Runner alone appends
  `--max-items 10`. Host plus CLI focused verification passed `28` tests;
  PowerShell 5.1/7 parsing and diff-check passed.

## Live verification

- Re-registered task `AgentGlobalContext-Capture-25e9201ae2f5` uses exactly
  `cycle --root <Memory Root> --once`, remains `IgnoreNew`, and is enabled.
- A manual start through Windows Task Scheduler completed with
  `LastTaskResult=0`. The post-run overview remained `38/38` accounted with
  `silent_loss=0`; no Runner, Hook, Extractor, or model was enabled.
