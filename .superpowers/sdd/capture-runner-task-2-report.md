# Capture Extractor/Runner Task 2 Verification Report

## Scope and baseline

Implemented only Task 2 of the approved Extractor/Runner plan on clean `main`
baseline `549fb0d`. The change adds strict extractor DTOs, the static
`capture-extractor-v1` JSON Schema, and a bounded isolated Codex reference
adapter. It does not add Runner state, token reservations, persistence,
activation, Hooks, scheduling, or live model/profile access.

The pre-change Task 1/source regression baseline was:

```text
478 passed in 7.01s
```

No adjacent production interface change was required. The future Task 3
`TokenReservation` remains a type-only forward annotation, and collected drafts
round-trip through the existing Task 1 `ObservationDraft` contract.

## Authentic RED evidence

The first RED run contained the brief, schema scaffold, real fake executable,
and tests, but neither production extractor module nor package-data entry:

```text
32 failed, 1 passed in 4.44s
```

The one pass was the static schema-structure test. The failures were caused by
missing production modules/package data, not artificial assertions.

Subsequent self-review added focused tests before each corresponding production
change:

```text
representative JSONL + direct DTO validation: 2 failed, 4 passed, 30 deselected
standalone stdin help token:                    1 failed
missing smoke metadata fail-closed:             1 failed, 4 passed
child never reads stdin timeout:                1 failed in 6.16s
canonical direct DTO / resolved boundaries:     1 failed in 0.71s
```

The blocked-stdin RED demonstrated that a synchronous pipe write delayed a
0.35-second timeout until the fake child exited after about five seconds. The
canonical DTO RED demonstrated that direct dataclass replacement could retain a
noncanonical statement even though mapping construction normalized it.

An adjacent run also exposed a pre-existing exact package-data text contract:

```text
516 passed, 1 failed
```

The correction preserved the exact Task 1 `agc_runtime` package-data declaration
and added the schema through setuptools' `"*"` package-data entry. No Task 1
file was modified.

## Implemented boundaries

- All DTO mappings are exact-key, JSON-safe, finite, valid-UTF-8, and
  state-consistent. Direct dataclass construction performs the same validation;
  collected drafts must be canonical Task 1 mappings.
- The schema is closed and permits exactly zero through eight drafts. Its draft
  fields, enums, lengths, and integer bounds mirror the reviewed Task 1 DTO.
- The adapter constructs a tuple/list argv boundary and always calls
  `subprocess.Popen(..., shell=False)`. Capsule JSON is the only stdin content;
  no content file is created.
- Each child gets a fresh empty temporary cwd and an exact environment allowlist.
  AGC activation/Hook/profile variables, `CODEX_HOME`, `PYTHONPATH`, and
  `PYTHONHOME` are not inherited.
- Stdout and stderr are drained concurrently with independent byte limits.
  Stdin is also written on a managed thread, so timeout covers a child that never
  reads its pipe. Raw buffers are cleared after parsing and never appear in DTO
  repr, errors, or logs.
- JSONL accepts only the closed representative event set, exactly one thread and
  final agent message, at most one turn start and usage event, and ignores only
  a structurally valid reasoning item. Duplicate keys, malformed/unknown events,
  ambiguous finals, invalid output, invalid complete usage, and invalid Unicode
  fail with fixed `stage/code/retryable` errors.
- Missing or partial usage is represented as `None`; both the legacy total shape
  and representative cached-input Codex usage shape are normalized to strict
  `TokenUsage`.
- Capability activation requires a parseable version, every required help token
  including standalone `-`, a successful content-free smoke call, and resolved
  model/provider/auth/read-only metadata. Any omission returns the same
  content-free unavailable probe.

## Verification

Focused final:

```text
39 passed in 13.16s
```

Task 1/source/disabled-boundary adjacent before the final stdin/DTO tightening:

```text
517 passed in 19.56s
```

The first full run used an incorrect local dependency path. Product assertions
reached 100%, but the existing wheel test could not import its offline backend:

```text
1143 passed, 1 failed, 1 expected warning in 498.33s
failure: ModuleNotFoundError: setuptools in test wheel precondition
```

After correcting `PYTHONPATH` from `dependencies/python/site-packages` to
`dependencies/python/Lib/site-packages`, the exact existing wheel node passed:

```text
1 passed in 15.90s
```

Final adjacent/full/wheel/static results are recorded below after the fresh
post-tightening runs.

## Frozen final acceptance

At the user's deadline the scope was frozen: no new behavior or exploratory
test variants were added after this point. The final source was verified with
the following evidence:

```text
focused extractor suite (fresh root run): 39 passed in 9.21s
Task 1/source/disabled-boundary adjacent: 518 passed in 19.19s
natural-order full repository suite:      1145 passed, 1 expected duplicate-ZIP warning in 534.64s
```

The final static gate compiled all four changed Python files with an isolated
bytecode cache, strictly decoded all eight scoped text files as UTF-8 without a
BOM, parsed the packaged schema, asserted its closed eight-item bound, scanned
the production boundary for unsafe shell/external execution forms, and ran
`git diff --check`. It completed with `STATIC_GATE=PASS`.

The focused source inspection also confirmed the security-critical process
boundary: tuple/list argv, `shell=False`, fresh temporary working directory,
explicit environment allowlist, concurrent bounded stdout/stderr drains,
timeout-covered stdin, fixed content-free errors, and raw-buffer clearing.
No Critical acceptance finding remained in the frozen Task 2 scope.

## Isolation statement

All subprocess integration used only `tests/fixtures/fake_codex_exec.py`. No
live Codex executable, installed Codex profile, model/provider, network, MCP,
Skill, Hook, scheduler, service, AGC Memory Root, Observation writer, or formal
memory path was invoked or modified. Build/install verification uses dedicated
synthetic directories outside the repository.
