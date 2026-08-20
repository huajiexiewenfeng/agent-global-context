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
- current_gate: Codex Source Census Task 6 verified; Extractor/Runner remains the next inactive implementation gate
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
- Remaining implementation gates: Extractor/Runner focused TDD, token-budget
  and model-call evidence, real-profile shadow-backfill diagnostics, continuous
  hosting, Hook trust and foreground-latency measurement, host route
  activation, and binary downgrade prevention.

## Execution Status

- requirement: in progress; Capture Core and Codex Source Census implemented, overall MVP not complete
- written_spec: approved
- implementation_plan: confirmed
- development: Capture Core and Codex Source Census Tasks 1-6 complete; Source
  Census Task 6 added a narrowly authorized same-quarantine replay fix and no
  Extractor/Runner/model/host behavior
- testing: Source Census review focused `4 passed`; ordered adjacent `100 passed`;
  complete `648 passed, 1 warning`; the unchanged clean installed wheel proves
  `agc-capture` and exactly three MCP tools
- next_gate: keep Capture inactive; proceed only to the Extractor/Runner plan,
  with real-profile shadow backfill and Host rollout still requiring later
  explicit gates

## Capture Core Task 6 Verification

### Exact test commands and results

```powershell
& '.\.venv\Scripts\python.exe' -m pytest `
  tests/test_capture_core_end_to_end.py -q `
  --basetemp '<temporary-root>\agc-capture-core-e2e-red'
# exit 1; 1 failed

& '.\.venv\Scripts\python.exe' -m pytest `
  tests/test_cli_contract.py tests/test_capture_core_end_to_end.py `
  tests/test_runtime_end_to_end.py -q `
  --basetemp '<temporary-root>\agc-capture-core-e2e-green'
# exit 0; 11 passed in 11.59s

$env:PYTHONPATH='<repository-venv-site-packages>;<bundled-backend-site-packages>'
& '.\.venv\Scripts\python.exe' -m pytest -q `
  --basetemp '<temporary-root>\agc-capture-core-full-clean'
# exit 0; 514 passed, 1 warning in 318.80s
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
& '.\.venv\Scripts\python.exe' -m build --wheel --no-isolation `
  --outdir '<temporary-root>\wheel' '<temporary-clean-source-copy>'
# exit 0; wheel built

& '<temporary-venv>\Scripts\python.exe' -m pip install --no-deps '<wheel>'
# exit 0; installed agent-global-context-runtime 0.2.0

& '<temporary-venv>\Scripts\agc.exe' --version
# exit 0; accepted, runtime_version 0.2.0

& '<temporary-venv>\Scripts\agc.exe' version
# exit 0; accepted, runtime_version 0.2.0

'{"action":"validate"}' | & '<temporary-venv>\Scripts\agc.exe' admin `
  --root '<temporary-memory-root>' --input -
# exit 0; accepted
```

An installed-artifact MCP probe ran outside the repository, asserted
`agc_runtime.__file__` resolved under the temporary venv's `site-packages`,
exited `0`, and returned exactly three tools: `agc.admin`, `agc.read`, and
`agc.write`.

```powershell
# strict UTF-8 decoder plus no-BOM check over tracked text files
# exit 0; 132 files
& '.\.venv\Scripts\python.exe' -m compileall -q agc_runtime tests
# exit 0
git diff --check
# exit 0
```

### Production, tests, mocks, assertions, actual behavior

- Production: `agc_runtime/cli.py` accepts both `version` and `--version`.
  Capture remains disabled by default with mode `off`, configured source count
  `0`, and no configured model.
- Tests: one new disabled-core E2E and stronger ordinary Recall lifecycle,
  budget, and post-forget validation assertions.
- Mocks: boundary tripwires are installed before Runtime imports and init for
  subprocess calls, planned Source/model/provider imports, source-root
  enumeration, socket calls, and URL calls. Real store, transactions,
  dispatchers, catalog, backup/restore, and forget paths run end to end.
- Assertions: init/validate, two-level replay idempotency, explicit read
  isolation, a non-no-op restore from `3` observations back to the backed-up
  `2`, both exact forget unions, suppression tombstone, an outside-root source
  sentinel byte-exact through both forget types, zero external behavior, and
  unchanged Formal Catalog byte hash/memory count at every step.
- Actual behavior: all assertions pass on a synthetic temporary root without a
profile, transcript, provider, network, or deployed AGC data.

### Residual risk and gate

The current Capture-capable Runtime rejects unsupported Capture schema and
backup manifests carry Capture schema `1`, but the package version is still
`0.2.0`. A pre-Capture 0.2.0 binary cannot be distinguished by semantic version
alone and cannot safely restore post-Capture data. Host rollout must retain a
Capture-capable Runtime and block that binary downgrade. Capture remains inert
and is not yet usable. The CLI-version mismatch is resolved; the next stage is
the Codex Source Census plan, still without enabling Capture.

## Codex Source Census Task 6 Verification

### Synthetic truth and replay

- The synthetic configured root ends with `10` JSONL files / `3297` bytes and
  no real prompt, answer, credential, profile, or copied transcript. It covers
  ordinary completion, two revisions of one continued task, exact
  active/archive replay and an archive move, explicit subagent exclusion,
  incomplete/aborted and partial tails, unknown format, configured task
  exclusion, transient sharing failure, late/out-of-order completion, missed
  Hook delivery, and one delivered dirty marker.
- The first one-shot Census run reports `5` known, `5` accounted, `0` silent
  loss, and retains the unresolved locked marker. The second one-shot cycle
  reports `7` known, `7` accounted, `0` silent loss, creates the two recovered
  Receipts, and acknowledges the marker only while the matching key is present
  in the locked strict snapshot's accounted set.
- Final strict state is `7` Census keys, `7` Receipts/Ledger entries (`6`
  discovered, `1` excluded), `0` Observations, `0` tombstones, `1`
  content-free Source Quarantine, and `0` dirty markers. Source Health remains
  truthfully degraded for unkeyed anomalies; those anomalies never enter the
  denominator.
- Third-cycle exact replay creates `0` Receipts and reports `7` replays. Census
  key membership/correctness metadata, Receipt, Ledger, tombstone, quarantine,
  conflict, and normalized scan-state correctness deltas are all zero. New
  frozen-run identity and scan time/state version are explicit permitted
  bookkeeping; active/archive locator movement is not Revision identity.

### RED / review fix / GREEN

```powershell
& '.\.venv\Scripts\python.exe' -m pytest `
  tests/test_capture_census_end_to_end.py -q -p no:cacheprovider `
  --basetemp 'D:\tmp\agc-capture-source-red-6'
# exit 1; 1 failed at the intentional unimplemented E2E scaffold

# Completed E2E against be1fc4b:
# exit 1; exact replay changed only Source Quarantine.created_at

# Focused corrupt-quarantine contract before fail-closed fix:
# exit 1; malformed durable quarantine was silently overwritten

& '.\.venv\Scripts\python.exe' -m pytest `
  tests/test_capture_census_end_to_end.py -q -p no:cacheprovider `
  --basetemp 'D:\tmp\agc-capture-source-focused-final-6'
# exit 0; 3 passed in 3.70s

# Evidence-review import-tripwire RED at b84c773:
# exit 1; missing capture_capsule fell through to ModuleNotFoundError

# MetaPathFinder calibration node:
# exit 0; 1 passed in 0.10s

# Final review-focused file:
# exit 0; 4 passed in 3.68s
```

The narrowly authorized production correction makes exact
same-binding/same-code Source Quarantine replay byte-stable, retains the
existing different-code single-slot replacement with a new timestamp, rejects
malformed existing quarantine state without mutation, and collapses one
batch's diagnostic list to its deterministic final single-slot value. It does
not change Source discovery, Census identity, model/Runner/Hook activation, or
formal-memory behavior.

### Complete and package gates

```powershell
# disabled-boundary-first adjacent Source Census/Core suite
# exit 0; 100 passed in 39.67s

& '.\.venv\Scripts\python.exe' -m pytest -q -p no:cacheprovider `
  --basetemp 'D:\tmp\agc-capture-source-review-full-final-6'
# exit 0; 648 passed, 1 expected warning in 302.32s

# clean copied-source wheel build/install, installed agc-capture probe,
# installed-module provenance, and exact-three-MCP-tools node
# exit 0; 2 passed in 10.93s
```

The one expected warning is the existing duplicate-name ZIP adversarial case.
An earlier reverse custom adjacent order produced only the documented
disabled-Core `sys.modules` precondition failure after Source suites; the
review's disabled-boundary-first order passed all `100`. An earlier full E2E comparison
included the permitted active/archive locator representative and was corrected
to compare Revision membership/correctness fields while separately requiring
one replay identity.

### Isolation and pending gates

An import-system `MetaPathFinder` is installed before deferred imports. It is
separately calibrated by deliberately importing the exact next-plan
`capture_capsule`, `capture_safety`, `capture_extractor`, `codex_extractor`,
`capture_budget`, and `capture_runner` modules plus Host-plan
`capture_activation`; every import increments its named counter and raises.
During the real Census operation all those counters, network/subprocess,
target-turn loader, Observation/formal write, and unconfigured-root guards stay
`0`. No nonexistent `task_capsule`, Hook-installer, scheduler, provider, or
model module is claimed. The real Stop Hook is exercised only for its existing
failure-open marker path and remains silent while Scanner discovery accounts
the Revision.

Status returns exactly one source-root id equal to `source_root_id_for` of the
canonical configured root. Every persisted Census key and any persisted
ScanState binding use that id. Ordinary Recall stays empty;
Candidate/Formal Memory/Event counts and the Formal Catalog byte hash are
unchanged. Every response/stdout/stderr and every managed Memory Root file is
scanned bytewise for source-content, prompt, last-assistant, raw-exception, and
absolute-path sentinels. All hits are zero outside the explicit operator-owned
`config.yaml`, which contains the expected configured source root exactly once.

Extractor/Runner, token-budget/model-call proof, real-profile shadow backfill,
continuous hosting, Hook trust and foreground p95 latency, host route
activation, and binary downgrade prevention remain pending. No live profile
was read or activated, and the overall Capture Coverage MVP is not complete.

## 2026-08-20 Fast-track and Host Rollout Resume

- Phase A manual backfill and Phase B incremental Runner are implemented and
  locally installed. The latest production commit is `99fdcbd`; the synthetic
  Scanner → manual backfill → incremental cycle → status E2E is committed at
  `c3fe412`.
- Fresh Phase B evidence: focused Runner/status/CLI/locking `54 passed`,
  adjacent Store/transaction/budget/extractor/backup `246 passed` with the
  intentional duplicate-ZIP warning, and the natural full suite `1215 passed`
  with that same single warning.
- Runner scope now includes retry/backoff, explicit retry, source drift
  quarantine, durable incremental budget, per-root single-concurrency lock,
  truthful backlog/attempt/status/token diagnostics, and installed synthetic
  operation. Compatible-version automatic reopen and exact source-byte/peak
  resource sampling are deferred hardening; they do not authorize activation.
- Host Rollout Task 1 is now active. It must publish version `0.3.0`, add
  stable `agc-capture.cmd` and `agc-capture-hook.cmd` launchers to the existing
  transactional installer, prove upgrade rollback, and remain inert by
  default. Real Codex profile reads, scheduled-task mutation, Hook mutation,
  Scanner enablement, and model calls remain excluded until their explicit
  human gates.

### Host Rollout Task 1 evidence

- Authentic RED: the six exact version/install nodes failed because Runtime
  and package metadata still reported `0.2.0`, and installer output/launchers
  exposed only `agc-mcp`.
- GREEN: version aliases/package metadata now report `0.3.0`; the existing
  content-addressed installer validates and publishes `agc-mcp`,
  `agc-capture`, and `agc-capture-hook` executables plus stable `.cmd`
  launchers. All three launchers participate in unique backup, no-op rerun,
  and caught-failure rollback.
- Focused `tests/test_local_install.py tests/test_cli_contract.py
  tests/test_mcp_server.py`: `57 passed`. The exact real upgrade node and the
  three-launcher rollback node also pass after the final assertions.
- A fresh `0.3.0` wheel built and installed in a disposable target. Installed
  imports report `0.3.0`, packaged default config and extractor schema are
  present, local executables include `agc`, `agc-mcp`, `agc-capture`, and
  `agc-capture-hook`, and MCP remains exactly `agc.admin`, `agc.read`, and
  `agc.write`.
- Inert boundary: packaged defaults remain `enabled: false` / `mode: off`;
  installation creates no Memory Root, Hook registration, scheduled task, or
  model invocation. Activation remains a later digest-gated Host action.

### Host Rollout Task 2 evidence

- Authentic RED: `13 failed` because the planned `capture_activation` module,
  five readiness levels, authorization digest, paused reason, and status
  activation projection did not exist.
- `ActivationEvidence` is a strict content-free schema containing only counts,
  booleans, enum capability state, and hash-match facts. Unknown/missing fields
  fail with a fixed error. It contains no absolute paths, commands, source
  text, or user content.
- `ActivationReport` separates `installed_inert`, `scanner_ready`,
  `hook_ready`, `backfill_runner_ready`, and `continuous_runner_ready`.
  Continuous readiness requires an exact SHA-256 digest over Runtime/config,
  Memory/Source IDs, extractor boundary, budgets, state, exclusion counts, and
  Host evidence. Consent state and derived readiness are excluded from the
  digest, avoiding circular authorization.
- Ordinary Admin/MCP status does not accept Host evidence injection. It emits
  the same not-assessed digest projection without importing the deferred Host
  module; the Scanner-only and disabled byte-inert boundaries remain intact.
- Fresh GREEN: plan-focused Activation/status/MCP plus disabled/scanner-only
  boundaries `39 passed`; adjacent Core/Census/manual Runner/status/MCP
  `61 passed`. The only intermediate failures were missing optional MCP and
  pywin32 dependencies in the Codex test interpreter; the final run used the
  installed AGC Python for MCP/pywin32 and appended pytest only.
- No Codex profile, real Memory Root, Hook definition, scheduled task, model,
  or source transcript was inspected or changed. Host supervision remains the
  next synthetic-only task.

### Host Rollout Task 3 evidence

- Authentic RED groups: missing Host configurator `3 failed`; Scanner/Hook
  mutation `2 failed / 3 passed`; Runner/Pause/Disable/recovery `3 failed / 5
  passed`; latency-report enforcement `5 failed / 6 passed`.
- `scripts/configure-capture-host.ps1` supports Status, EnableScanner,
  EnableHook, EnableRunner, Pause, Disable, and Rollback with exact digest
  gating. Status is deterministic, content-safe, and byte-inert.
- Each accepted mutation writes a unique before-image manifest. Injected
  failures restore config, Hooks, and scheduler state byte-exact; explicit
  Rollback selects only the latest committed action. Capture data is never a
  mutation target and remains present after Pause/Disable.
- Scanner supervision uses the stable launcher, logon plus configurable
  repetition, `IgnoreNew`, start-when-available, and a one-shot max-10 cycle.
  Tests use a file scheduler adapter; production emits/registers Windows Task
  Scheduler XML and exports/restores a prior owned task.
- Hook merge is structural: unrelated Stop/SessionStart values and Codex
  `config.toml` remain unchanged, duplicate exact owned definitions normalize
  to one, and invalid JSON, managed Hook disablement, or unknown conflicts
  block activation. Hook enablement requires an exact-hash report with at
  least 1,000 samples, p95 below 100 ms, pass=true, and the current launcher
  hash. The user must still inspect/trust the Hook through Codex `/hooks`.
- Fresh GREEN: Host configurator `11 passed`; configurator plus transactional
  local installer `52 passed in 186.87s`. PowerShell 7 and Windows PowerShell
  5.1 both parse the final script.
- All tests used temporary CodexHome/Memory/Install roots and a fake scheduler.
  No real profile, real Task Scheduler, Hook, transcript, or model was read or
  changed.

### Host Rollout Task 4 evidence

- Authentic RED: `4 failed` because the installed Hook measurement script did
  not exist. Boundary, real-process, failure, and path tests all failed at that
  missing artifact.
- `scripts/measure-capture-hook.ps1` defaults to exactly 1,000 independent
  launcher invocations with redirected stdin/stdout/stderr. Any non-zero exit
  or emitted output counts as failure; Hook payload content is never copied to
  the report.
- The atomic JSON report records only counts, min/median/p95/max milliseconds,
  cold/warm sample counts, failure count, launcher and Runtime SHA-256, Host
  versions, and pass/fail. Passing requires exactly 1,000 samples, zero
  failures, and p95 strictly below 100 ms; 99.999 passes and 100.000 fails.
- Marker cleanup snapshots the synthetic dirty spool and deletes only files
  introduced by measurement; a pre-existing marker remains byte-identical.
- Task 3 EnableHook already verifies exact report hash, schema, at least 1,000
  samples, strict p95, pass=true, and current launcher hash before any backup or
  Hook mutation. A failed/stale report leaves Scanner-only as the supported
  state.
- Fresh GREEN: latency-specific `6 passed`; latency + Capture Hook + Activation
  `35 passed`. No real Hook, profile, Memory Root, transcript, or scheduler was
  used.

### Host Rollout Task 5 evidence

- Authentic documentation RED: the Capture operations guide, public action
  examples, Skill boundary, and README links were absent (`3 failed`; one
  unrelated temp-root permission error was environment-only).
- `docs/capture-operations.md` now documents inert defaults, Scanner-first
  activation, seven-day/100,000 bounds, exclusions, Hook trust and fallback,
  Provider/background-cost boundaries, pause/disable, backup, authorized Hard
  Forget, and post-data rollback without promising binary downgrade or
  provider-side deletion.
- The public Skill remains thin: Capture observations are evidence rather than
  formal Memory Items, are not automatically injected, and are not
  automatically promoted. Capture reuses the existing three MCP tools.
- Fresh GREEN: `tests/test_skill_adapter.py` `16 passed`; combined Skill and
  isolated local-installer verification `57 passed in 162.86s`. No live
  profile, Memory Root, Hook, scheduler, transcript, or model was accessed.
