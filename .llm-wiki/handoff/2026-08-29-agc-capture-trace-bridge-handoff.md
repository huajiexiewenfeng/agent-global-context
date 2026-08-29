# Handoff: AGC Capture Trace Bridge

## Delivered

AGC Capture Runner now has an optional, metadata-only Trace Runtime bridge at
the CLI boundary. `AGENT_TRACE_DB` is the explicit opt-in. Significant cycles
record one lifecycle root, empty successes are suppressed, and every Trace
failure preserves the original Capture result and exit code.

## Current State

- Source branch: `main`
- Implementation commit: `6780ffa`
- Runtime package version remains 0.4.2
- Trace dependency is optional, not part of the default install
- Production Runtime and scheduler are unchanged
- GitHub is not pushed by this flow

## Verification

See `.llm-wiki/verification/2026-08-29-agc-capture-trace-bridge.md` for focused
tests, full-suite coverage, Ruff, wheel, and cross-repository Snapshot evidence.

## Operational Behavior

- `disabled`: no explicit Trace database binding
- `suppressed`: successful cycle without significant activity
- `recorded`: intended lifecycle pair persisted
- `unavailable`: optional package, validation, or store failed without changing
  Capture semantics

## Next Authorized Boundary

Production activation remains separate. It requires explicit approval to:

1. choose a release/version strategy;
2. install AGC with its `trace` extra into the active Runtime;
3. bind a production Trace database in the Capture scheduled-task environment;
4. run one production-safe cycle and inspect its Snapshot;
5. publish or push the resulting release commits.

Eval integration, per-item spans, Recall tracing, Capture selection changes,
and memory-content tracing remain out of scope.
