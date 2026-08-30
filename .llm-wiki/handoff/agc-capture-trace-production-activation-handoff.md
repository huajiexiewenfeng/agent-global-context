# Handoff: AGC Capture Trace Production Activation

## Delivered

AGC 0.4.3 source now has an explicit local activation path for the verified
Capture-to-Trace bridge:

```powershell
.\scripts\install-local.ps1 `
  -EnableCaptureTrace `
  -TraceRuntimeRoot D:\tmp\github\agent-runtime-modules
```

The installer creates a separate immutable `mcp+trace` Runtime, validates the
local Contracts and Trace packages, and writes the Trace database binding only
to the stable Capture launcher. The default install remains Trace-free.

## Current State

- Source branch: `main`
- Source version: 0.4.3
- Production version: 0.4.2
- Production automatic Capture: unchanged and still active
- Production Capture Trace: not enabled
- Scheduled task and live launchers: unchanged
- GitHub: not pushed by this flow

## Verification

See `.llm-wiki/verification/agc-capture-trace-production-activation.md` for TDD,
regression, packaging, real local-source installation, Trace Doctor, Snapshot,
privacy, and test-integrity evidence.

## Operational Notes

- Trace Runtime 0.1.0 requires Python 3.12 or newer.
- The default database is
  `%USERPROFILE%\.agent-trace-runtime\trace.sqlite3`.
- `-TraceDatabase <absolute-path>` can override it only when Trace is enabled.
- Trace Runtime and Contracts are currently installed from an explicit local
  source because their 0.1.0 packages are not published on the configured index.

## Next Authorized Boundary

With explicit approval, install 0.4.3 into production, temporarily quiesce and
restore `AgentGlobalContext-Capture-25e9201ae2f5`, run one safe automatic
Capture cycle, inspect the resulting Snapshot, and then push the commits to
GitHub. Eval, Recall tracing, per-item spans, and content-bearing trace payloads
remain out of scope.
