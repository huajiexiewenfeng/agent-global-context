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

- [ ] Change exact version expectations in `tests/test_cli_contract.py`, `tests/test_local_install.py`, `tests/test_mcp_server.py`, and `tests/test_capture_activation.py` to `0.4.2`.
- [ ] Run focused tests and observe RED against the 0.4.1 source declarations.
- [ ] Set `pyproject.toml` and `agc_runtime/__init__.py` to `0.4.2`; update version-specific operations documentation.
- [ ] Re-run the focused version tests to GREEN and commit.

### Task 2: Regression and artifacts

- [ ] Run the project-aware focused suite and full repository suite with `--basetemp` under `D:\tmp_test`.
- [ ] Run compile, diff, and strict UTF-8/no-BOM gates.
- [ ] Build wheel/sdist into `D:\tmp_test\agc042-dist` and inspect members/hashes.
- [ ] Install the wheel into an isolated test venv and verify imports, four entry points, version, and `pip check`.

### Task 3: Immutable production install

- [ ] Capture content-free pre-state: Runtime/config hashes, formal-memory fingerprint/count, Observation count, token total, and scheduler state.
- [ ] Run `scripts/install-local.ps1` with the committed repository, active Skills/Codex config/Memory Root/Install Root, and the stable Python executable.
- [ ] Verify the new content-addressed venv, source hashes, entry points, `pip check`, config route, and installer backup.
- [ ] Re-read live MCP status; stop for App restart if the existing process still reports 0.4.1.

### Task 4: Automatic Runner activation

- [ ] Audit one effective v2 Skill, zero legacy Skills, one MCP block/root, Runtime/config hash matches, Recall Gate, App Extractor capability, frozen Census, Hook state, and scheduler state.
- [ ] Write one content-free activation-evidence JSON under `D:\tmp_test`.
- [ ] Run configurator `Status` and capture the exact fresh activation digest.
- [ ] Run `EnableRunner` with the exact digest, `IncrementalTokenBudget 500000`, and `ScheduleMinutes 15`.
- [ ] Verify `mode=runner`, enabled/unpaused, positive budget, one worker, scheduler, healthy accounting, zero automatic formal-memory delta, and configured `gpt-5.6-sol`.

### Task 5: Finish evidence

- [ ] Record exact commands/results, artifact hashes, immutable Runtime id, transaction backup, activation digest/status, test integrity, and residual risk.
- [ ] Update the Flow Record, verification artifact, handoff, Artifact Registry, and log through `project-finish`.
