# LLM Wiki Log

## 2026-09-12 — M3 matrix and implementation-version evidence

- Added readable M3 six-field matrix and real implementation-version comparison
  between independent business start and the unique same-time Trace start.
  AGC adds version metadata to its own root payload; no Trace Runtime schema edit.
- Frozen transforms add .trace-version1; old field sets/versions stay readable.
  Missing labels remain unchecked; configuration/result references do not acquire
  fabricated verification. Labels prove metadata consistency, not binary identity.
- Red: three missing behaviors (9e6fc8). Initial regression found expected root
  payload needed its new version field (2fcff5); updated exact contract assertion.
  Focused regression: 68 passed in 5.72 s (fbd1e2). All metrics plus Capture Trace:
  474 passed in 168.82 s (74ab60), exit 0. Default host isolated, fake models only.
  Scoped independent static review: no Critical/Important findings. Diff check
  passed (f1b4f1), existing line-ending warnings.
- Single-case evidence-response patch rejected by safety approval before writing:
  private source/Judge text may persist in Codex conversation history. No bypass,
  no private reads, no implementation landed; discarded only this turn's draft
  tests for the unapproved command. Await explicit destination authorization.
- No production install, real Judge, commit or push. Overall acceptance remains
  open, including that entry point and policy-blocked visual check.

## 2026-09-12 — Original-spec acceptance checkpoint

- Added synthetic CLI journey through fake Judge, managed report, evidence index,
  fixture human correction and byte-identical no-host offline render. Original
  assessment retained; no real feedback/memory changes. 58 tests passed in 8.62 s
  (ded74c, exit 0); files under D:/tmp_test/metrics-acceptance-0912.
- Specification audit found remaining M3 verification/matrix and single-case
  evidence-view gaps. Local HTML navigation was blocked by Browser safety policy;
  no workaround attempted, no visual acceptance claimed. Checklist is recorded in
  docs/metrics-acceptance-2026-09-12.md. Runtime source unchanged this turn.
- No production install/config mutation, real Judge, commit or push. Next close
  those original-scope gaps before proposing installation; full flow remains open.

## 2026-09-11 — Attempt ownership and managed report cleanup

- Completed OS attempt locks (including real abrupt child-process exit test),
  inactive unfinished-attempt cleanup, and active/unknown fail-closed handling.
- Registered quality reports, classification exports and evidence exports with
  fixed files, source bindings, directory identity and hashes. Source checks and
  publication share Capture forget's root lock. Committed cleanup intents now
  include these report bundles; externally copied/offline reports are unmanaged.
- TDD report tests initially failed for missing module (74689a); fixed absent
  path probing during implementation. Reviewed P2 partial-write recovery defect
  was reproduced (b54bc3) and fixed with registered internal staging + exclusive
  hard-link publication; independent read-only review closed the finding.
- Full metrics/Capture Eval/Capture forget regression: 505 passed, 147.73 s
  (755aa7). Afterwards, reproduced CLI busy-lock traceback (a500b4) and sanitized
  RuntimeError at the CLI boundary. Final affected evidence CLI/attempt lock/report
  suite: 23 passed, 26.25 s (6d360e). No need to rerun unrelated suites for that
  exception-list-only change. Diff check passed (68a2fa), existing LF/CRLF warnings.
- All files and model data synthetic under D:/tmp_test; only test-owned artifacts
  removed. No production install/config changes, private sessions, real Judge,
  commit or push. Full original metrics goal remains open: P1–P4 end-to-end/visual
  acceptance and explicit P5 production authorization, not more cleanup redesign.

## 2026-09-11 — Connect Capture forget and recover cleanup intents

- Source invalidation and metadata-only cleanup intent now share the original
  Capture transaction; external result deletion follows commit under existing
  locks. Partial failures defer and preserve intent for the next explicit forget.
- Fixed read-lock reentry in recovery and a reviewed fail-open when metrics host
  configuration disappeared. Host sends now preserve ledger binding metadata;
  missing/replaced host or ledger cannot silently skip cleanup.
- Full metrics/Capture Eval/Capture forget suite: 491 passed in 173.66 s (f83f55).
  Independent read-only review finding closed; diff check passed. Only synthetic
  test data and fake models used; no production install or publication.
- Remaining: pending attempts, report dependencies and original-scope final
  acceptance/authorized production rollout. Full metrics goal remains open.

## 2026-09-11 — Restricted artifact cleanup executor

- Added internal exact-snapshot cleanup under the shared commit guard, with
  preflight rejection, immediate fixed-file verification and final absence check.
  Partial unlink progress is explicit; there is no rollback or durable recovery.
- Reproduced and fixed status-only terminal binding and recreated-file success
  reporting. Candidate snapshots now include full terminal digests.
- Final affected suite: 57 passed, 55.29 s (256e83). Read-only review findings
  closed. Only synthetic test-owned files deleted; no production/model/push.
- Production forget integration and recovery remain unfinished; no new CLI added.

## 2026-09-11 — Cleanup candidate selection and result commit coordination

- Added read-only exact receipt/subject candidate selection with fixed artifacts,
  directory identities, bounded hashes and separate pending/unbound states.
- Host Eval/classification now share the existing Memory Root lock only during
  final source/config/registration checks and result persistence, not model calls.
- Reproduced and fixed reviewed final-source/registration ordering gap (0e5ef7).
  Final affected suite: 59 passed, 23.60 s (be6453); review finding closed.
  Earlier broader suite: 427 passed (b40d64), before the ordering correction.
- No production, real model, non-test deletion or publication. Exact invalidation,
  actual managed cleanup and forget integration remain unfinished.

## 2026-09-11 — Bind source inventory to managed directory identity

- Added directory registration v2 source-binding identity/membership checks.
  Missing/changed source inventory invalidates registered results. Host sending
  cannot fall back to null-binding standalone behavior.
- Reproduced and fixed host exports accepting legitimate unbound v2 results;
  strict source binding now propagates through all host reader paths and recursion.
- 86 affected tests passed in 55.60 s (683b54), independent review finding closed.
  No production/model/non-test deletion or publication. Cleanup candidate selection,
  in-flight writer coordination and existing forget integration remain outstanding.

## 2026-09-11 — Exact source receipt bindings

- Added per-plan controlled source joins for Capture, research and ready-only
  classification inputs, persisted before host model execution. No text/locators;
  immutable exact reuse, no inverse hash guessing or keyword-based matching.
- Fixed a reviewed regression where ignored duplicate references blocked a ready
  classification input; exact manifest multiplicities retained, only ready bound.
- 60 affected tests passed in 32.51 s (2f9791), read-only review finding closed.
  No production/model/deletion/push actions. Directory identity linkage and
  existing forget cleanup integration remain necessary before retention acceptance.

## 2026-09-11 — Close host consumer registration bypass

- Reproduced and fixed CLI refreeze/export accepting output whose host registry
  was corrupt. Explicit ledger binding now reaches summary, review/evidence and
  recursive step verification. Offline HTML remains a frozen view, not live proof.
- Independent review found a later source-read window; reproduced with two source
  call positions and fixed final per-entry registration verification before export.
- 53 affected tests passed in 25.25 s (cfded7); review finding closed. Production,
  real models, deletion and publication were not exercised. Cleanup remains open.

## 2026-09-11 — Exact external execution directory inventory

- Added host-ledger artifact registration before model calls and bounded reuse
  checks in Runner/classification reader. Directory substitution and changed
  local/host records reject verification. No source bodies, deletion rules or
  actual cleanup are added; exact source-to-forget integration remains open.
- Final affected suite: 60 passed in 23.28 s (28c73a); independent scoped review
  passed. Tests use synthetic data only. No production/model/publication actions.
- Audit lower-level freeze/export readers' host binding next; do not describe
  this increment as complete global retention enforcement.

## 2026-09-11 — Human review triage, bounded normal spotchecks

- Added the original-design review queue, using controlled metadata and shared
  validated human feedback. All flagged/unknown/disputed cases remain visible;
  unflagged spotchecks are capped at two across scenarios, not metric denominators.
- TDD: 23 expected missing-queue failures; 48 affected tests passed. Full metrics
  and Capture Eval adapter regression: 380 passed in 76.22 s (636f49). Independent
  read-only review passed for this increment. Model execution was simulated.
- External managed retention, on-demand evidence and original full acceptance
  remain unfinished. No production, real model, commit or push actions.

## 2026-09-11 — Local result dependencies

- Eval and classification executions register exact source/config/result dependencies
  before sending; readers reject missing/changed records and recheck before return.
- 55 related tests passed (f3bc68), independent review passed. No files deleted or
  production configuration changed. Global output discovery/forget cleanup remains
  incomplete; local dependency records alone do not satisfy managed retention.

## 2026-09-11 — Correct bulk evidence export to original privacy scope

- Original design section 10 disallows bulk source-body HTML and unmanaged derived
  content persistence. Removed raw annex file/body HTML export introduced earlier;
  only controlled reference index and content-free HTML are generated now.
- 19 related tests passed (012d5b), independent review confirmed. Existing files
  not deleted. Execution-result dependency registration/invalidation still open;
  do not equate this correction with full retention or original goal completion.

## 2026-09-11 — Private evidence export CLI

- Connected explicit Capture/research evidence export to fixed host and live source
  verification, producing private annex/HTML without rerunning Judge.
- Reproduced and fixed reviewer finding for empty research plans. Latest related
  tests: 24 passed (c09a10), including zero-call empty-plan export. Full original
  source/retention/visual/production acceptance requirements remain open.

## 2026-09-11 — Private evidence HTML drilldown

- Explicit matching evidence annex renders original model assessments and safe
  documents as escaped text; default reports do not include this private content.
- Latest related tests: 24 passed (429407), independent review passed. Generation
  CLI, managed invalidation, visual and full original acceptance remain pending.

## 2026-09-11 — Explicit private evidence annex

- Added full assessment/safe-document annex with exact review binding and live
  source checks at generation; unavailable cases contain no private content.
- Latest related tests: 27 passed (8842a4); independent review passed. CLI/HTML,
  managed invalidation and full original acceptance remain pending. No production
  source reads, model calls, installed configuration changes or publication.

## 2026-09-11 — Preparation-state report coverage

- Added content-free preparation status chart and reference details with methods;
  preserved complete input validation for classification/model-call paths.
- Latest affected tests: 31 passed (cc1a91). No live data or model calls. Broader
  original report/evidence and production acceptance requirements remain active.

## 2026-09-11 — Research cohort report coverage

- Optional frozen cohort section displays selection states, reasons and methods
  separately from M5 judgments; does not equate counts with benefit or population.
- Affected reports and Skill tests: 17 passed (8e1628). Complete preparation-state
  display and other original report/evidence requirements remain unfinished.

## 2026-09-11 — Verified classification export and M5 handoff

- Added host-bound export command with point-in-time verification metadata and
  complete preparation coverage, then tested exported cohort feeding M5 planning.
- Complete metrics/Capture Eval regression: 326 passed, no skips (70d973); local
  Runtime loaded, model process simulated. Independent review and Skill checks pass.
- Original scope remains active; no production changes or real model calls.

## 2026-09-11 — Classification result verification

- Added read-only classification artifact/ledger and live-source verification;
  rejects stale, incomplete or inconsistent results without calling a model.
- Latest affected tests: 26 passed (c365a1), independent review passed. Verification
  is consistency, not authenticity. CLI handoff and full acceptance remain pending.

## 2026-09-11 — Classification CLI host integration

- Connected classification preparation/execution to fixed host and ledger;
  preparation persists no input bodies, execution reports real call attempts.
- Synthetic native-source CLI integration and affected tests: 19 passed (71d371).
  Independent review passed. Result verification/handoff and full scope remain.

## 2026-09-11 — Bounded classification execution

- Implemented digest-bound single-send classification plans, live pre/post source
  and configuration checks, exclusive shared reservations and controlled artifacts.
- Latest affected tests: 34 passed (16be3a); independent review passed. No real
  model calls or production changes. Host CLI and full original acceptance pending.

## 2026-09-11 — Structured classification contract

- Projected input-only classification into the existing MetricsGateway payload;
  validated structured output before exact label/cohort binding.
- Latest affected tests: 25 passed (3ed72e), including fake-adapter integration.
  No live classifier, production changes or automatic publication.

## 2026-09-11 — Bounded research classification inputs

- Added explicit research-inputs using native references and live access checks,
  preserving ambiguity/unavailable states without model calls or file writes.
- Reproduced and fixed cumulative-budget manifest loss found in independent
  review; oversized entries now retain input_budget_exceeded without body.
- Latest affected regression: 35 passed (b29ed3). Reviewer confirmed closure.
  Classification execution and full original acceptance remain unfinished.

## 2026-09-11 — Research CLI host integration

- Connected research plan/evaluate commands to fixed host roots and shared ledger,
  actual historical input/final source and live Capture access checks. Bound native
  delivery timestamps to the selected cohort after reproducing a missing check.
- Updated explicit Skill guidance; independent bounded review found no new bug.
- Full metrics + Capture Eval adapter suite with local Runtime: 282 passed, no
  skips. Skill validation and diff check pass. No production/model/Git publication.

## 2026-09-11 — Research access policy and reviewed evidence boundaries

- Mandatory live Capture exclusion/forget checks now wrap historical source reads.
  Uncaptured tasks remain eligible; missing control configuration fails closed.
- Independently reviewed and reproduced three message-projection bugs plus a
  missing-config race, then fixed them with targeted regressions.
- Broad intermediate run 77 passed; latest affected run 38 passed. All source,
  config and forget operations used isolated synthetic data. No live Judge or
  production installation, configuration change, commit or push.

## 2026-09-11 — Native research input/final evidence

- Added scoped CodexResearchSource and live source revision checks; no background
  inference, current memory substitution or hidden/tool message projection.
- Fixed native subagent mapping-key exclusion in the new adapter after a failing
  test. Final 47 related tests passed using synthetic JSONL only.
- Production source authorization/forget gates, richer historical evidence and
  research CLI remain pending. No production configuration or model call.

## 2026-09-11 — Research plan execution binding

- Added selected-task research plan/source map and live resolver contract. Rejects
  source changes, mismatched cohort membership and current-memory substitution.
- 35 related tests passed, including mock Judge runner/review/HTML integration.
  Historical production source and CLI integration remain pending; no live calls.

## 2026-09-11 — Independent research cohort

- Added bounded, deterministic M5 task metadata cohort and explicit research-cohort
  CLI. Retains unknown/excluded cases and unverified classification provenance;
  no Recall-derived denominator or quality/causality claim.
- 59 related tests passed. Historical source resolution and M5 execution remain
  pending. No production data/configuration, live model call or Git publication.

## 2026-09-11 — Complete preview return evidence

- capture_preview validates/returns complete Markdown without memory or receipt
  writes. Optional metadata records runtime_returned, not human confirmation.
- Updated repository formalization guidance; installed production Skill unchanged.
- Combined regression: 289 passed, 1 optional adapter import skipped. Fixed short
  test IDs after reproducing Windows environment variable length errors.
- No real Judge, production install/configuration, commit or push.

## 2026-09-11 — Caller-supplied source provenance

- Business evidence v2 preserves opaque request source/revision/digest, explicitly
  unverified; old v1 records remain readable. No source plaintext recorded.
- 40 business/report/write tests passed. Preview delivery and confirmation are
  still unknown; no production changes or model calls.

## 2026-09-11 — Write-time version evidence and scope audit

- Added committed content digests to mutation results and opt-in business metrics;
  duplicate sources do not claim a new version. Disabled response shape unchanged.
- 49 related store/write/business tests passed using temporary memories.
- Removed general retry-grant development from required scope after checking the
  original design. Full original P1–P5 acceptance remains incomplete.

## 2026-09-11 — Frozen M4 attempt history

- Added strict content-free history projection and M4 first/latest/unfinished
  table with scope and method caveats. Retained older review schema reads.
- 30 relevant synthetic tests passed. Full development remains active; no
  production writes, model call or installation.

## 2026-09-11 — Metrics host and Capture evaluate CLI

- Added fixed per-user host binding, reference-only Capture plan preparation,
  authorized execution/reuse and unique frozen report outputs.
- 28 relevant tests passed with temporary host config and simulated gateway.
  Missing ledger stays missing; output relocation cannot reset reservations.
- No production installation or real model calls. Full design remains active.

## 2026-09-11 — Capture plan source map and Eval cutoff

- Added reference-only Capture plan preparation and fresh identity resolution.
- Separated source and evaluation observation cutoffs in review v2, retaining v1
  reads. Methods and human feedback timing use the distinct observation times.
- 34 related synthetic tests passed; complete host/CLI execution remains open.

## 2026-09-11 — Bounded metrics plan runner

- Composed verified reuse, live source identity checks, dependency execution and
  shared pre-send reservations; failures do not auto-retry or refund slots.
- 35 relevant tests passed, including concurrent roots using the same ledger.
  Host-stable ledger/consent binding and evaluate CLI still pending; no production
  call or installation performed.

## 2026-09-11 — Explicit metrics review Skill source

- Added explicit-only Skill and runnable command reference; tests exercise
  documented human feedback and rerender against synthetic artifacts.
- Fixed CLI relative revisions-dir handling without bypassing linked-root checks.
- 22 relevant tests passed; Skill structure valid. Not installed; complete
  evaluate orchestration and real acceptance remain pending.

## 2026-09-11 — Human metrics review revisions

- Added explicit append-only feedback CLI and separate HTML human state/corrected
  arithmetic. Original Judge results and formal memories remain unchanged.
- Related 26 tests passed; simulated feedback only, real review and visual
  acceptance pending. Full metrics development remains active.

## 2026-09-11 — Frozen metrics review report

- Connected validated review annexes to offline HTML and explicit render CLI.
- M2 fractions/uncertainty, M4 planned-case coverage and M5 independent axes
  retain methods and unreviewed boundaries. No live source/model calls.
- Tests: 186 passed, 1 optional adapter integration skipped. Full design and
  production acceptance remain incomplete; no installation or push performed.

## 2026-09-11 — Metrics service evidence

- Added opt-in read/write/notice metadata and explicit v3 batch collection;
  separate service states do not imply use, new mutations or preview delivery.
- 77 service regression tests and 76 metrics tests passed in overlapping runs.
  Real temporary memory writes/reads verified; no production or model calls.
- P3 adapter inspected read-only; effort/structured output missing. Full metrics
  goal remains active, including remaining P2 bindings and P3—P5 work.

## 2026-09-11 — Independent Capture attempts consumed by metrics

- Added explicit attempts-dir collector, v2 frozen batches and business-based
  M1/M3 accounting; v1 remains supported. Missing input is not event absence.
- 63 metric/evidence tests passed, agent-local; no production/model/install actions.
- Full metrics-development goal remains active; downstream business evidence and
  Judge/review workflow are not complete.

## 2026-09-11 — Metrics P2 Capture attempt evidence

- Added opt-in independent started/finished receipts at Runner run/cycle boundary,
  with shared Trace IDs, content-free projection and visible recording failures.
- First regression 89 passed; after boundary fixes 45 directly related tests passed.
  Agent-local synthetic checks, not production acceptance.
- No installation, production configuration changes, Judge, commit or push.
  Frozen-report ingestion and review/save/Recall evidence are still pending.

## 2026-09-11 — AGC metrics P1 offline implementation

- Added explicit read-only metadata collectors, reproducible frozen batches, limited deterministic M1/M3/M4 accounting, and offline HTML with per-metric methods. M2/M5 remain unmeasured.
- New and adjacent regression: 64 passed. Synthetic report checked at desktop and 375px widths; no horizontal overflow, page errors or remote requests.
- No production reads, Judge calls, installation, configuration changes, commit or push. Full metrics upgrade and production acceptance remain pending.
- See `handoff/agc-metrics-upgrade-v1-handoff.md` and `../docs/metrics-review.md` (repository documentation).

## 2026-09-07 — Exact-read repair installed, restart pending

- User authorized production installation and will restart Codex. Immutable local 0.4.5 repair deployment `3345a0e8...` installed successfully; prior environment and installer backup retained.
- Installed source hashes and dependency checks pass; no RSI experiment modules. All 36 formal memory file hashes and Memory Root config are unchanged; Trace path and enabled automatic task preserved.
- Host MCP acceptance awaits restart. This is not closure of global Census/status contention and was not pushed to GitHub.

## 2026-09-07 — Bounded Capture exact-read repair

- Diagnosed repeated Census validation under the global Capture lock; 981 run manifests contained 1,028,000 memberships for 3,303 unique revisions.
- Exact observation/receipt reads now validate only the committed receipt and at most eight members, with ledger/review checks and unchanged transaction locking. No production installation or formal-memory writes.
- New and adjacent read/forget/notification tests: 118 passed in 57.59 seconds. One content-hidden production-data read using the patched source took 0.0561 seconds.
- See `bugs/2026-09-07-capture-review-read-contention.md`. Global status/search/Runner Census work remains unchanged; rollout and broader contention acceptance pending.

## 2026-09-07 — Capture experiment source preflight

- Continued the existing supervised loop without production or external repository changes.
- Added read-only source/Prompt/Schema/Profile fingerprints and candidate Prompt isolation; snapshots explicitly do not attest execution or authorize models.
- Nine new tests plus existing core/provider/adjacent regression: 64 passed. No model calls, dependency installs, formal memory writes, commit or push.
- Next: real safe-Capsule request binding, independently reviewed labels, and a concrete first-round authorization summary. The RSI quality loop remains incomplete.

## 2026-09-05 — AGC supervised improvement loop specification

- Recorded the user-confirmed AGC-first direction in `requirements/agc-capture-supervised-improvement-loop.md` and the artifact registry.
- Proposed 24 synthetic cases split by task family, two supervised iterations, explicit baseline comparisons and persistent rejected-attempt evidence.
- Specification remains draft; implementation, model execution, production changes and publication have not started.

### Follow-up: specification confirmed and offline skeleton

- User confirmed continuation into implementation planning and offline development; branch `codex/agc-capture-loop`.
- Added pure synthetic experiment execution, evidence-bound comparison and linked round receipts; 24 exposed development fixtures are not a sealed acceptance dataset.
- New unit tests: 26 passed; combined targeted regressions: 49 passed, 1 optional-dependency skip. Full offline regression: 1453 passed, 1 skipped, 1 expected duplicate-ZIP-name warning in 593.20 seconds.
- No real model calls, production mutation, installation, commit or push. Trace/Eval/Wiki integration and two real improvement rounds remain pending.

### Follow-up: isolated real-provider integration

- Added AGC-owned Eval/Trace/Wiki bridge and a create-only experiment Wiki profile. Related tests: 55 passed with actual provider stores and only simulated model boundaries.
- Verified invalid-citation rejection, dataset mismatch before writes, complete reference coverage, Wiki readback, and duplicate-write idempotency.
- Preserved unrelated pre-existing LLM Wiki Runtime changes; local-source fingerprint and release limitation recorded in the implementation plan.
- Real Capsule/model identity integration, human-reviewed labels, independent holdouts, and two semantic improvement rounds remain pending. No production configuration, formal memory, dependency installation, commit or push.

## 2026-08-31 — AGC proactive Capture review notification

- Added deterministic `capture_review_status` readiness using a 10-observation or 24-hour threshold, oldest-first batches of 10, integrity fail-closed behavior, and content-safe aggregates.
- Added a content-free 24-hour notification cache and strict `capture_review_notice` admin action without changing the three-tool MCP surface.
- Added a Codex App scheduled-review Skill workflow that stays quiet when not ready, produces at most three complete previews, and preserves explicit confirmation as the only formal-memory write gate.
- Prepared Runtime 0.4.5 and passed 1427 full-suite tests with one skip and one expected adversarial ZIP warning, plus compile, package, dependency, UTF-8/no-BOM, version, and diff gates.
- No production installation, scheduled-task creation, preview model call, formal-memory mutation, or GitHub push was performed.

## 2026-08-25 — AGC project-aware Observation context

- Added deterministic opaque project scopes derived from validated Session cwd metadata without persisting or exposing the source path.
- Propagated exact scopes through Capsule and Observation persistence while preserving explicit caller scopes and schema v1.
- Strengthened extractor instructions for grounded self-contained project referents while retaining atomic predicates and prohibiting inference from opaque scope hashes.
- Updated quality-first formalization to group same-receipt observations, expand exact non-null project scopes to at most 20 items, and keep null/different scopes conservative.
- Agent-local verification passed 582 focused adjacent tests in the feature worktree and again after local fast-forward merge to `main`; compileall, diff, UTF-8/no-BOM, and test-integrity checks passed.
- No install, release, production replay/model call, historical rewrite, formal-memory promotion, or GitHub push was performed.

## 2026-08-22 — semantic Capture candidates

- Fixed historical `extractor_empty` results by adding a bounded semantic input lane while preserving exact deterministic direct-memory validation.
- Broader user evidence can persist only as atomic `agent_inferred` plus `tentative` observations; direct evidence cannot be semantically rewritten.
- Empty Capsules now complete as `no_durable_signal` before token reservation or Extractor invocation.
- Agent-local verification passed 761 relevant tests; the full suite passed 1293 tests with only two pre-existing Windows CRLF byte-idempotence failures and no new regression.
- Built and isolated-tested wheel `1B9405A...7249B8`, then installed immutable Runtime `af38109d...a5bc0`; installed core hashes match source.
- The exact-digest authorized `gpt-5.6-sol` Pilot processed one revision, produced two collected tentative inferred observations, reported zero failure and zero silent loss, and left production formal memory at 24 with no automatic promotion.
- Final handoff and artifact registrations were created. The verified branch was fast-forward merged into `main`; the merged relevant suite passed 761 tests and installed core files exactly matched authoritative main Git blobs.

## 2026-08-13 — agc-capture-coverage-mvp

- Locked the next milestone to provable Codex main-task Revision coverage rather
  than the complete automatic-learning loop.
- Revised the written design so Phase 1 stops at truthful Capture Receipt plus
  zero to eight Recall-isolated Collected Observations; aggregation, Candidate,
  and Formal Memory mutation remain deferred.
- Defined active-profile scope, completed-turn Revision identity, Hook/Scanner
  separation, two-level idempotency, transaction recovery, Source Health,
  backup/restore, Hard Forget, token accounting, and foreground latency gates.
- Registered the Change Brief and design for user written-spec review. Planning,
  production implementation, deployment, and Capture activation have not started.
- The user approved continuation after written-spec review. Split implementation
  into four dependency-ordered TDD plans: deterministic core, Codex source/Census,
  Extractor/Runner, and Windows host rollout.
- Mapped AC-01 through AC-20 to independently runnable tests and preserved four
  later human gates: real Scanner enablement, Hook trust, Shadow Backfill, and
  continuous Runner activation.
- Corrected rollback compatibility: released 0.2.0 cannot retroactively reject a
  future Capture schema, so post-data rollback disables processing while retaining
  a Capture-capable Runtime for read/status/forget instead of binary downgrade.
- Production code, tests, installation, and real-profile Capture remain unchanged.
- Implemented and independently hardened Capture Core, Source Census, safe
  Capsule/Extractor/Runner, inert Host installation, transactional supervision,
  Hook latency gate, explicit operations, and Runtime-bound activation digest.
- Agent-local AC-01..20 release verification passed: 1255 full-suite tests, one
  expected adversarial ZIP warning, wheel/sdist build, isolated installed
  four-entrypoint provenance, pip check, diff, and strict UTF-8/no-BOM.
- Capture remains off. Live Scanner, Hook trust, Shadow Backfill, sample review,
  and continuous Runner are still separate explicit human gates.
- On 2026-08-21 the user-authorized inert upgrade installed commit `8a8f75a`
  as immutable Runtime `97cda42d...a622e9`; version, four entry points,
  committed-source hashes, exact three-tool MCP surface, Codex binding, and
  default-off Capture state passed. A stable-Python selector and Python-bound
  deployment key prevent reuse of venvs built by a different interpreter.
- The user then authorized Scanner-only activation for the active Codex Home.
  Config migration retained 23 formal memories; Census and replay converged at
  38/38 known/accounted keys with zero silent loss. The 15-minute Windows task
  completed with result 0, Hook/Runner/model remained off, and a live-found
  Scanner/Runner argument bug was fixed in `47f5325` with 28 focused tests.
  Source health remains explicitly degraded by one `unknown_source_shape`
  quarantine, so Shadow Backfill and Runner are not authorized.

## 2026-08-11 — agc-recall-consistency-filter-validation

- Added an explicit Recall trigger for evaluating whether a project, repository,
  tool, or technology fits the user's research, learning, or long-term goals.
- Restricted Search filters to the six documented names and changed unknown names
  from silent ignore to the standard `invalid_request` response.
- Agent-local release gate passed twice at 195 tests, plus Skill validation,
  strict UTF-8/no-BOM, diff, deployed Runtime, and active Skill hash checks.
- Local deployment reports all 22 memories valid and unchanged; the current Codex
  process requires a new task or restart to load the new Skill and MCP process.

## 2026-07-29 — agc-v2-runtime-foundation

- Flow Record moved from execution to archived completion.
- Runtime Foundation implemented in commits `1ab7ba0` through `4a01076`.
- Agent-local release gate passed: 94 tests, wheel/sdist build, CLI version, strict UTF-8/no-BOM scan, and `git diff --check`.
- Verification and handoff registered under `.llm-wiki/verification/` and `.llm-wiki/handoff/`.
- No dashboard was created because this repository has no enabled or registered progress dashboard.
- Next independent deliverable: v2 Recall/Skill Adapter.

## 2026-07-29 — agc-v2-local-upgrade

- Flow Record moved from implementation to archived completion.
- One public Skill and the three-tool MCP adapter replaced the five alpha Skill surface.
- Deterministic v1 migration, manifest integrity, path containment, shared-source Hard
  Forget, retry recovery, and repeatable local installation were independently reviewed.
- Agent-local release gate passed: 188 tests, wheel/sdist build, CLI, MCP 2.0 stdio,
  strict UTF-8/no-BOM, backup ZIP, no-op installer, and local cutover checks.
- Local v2 contains 19 formal memories and one candidate; exposure is limited to one
  core card, with no personal core cards.
- v1 remains rollback material with auto capture disabled.
- Capture/backfill, Trace/Eval/Loop, and LLM Wiki Runtime remain deferred.
- No dashboard was updated because this repository has no enabled or registered progress dashboard.

## 2026-08-01 — 2026-08-01-catalog-stale-after-write

- Reproduced a write-to-recall consistency defect: one persisted formal memory
  was available by exact ID but absent from stale overview/search catalogs.
- The write dispatcher now refreshes derived catalogs for accepted formal-memory
  results and reports `catalog_refresh_failed` without contradicting a committed write.
- Agent-local verification passed: 190 tests, diff check, installed Runtime smoke
  test without manual rebuild, and live validation/search of all 20 formal memories.
- Codex configuration now points to content-addressed Runtime `0918faf6...6145ee`;
  the previous Runtime and installer rollback backup remain available.
- Verification and handoff artifacts were registered. No dashboard was updated
  because this repository has no enabled or registered progress dashboard.
## 2026-08-23 — task-aware Census catalog 0.4.1

- Replaced repeated frozen-member hot reads with an atomically published packed v2 Census catalog and concurrent one-time cold rebuild.
- Added transactional catalog invalidation/recovery for scan and Hard Forget paths, while keeping the derived catalog out of backups.
- Added deterministic local Capsule ranking, round-robin task selection, a three-per-task invocation cap, and selected-Capsule reuse without changing the model or persistence boundary.
- Agent-local evidence: 1334 full-suite tests before the final Capture-only packed layout, then 1064 Capture tests after it; package and installed/source hash gates passed.
- Production read-only acceptance found 915 unique revisions, cold rebuild 26.172 seconds, hot reads 8.370/6.122 seconds, zero hot member reads, and zero formal-memory/observation/token/Extractor deltas.
- Installed immutable Runtime 0.4.1 at `4f63831e...96bcf`. Codex config is updated; the current App task still holds the previous MCP process and requires restart before live-route closure.
- On 2026-08-24 the user restarted Codex App. The live MCP returned Runtime 0.4.1 with the expected production binding, enabled `scanner_only`, paused false, 946/946 accounted keys, zero pending keys, and zero silent loss; the archive gate is closed.

## 2026-08-25 — AGC 0.4.2 automatic Capture rollout

- Released and immutably installed Runtime 0.4.2, then verified the live Codex App MCP route after restart.
- Enabled the automatic Runner with one worker, a 500000-token incremental ceiling, a 15-minute `IgnoreNew` schedule, `gpt-5.6-sol`, and Hook/automatic formal-memory promotion disabled.
- Final activation reported route/scanner/backfill/continuous Runner ready with no conflicts; Census accounting was 1214/1214 with zero pending and zero silent loss.
- The first verification cycle settled 10 incremental calls, added one review-only Observation, and left all 26 formal memories byte-identical.
- Fixed two Host configurator defects found during activation: scheduler registration errors now terminate/roll back, and an independent TimeTrigger starts the 15-minute cadence in the active Windows session. Two RED/GREEN cases and 14/14 focused tests passed; a real automatic start was observed.
- A real scheduled cycle then exposed a 15-minute execution-limit collision that orphaned children and allowed the next trigger to start another scan. The task was quiesced, stale processes were removed after exact PID checks, accounting remained lossless, and `fc00887` raised the limit to 30 minutes with a third RED/GREEN contract; Host tests pass 15/15.
- The repaired task then completed a real 17:11:45–17:32:24 automatic cycle. It stayed single-instance across the 17:26:45 trigger, used Codex App `gpt-5.6-sol`, exited with result 0 and no leftover processes, added five isolated Observations, and left all 26 formal memories byte-identical; final accounting was 1238/1238 with zero pending or silent loss.
- GitHub push and GitHub Release remain intentionally excluded.

## 2026-08-30 — AGC 0.4.3 Capture Trace activation source

- Added an opt-in `mcp+trace` local-install profile that consumes the current
  local Runtime Contracts and Trace Runtime packages and binds their contents
  into a distinct immutable deployment key.
- Kept default installation, MCP, Hook, scheduler XML, Capture semantics, and
  production 0.4.2 unchanged; only an enabled Capture launcher receives
  `AGENT_TRACE_DB`.
- TDD covered invalid options, Windows absolute-path validation, real Contracts
  layout, launcher isolation, and immutable profile separation.
- Built AGC 0.4.3 and completed an isolated real cross-repository install under
  `D:\tmp_test`; Trace Doctor passed and a controlled failed Capture cycle
  persisted only a sanitized two-event root.
- The user then authorized production activation. Runtime 0.4.3 was installed
  into immutable deployment `13728135...eac8a`; package/import, launcher,
  config-route, pip, Trace Doctor, safe Snapshot, and unchanged 32-file formal
  memory gates passed. The existing task definition was restored; its missed
  09:41 trigger then completed through 0.4.3 with result 0, a complete two-event
  aggregate Trace, and zero silent loss. Closure commits were synchronized to
  `origin/main` after this record.

## 2026-09-08 — AGC Trace Event Query

- Implemented event-page adaptation with old Runtime fallback only when the API is absent. Retained domain checks, Case IDs and selected-Trace Snapshot caching.
- 8 RED tests; 42 related tests passing with synthetic evidence and fake Judge. One pre-existing lint finding unchanged; no production/model/installation/GitHub actions.
- Flow and handoff: `agc-trace-event-query`. Existing RSI and exact-read edits preserved.
