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
  relative high-level locators. Configured sensitive-label text is not carried
  forward; only domain-separated, non-serialized, comparison-neutral label
  fingerprints remain in memory for the post-extractor safety gate.
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
  turn, requires explicit trusted main-turn/type/provenance metadata, keeps
  only high-signal user and semantically classified final-message classes,
  selects only the last final assistant message, scrubs known credential patterns before
  selection/hashing, removes private absolute paths, and drops reasoning,
  encrypted/tool/attachment/other-turn records plus code, diff, traceback,
  terminal, log, quoted-source, and serialized-payload blocks. Content-part
  lists accept only explicitly typed text parts; unknown/untyped parts,
  unbalanced fences, repeated serialized mappings, dense method calls, and any
  log-shaped line fail closed for the whole record.
- The known-secret corpus covers JSON/YAML scalar and block assignments, XML
  elements, partial and complete PEM blocks, password and generic token assignments,
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
  substantive lexical units. Declarative user evidence must match the claim's
  durable predicate class and polarity/down-toner class. Assistant result and
  method provenance cannot be recast as preferences, goals, identity, or
  personality, and repeated durable predicates are non-atomic regardless of
  comma, colon, slash, or sentence separators.
- Direct DTOs round-trip through the same strict mapping validator. Evidence is
  deduplicated before scoring. Accepted drafts are canonically deduplicated
  within the Revision, ranked first by the specified semantic tier (verified
  outcomes, constraints, preferences, goals, and methods before research
  changes), then evidence/priority/assertion mode and stable locator, and bounded
  to eight. The result retains no rejected draft text and returns only safety,
  policy, duplicate, and over-limit counts. It never creates a
  `CollectedObservation`.
- `CodexSourceAdapter.load_capsule()` retains the existing complete-main-turn,
  locator-containment, two-pass identity/completion, and full critical-state
  checks. Content-free file signatures around both passes also fail closed on
  ordinary source drift. Active/archive loading produces stable hashes for
  identical safe content. Census discovery remains metadata-only and computes
  no source or Capsule fingerprint. Interleaved lifecycle events from another
  turn while the target is active fail closed before any Capsule is returned.

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

### Independent security review RED/GREEN

The review evidence came from an **independent reviewer message** against main
commit `53e4532`. It reported one Critical and six Important findings covering
structured-secret/hash leakage, interleaved-turn provenance, fail-open
allowlisting, direct-DTO/path validation, grounding/polarity, personal
relevance/atomicity, and ranking/evidence deduplication.

All adversarial probes were added before the security production changes. The
authentic security RED was:

```text
29 failed, 28 passed in 0.61s
```

Paired-secret cases explicitly require two different JSON/YAML/XML/partial-PEM/
URL-userinfo values to produce identical `source_fingerprint`, `capsule_hash`,
and public counts, with neither value retained in Capsule mappings, errors, or
repr surfaces. The focused security GREEN after the review fixes was:

```text
57 passed in 0.21s
```

A final self-review then found that an `agent_inferred` draft could claim a
higher-tier signal label. A separate authentic RED was `1 failed`; making
inference unconditionally the lowest semantic tier produced the final GREEN:

```text
58 passed in 0.26s
Task 1 plus Codex Source Adapter: 73 passed in 0.71s
```

### Second independent security review RED/GREEN

A second **independent reviewer message** against main commit `7d363f5`
reported one Critical and four Important remaining gaps: structured configured
labels and the persistence label-policy handoff; fail-open content parts and
structural payloads; interrogative/polarity/provenance grounding; and repeated
predicate atomicity.

The first adversarial subset, before any second-review production change, was:

```text
15 failed, 6 passed, 59 deselected in 0.42s
```

The six baseline-green cases represented already-conservative behavior. The
configured-label fixtures were then corrected to keep the structured value in
the same high-signal unit; their authentic focused RED was `5 failed`. Minimal
fixes produced label `5 passed`, typed-content/structural `7 passed`, and
semantic/provenance/atomicity `10 passed`.

Two self-review edges received separate RED/GREEN cycles: compositional
`hardly ever avoid` polarity (`1 failed, 3 passed` before the fix) and inline
configured `label:` fingerprint matching (`1 failed` before the fix). Final
second-review focused evidence is:

```text
Task Capsule and safety file: 81 passed in 0.29s
Task 1 plus Codex Source Adapter: 96 passed in 0.78s
```

The managed-root sentinel tripwire initially had one Windows-only test harness
failure because `Path.write_text` produced CRLF rather than the asserted LF.
The product made no write. The assertion was corrected to require byte-exact
before/after equality independent of the baseline newline convention.

## Verification evidence

Final Source Adapter, Source Contracts, Census, Scanner, and disabled-boundary
adjacent suite, in its required census-before-adapter import order:

```text
46 passed in 20.23s
```

A deliberately contaminated reverse order produced only the repository's
documented `sys.modules` census precondition (`44 passed, 2 failed`); the clean
required order passed without a product change.

Final natural-order complete repository suite:

```text
729 passed, 1 expected warning in 296.29s
```

The warning is the existing intentional duplicate-name ZIP adversarial
fixture.

Clean package evidence:

- Existing offline wheel/install plus exact MCP surface nodes: `2 passed in
  11.61s`; the server exposes only `agc.admin`, `agc.read`, and `agc.write`.
- A fresh `python -m build --wheel --no-isolation` succeeded and explicitly
  packaged `capture_capsule.py`, `capture_safety.py`, and the updated source
  adapter.
- `pip --no-deps --target` installed that wheel to an isolated directory;
  `python -I` loaded all four Task-1 modules from the installed target, not the
  checkout.

Final static and filesystem gates:

```text
compileall: clean
strict UTF-8 / no BOM: 6 implementation/test/report files
git diff --check: clean (line-ending advisory only)
in-memory module subprocess/tempfile/network/write-call hits: 0
unresolved marker hits: 0
synthetic Memory Root files: 1 unchanged baseline file
FILESYSTEM_SENTINEL hits below that Memory Root: 0
```

No live Codex profile, installed AGC Memory Root, model/provider, network,
subprocess, Runner, Observation writer, Candidate/Formal Memory writer, Hook
installer, scheduler, or service was read, called, or changed.
