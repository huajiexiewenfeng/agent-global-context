# AGC Capture Trace Production Activation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make AGC Runtime 0.4.3 reproducibly install and activate the already verified optional Capture-to-Trace bridge.

**Architecture:** Preserve the scheduled task's stable `agc-capture.cmd` target. Bind the optional dependency profile and the explicit local Trace source into the immutable Runtime deployment key, install local Contracts + Trace with AGC only when explicitly enabled, and inject the database path only in the Capture launcher.

**Tech Stack:** PowerShell 5.1-compatible installer, Python 3.12+ for the Trace-enabled profile, pytest, setuptools.

## Global Constraints

- Work directly on the user-approved current branch.
- Put temporary test artifacts only under `D:\tmp_test`.
- Keep Trace optional and failure-open; default installation behavior must not change.
- Do not modify the scheduled-task definition, Capture semantics, Recall, Eval, or Trace Runtime.
- Do not install into production, publish, or push GitHub in this implementation phase.

---

### Task 1: Lock the installer activation contract with failing tests

**Files:**
- Modify: `tests/test_local_install.py`

**Interfaces:**
- Consumes: `scripts/install-local.ps1` command-line parameters and JSON result.
- Produces: regression coverage for the default profile, local-source Trace profile, launcher environment, and invalid option combinations.

- [x] **Step 1: Extend the test invocation helper**

Add `enable_capture_trace: bool = False`, `trace_runtime_root: Path | None = None`, and `trace_database: Path | None = None`; append each matching installer argument only when requested. Build a minimal local Contracts + Trace package fixture inside the test directory.

- [x] **Step 2: Add focused behavioral tests**

Add tests which assert that the default Capture launcher remains one line, the enabled launcher contains `@set "AGENT_TRACE_DB=<escaped path>"` before the executable, MCP and Hook launchers remain unchanged, and `-TraceDatabase` without `-EnableCaptureTrace` fails before active mutation.

- [x] **Step 3: Add the immutable profile test**

Run a no-dependency local Runtime install once with the default profile and once with Trace enabled from the fixture root; assert that the published executable paths differ and both immutable deployments remain present.

- [x] **Step 4: Run RED verification**

Run:

```powershell
python -m pytest tests/test_local_install.py -k "capture_trace or trace_database or runtime_deployment_key" --basetemp D:\tmp_test\agc-trace-activation-red -q
```

Expected: failures because the installer does not yet accept `-EnableCaptureTrace`, does not bind an install profile into the deployment key, and does not write the environment-setting launcher line.

### Task 2: Implement the minimal activation path

**Files:**
- Modify: `scripts/install-local.ps1`

**Interfaces:**
- Consumes: `-EnableCaptureTrace` and optional `-TraceDatabase`.
- Produces: a profile-specific immutable Runtime and stable Capture launcher.

- [x] **Step 1: Add and validate parameters**

Add `[switch]$EnableCaptureTrace`, `[string]$TraceRuntimeRoot`, and `[string]$TraceDatabase`. Require a validated local Trace root when enabled, reject Trace options without the enable switch, and resolve the database to an absolute path defaulting to `.agent-trace-runtime/trace.sqlite3` below the current user profile.

- [x] **Step 2: Bind the install profile into the deployment key**

Add `InstallProfile` and optional `TraceRuntimeRoot` arguments to `Get-RuntimeDeploymentKey`; hash `mcp` or `mcp+trace` plus the local Contracts/Trace package inputs.

- [x] **Step 3: Install and validate the selected extras**

Use `<repository>[mcp]` by default. When enabled, install `<trace-root>/contracts`, `<trace-root>/runtimes/trace`, and `<repository>[mcp,trace]` together. On a normal dependency install, add `import agent_trace_runtime` to inactive deployment validation.

- [x] **Step 4: Generate the Trace-enabled Capture launcher**

Prefix only `agc-capture.cmd` with the quoted `AGENT_TRACE_DB` assignment. Escape literal percent characters in both the database path and executable path.

- [x] **Step 5: Run GREEN verification**

Run the focused command from Task 1 with basetemp `D:\tmp_test\agc-trace-activation-green`; expected result: all selected tests pass.

### Task 3: Version, document, and verify the release candidate

**Files:**
- Modify: `pyproject.toml`
- Modify: `agc_runtime/__init__.py`
- Modify: `tests/test_cli_contract.py`
- Modify: `tests/test_mcp_server.py`
- Modify: `tests/test_local_install.py`
- Modify: `README.md`
- Modify: `README.en.md`
- Modify: `README.zh.md`
- Modify: `docs/install.md`
- Modify: `docs/capture-operations.md`
- Modify: `.llm-wiki/requirements/agc-capture-trace-production-activation.md`

**Interfaces:**
- Consumes: the verified installer activation behavior.
- Produces: Runtime 0.4.3 source and user-facing activation instructions.

- [x] **Step 1: Bump version contracts to 0.4.3**

Update package metadata, `agc_runtime.__version__`, and exact version assertions.

- [x] **Step 2: Document the opt-in command**

Show `-EnableCaptureTrace` with the default database path and the optional `-TraceDatabase` override. State that only automatic Capture batch metadata is recorded.

- [x] **Step 3: Run focused and full verification**

Run installer/version tests, the complete pytest collection under `D:\tmp_test`, Ruff on modified Python files, and `python -m build` with output directed under `D:\tmp_test`.

- [x] **Step 4: Run an isolated local smoke**

Install with Trace enabled under `D:\tmp_test`, run one controlled significant Capture cycle, and inspect the Trace Snapshot. Do not access or modify production AGC state.

- [x] **Step 5: Record verification evidence**

Update the Change Brief Flow Record with exact commands and outcomes; leave production installation, publishing, and GitHub push pending explicit authorization.
