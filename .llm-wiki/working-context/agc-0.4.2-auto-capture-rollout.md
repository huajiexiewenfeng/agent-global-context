# AGC 0.4.2 Auto Capture Rollout Plan

> **For agentic workers:** Execute inline with TDD and verification checkpoints; no delegation is authorized.

**Goal:** Release, install, and activate the verified project-aware Capture implementation without automatic formal-memory promotion.

**Architecture:** Preserve the existing immutable deployment and exact-digest Host configurator. Version-only source changes precede regression and packaging; installation precedes route/Extractor evidence; Runner activation occurs last and only from a freshly verified status.

**Tech Stack:** Python, pytest, setuptools/build, PowerShell installer/configurator, Windows Task Scheduler, Codex App `gpt-5.6-sol` boundary.

## Global Constraints

- All test/build/evidence artifacts stay under `D:\tmp_test`.
- Do not push GitHub, enable Hook, auto-promote memory, delete Capture data, or change the provider/model.
- Stop before Runner activation if installed/live Runtime, route, Recall, Extractor, Census, or digest evidence is not ready.

### Task 1: Version contract

- [x] Change exact version expectations in `tests/test_cli_contract.py`, `tests/test_local_install.py`, `tests/test_mcp_server.py`, and `tests/test_capture_activation.py` to `0.4.2`.
- [x] Run focused tests and observe RED against the 0.4.1 source declarations.
- [x] Set `pyproject.toml` and `agc_runtime/__init__.py` to `0.4.2`; update version-specific operations documentation.
- [x] Re-run the focused version tests to GREEN and commit.

### Task 2: Regression and artifacts

- [x] Run the project-aware focused suite and full repository suite with `--basetemp` under `D:\tmp_test`.
- [x] Run compile, diff, and strict UTF-8/no-BOM gates.
- [x] Build wheel/sdist into `D:\tmp_test\agc042-dist-b1c9629` and inspect members/hashes.
- [x] Install the wheel into an isolated test venv and verify imports, entry points, version, and `pip check`.

### Task 3: Immutable production install

- [x] Capture content-free pre-state: Runtime/config hashes, formal-memory fingerprint/count, Observation count, token total, and scheduler state.
- [x] Run `scripts/install-local.ps1` with the committed repository, active Skills/Codex config/Memory Root/Install Root, and the stable Python executable.
- [x] Verify the new content-addressed venv, source hashes, entry points, `pip check`, config route, and installer backup.
- [x] Re-read live MCP status; App restart completed and live MCP reports 0.4.2.

### Task 4: Automatic Runner activation

- [x] Audit one effective v2 Skill, zero legacy Skills, one MCP block/root, Runtime/config hash matches, Recall Gate, App Extractor capability, frozen Census, Hook state, and scheduler state.
- [x] Write one content-free activation-evidence JSON under `D:\tmp_test`.
- [x] Run configurator `Status` and capture the exact fresh activation digest.
- [x] Run `EnableRunner` with the exact digest, `IncrementalTokenBudget 500000`, and `ScheduleMinutes 15`.
- [x] Verify `mode=runner`, enabled/unpaused, positive budget, one worker, scheduler, healthy accounting, zero automatic formal-memory delta, and configured `gpt-5.6-sol`.

Activation evidence:

- Immutable Runtime: `451b84dc62f34677755ec256683eed5d78e6a5a0041037ca942c31976a03fdd1`.
- Evidence SHA-256: `ff280a62fad48b2a68fe42f499a3eb202fd48f88bc7aa41687c07e1e8c52be0f`.
- Final activation digest: `dc7e0e096eaa2e9ebf33e1a63b5ff83ffe9313f6cac39dec1179734bc66318af`.
- Final readiness: route/scanner/backfill/continuous Runner ready; Hook remains disabled.
- First verification cycle: 10 incremental settlements, 60,000 reserved tokens charged, one new Observation, formal Memory count/hash unchanged at 26 / `41b92a78473d58600dc1d3876a927c6edda82cce014950cb526bf128ee749c17`.
- Census after cycle: 1,214 known/accounted, pending 0, silent loss 0.
- Scheduler: enabled, LogonTrigger plus 15-minute TimeTrigger, `IgnoreNew`, Runner maximum 10 items; Windows automatically started the task at 16:41:44 and scheduled the next run for 16:56:44.
- Host bugs found during activation: scheduler registration denial was non-terminating, and a LogonTrigger alone did not start periodic work in the active session. Both received observed RED/GREEN regressions; `tests/test_capture_host_config.py` passes 14/14.

### Task 5: Finish evidence

- [x] Record exact commands/results, artifact hashes, immutable Runtime id, transaction backup, activation digest/status, test integrity, and residual risk.
- [x] Update the Flow Record, verification artifact, handoff, Artifact Registry, and log through `project-finish`.
