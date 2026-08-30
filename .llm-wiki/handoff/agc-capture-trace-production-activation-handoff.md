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
- Production version: 0.4.3
- Production automatic Capture: unchanged and still active
- Production Capture Trace: enabled for the stable Capture launcher
- Scheduled-task definition: unchanged; task restored after installation
- GitHub: closure commits synchronized to `origin/main`

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

Restart Codex so foreground MCP Recall loads 0.4.3. Automatic Capture already
completed one production cycle through the new Runtime and persisted a complete
two-event aggregate Snapshot with zero silent loss. Eval, Recall tracing,
per-item spans, and content-bearing trace payloads remain out of scope.
