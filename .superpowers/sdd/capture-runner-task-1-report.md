# Capture Extractor/Runner Task 1 Report

## Status and scope

Task 1 has a locally verified candidate implementation on synthetic source and
Memory Roots only; independent thirteenth-review acceptance remains pending.
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
  per-signal/title and configured sensitive-label inputs. Sensitive labels
  containing any Unicode control/format/surrogate/private-use category fail
  closed at policy construction. Label matching uses the same controlled
  confusable security skeleton as known-secret matching.
- `TaskCapsule` is frozen and versioned. Every identity or content-bearing
  field is `repr=False`; only its schema version appears in `repr`. It contains
  the bound Revision identity, completion/project metadata, selected target-turn
  user signals, final decisions/results, reusable methods, next steps, and safe
  relative high-level locators. Configured sensitive labels are canonicalized
  once with NFKC, Unicode casefold, NFKD combining-mark removal, and whitespace
  collapse, then retained only
  in a private, non-serialized, `repr=False`, comparison-neutral in-memory field
  for the post-extractor safety gate.
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
  log-shaped line fail closed for the whole record. Any backtick or tilde
  fence marker, single-line JSON/mapping/array payload, plain/awaited/dotted/
  bracketed or Unicode call, parentheses, assignment, structural character,
  decorator, obvious interpreter-command shape, or code keyword drops the
  entire text unit. Recognized assistant prefixes also use a closed action/body
  shape rather than accepting arbitrary imperative text. User signals require an anchored first-person
  declarative predicate grammar; assistant signals require an explicit
  Decision/Result/Constraint/Method/Next prefix and a conservative
  plain-language body.
- The known-secret corpus covers JSON/YAML scalar and block assignments, XML
  elements, partial and complete PEM blocks, password and generic token assignments,
  OpenAI/AWS-style environment names, Bearer/Basic authorization, API keys,
  cookies, private keys, database/HTTP user-info connection strings, JWTs, and
  configured secret/sensitive labels. Patterns run against the shared security
  view and replace the entire matching unit before hashing. This is a
  known-pattern pre-scrub, not a
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
  Capsule signal rather than a substring and must canonicalize to the exact
  same proposition as the claim. First/second/person user subjects and supported
  predicate morphology/contractions normalize deterministically; subject,
  predicate, object, polarity, and provenance must otherwise remain identical.
  Declarative user evidence must match the claim's durable predicate class and
  polarity/down-toner class. Assistant result and
  method provenance cannot be recast as preferences, goals, identity, or
  personality; an assistant-grounded user outcome requires the stripped body
  to begin grammatically with `You` or `The user`, not merely contain user text
  as an object or beneficiary. Statements require one supported anchored
  subject/predicate/object template. Comma, colon, semicolon, slash, newline,
  en/em dash, conjunction (including `while`, `whereas`, and `although`),
  repeated subject, secondary finite predicate, or multiple sentences are
  non-atomic even when a later predicate is otherwise unknown.
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

### Third independent security review RED/GREEN

A third **independent reviewer message** against main commit `8b13fd4`
reported configured-label scalar-tail hash leakage; single-line payload,
call/assignment, and fence-marker admission; indirect interrogatives;
assistant and third-party attribution recasting; and fail-open unknown-clause
atomicity.

All exact and generalized adversarial probes were added before the third-review
production changes. The authentic aggregate RED was:

```text
24 failed, 1 passed, 81 deselected in 0.55s
```

Configured-label units are now replaced wholesale by one fixed,
content-independent redaction unit, so arbitrary secret values and comma tails
cannot affect either hash or public counts. Structural payloads and code-like
units fail closed. Interrogative, provenance, attribution, and atomicity rules
were tightened conservatively. A generalized plain/awaited call follow-up had
an authentic `2 failed, 8 passed` RED before its `10 passed` GREEN.

Final third-review focused evidence is:

```text
Task Capsule and safety file: 108 passed in 0.27s
Task 1 plus Codex Source Adapter: 123 passed in 0.83s
```

### Fourth independent security review RED/GREEN

A fourth **independent reviewer message** against main commit `aac0adb`
required replacing incremental cue blacklists with a conservative positive
grammar. It identified sensitive-label canonicalization gaps for repeated
whitespace and Unicode casefold, empty/small structural payloads and code
forms, arbitrary uncertainty prefixes, assistant object/beneficiary user
mentions, additional third-party attribution forms, and Unicode clause
separators.

Generalized parameterized probes were added first across label, structural,
uncertainty, subject-position, attribution, and Unicode-separator families.
The authentic fourth-review RED was:

```text
30 failed, 5 passed, 108 deselected in 0.74s
```

The minimal positive-grammar implementation produced `35 passed` for that
group. Legacy interrogative and durable-cue blacklists were then removed so
acceptance is determined by explicit user, persisted-statement, assistant
prefix, and assistant grammatical-subject templates. Final focused evidence:

```text
Task Capsule and safety file: 143 passed in 0.33s
Task 1 plus Codex Source Adapter: 158 passed in 0.80s
```

### Fifth formal security review RED/GREEN

The fifth formal reviewer **REJECT** against main commit `4624fd0` identified
control-bearing label/source normalization divergence, Unicode and plain-code
shape admission, suffix uncertainty/alternative/attribution, lossy lexical
grounding, assistant action/object rewriting, and remaining independent-clause
atomicity gaps.

All specified probes were added before production changes. The authentic RED
was:

```text
24 failed, 143 deselected in 0.65s
```

After that group reached GREEN, generalized Python-command variants across all
assistant prefixes had a separate authentic `5 failed, 6 passed` RED before
their `11 passed` GREEN. Exact proposition morphology then received a separate
`2 failed` RED for `don't`/`can't` versus `does not`/`cannot`, followed by a
`2 passed` GREEN. Final focused evidence is:

```text
Task Capsule and safety file: 174 passed in 0.36s
Task 1 plus Codex Source Adapter: 189 passed in 0.91s
```

### Fifth-review follow-up: complete-consumption grammar

A follow-up **independent reviewer message** found five remaining Important
issues in the worktree based on main commit `4624fd0`: canonical-empty
configured labels; command-shaped assistant prefix bodies; conditional,
uncertain, and attributed object tails; assistant attribution suffixes; and
unconsumed finite clauses inside nominal objects.

All exact review examples were added before the follow-up production changes.
The authentic aggregate RED was:

```text
17 failed, 4 passed, 174 deselected in 0.58s
```

The four baseline-green parameters were retained as regression controls. The
contract is now intentionally narrower: `_class_from_patterns` returns a
fully consumed `(predicate_class, polarity, normalized_object)` proposition;
user, persisted, and assistant evidence use anchored subject/predicate forms;
and persistence grounding compares proposition equality only. There is no
lexical-overlap fallback. Nominal objects use a conservative token grammar and
reject residual clause, conditional, uncertainty, attribution, structural,
and command shapes. Assistant Capsule admission retains only a strictly parsed
user proposition or a tiny complete `Result:` grammar. The former broad test
expectations for command-like `Decision:`, `Method:`, and `Next step:` bodies
were therefore updated to the documented false-negative policy.

A self-review then challenged the object parser with four residual clauses
that were absent from every earlier cue family (`located`, `provided`, `under`,
and `whenever`). Their authentic RED was `4 failed`. Replacing the remaining
negative word exclusions with a positive modifier/head and restricted-action
object grammar produced `21 passed` across that group and its core positive
controls.

Final follow-up evidence is:

```text
Task Capsule and safety file: 199 passed in 0.40s
Task 1 plus Codex Source Adapter: 214 passed in 0.97s
Adjacent census/source/contracts/scanner/adapter: 152 passed in 19.23s
```

### Sixth follow-up review: fixed-arity AST objects

The next **independent reviewer message** rejected the remaining nominal
modifier/head parser because its final token was unconstrained and arbitrary
capitalized tokens could be treated as modifiers. This admitted suffixes such
as `maybe`, `reportedly`, unknown finite predicates, capitalized clauses, and
assistant attribution when the persisted statement repeated the same text.

All exact examples plus generalized `breaks`, `occurs`, `claims`, and random
capitalized-clause probes were added before production changes. The authentic
RED was:

```text
10 failed, 1 passed, 199 deselected in 0.55s
```

The one baseline-green `claims` case was already rejected by the independent
quoted-assertion gate and remains a regression control. A separate positive
control for an action with no complement had an authentic `1 failed` RED.

The object grammar is now fixed arity and has no modifier or head inference:
a nominal production consumes exactly one atomic Unicode letter/number token
with restricted internal hyphens; an ability, goal, constraint, or action
trajectory consumes one closed action verb plus zero or one atomic complement.
Assistant user propositions use the same parser. Existing multiword recall and
ranking fixtures were intentionally rewritten to atomic or bounded-action
forms; this is a documented false-negative narrowing, not an attempt to retain
the former natural-language breadth.

A final shape audit added standalone lowercase ASCII function/predicate atoms.
Its authentic RED was `3 failed, 1 passed`; the existing `-ly` rule already
rejected the fourth parameter. The grammar now rejects that whole lowercase
ASCII shape without introducing a vocabulary list. Closed action verbs and
closed method nouns are the only lowercase exceptions.

Current focused evidence before the final repository gate is:

```text
Task Capsule and safety file: 215 passed in 0.43s
Task 1 plus Codex Source Adapter: 230 passed in 0.90s
Adjacent census/source/contracts/scanner/adapter: 152 passed in 18.87s
```

### Seventh independent review: balanced fixed-arity grammar

The seventh **independent reviewer message** reported three remaining Important
issues: surface-case/NFC-only atom checks admitted case, compatibility, and
diacritic variants; transitive actions admitted missing complements; and the
single-atom grammar had lost supported lowercase user signals and safe
assistant Decision/Method/Next/Constraint productions.

Exact and metamorphic case/NFKC/diacritic probes, missing-complement probes,
the requested lowercase positive controls, and four assistant-prefix positive
controls were added before production changes. The authentic aggregate RED was:

```text
18 failed, 1 passed, 215 deselected in 0.71s
```

Security classification now uses one proposition skeleton: NFKC, Unicode
casefold, NFKD combining-mark removal, and whitespace collapse. Surface casing
is never used as a part-of-speech proxy. Nominals consume one atom or a closed
two-atom compound production. Actions consume a closed transitive verb plus a
required one- or two-atom nominal complement; the only longer production is a
controlled direct-object `in` location form. Assistant Decision, Method, Next,
and Constraint bodies use per-prefix closed action productions, including one
fixed compound Method production, while Result retains its tiny declarative
grammar. Unknown residual predicates such as `occurs` cannot become a nominal
tail merely by changing case or Unicode presentation.

The two previous positive fixtures that used incomplete `run` were
intentionally narrowed to `run tests`. This reflects the required transitive
valency contract rather than an implementation accommodation. Final seventh-
review evidence is:

```text
Review adversarial/positive subset: 22 passed in 0.11s
Task Capsule and safety file: 237 passed in 0.49s
Task 1 plus Source Contracts and Codex Source Adapter: 257 passed in 1.06s
Adjacent census/contracts/source/scanner/adapter: 152 passed in 20.16s
```

### Eighth independent review: shared security skeleton and structured compounds

The eighth **independent reviewer message** reported one Critical and three
Important issues: configured labels and known-secret patterns did not share the
NFKC security view; the two-atom rule still admitted arbitrary first tokens;
mixed-script confusables bypassed atom decisions; and normal concise lowercase
user/assistant phrases were lost by the closed compound-head set.

Fullwidth configured-label probes for title, user, persistence, paired hashes,
and counts; a paired fullwidth `sk-` token probe; eight compound-bypass probes;
Greek/Cyrillic/fullwidth metamorphic probes; and all requested lowercase
positive phrases were added before production changes. The authentic RED was:

```text
21 failed, 1 passed, 237 deselected in 0.76s
```

The sole baseline-green parameter was fullwidth `whenever`, which the existing
NFKC atom skeleton already rejected. The security skeleton now lives in
`capture_capsule.py`; policy-label canonicalization, pre-Capsule detection, and
post-extractor detection all call that single NFKC/casefold/NFKD/mark-removal/
whitespace implementation. Known-secret patterns run against the same security
view, and any match replaces the entire unit with one fixed redaction before
either hash.

Atoms now reject more than one Unicode letter script. Two-token nominals use a
positive modifier production (conservative morphology or a small domain set)
plus open noun morphology instead of an arbitrary modifier or a closed head
list. Pronoun, subordinator, conditional, attribution, subject-like plural,
and proper-name-shaped modifiers cannot enter through that production.
Per-predicate grammar retains one-atom values and structured two-token values;
closed actions require their complement, while `keep` additionally supports a
noun plus predicative adjective. Assistant prefixes use the same production
without the previous fixed phrase exception.

The estimator-only fixture formerly placed Latin and Han characters inside one
atom. It was changed to an equal-length pure-Latin payload so the estimator
test remains independent of the new mixed-script rejection contract. Final
eighth-review remediation evidence is:

```text
Review adversarial/positive subset: 22 passed in 0.12s
Task Capsule and safety file: 259 passed in 0.58s
Task 1 plus Source Contracts and Codex Source Adapter: 279 passed in 0.99s
Adjacent census/contracts/source/scanner/adapter: 152 passed in 19.18s
```

### Ninth independent review: mixed-script units and controlled English

The ninth **independent reviewer message** reported a P0 mixed-script title
side channel and remaining controlled-grammar imbalance. Mixed-script `AСME`
and `sк-` text bypassed title scrubbing because script checks ran only inside
nominal parsing. Broad `-ent` modifiers and arbitrary plural `s` heads admitted
person names and finite predicates, while representative user and assistant
phrases were still filtered.

Paired mixed-script title/hash/count probes, a postgate safety probe, six exact
name/finite-predicate combinations, case metamorphs, generalized `improves`,
`changes`, and `continues` heads, and all requested lowercase user/assistant
positive phrases were added before production changes. The authentic RED was:

```text
21 failed, 259 deselected in 0.78s
```

The shared capsule safety layer now exposes a continuous letter/mark atom
script detector. Any text unit containing a single atom with more than one
Unicode script is replaced wholesale by the fixed redaction before configured
labels or known-token matching. Title, user, assistant, and persistence paths
therefore share the same policy; separate single-script atoms in different
scripts remain allowed.

The grammar is explicitly a deterministic controlled-English profile, not an
arbitrary-English parser. `-ent` is no longer a modifier production,
title-cased internal modifiers fail closed, and common safe modifiers are
listed deliberately. Generic plural `s` is gone: noun heads use defined
singular/plural morphology families plus a small explicit common-head set.
Ambiguous `matters` fails closed. This preserves representative high-signal
phrases such as software engineer, direct communication, brief answers, test
coverage, team conventions, and noun-plus-predicative-adjective constraints
without reopening arbitrary finite tails.

Final ninth-review remediation evidence is:

```text
Review adversarial/positive subset: 21 passed in 0.14s
Task Capsule and safety file: 280 passed in 0.63s
Task 1 plus Source Contracts and Codex Source Adapter: 300 passed in 1.19s
Adjacent census/contracts/source/scanner/adapter: 152 passed in 18.32s
```

### Tenth independent review: unit-wide script safety and plural profile

The tenth **independent reviewer message** reported a P0 cross-token script
channel plus plural/profile gaps. Mixed scripts separated by whitespace or a
hyphen bypassed redaction; all-caps modifiers bypassed title-case rejection;
several plural suffixes admitted finite verbs; and additional representative
controlled-English phrases were filtered.

All exact examples plus generalized `offers`, `clings`, `persists`, `secures`,
`damages`, `enhances`, `influences`, and `balances` probes were added before
production changes. The authentic aggregate RED was `22 failed, 2 passed`;
the two controls were a pure-Han title and one already-rejected finite form.

Script classification now accumulates across the entire text unit and never
resets at punctuation or whitespace. More than one letter script causes one
fixed whole-unit redaction; pure single-script Unicode remains eligible.
Internal modifiers reject title case and all caps. The deterministic
controlled-English profile no longer has any generic plural `s`; it retains
only the conservative `tions`, `sions`, `ments`, `nesses`, and `ities`
families plus explicit common noun heads. Controlled participial modifiers are
position-specific, and the common modifier/head/predicative sets cover the
reviewed representative phrases without making a general-English claim.

Final tenth-review remediation evidence is:

```text
Review adversarial/positive subset: 26 passed in 0.14s
Task Capsule and safety file: 306 passed in 0.64s
Task 1 plus Source Contracts and Codex Source Adapter: 326 passed in 1.09s
Adjacent census/contracts/source/scanner/adapter: 152 passed in 18.27s
```

### Eleventh independent review: confusable secrets and versioned vocabulary

The eleventh **independent reviewer message** reported a P0 pure-script
homoglyph channel and remaining suffix/case inference in the controlled-English
grammar. Pure Cyrillic `sk-` and Cyrillic/Greek `TEAM` labels bypassed secret
matching, while the whole-unit script rule incorrectly removed normal
cross-language units such as `Rust 项目`. Generic noun suffixes still admitted
finite predicates, mixed-case unknown modifiers remained eligible, and eight
representative user/assistant phrases were filtered.

The first P0 fixture accidentally combined Latin wrapper text with the
confusable token, so the old whole-unit script rule made it green. It was not
counted as RED. Rewritten pure Cyrillic/Greek paired-secret fixtures produced
the authentic P0 RED of `3 failed`; their source fingerprints changed with the
secret tails. The remaining exact/generalized review subset produced the
authentic aggregate RED of `18 failed, 7 passed`; the seven baseline controls
were kept as regressions rather than represented as failures.

Secret safety now has two deliberately separate shared primitives in
`capture_capsule.py`:

- script validation resets only between continuous letter/mark atoms, so a
  mixed-script `AСME` atom fails closed while separate `Rust` and `项目` atoms
  remain eligible; and
- the confusable security skeleton performs NFKC, casefold, NFKD mark removal,
  whitespace collapse, then a controlled Cyrillic/Greek-to-Latin homoglyph
  mapping. Policy labels, pre-Capsule label checks, persistence checks, and
  known-secret patterns all use this exact view. Any match still replaces the
  whole unit with one content-independent redaction before both hashes.

The semantic parser continues to use the non-confusable proposition skeleton;
normal non-Latin language is therefore not rewritten into a Latin claim. All
generic modifier/head suffix morphology and all surface-case POS guesses have
been removed. Two-token nominals must be a member of the finite, versioned
controlled modifier vocabulary followed by a finite controlled noun-head
vocabulary. `keep` predicative forms use a separate finite adjective set.
Single safe atoms remain supported. Unknown multiword English is an intentional
false negative, not inferred from suffixes or capitalization.

Final eleventh-review remediation evidence is:

```text
Review adversarial/positive subset: 24 passed in 0.21s
Task Capsule and safety file: 330 passed in 1.57s
Task 1 plus Source Contracts and Codex Source Adapter: 350 passed in 2.08s
Adjacent census/contracts/source/scanner/adapter: 152 passed in 16.54s
Complete repository suite: 978 passed, 1 expected warning in 283.56s
```

The original project `.venv` launcher lost its external CPython 3.13 home
during verification. The final full run therefore used the managed offline
Python 3.12 runtime, existing project site packages after the runtime's native
packages, and in-memory empty imports for the four Win32 process-transport
modules absent from that runtime. No MCP server test exercises that transport;
all 11 MCP server tests passed. The installer node separately passed offline
with build isolation disabled, the wheel node passed, and the Windows
long-path node passed from a short temporary root. The initial dependency-only
full attempt (`967 passed, 11 failed`) is not recorded as the final gate.

### Twelfth independent review: unresolved confusables and natural script boundaries

The twelfth **independent reviewer message** found that the deliberately small
homoglyph table still left P0 channels for small-cap Latin, script-g Latin, and
Cyrillic Palotchka forms. The atom rule also treated natural Latin-to-CJK
boundaries without whitespace as confusable mixing, and user method claims
were subjected to a second method-noun allowlist after already passing the
controlled nominal grammar.

Exact paired-secret/hash probes for `sᴋ-`, `ɡhp_`, and `ѕһеӏӏ`; three
unresolved-label constructor probes; four no-whitespace Latin/CJK titles; one
plain-Cyrillic control; and four user-method positives were added before the
production change. Their authentic RED was:

```text
11 failed, 1 passed, 330 deselected in 1.10s
```

The one baseline-green control was plain Cyrillic with no configured label or
identifier shape, which the new contract intentionally preserves. It is not
reported as a failure. Additional user, assistant, and persistence-path probes
were then retained to prove that the shared gate is used on both sides of the
Capsule boundary.

A final self-review removed an unjustified minimum length from the ASCII
identifier run. The paired `ᴋA` probe first produced an authentic `1 failed,
3 passed` RED against the three already-green P0 variants, then all four passed
after a one-character ASCII run became sufficient to trigger fail-closed risk.

The hand-written homoglyph map is now documented and named only as a
best-effort security view; it does not claim complete UTS39 coverage. A shared
unresolved-confusable risk detector runs after NFKC, casefold, and NFKD. If
non-ASCII Latin or any Cyrillic/Greek letter remains, the whole unit is replaced
by one fixed redaction when either:

- the unit also has identifier/secret punctuation (`- _ : = / @`) or an ASCII
  identifier run; or
- any sensitive label is configured for that policy.

Sensitive labels containing unresolved risk fail closed at policy construction
with the fixed content-free contract error. Configured-label, known-secret,
title, user, assistant, and persistence paths all use the same detector before
hashing or acceptance. Plain Cyrillic without labels/identifier shape remains
eligible.

Mixed-script atom rejection is now limited to transitions among the three
confusable scripts: Latin, Cyrillic, and Greek. Han, Hiragana, Katakana, Hangul,
and other natural-language scripts form a boundary even without whitespace, so
`Rust项目`, `C语言`, `GPT模型`, and `Vue组件` are not treated as secrets. Finally,
user method objects use the same fully consumed controlled nominal/action
grammar as other durable propositions; the redundant `_METHOD_NOUNS` gate was
removed.

Final twelfth-review remediation evidence is:

```text
Initial review subset after remediation: 12 passed in 0.20s
Shared user/assistant/persistence checks: 3 passed in 0.19s
Task Capsule and safety file: 346 passed in 0.94s
Task 1 plus Source Contracts and Codex Source Adapter: 366 passed in 8.02s
Adjacent census/contracts/source/scanner/adapter: 152 passed in 14.65s
Complete repository suite: 994 passed, 1 expected warning in 305.73s
Wheel build/install node: 1 passed in 11.54s
Exact MCP/docs/in-memory tripwire nodes: 3 passed in 1.24s
```

The managed-root sentinel tripwire initially had one Windows-only test harness
failure because `Path.write_text` produced CRLF rather than the asserted LF.
The product made no write. The assertion was corrected to require byte-exact
before/after equality independent of the baseline newline convention.

### Thirteenth independent review: Unicode 17 confusable closure

The thirteenth **independent reviewer message** rejected the hand-written
homoglyph table and the broad unresolved-script deletion policy. The table
could not be complete (notably Cherokee `ᏚᏦ`, small-cap `ᴋ`, script-g `ɡ`, and
Cyrillic Palotchka variants), while the fallback incorrectly treated normal
`Łódź`, `Æsir`, Cyrillic, Greek, and natural Latin/CJK boundaries as secrets.
The user-method controlled-nominal fix from the twelfth review remains in
place.

Exact Unicode provenance, confusable-secret/hash, normal-Unicode controls,
and policy-label tests were added before the production change. Their
authentic RED was:

```text
10 failed, 9 passed, 346 deselected in 6.12s
```

The nine baseline-green cases were older broad-risk detections and ordinary
script controls; they are not represented as RED failures. The real failures
were the missing generated module, the Cherokee hash/content channel, four
normal titles removed by the broad rule, and four valid Unicode labels rejected
at policy construction.

Secret canonicalization now uses a vendored, offline Unicode 17.0.0 UTS
#39-derived ASCII closure. The official input is Unicode's
`https://www.unicode.org/Public/17.0.0/security/confusables.txt`, dated
2025-07-22 in its header, with SHA-256
`091c7f82fc39ef208faf8f94d29c244de99254675e09de163160c810d13ef22a`.
The file's Unicode copyright and license URL are retained in the generated
module header. The initially supplied `/Public/security/17.0.0/` URL returned
404; the versioned official Unicode directory above is the reproducible source.

`scripts/generate_unicode_confusables.py` verifies the source version and hash,
applies the runtime's NFKC/casefold/NFKD-mark-removal security normalization,
joins official casefold-equivalent source classes, recursively resolves their
single-codepoint mappings to stable ASCII sequences, and refuses recursive
cycles. Non-convergent non-ASCII normalization artifacts are outside this
deliberately ASCII profile. The generated
`agc_runtime/_unicode_confusables.py` contains 2,649 immutable mappings and no
runtime I/O. Every emitted value is ASCII and a second mapping pass is a fixed
point. This is deliberately described as a **UTS #39-derived ASCII closure**,
not as the complete standard UTS skeleton algorithm.

The generated module is byte-reproducible from the verified source under the
recorded command. Its SHA-256 is
`724e24c836afc1ae2374cdaf450540209ef04a6e7dc9acedfda268e6be598559`.
Runtime title/user/assistant checks, configured policy labels, known-token
checks, post-Capsule persistence checks, and both hashes now use the same
closure. A match replaces the entire unit with one fixed redaction. Script
shape is no longer itself a secret: the mixed-script atom check remains only
inside the conservative semantic grammar. Consequently normal Unicode is
preserved unless its actual closure matches a configured label or known-secret
pattern.

The final focused and broad evidence after this remediation is:

```text
Task Capsule and safety file: 366 passed in 1.21s
Task 1 plus Source Contracts and Codex Source Adapter: 386 passed in 3.59s
Adjacent census/contracts/source/scanner/adapter: 152 passed in 16.40s
Complete repository suite: 1014 passed, 1 expected warning in 325.91s
Wheel build/install/isolated imports: passed; 5 modules, 2649 mappings
Exact MCP/docs/in-memory tripwire nodes: 3 passed in 4.79s
```

The first adjacent run used pytest's long default Windows temporary path and
produced 19 `FileNotFoundError` path-length failures. A fresh run under the
established short `D:\t13` root passed all 152 nodes without a product change.
The wheel was built offline with isolation disabled, installed under `D:\t15`,
and imported with `python -I`; the generated Unicode module and all four Task-1
runtime modules resolved from the installed wheel rather than the checkout.

This implementation was submitted for the fourteenth independent security
review; its rejection and remediation are documented next.

### Fourteenth independent review: exact raw mappings and Unicode notice

The fourteenth **independent reviewer message** found that the first generator
normalized source codepoints before using them as dictionary keys. Casefold
collisions allowed one official row to overwrite another: `ƙ` and `ɠ` reached
the wrong ASCII-plus-apostrophe projections, 198 of the reviewer's 2,139
direct-ASCII probes differed, and `sƙ-` / `ɠhp_` remained content-dependent
hash channels. The review also found that generation depended on an unstated
host `unicodedata` version and that a URL in the module header did not satisfy
the Unicode License v3 notice-distribution requirement.

Exact raw-row, exhaustive invariant, toolchain, duplicate/cycle, packaged
license, and paired-secret tests were added before the production change.
Their authentic RED was:

```text
8 failed, 6 passed, 356 deselected in 1.61s
```

The six passes were retained baseline confusable controls. The eight failures
were the missing raw artifact/invariant APIs, missing raw-cycle and duplicate
guards, missing toolchain guard, missing notice, and the two exact hash
channels.

The generator now keys all 6,565 records by their exact official source
codepoint. Duplicate raw keys are rejected; targets are recursively resolved
over that raw graph; and any cycle aborts generation. It no longer selects a
winner among NFKC/casefold-collided source rows. The generated module also
contains the exhaustive 2,139-entry non-empty direct-ASCII invariant: every raw
closure target whose pinned casefold/NFKD/mark-removal result is ASCII. Tests
compare that complete invariant and explicitly verify official rows U+0199,
U+0260, U+01A5, and U+01BD as `k`, `g`, `p`, and `s` at runtime.

Runtime secret canonicalization now performs NFKC without casefold, applies
the exact raw closure, then casefolds, performs NFKD mark removal, and reapplies
the raw closure until a fixed point. A generated-wide idempotence test covers
every raw source. Configured sensitive labels use a symmetric two-candidate
canonicalization (the exact raw-first view plus a case-insensitive label view)
without changing generator keys. This preserves existing case-insensitive and
Greek/Cyrillic configured-label contracts while the known-token path remains
the exact reviewed runtime pipeline.

This exact-data contract corrects an earlier non-official projection. Unicode
17 maps `ᴋ`, Cyrillic `к`, and Greek `κ` to U+0138 `ĸ`; it does not provide a
raw U+0138-to-ASCII-`k` row. Previous tests that invented that projection were
replaced by U+0199 `ƙ`, whose official target is `k` plus a removable combining
mark. No hand-written exception restores the rejected projection.

Generation is now deliberately pinned to CPython 3.12.13 with
`unicodedata.unidata_version == "15.0.0"`. The CLI checks both before using
Unicode normalization and raises the fixed content-free
`unicode_confusables_generator_toolchain_mismatch` error otherwise. The
generated artifact remains importable on the project's supported Python
3.10+ runtimes, but byte reproducibility is claimed only for that pinned
generator toolchain. Under it, the module is byte-reproducible at 165,893
bytes with SHA-256
`58799beda4ce19d6873e3fb84d2774e5f4e47bd915fc22e865685c0e3fd26b23`.

`agc_runtime/UNICODE-LICENSE.txt` contains SPDX `Unicode-3.0` followed by the
complete official Unicode License v3 copyright, permission, warranty, and
liability notice from `https://www.unicode.org/license.txt`. Its SHA-256 is
`bdd51f03760a320f9e14686958f67c2ee2cd1ecd7247940b14be42413eda4c25`.
`pyproject.toml` explicitly packages it, the generated module header points to
the local notice, and the isolated wheel check reads the complete notice from
the installed package.

Final fourteenth-review remediation evidence is:

```text
Exact review slice: 13 passed in 0.40s
Task Capsule and safety file: 369 passed in 1.09s
Task 1 plus Source Contracts and Codex Source Adapter: 389 passed in 1.79s
Adjacent census/contracts/source/scanner/adapter: 152 passed in 18.21s
Complete repository suite: 1017 passed, 1 expected warning in 354.68s
Wheel build/install/isolated notice import: passed; 6565 raw, 2139 direct ASCII
```

This implementation was submitted for the fifteenth independent security
review; its rejection and remediation are documented next.

### Fifteenth independent review: raw lookup must precede compatibility

The fifteenth **independent reviewer message** found one remaining Critical
ordering error. Runtime `_confusable_skeleton` applied NFKC before consulting
the exact raw table. Compatibility normalization therefore erased 90 of the
2,139 official direct-ASCII source identities. The previous test was named as
an exhaustive runtime invariant but compared generated data exhaustively while
calling production runtime for only four characters. Greek lunate sigma `ϲ`
was the concrete secret channel: its official target is `c`, but NFKC changed
it to final sigma before lookup, allowing `ϲOMPANY` and a configured `C` label
to bypass pre-Capsule and persistence gates.

The production-wide 2,139-entry test, representative mismatch categories,
paired title hashes, and persistence probe were added before the production
change. Their authentic RED was:

```text
7 failed, 1 passed, 368 deselected in 1.21s
production OFFICIAL_DIRECT_ASCII mismatch count: 90
```

The one passing control proved that the generated raw closure itself was
already a fixed point. The failures covered the complete runtime mismatch
dictionary, long-s `ſ`, Greek capital mu `Μ`, fullwidth brackets, the
`ϲOMPANY` hash channel, and the configured-`C` persistence bypass.

Runtime now examines every **original codepoint** first. If it has an exact
entry in `RAW_CONFUSABLE_CLOSURE`, that fixed target is used; only an unmapped
codepoint receives canonical NFD fallback. The mapped text is then casefolded,
NFKC/NFKD-normalized, and stripped of combining marks. No compatibility
normalization occurs before the first raw lookup, and no post-casefold raw
mapping pass invents a different direct target.

The raw-derived skeleton deliberately preserves official whitespace output,
including tabs; it neither collapses nor trims. Configured-label
canonicalization is a separate wrapper that collapses and trims whitespace and
compares the exact raw-first and case-insensitive candidate views. Known-secret
patterns inspect both the raw-derived view and the compatibility view, which
preserves the earlier fullwidth-token behavior without corrupting the official
raw invariant.

The runtime test now calls production `_confusable_skeleton(chr(source))` for
every one of the 2,139 generated `OFFICIAL_DIRECT_ASCII` entries and reports an
explicit mismatch dictionary. Its GREEN mismatch count is zero. A separate
complete test proves that every generated raw-closure target is unchanged by a
second raw-table application. The report does **not** claim whole-skeleton
idempotence: official data requires both `Μ -> m` and ASCII `m -> rn`, so whole
skeleton idempotence would conflict with direct-row equality.

Final fifteenth-review remediation evidence is:

```text
Exact production invariant/adversarial slice: 8 passed in 0.37s
Task Capsule and safety file: 376 passed in 1.63s
Task 1 plus Source Contracts and Codex Source Adapter: 396 passed in 4.80s
Adjacent census/contracts/source/scanner/adapter: 152 passed in 25.58s
Complete repository suite: 1024 passed, 1 expected warning in 459.82s
Wheel isolated official-runtime mismatch count: 0 of 2139
```

The Unicode source, pinned generator toolchain, generated raw artifact, and
packaged Unicode License v3 notice are unchanged and remain under regression.
That checkpoint was submitted for the sixteenth independent security review;
it did not claim reviewer-clean completion.

### Sixteenth independent review: symmetric sensitive-label candidates

The sixteenth review found that storing only the lexicographically smallest
configured-label candidate made policy construction asymmetric. In
particular, lower-, title-, and upper-case `m`, `team`, and `memory` labels did
not all match the same ASCII, Greek-confusable, and fullwidth text surfaces.
The authentic RED exercised policy storage, title pre-scrub, both hashes, and
the persistence-boundary detector across those Cartesian products:

```text
34 failed, 376 deselected in 7.56s
```

`capture_capsule` now owns the single `_sensitive_candidates` contract. It
passes the original, lower, upper, and casefold surfaces, plus each surface's
NFKC form, through the unchanged raw-first confusable skeleton. Each result is
then whitespace-collapsed and trimmed; empty values are discarded and the
remaining candidate set is returned sorted and unique. The construction has a
fixed upper bound of eight candidates and is deterministic.

`CapsulePolicy` stores the flattened, deduplicated union for every configured
label instead of choosing one candidate. A label whose complete candidate set
is empty remains a fixed contract error. Pre-scrub, known-secret inspection,
and post-gate sensitive-label detection all reuse the same helper, so policy
and text now have symmetric candidate generation. Existing tests that asserted
an internal one-canonical-value representation were intentionally narrowed to
the new `1..8`, sorted, unique representation contract; their safety behavior
was not relaxed.

Final sixteenth-review remediation evidence is:

```text
Task Capsule and safety file: 410 passed in 1.57s
Task 1 plus Source Contracts and Codex Source Adapter: 430 passed in 2.75s
Adjacent census/contracts/source/scanner/adapter: 152 passed in 21.10s
Complete repository suite: 1058 passed, 1 expected warning in 568.51s
Wheel isolated official-runtime mismatch count: 0 of 2139
Wheel isolated sensitive-candidate contract: passed
```

The first complete-suite attempt used an inaccessible `D:\t20` entry in
`PYTHONPATH`, a long writable basetemp, and a dependency venv without the
build backend. It produced three environment-only failures after 1,055 passes.
The fresh natural-order rerun removed the inaccessible entry, supplied the
existing offline build backend, used the established short path, and passed
all 1,058 nodes without a product change.

That checkpoint was submitted for the seventeenth independent security review;
it did not claim reviewer-clean completion.

### Seventeenth independent review: reject partially empty label variants

The seventeenth review found that text candidate filtering had hidden empty
committed variants from policy construction. A label such as acute accent
`U+00B4` retained a nonempty apostrophe candidate even though its compatibility
form became only whitespace plus a combining mark and compacted to empty. That
made configured-label and text candidate promises asymmetric.

The review reported 21 affected non-control single codepoints. A fresh scan of
the complete Unicode range under the pinned CPython 3.12.13 / Unicode 15.0.0
generator toolchain found the same family plus `U+0345 COMBINING GREEK
YPOGEGRAMMENI` and `U+037A GREEK YPOGEGRAMMENI`, for a conservative 23-codepoint
superset. Both additional values were demonstrably accepted by the old policy
and had partially empty views, so they are covered by the same fail-closed rule.
The authentic RED was:

```text
25 failed, 23 passed, 410 deselected in 5.63s
```

`capture_capsule` now exposes one internal `_sensitive_candidate_views` helper
that always returns the eight committed compact views in positional order,
including empty strings. `_sensitive_candidates` is the text-facing projection
and returns only nonempty, sorted, unique values. `CapsulePolicy` uses the raw
eight-view helper and rejects an input label if **any** committed view is empty;
only then does it flatten and deduplicate the union. Contract exceptions remain
fixed and content-free. Safety pre-scrub, known-secret matching, and post-gate
matching continue to use the one text-facing helper; there is no duplicate
candidate implementation.

The full-Unicode regression scans every non-control single codepoint, asserts
the exact 23-value boundary for this pinned toolchain, and proves all 23 policy
inputs fail closed. Separate controls prove empty text views cannot match a
nonempty configured label and normal case/Greek/fullwidth label equivalence is
unchanged.

Final seventeenth-review remediation evidence is:

```text
Exact review/full-Unicode slice: 48 passed in 4.03s
Task Capsule and safety file: 458 passed in 5.46s
Task 1 plus Source Contracts and Codex Source Adapter: 478 passed in 5.96s
Complete repository suite: 1106 passed, 1 expected warning in 565.75s
Wheel isolated official-runtime mismatch count: 0 of 2139
Wheel isolated partial-empty policy rejects: 23 of 23
```

This implementation is awaiting the eighteenth independent security review;
the report does not claim reviewer-clean completion.

## Verification evidence

Final Source Adapter, Source Contracts, Census, Scanner, and disabled-boundary
adjacent suite, in its required census-before-adapter import order:

```text
152 passed in 21.10s
```

A deliberately contaminated reverse order produced only the repository's
documented `sys.modules` census precondition (`44 passed, 2 failed`); the clean
required order passed without a product change.

Final natural-order complete repository suite:

```text
1106 passed, 1 expected warning in 565.75s
```

The warning is the existing intentional duplicate-name ZIP adversarial
fixture.

Clean package evidence:

- Exact MCP/docs/in-memory tripwire nodes: `3 passed in 1.82s`; the server
  exposes only `agc.admin`, `agc.read`, and `agc.write`.
- A fresh `python -m build --wheel --no-isolation` succeeded and explicitly
  packaged `_unicode_confusables.py`, the full `UNICODE-LICENSE.txt` notice,
  `capture_capsule.py`, `capture_safety.py`, and the updated source adapter.
- `pip --no-deps --target` installed that wheel to an isolated directory;
  `python -I` loaded all four Task-1 modules from the installed target, not the
  checkout.

Final static and filesystem gates:

```text
compile: clean for 7 Python files
strict UTF-8 / no BOM: 10 scoped implementation/test/report/license files
git diff --check: clean (line-ending advisory only)
in-memory module subprocess/tempfile/network/write-call hits: 0
unresolved marker hits: 0
synthetic Memory Root files: 1 unchanged baseline file
FILESYSTEM_SENTINEL hits below that Memory Root: 0
```

No live Codex profile, installed AGC Memory Root, model/provider, network,
subprocess, Runner, Observation writer, Candidate/Formal Memory writer, Hook
installer, scheduler, or service was read, called, or changed.
