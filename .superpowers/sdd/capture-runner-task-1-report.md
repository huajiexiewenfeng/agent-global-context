# Capture Extractor/Runner Task 1 Report

## Status and scope

Task 1 is implemented and verified on synthetic source and Memory Roots only.
It adds the in-memory Task Capsule, deterministic pre-Capsule and persistence
gates, and `CodexSourceAdapter.load_capsule()` for exactly one settled main
turn. It does not call a model/provider or network, launch a subprocess, create
a tempfile, invoke a Runner, or persist a Capsule, draft, Observation, Receipt,
event, cache, journal, log, or backup.

Production scope:

- `agc_runtime/capture_capsule.py`
- `agc_runtime/capture_safety.py`
- `agc_runtime/capture_source.py`
- `agc_runtime/codex_source_adapter.py`

Tests are in `tests/test_capture_capsule_safety.py`.

## Contracts implemented

- `CapsulePolicy` is frozen and versioned. It requires an explicit opaque
  project scope or `None`, rejects workstation paths, uses a deterministic
  target estimator limit of 1,200 and a hard maximum of 3,000, and bounds
  per-signal/title and configured sensitive-label inputs.
- `TaskCapsule` is frozen and versioned. Every identity or content-bearing
  field is `repr=False`; only its schema version appears in `repr`. It contains
  the bound Revision identity, completion/project metadata, selected target-turn
  user signals, final decisions/results, reusable methods, next steps, and safe
  relative high-level locators.
- `CapsuleResult` contains no raw records or excerpts. It returns the hidden
  Capsule, distinct versioned `source_fingerprint` and `capsule_hash`, exact
  source schema versions, the deterministic estimate, and content-free
  allowlist/filter/scrub/selection/truncation counts.
- `source_fingerprint` hashes only the privacy-cleaned allowlisted source
  representation. Filtered record insertion, secret-value changes after
  redaction, and active/archive moves do not feed forbidden content or source
  location into the digest. `capsule_hash` separately hashes the exact canonical
  Capsule supplied to a future extractor.
- `pre_capsule_gate` normalizes NFC/LF/control/spacing, isolates the target
  turn, keeps only explicit title/user/final-message classes, selects only the
  last final assistant message, scrubs known credential patterns before
  selection/hashing, removes private absolute paths, and drops reasoning,
  encrypted/tool/attachment/other-turn records plus code, diff, traceback,
  terminal, log, quoted-source, and serialized-payload blocks.
- The known-secret corpus covers password and generic token assignments,
  OpenAI/AWS-style environment names, Bearer/Basic authorization, API keys,
  cookies, private keys, database/HTTP user-info connection strings, JWTs, and
  configured secret/sensitive labels. This is a known-pattern pre-scrub, not a
  claim that deterministic rules identify every unknown sensitive meaning.
- The Task-1 `ObservationDraft` is an in-memory DTO independent of the future
  process adapter. Strict mappings require exactly statement, assertion,
  taxonomy, scope, confidence/sensitivity/signal, evidence, priority, and
  locator fields. Unknown/missing/wrongly typed fields fail content-safely.
- `persistence_gate` rejects non-normal/personal sensitivity, known secrets,
  code/diff/log/raw-source content, questions, hypotheticals, third-party and
  one-off command facts, pure project facts without personal relevance,
  unsupported psychological inference, non-atomic/multi-claim statements,
  project-scope mismatch, and ungrounded evidence. Evidence must equal a whole
  Capsule signal rather than a substring and cover at least 75% of the claim's
  substantive lexical units.
- Accepted drafts are canonically deduplicated within the Revision, ranked by
  assertion/evidence/personal-signal priority and stable locator, and bounded
  to eight. The result retains no rejected draft text and returns only safety,
  policy, duplicate, and over-limit counts. It never creates a
  `CollectedObservation`.
- `CodexSourceAdapter.load_capsule()` retains the existing complete-main-turn,
  locator-containment, two-pass identity/completion, and full critical-state
  checks. Content-free file signatures around both passes also fail closed on
  ordinary source drift. Active/archive loading produces stable hashes for
  identical safe content. Census discovery remains metadata-only and computes
  no source or Capsule fingerprint.

## TDD evidence

### Initial authentic RED

Before any production file was created or changed:

```text
pytest tests/test_capture_capsule_safety.py -q -p no:cacheprovider
14 failed in 0.31s
```

Every failure was the intended missing production surface:
`agc_runtime.capture_capsule` or `agc_runtime.capture_safety`. The adapter-load
nodes could not progress past the missing Capsule policy.

### First GREEN

The first minimal implementation produced:

```text
Focused Task 1: 14 passed in 0.23s
Task 1 plus Codex Source Adapter: 29 passed in 0.69s
```

### Review RED/GREEN cycles

Four new privacy/format regressions were added before their fixes. RED was
`4 failed, 15 passed`: filtered record positions perturbed the cleaned source
hash; a Windows private path was accepted as project scope; whole diff and
traceback bodies left payload lines behind. The minimal corrections produced
`19 passed`.

Two further safety/evidence nodes were then added before their fixes. RED was
`2 failed`: the expanded known-credential corpus exposed env/generic-token/JWT/
HTTP-user-info misses, and evidence accepted a substring/shared-token claim.
The stricter pre-scrub and whole-signal/claim-coverage gate produced `2 passed`.

The final focused results are:

```text
Task Capsule and safety file: 20 passed in 0.17s
Task 1 plus Codex Source Adapter: 35 passed in 0.61s
```

The managed-root sentinel tripwire initially had one Windows-only test harness
failure because `Path.write_text` produced CRLF rather than the asserted LF.
The product made no write. The assertion was corrected to require byte-exact
before/after equality independent of the baseline newline convention.

## Verification evidence

Final Source Adapter, Census, Scanner, and disabled-boundary adjacent suite:

```text
66 passed in 17.70s
```

Final natural-order complete repository suite:

```text
668 passed, 1 expected warning in 300.60s
```

The warning is the existing intentional duplicate-name ZIP adversarial
fixture.

Clean package evidence:

- Existing offline wheel/install plus exact MCP surface nodes: `2 passed in
  11.42s`; the server exposes only `agc.admin`, `agc.read`, and `agc.write`.
- A fresh `python -m build --wheel --no-isolation` succeeded and explicitly
  packaged `capture_capsule.py`, `capture_safety.py`, and the updated source
  adapter.
- `pip --no-deps --target` installed that wheel to an isolated directory;
  `python -I` loaded all three modules from the installed target, not the
  checkout.

Final static and filesystem gates:

```text
compileall: clean
strict UTF-8 / no BOM: 5 implementation/test files
git diff --check: clean (line-ending advisory only)
in-memory module subprocess/tempfile/network/write-call hits: 0
unresolved marker hits: 0
synthetic Memory Root files: 1 unchanged baseline file
FILESYSTEM_SENTINEL hits below that Memory Root: 0
```

No live Codex profile, installed AGC Memory Root, model/provider, network,
subprocess, Runner, Observation writer, Candidate/Formal Memory writer, Hook
installer, scheduler, or service was read, called, or changed.
