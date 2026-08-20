# Agent Global Context Capture Host Rollout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Package, install, supervise, measure, and safely roll out Capture on Windows/Codex through explicit consent gates, while upgrades remain inert by default and rollback preserves read/forget governance.

**Architecture:** The existing content-addressed installer deploys a Capture-capable Runtime and stable launchers but leaves Capture off. A separate transactional host configurator diagnoses the effective Skill/MCP/Memory/Source/Extractor route, registers a non-overlapping user Task Scheduler job for one-shot cycles, optionally merges a trusted async Stop Hook, and moves through scanner-only, shadow backfill, and continuous Runner gates. An executable release verifier records content-free evidence and a rollback drill proves that feature-disable retains Capture read/forget without touching Formal Memory.

**Tech Stack:** PowerShell 7 and Windows PowerShell 5.1, Windows Task Scheduler XML/cmdlets, Codex user `hooks.json`, Python package build/install, pytest 9.1.1, SHA-256 activation digests, existing transactional installer.

## Global Constraints

- Requires all three previous plan exit gates.
- This is plan 4 of 4. Code implementation does not itself authorize scanning the real profile, background model calls, Hook trust, seven-day backfill, or continuous activation.
- A normal install or upgrade must leave `capture.enabled=false`, `capture.mode=off`, Hook unregistered, scheduled task absent, and real Capture store empty.
- Every state-changing host action requires an explicit action plus the exact activation digest shown by `capture_status`; route, source, extractor, budget, or exclusion drift invalidates prior consent.
- Do not embed Scanner/Runner in the MCP process. The scheduled task invokes `agc-capture cycle --once`; Store leases and journal recovery handle overlap/crash.
- Never overwrite an existing `notify`, non-AGC MCP entry, Hook group, Skill, or project file. Unknown/ambiguous v1/v2 routes block activation and require a separate explicit resolution.
- Non-managed Codex Hooks require the user to review and trust the exact definition in `/hooks`; automation must not bypass Hook trust.
- If the installed Hook's 1,000-run latency has `p95 >= 100 ms`, do not activate it. Scanner-only remains the supported path.
- Seven-day Shadow Backfill is a separate explicit user gate and has a hard 100,000 actual-or-reserved token ceiling. Continuous Runner requires another explicit gate and a non-null incremental budget.
- Once Capture data exists, rollback means stop processing while retaining a Capture-capable Runtime for read/status/forget. Do not binary-downgrade to 0.2.0 and do not delete Capture data during uninstall/rollback.
- Every task follows red-green TDD and ends in a focused commit.

## Host Decisions Locked by This Plan

- Supervision: per-user Windows Scheduled Task, not a daemon and not MCP.
- Task name: `AgentGlobalContext-Capture-<first-12-chars-of-memory-root-id>`.
- Trigger: at user logon plus a configurable 15-minute repetition; no wall-clock completion SLA is promised.
- Overlap: `MultipleInstancesPolicy=IgnoreNew`; Scanner reconciliation means a skipped trigger cannot lose a Revision.
- Command: stable installed `agc-capture.cmd cycle --root <memory-root> --once --max-items 10`.
- Recovery: start when available, content-free local diagnostics, next cycle retries; Store recovery runs before scan/run.
- Hook source: user-level `<CODEX_HOME>/hooks.json`, merged structurally and backed up; inline/project Hooks remain untouched.
- Hook definition: async `Stop`, command points to stable `agc-capture-hook.cmd`, five-second timeout, no status message or output.

---

### Task 1: Make Installation Capture-Capable but Inert by Default

**Files:**
- Modify: `scripts/install-local.ps1`
- Modify: `tests/test_local_install.py`
- Modify: `pyproject.toml`
- Modify: `agc_runtime/__init__.py`
- Modify: `tests/test_cli_contract.py`
- Modify: `README.md`
- Modify: `README.zh.md`

**Interfaces:**
- Installs stable `agc-capture.cmd` and `agc-capture-hook.cmd` beside `agc-mcp.cmd`.
- Packages the default config and extractor schema.
- Sets the Capture-capable release version to `0.3.0` only after all prior plan suites pass.

- [x] **Step 1: Add failing inert-install tests**

Extend the install harness to assert a fresh install and a 0.2.0 upgrade:

```text
capture.enabled=false
capture.mode=off
capture Hook count=0
Capture scheduled-task count=0
Census/Receipt/Observation count=0
model invocation count=0
existing notify/config outside managed blocks byte-identical
```

Test missing/invalid Capture package assets, upgrade failure rollback, percent/non-ASCII paths, and launcher operation from the final content-addressed venv.

- [x] **Step 2: Verify RED**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest `
  tests/test_local_install.py tests/test_cli_contract.py -q `
  --basetemp 'C:\tmp\agc-capture-host-red-1'
```

- [x] **Step 3: Extend the transactional installer**

Reuse its path validation, preflight, unique backups, content-addressed venv, stable launcher swap, and rollback. Install package assets and launchers only. Do not accept an installer flag that silently enables Capture; activation belongs to the separate configurator and requires a digest.

Update documented version expectations to 0.3.0 in the same commit. Keep exactly three MCP tools; new executables are local operations, not MCP tools.

- [x] **Step 4: Verify GREEN and commit**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest `
  tests/test_local_install.py tests/test_cli_contract.py tests/test_mcp_server.py -q `
  --basetemp 'C:\tmp\agc-capture-host-green-1'
git add scripts/install-local.ps1 tests/test_local_install.py pyproject.toml `
  agc_runtime/__init__.py tests/test_cli_contract.py README.md README.zh.md
git commit -m "feat: package capture disabled by default"
```

---

### Task 2: Implement Route Diagnosis and Activation Digests

**Files:**
- Create: `agc_runtime/capture_activation.py`
- Create: `tests/test_capture_activation.py`
- Modify: `agc_runtime/capture_status_service.py`
- Modify: `agc_runtime/admin_service.py`
- Modify: `agc_runtime/mcp_server.py`
- Modify: `tests/test_capture_status.py`

**Interfaces:**
- Produces: `ActivationReport` and `activation_digest_for(report) -> str`.
- `capture_status` reports exactly one effective v2 Skill, installed Runtime hash/version, Memory Root ID, configured Source Root IDs, config source, extractor/provider/model boundary, Hook/Scheduler/Runner state, budgets, exclusions, Recall Gate, conflicts, and readiness.
- Absolute source paths stay local to the host configurator and are not returned through MCP.

- [x] **Step 1: Add failing AC-01/14 tests**

Create exact nodes:

```text
tests/test_capture_activation.py::test_ac_01_route_and_explicit_consent_gate
tests/test_capture_status.py::test_ac_14_pause_exclusions_and_scanner_only_are_diagnosable_and_recoverable
```

Cover disabled, scanner-only, runner, paused, missing source, invalid extractor, Recall Gate failure, project-level v1 plus user-level v2, multiple MCP blocks, multiple Memory Roots, stale binary/config hash, task/project exclusions, and digest change after any relevant field changes.

- [x] **Step 2: Verify RED**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest `
  tests/test_capture_activation.py tests/test_capture_status.py tests/test_mcp_server.py -q `
  --basetemp 'C:\tmp\agc-capture-host-red-2'
```

- [x] **Step 3: Implement fail-closed readiness**

Separate readiness levels:

```text
installed_inert
scanner_ready
hook_ready
backfill_runner_ready
continuous_runner_ready
```

`scanner_ready` needs one unambiguous v2 route and source binding. `hook_ready` additionally needs enabled Hooks, trusted effective definition evidence, and a passing latency report. `backfill_runner_ready` needs the frozen Census, extractor capability probe, and 100,000 budget. `continuous_runner_ready` additionally needs a non-null incremental budget and explicit activation digest.

Route conflicts are diagnostics only; do not delete project Skills or rewrite unknown config to make readiness pass.

- [x] **Step 4: Verify GREEN and commit**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest `
  tests/test_capture_activation.py tests/test_capture_status.py tests/test_mcp_server.py -q `
  --basetemp 'C:\tmp\agc-capture-host-green-2'
git add agc_runtime/capture_activation.py agc_runtime/capture_status_service.py `
  agc_runtime/admin_service.py agc_runtime/mcp_server.py `
  tests/test_capture_activation.py tests/test_capture_status.py
git commit -m "feat: gate capture activation by route digest"
```

---

### Task 3: Add Transactional Windows Supervision and Optional Hook Merge

**Files:**
- Create: `scripts/configure-capture-host.ps1`
- Create: `tests/test_capture_host_config.py`
- Create: `tests/fixtures/codex-hooks/existing-hooks.json`
- Create: `tests/fixtures/codex-hooks/existing-inline-config.toml`
- Modify: `tests/test_local_install.py`

**Interfaces:**
- Supports:

```text
-Action Status|EnableScanner|EnableHook|EnableRunner|Pause|Disable|Rollback
-CodexHome <path>
-MemoryRoot <path>
-InstallRoot <path>
-ExpectedActivationDigest <sha256>
-ActivationEvidencePath <content-free-json>
-ScheduleMinutes 15
-IncrementalTokenBudget <positive-int, EnableRunner only>
```

- Every mutating action creates a unique backup manifest before changing config, Hooks, or scheduled-task state.

- [x] **Step 1: Add failing host-config transaction tests**

Use temporary profiles and a fake Task Scheduler adapter to test exact task name/XML/command, no overlap, logon/repetition triggers, start-when-available, stable launcher, quoting, idempotent rerun, pause/disable, digest mismatch, path overlap/junction rejection, and rollback after each injected mutation failure.

Test structural `hooks.json` merge with existing Stop and other event groups. Require existing JSON values and `config.toml` (including unrelated `notify`) to remain byte-equivalent outside AGC-owned changes. Duplicate AGC Hook definitions are rejected or normalized to one. Invalid JSON, managed policy disabling Hooks, or an unknown conflicting AGC command blocks Hook activation.

- [x] **Step 2: Verify RED**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest `
  tests/test_capture_host_config.py tests/test_local_install.py -q `
  --basetemp 'C:\tmp\agc-capture-host-red-3'
```

- [x] **Step 3: Implement explicit staged actions**

`EnableScanner` verifies the digest, writes the one source binding, sets `enabled=true, mode=scanner_only`, and registers the scheduled task. It performs no immediate scan unless a separate `agc-capture scan` command is explicitly invoked.

`EnableHook` requires a passing latency-report hash, merges this exact user Hook shape, and tells the user to inspect/trust it through `/hooks`:

```json
{
  "type": "command",
  "command": "<stable agc-capture-hook.cmd command with --root>",
  "commandWindows": "<stable agc-capture-hook.cmd command with --root>",
  "async": true,
  "timeout": 5
}
```

It must not bypass trust. `EnableRunner` requires extractor capability evidence and explicit non-null incremental budget before setting `mode=runner`. `Pause` stops new model calls but keeps Scanner/Ledger/views. `Disable` sets mode off and unregisters new processing, preserving Capture data and read/forget.

- [x] **Step 4: Verify GREEN and commit**

Run the focused tests in both available PowerShell hosts where supported:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest `
  tests/test_capture_host_config.py tests/test_local_install.py -q `
  --basetemp 'C:\tmp\agc-capture-host-green-3'
git add scripts/configure-capture-host.ps1 tests/test_capture_host_config.py `
  tests/test_local_install.py tests/fixtures/codex-hooks
git commit -m "feat: supervise capture on Windows"
```

---

### Task 4: Add the Installed Hook Latency Gate and Scanner-Only Fallback

**Files:**
- Create: `scripts/measure-capture-hook.ps1`
- Create: `tests/test_capture_hook_latency_script.py`
- Modify: `scripts/configure-capture-host.ps1`
- Modify: `agc_runtime/capture_status_service.py`

**Interfaces:**
- Measures 1,000 representative invocations of the final installed launcher.
- Writes a content-free signed/hash-bound JSON report with sample count, min/median/p95/max, failures, launcher hash, Runtime hash, Host versions, and pass/fail.
- Never persists Hook stdin content; test markers use synthetic IDs and are removed after measurement.

- [x] **Step 1: Add failing benchmark-script tests**

Test percentile calculation, exactly 1,000 samples, cold/warm mix, launcher failure, marker cleanup, report binding, path quoting, and p95 boundary values of 99.999 and 100.000 ms. A failed or stale report must make Hook readiness false.

- [x] **Step 2: Verify RED**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_capture_hook_latency_script.py -q `
  --basetemp 'C:\tmp\agc-capture-host-red-4'
```

- [x] **Step 3: Implement AC-05 gate**

Run the installed command as the Codex user with representative environment and synthetic Stop metadata. Do not optimize by removing validation or atomic spool safety. If p95 is not strictly below 100 ms, `EnableHook` refuses and leaves Scanner-only operating; this is a supported outcome, not a release failure.

- [x] **Step 4: Verify GREEN and commit**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest `
  tests/test_capture_hook_latency_script.py tests/test_capture_hook.py `
  tests/test_capture_activation.py -q --basetemp 'C:\tmp\agc-capture-host-green-4'
git add scripts/measure-capture-hook.ps1 scripts/configure-capture-host.ps1 `
  agc_runtime/capture_status_service.py tests/test_capture_hook_latency_script.py
git commit -m "test: enforce capture hook latency gate"
```

---

### Task 5: Document Public Actions, Operator Gates, and Rollback Semantics

**Files:**
- Modify: `skills/agent-global-context/references/tool-contract.md`
- Modify: `skills/agent-global-context/SKILL.md`
- Modify: `tests/test_skill_adapter.py`
- Modify: `README.md`
- Modify: `README.zh.md`
- Create: `docs/capture-operations.md`

**Interfaces:**
- Documents explicit `capture_overview/search/get`, `capture_status`, and authorized `capture_forget` without adding a fourth MCP tool.
- Documents that Capture observations are inspectable evidence, not formal memory and not automatically injected.

- [x] **Step 1: Add failing documentation contract tests**

Require exact action examples, safe defaults, global scope definition, background cost disclosure, Provider boundary, exclusions, Hook trust, scanner-only fallback, seven-day/100,000 limit, and post-data rollback. Reject wording that implies every task becomes memory, zero latency/resource cost, provider-side Hard Forget, automatic promotion, or binary downgrade after data.

- [x] **Step 2: Verify RED**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_skill_adapter.py tests/test_local_install.py -q `
  --basetemp 'C:\tmp\agc-capture-host-red-5'
```

- [x] **Step 3: Update operator and Skill documentation**

Keep the public Skill thin: ordinary Recall behavior stays unchanged; Capture views are used only when the user asks to inspect/audit capture. Put operational commands, state transitions, activation-digest procedure, scheduled-task behavior, Hook review, model-cost warning, pause/disable, backup, forget, and rollback drill in `docs/capture-operations.md`.

- [x] **Step 4: Verify GREEN and commit**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_skill_adapter.py tests/test_local_install.py -q `
  --basetemp 'C:\tmp\agc-capture-host-green-5'
git add skills/agent-global-context/SKILL.md `
  skills/agent-global-context/references/tool-contract.md tests/test_skill_adapter.py `
  README.md README.zh.md docs/capture-operations.md
git commit -m "docs: explain capture controls and boundaries"
```

---

### Task 6: Build the AC-01..20 Release Verifier and Verification Record

**Files:**
- Create: `scripts/verify-capture-release.ps1`
- Create: `tests/test_capture_release_verifier.py`
- Create: `.llm-wiki/verification/2026-08-13-agc-capture-coverage-mvp.md`
- Create: `.llm-wiki/handoff/2026-08-13-agc-capture-coverage-mvp-handoff.md`
- Modify: `.llm-wiki/requirements/agc-capture-coverage-mvp.md`
- Modify: `.llm-wiki/working-context/agc-capture-coverage-mvp.md`
- Modify: `.llm-wiki/artifacts/index.md`
- Modify: `.llm-wiki/log.md`

**Interfaces:**
- One script executes every AC node plus full test/package/install/profile/text gates and writes content-free raw evidence.

- [ ] **Step 1: Add failing release-verifier integrity tests**

Require the script to enumerate AC-01 through AC-20 exactly once, stop on any nonzero gate, preserve raw stdout/stderr as content-free files, hash artifacts, and reject a Verification Record missing production/test/mock/assertion/behavior/residual-risk sections. Test path quoting and no secret/Observation/transcript leakage into evidence.

- [ ] **Step 2: Implement exact AC node execution**

The verifier runs the independently named nodes from all four plans, then:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest -q `
  --basetemp 'C:\tmp\agc-capture-release-pytest'
& '.\.venv\Scripts\python.exe' -m build
git diff --check
```

It also installs wheel and sdist into clean temporary environments, runs `pip check`, validates every entry point, tests PowerShell installer/host configuration, confirms exactly three MCP tools, and strictly decodes tracked text as UTF-8 without BOM.

- [ ] **Step 3: Verify inert deployed-profile upgrade before any activation**

With explicit deployment authorization, back up and upgrade the active profile. Record Runtime/Skill/config/launcher hashes, one effective MCP binding, Formal Memory count and Catalog hash before/after, and prove Capture remains off with zero scan/model/data. Resolve any project v1/global v2 ambiguity only through a separately confirmed exact target; otherwise stop at failed readiness.

- [ ] **Step 4: Perform the reversible host rollback drill**

On a synthetic or separately authorized user-scoped host binding: enable Scanner-only, run one cycle, pause, disable, and restore host config from its manifest. Verify unrelated `notify`/Hooks/config bytes, Formal Memory count/Catalog hash, Capture data, read/status/forget, Ledger resume point, and original Codex sources. Do not delete Capture data and do not downgrade after data.

- [ ] **Step 5: Complete release evidence and commit**

Run the verifier from a clean merged candidate. Populate the Verification Record with exact commands, exit codes, counts, hashes, installed evidence, test integrity, and residual risks. Populate the Handoff with disabled default and explicit next human gate.

```powershell
git add scripts/verify-capture-release.ps1 tests/test_capture_release_verifier.py `
  .llm-wiki/verification/2026-08-13-agc-capture-coverage-mvp.md `
  .llm-wiki/handoff/2026-08-13-agc-capture-coverage-mvp-handoff.md `
  .llm-wiki/requirements/agc-capture-coverage-mvp.md `
  .llm-wiki/working-context/agc-capture-coverage-mvp.md `
  .llm-wiki/artifacts/index.md .llm-wiki/log.md
git commit -m "test: verify capture coverage release"
```

---

### Task 7: Execute the Human-Gated Shadow Rollout

**Files:**
- Modify: `.llm-wiki/verification/2026-08-13-agc-capture-coverage-mvp.md`
- Modify: `.llm-wiki/handoff/2026-08-13-agc-capture-coverage-mvp-handoff.md`
- Modify: `.llm-wiki/requirements/agc-capture-coverage-mvp.md`

This task is intentionally blocked on new explicit user authorization after code/release review. Do not infer authorization from approval of this implementation plan.

- [ ] **Step 1: Obtain explicit Scanner-only authorization for the displayed digest**

Show the active Source Root IDs, seven-day half-open window, exclusions, zero model calls, schedule, resource boundary, and exact activation digest. After approval, enable Scanner-only, freeze the real Census, and verify main/subagent/revision classification and source health.

- [ ] **Step 2: Measure the final Hook and choose Hook or Scanner-only**

Run the 1,000-invocation installed benchmark. If and only if p95 is below 100 ms and the user reviews/trusts the Hook in `/hooks`, enable it. Otherwise record Scanner-only as the selected mode.

- [ ] **Step 3: Obtain explicit Shadow Backfill authorization**

Show extractor/provider/model, Capsule boundary, AGC-vs-provider deletion boundary, frozen Census size, and 100,000 actual-or-reserved ceiling. After approval, run concurrency one in bounded batches. Pause automatically at budget exhaustion, Source Health degradation, or safety/route anomaly.

- [ ] **Step 4: Let the user inspect Capture samples**

Use only explicit `capture_overview/search/get` views. Compare Capture-off, Scanner-only, and Runner-working resource measurements. Record classification/safety/noise feedback without promoting anything to Candidate or Formal Memory.

- [ ] **Step 5: Obtain separate continuous-incremental authorization**

Show the new activation digest and require a non-null incremental token budget. Only then enable continuous Runner. If approval is absent, leave Scanner-only or paused; the implementation remains valid and reversible.

## Acceptance Mapping

| Gate | Task/Test |
|---|---|
| AC-01 | Task 2 route/digest test and Task 6 deployed profile |
| AC-05 | Tasks 3/4 Hook boundary, 1,000-run p95, Scanner-only fallback |
| AC-14 | Tasks 2/3 pause, exclusions, modes, recovery |
| AC-20 | Task 6 release verifier and evidence |
| AC-03..19 integration | Task 6 invokes every independently named node from plans 1–3 |

## Executable Acceptance Index

`scripts/verify-capture-release.ps1 -Gate AC-NN` runs exactly the node below for AC-01 through AC-19. `-Gate AC-20` runs the full suite/package/install/deployed-profile/text gate without recursively invoking itself. `-Gate All` runs AC-01 through AC-20 in order.

| Gate | Independently runnable node or command |
|---|---|
| AC-01 | `tests/test_capture_activation.py::test_ac_01_route_and_explicit_consent_gate` |
| AC-02 | `tests/test_recall_activation_gate.py::test_ac_02_lifecycle_and_hard_overview_budget` |
| AC-03 | `tests/test_capture_scanner.py::test_ac_03_synthetic_seven_day_census_has_full_accounting` |
| AC-04 | `tests/test_codex_source_adapter.py::test_ac_04_only_completed_main_turns_are_revisions` |
| AC-05 | `tests/test_capture_hook_latency_script.py::test_ac_05_installed_hook_is_metadata_only_and_meets_or_falls_back` |
| AC-06 | `tests/test_capture_scanner.py::test_ac_06_reconciliation_recovers_missed_duplicate_and_moved_sources` |
| AC-07 | `tests/test_capture_runner.py::test_ac_07_complete_receipt_has_zero_to_eight_strict_observations` |
| AC-08 | `tests/test_capture_store.py::test_ac_08_two_level_idempotency_and_source_conflict` |
| AC-09 | `tests/test_capture_transaction.py::test_ac_09_every_crash_point_recovers_without_partial_or_duplicate_objects` |
| AC-10 | `tests/test_capture_end_to_end.py::test_ac_10_forbidden_sentinels_never_reach_managed_persistence` |
| AC-11 | `tests/test_capture_read_service.py::test_ac_11_capture_is_visible_only_to_explicit_capture_actions` |
| AC-12 | `tests/test_capture_runner.py::test_ac_12_pipeline_failures_never_change_foreground_result` |
| AC-13 | `tests/test_capture_runner.py::test_ac_13_single_concurrency_lease_and_backpressure_never_drop_revisions` |
| AC-14 | `tests/test_capture_status.py::test_ac_14_pause_exclusions_and_scanner_only_are_diagnosable_and_recoverable` |
| AC-15 | `tests/test_capture_token_budget.py::test_ac_15_backfill_never_exceeds_actual_or_reserved_ceiling` |
| AC-16 | `tests/test_capture_read_service.py::test_ac_16_views_filter_sort_page_and_redact_sources` |
| AC-17 | `tests/test_capture_backup_restore.py::test_ac_17_round_trip_preserves_capture_invariants_and_recall_isolation` |
| AC-18 | `tests/test_capture_forget.py::test_ac_18_observation_and_revision_forget_remove_all_managed_content` |
| AC-19 | `tests/test_codex_source_adapter.py::test_ac_19_unknown_formats_fail_closed_without_false_conflicts` |
| AC-20 | `& '.\scripts\verify-capture-release.ps1' -Gate AC-20` |

## Rollback Definition

Before Capture data exists, installer backup may restore the prior binary. After any Capture data exists, rollback is:

1. pause Runner;
2. disable Hook, Runner, and Scanner new processing;
3. retain Capture-capable Runtime and explicit read/status/forget;
4. preserve Capture data and Ledger resume point;
5. leave Formal Memory and original Codex tasks unchanged;
6. delete Capture data only through authorized `capture_forget`.

## Final Exit Gate

The implementation is release-ready when Task 6 passes with Capture inert. The Phase 1 outcome is operationally complete only after the separate Task 7 human gates establish Scanner coverage, optional Hook selection, bounded Shadow Backfill, user sample review, and an explicit decision on continuous incremental processing.
