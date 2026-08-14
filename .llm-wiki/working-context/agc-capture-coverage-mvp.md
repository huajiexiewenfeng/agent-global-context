# Working Context: agc-capture-coverage-mvp

## Context Handoff

- lifecycle_session: agc-capture-coverage-mvp
- user_intent: Continue from the approved Capture Coverage written specification into dependency-ordered implementation plans, then pause for an execution-mode decision before production or test changes.
- active_sources:
  - `../requirements/agc-capture-coverage-mvp.md`
  - `../../docs/superpowers/specs/2026-07-28-agent-global-context-v2-design.md`
  - `../../docs/superpowers/specs/2026-08-13-agent-global-context-high-coverage-capture-design.md`
  - `../../docs/superpowers/plans/2026-08-13-agent-global-context-capture-core.md`
  - `../../docs/superpowers/plans/2026-08-13-agent-global-context-codex-source-census.md`
  - `../../docs/superpowers/plans/2026-08-13-agent-global-context-capture-extractor-runner.md`
  - `../../docs/superpowers/plans/2026-08-13-agent-global-context-capture-host-rollout.md`
- active_scope:
  - `.llm-wiki/requirements/agc-capture-coverage-mvp.md`
  - `.llm-wiki/working-context/agc-capture-coverage-mvp.md`
  - `.llm-wiki/artifacts/index.md`
  - `.llm-wiki/log.md`
  - `docs/superpowers/specs/2026-08-13-agent-global-context-high-coverage-capture-design.md`
  - `docs/superpowers/plans/2026-08-13-agent-global-context-capture-core.md`
  - `docs/superpowers/plans/2026-08-13-agent-global-context-codex-source-census.md`
  - `docs/superpowers/plans/2026-08-13-agent-global-context-capture-extractor-runner.md`
  - `docs/superpowers/plans/2026-08-13-agent-global-context-capture-host-rollout.md`
- read_only_scope:
  - `agc_runtime/`
  - `tests/`
  - `scripts/`
  - `skills/agent-global-context/`
  - `README.md`
  - `README.zh.md`
  - current Codex Host configuration and task-source metadata
- candidate_scope:
  - exact Runtime, Source Adapter, Scanner/Runner, host, installer, documentation, and test files named by the four proposed implementation plans
- excluded_scope:
  - production and test edits before plan confirmation
  - Observation aggregation, Candidate/Formal Memory mutation, semantic Recall changes, Trace/Eval/Loop, external memory engines, and full-history replay
- current_gate: Capture Core Task 6 package-gate review
- requested_stage_or_bridge: Subagent-Driven Development directly on `main`, with per-task TDD and independent review
- constraints:
  - current task behavior remains failure-open
  - foreground Hook performs no LLM, network, transcript parsing, or formal-memory work
  - collected observations remain outside ordinary Recall
  - no sensitive or secret persistence
  - Capture data is included in safe backup/restore and user-authorized Hard Forget
  - seven-day backfill and `100,000` total model-token ceiling

## Scope Lock

- locked_active_scope: planning and lifecycle documentation files listed under `active_scope`
- locked_read_only_scope: existing Runtime, tests, installers, Skills, README, and Host evidence
- locked_candidate_scope: implementation files and tests named by the four proposed plans
- locked_excluded_scope: production implementation in the written-spec revision; Phase 2 aggregation/promotion; Phase 3 application evaluation
- accepted_assumptions:
  - Hook delivery is an optimization and Scanner reconciliation is the coverage authority.
  - Main task is the capture unit; subagent work is evidence inside the parent task, not an independent memory source.
  - Short or irrelevant tasks legitimately produce zero observations but still produce truthful Receipt state.
- escalation_rule: Any change that lets Capture block a foreground task, automatically mutate formal memory, persist sensitive/raw transcript content, or expand beyond the seven-day window requires a new user decision and Change Brief scope update.

## Verification Plan

- Written-spec self-review: unresolved-marker scan, phase-boundary check, schema/state-machine consistency, and acceptance-to-design traceability.
- Source-contract review: main-task/revision identity, active/archive reconciliation, transcript-format drift, and Hook/Scanner separation.
- Documentation integrity: strict UTF-8/no-BOM scan for changed Markdown, `git diff --check`, and link/path existence checks.
- Implementation planning gate: every acceptance criterion must map to one independently testable plan task before execution can be confirmed.
- Future implementation gate: focused TDD per Capture contract, complete existing suite, package build, installer checks, deployed-profile diagnostics, synthetic seven-day census, crash/replay tests, sensitive-content tests, and foreground-latency measurement.

## Execution Status

- requirement: planned
- written_spec: approved
- implementation_plan: confirmed
- development: Capture Core Task 6 test/docs implementation complete; no production delta
- testing: focused and complete suites pass; installed wheel behavior passes except the literal `agc --version` spelling required by the Task 6 brief
- next_gate: resolve or explicitly accept the existing `agc --version` versus `agc version` contract mismatch before entering the Codex Source Census plan

## Capture Core Task 6 Verification

### Exact test commands and results

```powershell
& '.\.venv\Scripts\python.exe' -m pytest `
  tests/test_capture_core_end_to_end.py -q `
  --basetemp '<temporary-root>\agc-capture-core-e2e-red'
# exit 1; 1 failed

& '.\.venv\Scripts\python.exe' -m pytest `
  tests/test_capture_core_end_to_end.py tests/test_runtime_end_to_end.py -q `
  --basetemp '<temporary-root>\agc-capture-core-e2e-green'
# exit 0; 6 passed in 8.81s

$env:PYTHONPATH='<repository-venv-site-packages>;<bundled-backend-site-packages>'
& '.\.venv\Scripts\python.exe' -m pytest -q `
  --basetemp '<temporary-root>\agc-capture-core-full-clean'
# exit 0; 513 passed, 1 warning in 330.29s
```

The final full run orders the repository venv before the bundled backend. An
earlier diagnostic run put the bundled path first and produced `505 passed, 8
failed`; seven MCP failures came from a mismatched compiled `pydantic_core`, and
one installer failure came from an inherited offline flag. The exact affected
subset plus the wheel test then passed `12 passed in 167.71s`, followed by the
clean complete-suite result above. No product code was changed for these test
environment failures.

### Clean package and installed artifact

```powershell
$env:PYTHONPATH='<repository-venv-site-packages>;<bundled-backend-site-packages>'
$env:PIP_NO_INDEX='1'
$env:PIP_NO_INPUT='1'
$env:PIP_DISABLE_PIP_VERSION_CHECK='1'
& '.\.venv\Scripts\python.exe' -m build --wheel --no-isolation `
  --outdir '<temporary-root>\wheel' '<temporary-clean-source-copy>'
# exit 0; wheel built

& '<temporary-venv>\Scripts\python.exe' -m pip install --no-deps '<wheel>'
# exit 0; installed agent-global-context-runtime 0.2.0

& '<temporary-venv>\Scripts\agc.exe' --version
# exit 1; existing invalid_tool envelope

& '<temporary-venv>\Scripts\agc.exe' version
# exit 0; accepted, runtime_version 0.2.0

'{"action":"validate"}' | & '<temporary-venv>\Scripts\agc.exe' admin `
  --root '<temporary-memory-root>' --input -
# exit 0; accepted
```

An installed-artifact MCP probe from outside the repository returned exactly
three tools: `agc.admin`, `agc.read`, and `agc.write`.

### Production, tests, mocks, assertions, actual behavior

- Production: no changed production files. Capture remains disabled by default
  with mode `off`, configured source count `0`, and no configured model.
- Tests: one new disabled-core E2E and stronger ordinary Recall lifecycle,
  budget, and post-forget validation assertions.
- Mocks: only boundary tripwires for subprocess calls and deferred Capture
  Source/Scanner/Runner/Hook imports. Real store, transactions, dispatchers,
  catalog, backup/restore, and forget paths run end to end.
- Assertions: init/validate, two-level replay idempotency, explicit read
  isolation, backup/restore, both exact forget unions, suppression tombstone,
  source-task preservation, zero external behavior, and unchanged Formal
  Catalog byte hash/memory count at every step.
- Actual behavior: all assertions pass on a synthetic temporary root without a
  profile, transcript, provider, network, or deployed AGC data.

### Residual risk and gate

The current Capture-capable Runtime rejects unsupported Capture schema and
backup manifests carry Capture schema `1`, but the package version is still
`0.2.0`. A pre-Capture 0.2.0 binary cannot be distinguished by semantic version
alone and cannot safely restore post-Capture data. Host rollout must retain a
Capture-capable Runtime and block that binary downgrade. Capture remains inert
and is not yet usable. The Codex Source Census exit gate is held on the literal
CLI-version mismatch unless the user accepts `agc version` as the intended
installed-version check or separately authorizes a production CLI change.
