# Capture Source Census Task 6 Report

## Status and scope

Source Census Task 6 is implemented and verified on synthetic roots only. The
proof exercises the real in-process `agc_runtime.capture_cli.main` one-shot
`scan --mode census --once`, `cycle --once`, and `probe` paths. It does not read
or activate a live profile.

The planned scope was one E2E test plus lifecycle evidence. A completed-product
RED proved one release-gate defect, so the parent authorized a narrow production
extension:

- `CaptureStore.record_source_quarantine` preserves byte-exact durable state on
  same-binding/same-code replay, replaces a valid different code under the
  existing one-slot contract, and fails closed without overwriting corrupt
  state.
- `CaptureScanner` persists the deterministic final batch diagnostic for the
  existing one-slot binding quarantine instead of rewriting the slot for every
  code in one cycle.

There is no Source identity/discovery, semantic Capture, model/provider,
Extractor, Runner, scheduler, service, host-route, Hook-installation, MCP-tool,
or formal-memory behavior change.

## TDD evidence

### Intentional E2E scaffold RED

The new node was first created with only the required failing scaffold and run
before the proof implementation:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest `
  tests/test_capture_census_end_to_end.py -q -p no:cacheprovider `
  --basetemp 'D:\tmp\agc-capture-source-red-6'
```

Result: exit `1`, `1 failed in 0.18s`, at the intentional assertion
`scanner-only Capture coverage E2E proof is not implemented`.

### Authentic product replay RED

After harness-only import-guard corrections, the complete E2E reached the
exact replay assertion and failed with one durable delta:

```text
SourceQuarantine.created_at:
2026-08-19T12:00:01Z -> 2026-08-19T12:00:02Z
```

Census membership, Receipts, Ledger, tombstones, conflicts, and normalized
scan-state correctness were otherwise unchanged. This was reported before
production scope expanded.

The first same-code store change exposed a second strict-contract RED requested
by review:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest `
  tests/test_capture_census_end_to_end.py::test_source_quarantine_exact_replay_is_byte_stable_and_corruption_fails_closed `
  -q -p no:cacheprovider `
  --basetemp 'D:\tmp\agc-capture-source-red-6-quarantine'
```

Result: exit `1`; the exact replay and different-code assertions passed, but a
malformed existing quarantine did not raise and was silently overwritten. The
minimal fail-closed change then made this contract green.

### Focused GREEN

```powershell
& '.\.venv\Scripts\python.exe' -m pytest `
  tests/test_capture_census_end_to_end.py -q -p no:cacheprovider `
  --basetemp 'D:\tmp\agc-capture-source-focused-final-6'
```

Result: exit `0`, `3 passed in 3.70s`.

## Synthetic corpus and exact evidence

The final configured Codex root contains `10` JSONL files and `3297` bytes:

```text
archived_sessions/late-out-of-order.jsonl  274
archived_sessions/replay.jsonl             280
sessions/continued.jsonl                    420
sessions/excluded.jsonl                     286
sessions/incomplete-aborted.jsonl           418
sessions/locked.jsonl                       280
sessions/ordinary.jsonl                     567
sessions/partial-tail.jsonl                 188
sessions/subagent.jsonl                     296
sessions/unknown-shape.jsonl                288
```

The corpus proves:

- one ordinary completed main task containing prompt/message sentinels;
- one continued main task with two distinct completed Revision ids;
- exact active/archive replay, followed by removal of the active copy;
- an explicit subagent source outside main-task Census truth;
- started/aborted and malformed partial-tail sources outside completion truth;
- an unknown source shape producing content-free degraded Source Health;
- one configured task exclusion with `configured_task_exclusion`;
- one first-cycle `PermissionError`/sharing failure recovered on cycle 2;
- one late completion inside the seven-day overlap added before cycle 2;
- a failed/missed real Stop Hook marker delivery recovered by Scanner;
- one immutable dirty marker retained after cycle 1 and acknowledged only after
  its matching Receipt/Ledger is durable in cycle 2; and
- a separate unconfigured source root that every enumeration/open guard rejects.

Cycle 1 reports `5` known, `5` accounted, `0` silent loss, `5` created
Receipts, degraded Source Health, and `0` marker acknowledgements. Cycle 2
reports `7` known, `7` accounted, `0` silent loss, `2` created plus `5`
replayed Receipts, and `1` marker acknowledgement.

The strict post-cycle-2 snapshot contains:

```text
Census keys:                 7
accounted keys:              7
Receipts / Ledger entries:   7 / 7
discovered / excluded:       6 / 1
Observations:                0
tombstones:                  0
Source Quarantines:          1
dirty markers:               0
integrity diagnostics:       0
```

Cycle 3 is exact replay: `0` created and `7` replayed. Census key membership
plus anchor/completion/schema/identity metadata, Receipts, Ledger, tombstones,
Source Quarantine, conflicts, and scan-state correctness fields have zero
delta. Frozen-run ids/windows and scan timestamps/state versions are permitted
bookkeeping. Relative locator is deliberately excluded from membership
comparison because the contract defines an active-to-archive move as the same
Revision; a separate assertion requires exactly one `task-replay` identity.

## Privacy, Recall, and boundary guards

The test installs guards before deferred imports and execution for:

- model/provider and network APIs;
- subprocess APIs;
- Extractor and Runner imports;
- Task Capsule and target-turn content loading;
- Observation registration/commit;
- Candidate/Formal Memory writes;
- Hook installation and service/scheduler paths; and
- enumeration or opening of the unconfigured source root.

Every counter is `0`. The adapter reads configured JSONL only through its
census streaming path; `load_capsule` and `_iter_target_turn_records` are
fail-fast guards and remain unused. The injected real Stop Hook marker-write
failure exits `0` with zero stdout/stderr while Scanner still discovers the
Revision.

Observation, Candidate, Formal Memory, and Event counts remain unchanged; the
Formal Catalog byte hash and memory count `0` remain unchanged. Ordinary
`agc.read overview` and `search` return no Capture object or result. Responses
and Capture persistence contain zero hits for the synthetic task-content,
prompt, last-assistant-message, raw-exception, absolute source-root, and
absolute transcript-path sentinels. The operator-bound absolute source root
exists only in `config.yaml`, as permitted by the Task 1/5 binding contract.

The disabled/configured root is byte- and structure-identical after direct
status plus `agc-capture probe`; its source file is unchanged, no Source or
Scanner module is newly imported, and every external/enumeration counter is
zero.

## Verification

### Adjacent

The disabled-boundary-first focused/adjacent command covered Task 6, Core,
Scanner, Ledger, CLI, status, adapter, and Hook:

```text
99 passed in 35.04s
```

A reverse custom order put Source suites before the disabled-Core test and
produced the existing `sys.modules` precondition failure (`98 passed, 1
failed`). The documented disabled-boundary-first order passed all `99`; no
product change was made for that order-only failure.

### Complete repository

```powershell
& '.\.venv\Scripts\python.exe' -m pytest -q -p no:cacheprovider `
  --basetemp 'D:\tmp\agc-capture-source-full-final-6'
```

Result: exit `0`, `647 passed, 1 warning in 301.09s`. The warning is the
existing intentional duplicate-name ZIP adversarial fixture.

An earlier full run reported `646 passed, 1 failed` because the E2E replay
state compared the snapshot's arbitrary active/archive locator representative.
Frozen run ids are hashes, so adding an exact replay run can alter which equal
key is encountered first. The test was corrected to compare Census membership
and all correctness metadata except locator, while retaining the explicit
single-replay-identity assertion. No product code changed for this test
semantics correction.

### Clean installed wheel and MCP surface

```powershell
& '.\.venv\Scripts\python.exe' -m pytest `
  tests/test_runtime_config.py::test_built_wheel_contains_default_and_installed_admin_init_works `
  tests/test_mcp_server.py::test_server_exposes_exactly_three_host_bound_tools `
  -q -p no:cacheprovider `
  --basetemp 'D:\tmp\agc-capture-source-wheel-final-6'
```

Result: exit `0`, `2 passed in 10.93s`. The package test copies the working
source while excluding `.git`, `.venv`, build, dist, caches, and egg-info;
builds the wheel offline with no isolation; installs it with `--no-deps` to a
clean target; proves installed `capture_cli`, Source, and project-identity
module provenance; initializes from the installed default; resolves the
installed `agc-capture` entry point; and accepts an installed one-object probe.
The MCP node proves exactly `agc.admin`, `agc.read`, and `agc.write`.

### Static integrity

The final six-file Task 6 scope passes isolated `compileall`, strict UTF-8
decoding with no BOM, tracked `git diff --check`, and unresolved-marker scans.
The two production files have `0` forbidden model/provider, subprocess,
Extractor, Runner, Task Capsule, or target-turn-loader dependency hits. The
synthetic private-content sentinel appears in exactly one source file: the E2E
test fixture.

## Remaining gates

This closes only the Codex Source Census plan. Extractor/Runner implementation,
token budget and model-call evidence, real-profile shadow backfill, continuous
hosting, Hook trust and foreground p95 latency, host route activation, and
binary downgrade prevention remain pending explicit gates. No p95 claim is
made. Capture remains inactive for real profiles, and the overall Capture
Coverage MVP is not complete.
