# AGC Capture Trace Bridge Design

## Problem

AGC Recall can be observed through Codex Hooks when it runs inside a Codex Turn, but the scheduled Capture Runner executes as an independent process. Codex Hooks therefore cannot observe Capture batch health, backlog, duration, or failures.

The integration must not make memory collection depend on Trace availability and must not copy Session, Capsule, observation, or memory content into Trace.

## Decision

Add a small optional in-process bridge at the `agc-capture run/cycle` CLI boundary.

The bridge is enabled only when `AGENT_TRACE_DB` is explicitly present. It lazily imports the optional `agent-trace-runtime` package, writes directly through its public `TraceService` API, and converts every import, validation, or store failure into a content-free `trace_status: unavailable`. Capture keeps its original result and exit code.

No AGC configuration migration is required. Packaging declares a `trace` optional extra; normal AGC installations remain unchanged.

## Alternatives Rejected

- Hard dependency on Trace Runtime: makes AGC installation and operation depend on an observability component.
- Trace CLI subprocess: the current CLI is read/export oriented, has no event-ingest command, and would add process overhead and another protocol surface.
- Reading AGC databases or logs from Trace: reverses ownership and forces Trace to infer AGC business state.

## Components

### `agc_runtime.capture_trace`

Owns the optional boundary:

- detects explicit enablement through `AGENT_TRACE_DB`;
- lazily resolves Trace Runtime public imports;
- creates one Trace root for a useful Capture cycle;
- emits only allowlisted metadata;
- returns `recorded`, `suppressed`, `disabled`, or `unavailable`;
- never raises into Capture.

The fixed principal is `agent-global-context.capture` with kind `runtime`. The root name is `agc.capture.cycle` and the span kind is `workflow`.

### `agc_runtime.capture_cli`

Remains the owner of the real Runner boundary. It supplies the stable action, start time, sanitized result mapping, and sanitized failure code to the bridge, then exposes `trace_status` in the one-line CLI response.

Existing Capture Runner, scanner, extractor, receipt, observation, budget, and memory-write code does not import Trace.

## Event Model

For a non-empty or operationally significant successful cycle, emit:

```text
trace.root.started
trace.root.completed
```

For a sanitized Runner exception, emit:

```text
trace.root.started
trace.root.failed
```

Both events share one generated Trace ID and root Span ID. The start event uses the CLI cycle start time. The terminal event uses the observation time at recording. If only the first event is persisted before a store failure, the trace remains honestly incomplete.

Successful empty cycles are suppressed to avoid four low-value traces per hour. A cycle is significant when at least one of these values is non-zero:

- `attempted_count`
- `completed_count`
- `failed_count`
- `deferred_budget_count`
- `lease_contention_count`
- `observation_count`
- `charged_tokens`

## Metadata Allowlist

Terminal success metadata may contain only:

- `action`
- `attempted_count`
- `completed_count`
- `failed_count`
- `deferred_budget_count`
- `lease_contention_count`
- `observation_count`
- `charged_tokens`
- `backlog_count`
- `silent_loss_count`
- `run_time_ms`
- `status_deltas`

Terminal failure metadata may contain only the stable CLI action and sanitized error code/message already selected by `capture_cli`.

Forbidden fields include Prompt, assistant response, Session content, task/session/project IDs, source roots, locators, Capsule fields, observation statements, memory cards, extractor input/output, raw exceptions, credentials, and environment contents.

## Failure Semantics

- `disabled`: `AGENT_TRACE_DB` is absent; no import or store access occurs.
- `suppressed`: the cycle succeeded with no significant activity; no Trace is written.
- `recorded`: all intended lifecycle events were appended.
- `unavailable`: optional package resolution or event persistence failed; Capture remains successful or fails only for its original AGC reason.

The bridge must catch Trace-specific and unexpected exceptions internally. Trace warnings remain content-free and must never include the configured database path or exception text.

## Packaging And Activation

Add the optional package extra:

```toml
trace = ["agent-trace-runtime>=0.1,<0.2"]
```

Source tests inject a fake backend and do not require the extra. Cross-repository acceptance installs the locally verified Trace Runtime package beside AGC, sets `AGENT_TRACE_DB` to a test database under the fixed test area, runs one controlled Capture cycle, and inspects the resulting Snapshot.

Updating the production installation, scheduled task environment, AGC version, GitHub, or release artifacts requires a separate release/install confirmation.

## Scope

- Add the optional Capture Trace bridge and focused tests.
- Integrate only `agc-capture run` and `agc-capture cycle`.
- Add the optional package metadata and operational documentation.
- Verify failure-open behavior and cross-repository compatibility locally.

## Non-Goals

- Do not trace Recall, manual backfill, promotion, merge, or hard forget in this change.
- Do not create per-receipt, per-extraction, or per-observation child spans.
- Do not modify Capture selection, extraction, storage, scheduling, or memory behavior.
- Do not add AGC configuration fields or migrate `config.yaml`.
- Do not install or publish a new AGC version without later explicit confirmation.
- Do not begin Eval work.

## Acceptance Criteria

1. Without `AGENT_TRACE_DB`, the scheduled Runner behavior and output remain unchanged except for `trace_status: disabled`.
2. A successful significant cycle emits one completed metadata-only Trace root.
3. A successful empty cycle emits no Trace and reports `trace_status: suppressed`.
4. A sanitized Runner failure emits a failed root when Trace is available.
5. Missing Trace Runtime or an unavailable store reports `trace_status: unavailable` without changing the AGC result or exit code.
6. Persisted Trace payloads contain only the documented allowlist and no AGC content or identifiers.
7. Existing AGC tests, focused bridge tests, package tests, and a local cross-repository smoke pass.

## Test Strategy

Use TDD around a dependency-injected bridge backend. Observe failing tests before implementation for disabled, suppressed, recorded, unavailable, failure, allowlist, and CLI failure-open behavior. Then run focused tests, the full AGC suite, packaging checks, Ruff, LLM Wiki Doctor, and a controlled local Trace Snapshot smoke under the fixed test directory.

## Risks

- Two append operations are not transactionally atomic; partial persistence remains visible as an incomplete Trace rather than being hidden.
- Setting `AGENT_TRACE_DB` without installing the optional package produces `unavailable`, but never blocks Capture.
- This first bridge records batch-level health only; deeper per-stage spans should be justified by real Eval needs later.
