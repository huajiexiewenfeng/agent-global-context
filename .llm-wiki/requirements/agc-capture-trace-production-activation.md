# Change Brief: agc-capture-trace-production-activation

## Summary

- flow_id: `agc-capture-trace-production-activation`
- parent_flow_id: `agc-capture-trace-bridge`
- status: implemented-verified-local
- why: Make the verified optional Capture-to-Trace bridge reproducibly installable without mutating an existing immutable Runtime deployment or complicating the Windows scheduled-task definition.

## Change

Release the local source as Runtime `0.4.3` and add one explicit installer switch, `-EnableCaptureTrace`. Because Trace Runtime `0.1.0` and Contracts `0.1.0` are not yet available from the configured package index, enabled local installs also require `-TraceRuntimeRoot`. The installer installs both local packages with AGC into a distinct content-addressed Runtime deployment and writes `AGENT_TRACE_DB` into the stable Capture launcher. An optional `-TraceDatabase` overrides the default per-user database path.

## Active Scope

- `scripts/install-local.ps1`
- `tests/test_local_install.py`
- Runtime version declarations and version contract tests
- user-facing install and Capture operations documentation

## Read-Only Scope

- existing Capture-to-Trace bridge behavior
- existing scheduled task action targeting the stable `agc-capture.cmd`
- Trace Runtime `0.1.x` package and database contract

## Excluded Scope

- changing the scheduled-task XML or cadence
- tracing Recall, promotion, merge, Hard Forget, or individual Capture items
- Trace schema or Trace Runtime changes
- Eval integration
- production installation, task disable/enable, publishing, and GitHub push

## Acceptance Criteria

1. Default installation remains Trace-disabled, installs only the `mcp` extra, and preserves the existing one-line Capture launcher.
2. `-EnableCaptureTrace -TraceRuntimeRoot <root>` installs the local Contracts and Trace packages with AGC and binds their source content into a deployment key distinct from the default profile.
3. Trace activation writes only the stable Capture launcher with `AGENT_TRACE_DB`; MCP and Capture Hook launchers remain unchanged.
4. The default database is the current user's `.agent-trace-runtime/trace.sqlite3`; `-TraceDatabase` accepts an explicit absolute destination only when Trace is enabled, and Trace source options are rejected without the enable switch.
5. Installer failure continues to preserve the active immutable Runtime, config, skills, and launchers.
6. Runtime and CLI version contracts report `0.4.3`.

## Verification Plan

- Demonstrate failing installer tests before implementation.
- Run focused installer and version contract tests under `D:\tmp_test`.
- Run the full AGC suite under a short `D:\tmp_test` base path.
- Build the wheel and run a local Trace-enabled installation smoke without touching production.

## Flow Record

| Step | Status | Evidence | Updated |
|---|---|---|---|
| source | done | current immutable installer, stable launcher, and scheduled-task action | 2026-08-29 |
| design | done | user-confirmed minimal `-EnableCaptureTrace` activation approach | 2026-08-29 |
| plan | done | `docs/superpowers/plans/2026-08-29-agc-capture-trace-production-activation.md` | 2026-08-30 |
| development | done | optional local-source Trace profile and Capture-only launcher binding | 2026-08-30 |
| testing | passed-agent-local | `.llm-wiki/verification/agc-capture-trace-production-activation.md` | 2026-08-30 |
| archive | done | `.llm-wiki/handoff/agc-capture-trace-production-activation-handoff.md` | 2026-08-30 |

## Changed Assumption

The configured pip index does not contain `agent-trace-runtime`, and the local
Trace `0.1.0` release checklist is still at its manual gate. Production
activation therefore uses an explicit local source root for this release; a
future published Trace package may remove that parameter in a later change.
