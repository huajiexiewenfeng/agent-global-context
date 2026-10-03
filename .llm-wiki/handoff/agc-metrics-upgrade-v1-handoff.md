# AGC metrics P1 handoff

## Current closeout: 2026-10-03

- Scope is the deployed Capture reliability/performance and pending-review fixes,
  plus the metadata-only report; not completion of all Metrics/Eval work.
- Current deployed 0.4.5 artifact is `51e474b1ae39db746d3f00f29584dd7d204c7e3f900bb4f5d3e7ba3c779c1476`.
  All ten modified runtime modules match installed bytes. Existing memory,
  Trace database, schedule and human confirmation gates are retained.
- Automatic cycles now complete and reduce backlog, but individual extraction
  timeouts remain. A completed cycle does not imply all items succeeded, and
  no end-to-end performance gain or long-term reliability claim is made.
- Two delivered preview batches are pending confirmation; actual App reads
  select a later batch without writing review outcomes or formal memory.
- User confirmed the real metadata report can be opened. Computation/re-render
  checks passed previously; this is not a screenshot-based cross-browser audit.
  Frozen baseline data is separate from subsequent operational observations.
- Capture model was changed by explicit user request to `gpt-6.1-sol` in local
  production configuration only. Independent review stays `gpt-6-sol`.
- Remaining: verify the new model's actual automatic cycle, observe residual
  item timeouts, and separately authorize/accept real Judge and benefit trials.
  No Judge was called and no production content/configuration is included here.
- Delivery: `069a200` pushed to main and verified against the remote SHA;
  416 selected regression tests passed. At 20:52 the first observed post-switch
  cycle exited 124 at the worker deadline without a terminal Trace, so new-model
  production acceptance remains incomplete. No model cause is established.
- Verification and current flow state: [Capture closeout](../bugs/2026-09-23-capture-system-proxy-timeout.md#2026-10-03-delivery-closeout).

## Latest: 2026-09-22 authorized production performance-patch installation

- User approved installing the two existing performance patches and backing up /
  clearing the single old Source quarantine. No model/Judge run authorized here.
- Installed 0.4.5 patched artifact in immutable deployment
  `dea2c3afe5fdfbdf0d6d141977de8b30773ae11a2ff0df3adf81c7e5dc5e4b3d`.
  Both changed installed Python files hash-match tested repository source.
  Targeted regression: 26 passed in 7.21s; new environment `pip check` passed;
  independent installed MCP handler overview accepted with 37 formal memories.
- Installer rollback backup:
  `C:/Users/admin/.agent-global-context-runtime/backups/20260922-223712-611-ed3cc59a101c48748246ccc109e3e0ef`.
  Prior immutable environment retained; configured Memory Root and Trace DB kept.
- Exact old locator_escape record was backed up, hash-verified and removed under
  native runner/write locks. Backup and before/after evidence live under
  `D:/tmp_test/agc-performance-install-20260922`. Formal files and Capture config
  are byte-identical to the pre-clear snapshot; zero source quarantines after clear.
- Production Metrics acceptance FAILED: same two cases, installed package,
  no Census repair, unchanged 30s ceiling: 30.080s / 30.862s timeout in first
  live access check. First stopped at snapshot JSON read, second at Census catalog
  digest serialization. Ready 0/2, no source text export, no model or Judge calls.
- Do not equate installation or old quarantine removal with fixing latency,
  scheduler descendant containment, or the 3 pending accounting records seen
  before maintenance. No commit/push; host MCP reload still requires restart.
  Scheduler restoration / final path audit are recorded in the linked bug below.
- Final check: installed-adapter path audit 5,662 files / zero diagnostics
  (not a full scan); scheduler restored enabled/Ready, next run 22:56:44 local,
  both locks absent, formal/config hashes unchanged, source quarantine count 0.

## Latest: 2026-09-22 identifier hotspot follow-up

- Scheduler was restored by the user and verified enabled. A later real patched
  preflight still timed out in both first access checks (30.155s/30.061s), so the
  earlier parallel Census change alone does not resolve the production issue.
- Read-only profiling identified repeated per-character Unicode classification
  for ASCII Census identifiers. Added an equivalent valid-ASCII fast path in
  capture_schema._identifier, retaining the original diagnostic fallback.
- Regression: 144 passed in 8.70s (567c00), after the expected profile assertion
  failed on the original implementation. Same 32-manifest pure-validation A/B
  comparison returned identical mappings and a 3.05x median local-stage ratio.
- This is not end-to-end acceptance. Production writer lock remained present;
  no new full preflight, model call, source export, install, commit or push.
  Next: same two cases through unchanged safety checks within the 30-second
  ceiling when lock-free. Do not infer success from reboot, unit tests or this
  local-stage benchmark. See the existing snapshot-timeout bug for full evidence.

## Latest: 2026-09-22 preflight performance follow-up

- Installed baseline reproduced both 30-second first-check timeouts after the
  production lock naturally released (30.175s ledger, 30.144s Census manifests).
- Local uncommitted patch extends bounded snapshot read-ahead to Census manifests,
  preserving full validation and lock lifetime. Related 84 tests passed (20b6ae).
- New-version real preflight was blocked by an existing live Capture lock after
  a bounded 30-second wait. Performance benefit is NOT yet verified; do not
  install or declare Metrics accepted based on synthetic regression alone.
- See ../bugs/2026-09-22-metrics-preflight-snapshot-timeout.md. No production
  configuration, scheduled task, formal memory or Judge changes in this work.

## Integration verified: 2026-09-19 (local only)

- Integrated codex/agc-minimal-fixes (2721666) with the Metrics checkpoint
  bc68b95 on the existing main branch. Resolved two textual conflicts without
  replacing either full-snapshot access checks or the readiness-only reader.
- Both Skill test additions survived the merge. The workflow keeps zero-proposal
  non-memory outcomes and Metrics preview/notice semantics. Scheduler configuration
  was not changed; its explicit restrictions still take precedence.
- Cross-regression: 124 passed in 30.42s, exit 0 (71fdd4). Scope:
  capture_read_service, skill_adapter, capture_snapshot_read_ahead,
  metrics_research_access/source, metrics_acceptance/preview/forget_integration,
  and capture_trace. Synthetic fixtures only; no real Judge or installation.
- This does not resolve or revalidate the two real-case preflight timeouts,
  private evidence-view authorization, visual acceptance or production pilot.

## Current checkpoint: 2026-09-19 (not a release)

- Preserve the existing Metrics implementation and its tests as a local WIP
  checkpoint. This is not production acceptance, installation, or publication.
- The 2026-09-17 focused run passed 45 tests in 14.27 seconds (d0e127):
  snapshot read-ahead, research access/source, acceptance, and research report.
  Historical larger suite results below are not a fresh full-suite claim.
- Two real first-turn preflights remain unready at the 30-second test ceiling.
  Bounded snapshot read-ahead alone did not resolve the bottleneck. Research
  source loading performs three live full-snapshot access checks; Census work
  is still outside the read-ahead path. Do not bypass forget/exclusion checks.
- Private single-case evidence viewing, HTML visual acceptance, and real Judge /
  production pilot remain open. No source-content export or Judge call is
  authorized by checkpointing this implementation.
- The separate codex/agc-minimal-fixes branch overlaps capture_store.py,
  review-notification-workflow.md and test_skill_adapter.py. Preserve both the
  readiness-only read_review_snapshot and full read_snapshot(read_workers=1).
  Preserve both preview/notice semantics and the separately approved zero-proposal
  workflow; check scheduler instructions independently before changing behavior.
- Next: review the checkpoint, integrate the separate fix with semantic conflict
  checks, then affected cross-regressions and the same two real-case preflights.
  Do not expand metrics scope. Older sections are historical checkpoints.

## Latest: M3 matrix implemented; private case-view authorization pending

- M3 now has a readable six-field HTML matrix. AGC root-start Trace payload adds
  implementation_version; matching uses independent business time/version, not
  today's installed version. Mismatch is conflict, missing evidence unchecked.
- New frozen transforms append .trace-version1 and validate the new event field;
  legacy transforms keep their exact previous field sets. Focused suite: 68 passed
  in 5.72 s (fbd1e2). Read-only reviewer found no Critical/Important issue in this
  scoped increment. Whole metrics + Capture Trace compatibility: 474 passed in
  168.82 s (74ab60), exit 0; isolated synthetic host, no real models.
- Single-case private evidence response patch was rejected by safety approval
  before any source edit landed. It may persist private text in Codex conversation
  history; explicit destination authorization is required. Do not retry through
  an alternate tool or publish body HTML. Draft tests for this unimplemented
  command were removed. No private sources or real models were used.
- Need user choice on that data destination, plus remaining visual/production
  acceptance. Original overall flow remains open; no installation/commit/push.

## Latest: original-spec acceptance, 2026-09-12

- Added test_metrics_acceptance.py: synthetic prepare/evaluate/export/feedback/
  offline re-render journey, one fake Judge call, unchanged original review and
  byte-identical repeated HTML. Related suite: 58 passed in 8.62 s, exit 0 (ded74c).
- Acceptance is NOT complete: M3 implementation/config/result checks remain
  constants and fields are shown as JSON instead of a readable matrix; evidence
  resolver exists but the review workflow has no single-case content-view entry.
- Browser policy blocked local file navigation; no screenshot or visual pass.
  Do not bypass through a different browser/proxy. No production/model/install.
- Full checklist: docs/metrics-acceptance-2026-09-12.md. Next implement those two
  original-scope gaps, not more retention redesign or production installation.

## Latest continuation: attempt ownership and managed report dependencies

- OS attempt locks now cover the entire quality/classification execution. Valid
  inactive locks allow unfinished-result cleanup; active/unknown ownership stays
  pending. No fabricated terminal or usage. Cleanup reacquires the same lock.
- Quality run/review/HTML, classification export and evidence-index/HTML bundles
  are registered before publication with source binding, fixed names, original
  directory identity and content hashes. Live checks/build/publication hold the
  root guard; unavailable source/binding now blocks new managed exports.
- Existing Capture forget intents also clean report bundles. A reviewed partial
  write defect was fixed using registered bounded staging files, flush/fsync and
  exclusive hard-link publication. Final user-edited files still fail closed;
  staging is private runtime-owned work. Independent read-only review closed P2.
- Regression before the final CLI busy-lock guard addition: 505 passed in 147.73 s
  (755aa7), all metrics + Capture Eval + Capture forget, isolated synthetic host.
  Final focused guard/staging/attempt suite: 23 passed, 26.25 s (6d360e); diff check
  passed with existing line-ending warnings (68a2fa). Real child
  os._exit lock release is also tested; not merely a deleted-terminal simulation.
- No production install/configuration changes, real Judge/private-session calls,
  commit or push. These two cleanup increments are implemented, not deployed.
- Next: original-spec P1–P4 end-to-end/visual acceptance and scope checklist, then
  explicit installation/real-batch P5 authorization. Verify on-demand evidence
  review, M3 field coverage and overhead evidence against original requirements;
  do not infer completion from the test count or restart cleanup design.

Earlier sections below are historical checkpoints, not current remaining-work lists.

## Latest continuation: Capture forget transaction and durable cleanup recovery

- Capture forget now prepares a content-free receipt/ledger-identity intent in
  its existing transaction. The only new transaction namespace is the bounded
  Capture-root metrics-cleanup directory. External unlink occurs after commit,
  still under root and Capture write locks; no arbitrary external rollback paths.
- Failed/interrupted post-commit cleanup leaves the intent, returns deferred with
  explicit current_request_applied/source_forget_committed where possible, and
  resumes on a later explicit capture_forget. Existing transaction recovery runs
  first. Recovery checks original ledger identity and source receipt redaction or
  tombstone. No source bodies or model clients are loaded by cleanup.
- Fixed a reproduced Capture read-lock reentry during recovery by checking exact
  validated receipt/tombstone metadata under the already-held lock. Tests exercise
  source transaction interruption, actual partial unlink and subsequent recovery.
- Review found missing host.json silently skipped cleanup (872ea7). Fixed; host
  sends now persist/verify a content-free metrics-host.json binding in Capture
  runtime before model calls. Missing whole host directories are detected via that
  marker (reproduced 1ffeba); changed memory/ledger bindings fail closed. Independent
  read-only review confirmed the P1 closed. Marker is outside backup allowlist.
- Full metrics + Capture Eval + existing Capture forget regression: 491 passed in
  173.66 s (f83f55). Diff check passed with existing line-ending warnings. Default
  host lookup was isolated for tests; all models simulated, files synthetic.
- No production installation/config mutation, private session/model calls or
  publication. Pending/unbound attempts still defer; an interrupted model with no
  terminal is not silently declared dead. Remaining: pending-attempt reconciliation,
  report dependency coverage, original-requirements/end-to-end acceptance and
  explicitly authorized production P5. Do not call the full metrics goal complete.

## Latest continuation: restricted cleanup execution

- Added metrics_cleanup_apply.apply_cleanup as an internal API only. It requires
  explicit-request assertion, trusted ledger/commit guard and an exact snapshot.
  Changed/pending/unbound inventory fails before deletion. Each fixed file gets
  immediate registration/terminal/hash/stat checks, then unlink; all other files,
  directories, send reservations and metadata are retained.
- Successful unlink operations are reported exactly; failures are sanitized and
  partial progress is not described as atomic rollback. Final snapshot checks the
  expected absence. File-recreation regression reproduced then fixed (fc41ee).
- Review found status-only terminal binding missed changed finished_at. Reproduced
  (0f42ce), added full terminal_digest to candidates and per-file checks. Independent
  read-only review confirmed both fixes. Final cleanup/candidate/guard/registry/
  source-binding suite: 57 passed in 55.29 s (256e83); diff check passed.
- Only synthetic test-owned files were deleted under the fixed test workspace;
  no production, real model or publication actions. No production caller exists.
- Next: connect source invalidation and existing authorized forget transaction,
  including partial deletion and crash/pending handling. Existing Capture
  observation forget already marks its receipt redacted_by_forget; research access
  denies that receipt as well as revision tombstones (source-checked this turn),
  so do not assume a new general invalidation framework is needed. Current API
  itself neither invalidates source nor durably journals cleanup; full goal open.

## Latest continuation: read-only cleanup candidates and guarded commits

- Added exact receipt/subject candidate selection from bound registrations only.
  Files return bounded hash/stat metadata, no bodies; missing terminals and
  unbound records are separate. No files are deleted. Recovered candidate/source/
  registry verification: 37 passed in 20.67 s (4e1c9b).
- Host CLI now passes the existing Memory Root write-lock factory to quality and
  classification executors. Model work is outside the lock; final live source,
  configuration, registration checks and content writes are inside it. Busy or
  invalid final checks retain failure, never retry/refund. Library defaults remain
  explicitly uncoordinated standalone behavior.
- Independent review found quality checked registration before its final source
  callback. Reproduced during_final_source (0e5ef7); moved registration to a final
  commit_check after source/config validation and before writes. Reviewer confirmed
  the finding closed. Final affected execution/host/CLI/candidate suite: 59 passed
  in 23.60 s (be6453). Earlier all-metrics plus Capture Eval: 427 passed in 92.53 s
  (b40d64), before this final ordering correction; not final whole-tree acceptance.
- No production installation/config changes, real-model calls, private-session
  reads, non-test deletion or publication. Still open: exact invalidation and
  cleanup integration, existing/partial result retention, pending attempts and
  report dependencies. Guarded commits alone are not completed Hard Forget.

## Latest continuation: source inventory bound to directory registrations

- Directory registration v2 adds source_binding_id, reconstructed from the same
  ledger's validated source inventory and checked against case/input membership.
  Missing or changed source inventory invalidates bound records; v1 is rejected
  rather than silently migrated. Standalone records may explicitly use null.
- Host execution requires a non-null binding. A test reproduced a send-time
  disappearance silently falling back to null (f0740e); require_source_binding
  now prevents that. Classification requires it when native refs are supplied.
- Review identified host export accepting legitimate standalone null-bound v2
  records. Reproduced both quality and classification (4a3c17,8278ef); CLI now
  passes True throughout review freezing and both exports, recursive quality
  verification, summary, evidence final checks and classification pre/post checks.
  Independent read-only review confirmed the downgrade finding closed.
- Final affected source/registry/CLI/reader/review suite: 86 passed in 55.60 s
  (683b54). Diff check passed with existing LF/CRLF warnings. No production,
  real-model, or non-test deletion actions.
- Next: read-only exact cleanup candidate resolution using receipt join plus
  bound directory/filesystem identity, then existing forget transaction integration.
  Concurrent in-flight writers must not recreate content after cleanup; plan that
  coordination before adding deletion. No cleanup exists yet, goal remains open.

## Latest continuation: exact source receipt joins

- New metrics_source_bindings builds controlled per-plan joins. Capture uses the
  original evidence reference receipt ID; research joins host-supplied native
  RevisionRefs by task_ref then derives receipt_id_for(ref.key). Classification
  joins exact native-reference digests to its validated preparation manifest and
  registers only ready inputs. No body, locator, raw task or project path exported.
- Host evaluation CLI registers the map before Runner; classification CLI passes
  native refs into execution, which registers after authorization/live preparation
  and before the model call. Ledger/source-bindings/<plan_id>.json is exclusive,
  idempotent only for identical content, validated on reading, never overwritten.
- Builders validate metadata joins, not live provenance. The host resolver still
  must prove the native revision matches the frozen metrics evidence at execution.
  Registrations may exist for failed attempts; never treat inventory presence as
  successful evaluation or deletion authority.
- Review found classification [A,B,B] blocked ready A because B was duplicated.
  Reproduced (1fe733), fixed classification-only duplicate acceptance with exact
  manifest multiset matching; only A is sent/registered. Eval remains strict.
- Final source-binding/CLI/classification/registry suite: 60 passed in 32.51 s
  (2f9791). Independent read-only review finding closed; diff check passed with
  existing LF/CRLF warnings. All model calls simulated; no production/deletion.
- Next: bind this source-inventory identity into directory registrations and
  verify that chain when resolving cleanup candidates; then connect existing
  authorized forget transaction with narrow validated targets. Current source
  sidecar alone does NOT authorize filesystem deletion. No cleanup implemented.

## Latest continuation: host-bound result consumers

- Fixed a reproduced host-path bypass: after Runner refused corrupt inventory,
  CLI could still freeze old files as usable and export available evidence.
  verify_saved_step now accepts an explicit ledger, propagates it recursively,
  and checks registration before/after validation. Summary, freeze_review and
  freeze_evidence propagate it; both host CLI consumers pass context.ledger.
  Standalone no-ledger library checks remain explicitly lower-level.
- Review identified a further final-source-read window in freeze_evidence.
  Reproduced at source calls 4 and 6 (e8c603); final per-entry registration checks
  after those source reads now prevent accepting the case. This is bounded
  verification, not an atomic cross-source snapshot.
- Final affected reader/review/evidence/Runner/research CLI suite: 53 passed in
  25.25 s (cfded7). Independent read-only review confirmed the reported gap closed.
  Diff check passed with existing line-ending warnings. No production/model calls.
- Next actual retention work: map registered dependencies to exact Capture
  revision/observation invalidation and integrate managed cleanup. Existing
  Capture evidence reference.ref is receipt_id (capture_eval_adapter.resolve),
  but metric document refs hash the whole reference plus role; do not infer native
  keys from opaque hashes. Research _task_ref hashes adapter/root/task only;
  preserve exact revision binding when designing cleanup. Registry is not delete
  authority. Original full P1-P5 goal remains incomplete.

## Latest continuation: host artifact inventory and bounded reuse checks

- New metrics_artifact_registry records exact execution leaf paths, filesystem
  directory identity (device/inode), and reconstructed source/config dependencies
  under the caller's fixed host send-ledger/artifact-registry. Only fixed artifact
  filenames are admitted. Registration is exclusive, content-free, and not delete
  authority. No output directory scan or deletion is implemented.
- Runner and classification execution register after send reservation but before
  model calls. Registration failure cannot call the model or refund the slot.
  Runner reuse and classification reader check directory/dependency/registry
  consistency before and after their result verification. Old unregistered runs
  are not automatically migrated by those entry points.
- TDD: first registration suite failed (55f3de), then 38 passed (4016e7).
  Reuse-specific tests reproduced missing enforcement (817883); final affected
  runner/classification/dependency/host/research/evidence CLI suite: 60 passed in
  23.28 s (28c73a). Independent bounded read-only review passed. Diff check passed
  with existing LF/CRLF warnings. No production/model/deletion/publish operations.
- Next: connect inventories to exact source invalidation and existing forget
  semantics. Audit other result-consumer entry points (freeze_review and evidence
  export use the lower-level verify_saved_step without a ledger) before claiming
  host-wide enforcement. Standalone execution APIs remain lower-level; this is
  not complete managed retention or original P1-P5 acceptance.

## Latest continuation: human review queue

- Restored original section 8 requirement: all flagged/unknown/unusable cases and
  human disputes/corrections precede at most two cross-scenario normal spotchecks.
  Stable case-ID ordering, omitted counts and non-representative sampling limits
  are disclosed. No changes to quality denominators or original Judge judgments.
- Queue and human panel share one validated revision state. Only controlled
  metadata is rendered; source bodies/model free text remain excluded.
- New tests failed on absent queue first (23 failures, 249675). Related report,
  feedback and evidence suites then passed: 48 in 11.61 s (d718e3). Independent
  read-only review passed for this increment. Full metrics plus Capture Eval
  adapter regression: 380 passed in 76.22 s (636f49), using local Runtime with
  simulated model execution, not real Judge calls.
- Still open: global external-result registration/forget cleanup, on-demand
  evidence usability and full original acceptance. No production/model/publish
  actions this turn. Do not mark the original P1-P5 goal complete.

## Latest continuation: local derived-result dependency registration

- metrics_dependencies builds exact content-free dependency manifests for Eval
  steps and classification. Executors write dependencies.json before model calls;
  readers require exact current-plan/source/config/dependency agreement and reread
  it before reuse. Old results without a record are not automatically migrated.
- Registration failure prevents an Eval model call (tested). Missing/changed Eval
  and classification registrations reject reuse. Fixed artifact names only.
- Latest related dependency/execution/reader/runner suite: 55 passed in 16.85 s
  (f3bc68). Independent read-only review passed. No production actions/deletions.
- This is NOT complete managed retention: external output directories are not yet
  globally registered/discovered by existing hard-forget transactions. Next connect
  directory registration and source invalidation, with scoped synthetic cleanup
  tests. Do not label production content persistence compliant until that works.

## Latest correction: original design forbids bulk content exports

- Re-read authoritative overall design section 10: source/Capsule bodies must not
  be bulk embedded into HTML; content-derived caches without managed cleanup must
  not be persisted. The previous raw evidence.json/HTML feature violated this,
  despite private/opt-in labeling. Do not repeat that completion claim.
- export-review-evidence now writes only evidence-index.json (controlled hashes,
  references and states) and content-free report.html. render --evidence never
  embeds source bodies or unchecked model reasons. freeze_evidence remains an
  in-memory live-verification API, not permission to persist its return value.
- Final related tests: 19 passed in 9.44 s (012d5b), including all-export-file
  content checks. Independent read-only review confirmed the boundary correction.
  Existing user/test artifacts were not deleted. Model-derived
  execution-result registration/forget cleanup remains a separate open requirement.
- Re-read original P2/P3 scope before adding preview/formal adapters: it requires
  correctly identified assessed versions and honest unknown historical fields,
  not an invented parallel full-memory snapshot system. Goal remains original
  P1–P5, including on-demand evidence, retention and authorized production acceptance.
- Prior Skill validator shell session 39008 has now exited successfully (80ee64).

## Latest continuation: source-bound private evidence export CLI

- Added export-review-evidence with fixed host roots, source-map resolver and
  protected new output directory. Generates evidence.json and private report.html
  from saved results/live evidence, never re-executes Judge. Capture and research
  paths tested; unavailable sources remain content-free cases with explicit counts.
- Review found empty research plans misrouted to Capture. Reproduced (101f37),
  fixed empty-case dispatch using source-map schema while retaining strict resolver
  validation, and added zero-call prepare/evaluate/export end-to-end regression.
- Latest affected CLI/evidence/report/host/Skill tests: 24 passed in 14.57 s
  (c09a10). No production reads, installation/config changes or model calls.
- Remaining: richer historical/M2 evidence adapters, managed derived invalidation,
  browser visual and full original P1–P5 acceptance. Mixed-source plan export is
  explicitly unsupported; no output overwrites or Git publication.

## Latest continuation: explicit HTML private evidence drilldown

- render_report evidence= and CLI render --evidence require matching review and
  validate the annex before display. Expandable cases show full original assessment
  JSON, result digests and safe documents/ref/version. Defaults remain content-free.
- Source/model text is escaped, never interpreted as HTML/Markdown. Unavailable
  cases do not expose prior content; private/frozen/not-human-reviewed limits shown.
- Latest affected evidence/report/Skill suite: 24 passed in 6.28 s (429407),
  including isolated escaping and unavailable rendering. Independent review passed.
- Still required: source-bound explicit annex generation CLI, richer evidence/M2
  adapters, managed invalidation and original full P1–P5 acceptance. No production
  reads/model calls/installation/publication. Browser visual acceptance not done.

## Latest continuation: explicit private review evidence annex

- Added metrics_review_evidence freeze/validate APIs. For each usable review case,
  reverify saved steps and live sources, retain bound documents/full assessment
  records, and preserve unavailable cases without content. Default review unchanged.
- Offline validation checks exact review/results/subject/document binding, fixed
  fields and 16 MiB limit. This is private source/model content, not authenticity,
  current permission or automatic forget cleanup. No files/model calls by API.
- Latest related suite: 27 passed in 6.15 s (8842a4), including mid-generation
  revocation. Independent read-only review passed. CLI/HTML and cleanup pending along
  with richer historical/M2 source adapters and original full P1–P5 acceptance.

## Latest continuation: preparation-state coverage in offline report

- render --research-preparation accepts the content-free preparation manifest;
  shared metadata validation checks batch, identity, entries and counts. Displays
  five states, per-reference details and deterministic budget/sampling methods.
- Counts are reference entries, not independent tasks; ready does not mean
  classified/evaluated. No source-body read, no cross-chart inferred success rate.
  Classification still requires full input digest validation (explicit regression).
- Latest affected report/classification/input/Skill suite: 31 passed in 6.93 s
  (cc1a91). Prior full 326 run predates both report coverage increments.
- Remaining original scope includes complete evidence drilldown, richer historical
  evidence/M2 adapters, managed invalidation and full production/human acceptance.
  No real model calls, production installation/config changes or publication.

## Latest continuation: offline research cohort coverage section

- render_report and render CLI accept an optional validated research-cohort.
  Independent section shows selection-state chart, task/version/decision/reason
  details and methods. Does not modify M5 quality denominators or claim complete
  population, current source validity or automatic review-case association.
- Empty/tampered/cross-batch cohorts and offline command behavior tested. Latest
  affected report/review/Skill suite: 17 passed in 3.89 s (8e1628).
- Preparation-stage unavailable/over-budget inputs remain in manifest, not yet
  displayed here. Full evidence drilldown, historical evidence adapters, managed
  invalidation and original P1–P5 acceptance remain required. No production/model
  actions or publication; prior full suite was 326 before this report increment.

## Latest continuation: verified classification export into M5 preparation

- export-classification uses fixed host/ledger and read_classification before
  creating a new private directory. Exports research-cohort.json plus verification
  metadata retaining the complete preparation manifest and point-in-time limits.
- Synthetic end-to-end test passes exported cohort to prepare-research-plan
  without manual labels or another model call. Failed verification creates no
  output; existing output is never overwritten. Independent review passed.
- Latest complete metrics + Capture Eval adapter suite with local Runtime imports:
  326 passed in 50.68 s (70d973), no skips. Model processes remain simulated.
  Explicit Skill validator printed "Skill is valid!", but its shell session 39008
  has not returned an exit code; do not restart it solely for that observation.
  git diff --check passed with line-ending warnings.
- Classification source preparation/execution/verification/export are now linked.
  Still incomplete: richer historical research background/source evidence, M2
  preview/formal adapters, broader M3 evidence, full report drilldown/coverage,
  managed derived invalidation and original P1–P5 production/human acceptance.
  No installation/config changes, real Judge calls or Git publication performed.

## Latest continuation: read-only classification result verification

- Added read_classification: live preparation reconstructs the plan, then verifies
  reservation/start/finish/receipt/result, frozen labels, usage/config and time.
  Missing terminal or conflicting error is rejected. Sources and all artifacts
  are reread before returning; no writes/model calls or authenticity claim.
- Latest affected reader/execution/CLI tests: 26 passed in 11.68 s (c365a1),
  covering malformed artifacts, semantic receipt changes, time inversion and
  source revocation. Independent read-only review found no new concrete bug.
- Still pending: reader CLI/export and downstream cohort handoff; report/evidence/
  invalidation and original full P1–P5 acceptance. No production actions.

## Latest continuation: classification CLI with fixed host binding

- Added prepare-classification-plan and classify-research. Preparation writes
  content-free plan/manifest; execution uses the fixed host ledger, protected
  output checks and native source factory, with consent before body resolution.
- CLI reports actual call attempts and classification_status, including failed
  calls. Neither a successful command return nor classification is a quality
  evaluation. Updated explicit command guidance; no installed Skill changed.
- Native synthetic JSONL -> plan -> fake model -> cohort/artifacts tested. Latest
  related CLI/execution/research/Skill suite: 19 passed in 10.20 s (71d371).
  Independent read-only review found no new concrete bug.
- Still required: verified classification result reader/reuse and cohort handoff,
  other report/evidence/invalidation gaps, original full P1–P5 acceptance. No
  production changes, real model calls or Git publication.

## Latest continuation: bounded classification execution

- Added classification plan/executor: exact scope digest, live preparation and
  configuration checks before/after send, exclusive shared-ledger reservation,
  controlled result/receipt/terminal artifacts and no automatic retry. Empty
  preparations return without model call or reservation.
- Latest affected run: 34 passed in 9.41 s (16be3a), including failed-attempt
  cross-directory resend and empty-input tests. Independent read-only review
  found no new concrete bug; dynamic verification comes from the parent tests.
- Only synthetic data/fake model used. Host CLI binding and verified result reuse
  remain pending, as do other original P1–P5 requirements. No production changes.

## Latest continuation: structured classification gateway payload

- Added classification_payload and freeze_classification_output using the existing
  five-field MetricsGateway contract. Input-only documents, exact label count,
  no extra fields; semantic binding and decision/reason checks remain mandatory.
- Fake-adapter integration verifies the schema and projected evidence reach the
  existing gateway without answer content. No second model adapter was introduced.
- Red missing APIs: 2 failures/9 passes (151580). Latest affected suite: 25 passed
  in 5.09 s (3ed72e). No real model or production configuration changes.
- Still required: authorized execution/CLI with fixed send ledger and live checks,
  remaining report/evidence/invalidation scope and full original acceptance.

## Latest continuation: input-bound research classification contract

- Added metrics_research_classification: validates prepared input digests and
  metadata, builds an input-only intent request, and freezes exact version-bound
  labels into the existing cohort. No answers, quality fields or model calls.
- Missing/duplicate/foreign/stale labels fail; unavailable inputs remain in the
  complete preparation manifest without invented classifications or revisions.
- Latest affected tests: 23 passed in 3.79 s (32940b). Includes tampered inputs,
  manifest changes, exact label membership and unavailable coverage. Initial red
  was missing module; test fixture/reference and insertion mistakes were corrected.
- Still pending: structured model schema and authorized classification execution/
  CLI, live source rechecks, full report evidence and original P1–P5 acceptance.
  Contract hashes do not establish label authenticity or consent.

## Latest continuation: bounded research classification input preparation

- research-inputs prepares at most 100 explicit native references through the
  fixed host and live Capture access gate. No model calls or file writes; stdout
  contains private task input only, not answers, plus a content-free manifest.
- Outside-window and ambiguous task revisions are rejected before content reads.
  Stable ordering and a 2 MiB inputs-array budget preserve every manifest entry;
  input_budget_exceeded omits the body without truncation or losing the batch.
- Independent review identified the former aggregate-budget failure; reproduced
  it and fixed it. Reviewer confirmed closure read-only. Latest affected tests:
  35 passed in 6.85 s (b29ed3). No live Judge, installation or production changes.
- Still pending: authorized semantic classification and versioned label/cohort
  integration, richer historical evidence, complete report/invalidation and the
  original P1–P5 acceptance. Preparation alone is not completed classification.

## Latest continuation: research CLI with fixed host and actual source

- prepare-research-plan and evaluate-research now use configured host roots,
  mandatory CaptureResearchAccess and the same fixed send-ledger. At most five
  native references, no duplicate tasks, exact selected-task membership required.
- Added native completion/cohort delivery-time equality after a failing test
  (7078b7). Execute consent is checked before research source resolution; results
  retain per-entry failures and real call-attempt accounting. Existing Capture
  entrypoints retain their previous source/resolver.
- Actual host -> synthetic JSONL -> cohort/plan -> mocked Judge -> report/reuse
  integration passes. Independent bounded review found no new concrete bug.
- Latest complete metrics + Capture Eval adapter run loaded local Runtime packages:
  282 passed in 29.01 s, no skips (d57ba5). Model subprocess integration was mocked,
  not a real API call. Explicit Skill validates; git diff --check passes.
- Updated repository Skill command guidance and metrics docs, not installed copies.
  Still required: authorized research classification/input preparation, richer
  historical background/source evidence, full case/method display and managed
  invalidation, original P1–P5 acceptance and separately authorized production work.

## Latest continuation: Capture access gate and independent source review

- Added mandatory CaptureResearchAccess to CodexResearchSource. Before reading,
  after loading and before return it reloads exclusion policy and healthy Capture
  snapshot, rejects suppression tombstones/redacted or excluded receipts and
  source quarantine/conflicts. Missing control roots/config deny; no receipt is
  required, so the independent sample still includes uncaptured tasks.
- Real synthetic revision/observation forget operations prove rereads are denied;
  live task exclusion denies before content read, and exclusion added during read
  prevents return. No production control files changed.
- Independent reviewer found unsupported input omission, foreign-turn inclusion
  and conflicting analysis/final flags. Reproduced all three (81a2fb), fixed and
  tested. Follow-up found config check/load race; reproduced after final path check
  (51ffe7), then replaced default-fallback loader with required strict YAML read.
- Broad access/source/plan/cohort/forget regression: 77 passed (c6628e) before final
  race tests. Latest affected research tests: 38 passed in 4.31 s (52b9f4). Counts
  are separate runs, not additive. Reviewer test execution was not available;
  dynamic evidence comes from parent runs.
- Remaining: production consent/scope host wiring and research CLI, historical
  background/source and classification, report evidence/invalidation and full
  original acceptance. This gate is not managed deletion of derived artifacts.

## Latest continuation: native Codex research evidence source

- Added CodexResearchSource over explicitly bound native RevisionRefs. Reuses
  CodexSourceAdapter target-turn identity/completion/file-consistency validation;
  exposes describe_task metadata and task input/unique explicit final documents.
- Source/version/policy/transform binding is checked on every prepare. No current
  memory, tool output, reasoning or subagent content is projected. Missing or
  conflicting final, future output, known unsafe text and size overflow fail.
- A new test exposed native source={subagent:...} keys not being detected by the
  shared value-only provenance gate. The new adapter now excludes that shape;
  existing Capture safety code was not changed.
- Red missing module (cfe69c); transient policy serialization error corrected via
  dataclass asdict. Final 47 source/Codex/plan/cohort tests pass in 1.60 s (b919f4),
  including actual synthetic JSONL -> cohort -> research plan resolution.
- Still pending: production authorized-scope/forget-policy wiring, historical
  background/source-role extraction, research intent classification and CLI.
  No real session reads, Judge calls, installation/configuration or publication.

## Latest continuation: research plan and execution boundary

- metrics_research_plan maps validated selected task references/revisions to
  research_relevance cases. Source maps bind batch/cohort membership and cannot
  redirect even after rehashing. No source content persisted in plan/map.
- Input builder checks role allowlist and complete task input/output; current
  memory cannot substitute historical background. Live resolution compares full
  case/content identity before execution and reuse. Source authenticity remains
  the adapter's responsibility, not something these hashes establish.
- Red: six tests failed for missing module (c8c12e). Latest 35 related tests pass
  in 4.86 s (10ec18), including real runner -> frozen review -> HTML with mock
  Judge, reuse without a second send and rejection after source unavailability.
- Production historical-session source adapter, classification sourcing and CLI
  research evaluate remain pending; do not claim these synthetic tests close M5.
  No real Judge, production reads/configuration, installation or publication.

## Latest continuation: independent M5 cohort and explicit CLI

- Added metrics_research_cohort with strict caller-classification metadata,
  task/revision deduplication, half-open batch window and deterministic first-five
  eligible selection. Keep excluded, ambiguous, unavailable, outside-window and
  capped rows. No Recall field influences selection; no full-population claim.
- LLM classifier configuration/authorization references are caller supplied and
  unverified, separate from quality Judge output. Human method is supported but
  not required. No session content read or model call occurs in this module.
- research-cohort CLI writes an exclusive metadata-only research-cohort.json;
  docs/metrics-review.md documents fields and method. It does not yet discover or
  classify authorized sessions, resolve historical content or create M5 plans.
- Red module absent: 8 failed (be4301); red CLI absent: 1 failed/8 passed
  (c0b712). Final cohort/eval/input/batch/host tests: 59 passed in 1.50 s (cff62f).
- Next: source-backed selected-task resolution and research plan/evaluate wiring;
  keep original P1–P5 scope including remaining reporting/invalidation/acceptance.
  No production configuration, real Judge, installation, commit or push.

## Latest continuation: complete preview return boundary

- Added agc.admin capture_preview: bounded complete Markdown and observation ID
  validation, normalized preview and returned-representation digest. It neither
  initializes Memory Root nor writes formal memory/review receipts. Observation
  grounding remains unchecked and human confirmation unknown.
- Opt-in business records distinguish runtime_returned from unknown; no preview
  body is persisted. Failed validation never records delivery; unavailable metrics
  cannot block successful preview return. This is not proof of UI visibility.
- Repository formalization/notification/tool-contract references describe the
  operation and compatibility fallback. Installed production Skills unchanged.
- Fresh combined metrics/admin/write/Skill regression: 289 passed, 1 skipped in
  29.12 s. Skip is optional agent_eval_codex import; no real Judge invocation.
  A test-only Windows environment-length issue was reproduced and fixed by short
  parametrization IDs. git diff --check passed before this documentation update.
- Full P1–P5 remains open: independent research/M5 source integration, remaining
  provenance and case evidence, managed invalidation and production acceptance.
  No install, production configuration change, commit or push performed.

## Latest continuation: request-source provenance without false confirmation

- Inspected actual Capture review/notice and confirm handlers. Notice stores
  readiness, not actual preview delivery; ObservationSource is caller-supplied
  ref/revision/content_hash, not proof of human confirmation. Do not set task or
  confirmation fields to verified just because an observe/confirm request exists.
- Business evidence v2 adds request_source with opaque source/ref revision and
  digest plus caller_supplied_unverified. Invalid/missing input stays null; source
  plaintext is not recorded. v1 remains readable without fabricated fields.
- Red missing provenance (`74636f`); final business/report/write regression:
  40 passed in 5.39 s (`fa3705`), temporary data only. Preview delivery and actual
  confirmation proof remain unknown/unimplemented, not silently satisfied.
- Repository legacy review skill directories contain no files in this checkout;
  locate the actual preview producer before instrumenting delivery. Continue
  original source coverage/report/acceptance work. No installation or live call.

## Latest continuation: scope audit and write-time memory versions

- Re-read original P1–P5 requirements. A new general retry-grant system was an
  implementation suggestion, not an explicit acceptance requirement. Do not
  build it as a prerequisite: bounded attempts, failure retention and no infinite
  retry remain required and implemented. Keep the full original metrics scope.
- Store `_apply_mutation` returns the digest of normalized UTF-8 text only after
  commit; create/evidence/replace/transition propagate it via optional
  MutationResult.written_content_digest. No after-the-fact disk reread. Duplicate
  source returns no new written version. Existing transaction behavior retained.
- With metrics enabled, write responses expose memory_version and business
  evidence records written_content identity. Disabled response shape unchanged;
  old records remain readable. Confirmation/task provenance is still unknown,
  so this is not proof of user approval or complete save-chain coverage.
- Red real saved record stayed unknown (`c738a0`). Final store/write/business
  regression: 49 passed in 6.08 s (`25fccb`), including actual temporary file hash
  equality, duplicate handling and disabled response behavior. No production data.
- Remaining original requirements: preview delivery/confirmation and task evidence,
  independent research cohort and source adapters, fuller field/case review,
  invalidation and complete original acceptance. Production authorization later.

## Latest continuation: frozen M4 execution history

- Review v3 freezes `execution_history` from the supplied directory. The new
  strict validator checks field allowlists, plan/entry membership, timestamps,
  ordering and first/latest/count consistency. v1/v2 remain readable.
- HTML M4 shows first, latest finished and unfinished/total per case/step, with
  explicit source coverage and selection methods. No highest-score selection;
  not a claim that retries across unknown directories were discovered.
- Red missing history (`515f1a`). Final history/host/review regression: 30 passed
  in 5.56 s (`c23ead`), synthetic executions. No browser visual acceptance yet.
- Full goal still open: retry authorization/history collection, remaining M2/M5
  sources and P2 evidence, managed invalidation, full report/production acceptance.
  No production model call, installation or push in this continuation.

## Latest continuation: fixed host binding and Capture evaluate CLI

- `metrics_host.py` reads strict per-user metrics/host.json and fixed sibling
  send-ledger, independent of report output and Capture model settings. Missing
  ledger is not recreated; no ledger CLI/env override. Output cannot be placed
  under configured memory/session/host roots. Host setup is not installed yet.
- `prepare-capture-plan` now constructs the production CaptureMetricsSource and
  MetricsGateway through host factories and writes reference-only plan/map.
  `evaluate` checks same batch/consent, runs/reuses steps, freezes v2 review and
  writes unique run/review/report artifacts. Response includes per-entry status
  and model call attempts. Successful artifact production is not eval success.
- Tests inject synthetic source and gateway into otherwise real host/CLI/runner/
  filesystem/report flow. Red missing host (`c0d981`); final 28 relevant tests
  passed in 3.70 s (`880d99`), including invalid consent, fixed ledger missing,
  output isolation and repeat execution with zero additional calls.
- Skill/reference updated to actual Capture-only evaluate availability. No
  production host config, installation, real Judge call or push. Still open:
  explicit retry grants/history, other source kinds and evidence completeness,
  managed invalidation, UI acceptance and full production acceptance.

## Latest continuation: Capture plan map and distinct Eval cutoff

- `metrics_capture_plan.py` prepares plan + native Capture reference map only;
  no Capsule or candidate body in persisted planning artifacts. Resolver rebuilds
  the Capture projection on each access and matches the frozen case identity.
  Tests use an injected synthetic source; the existing CaptureMetricsSource is
  the intended production bridge, but host/CLI wiring is not yet implemented.
- Found a real integration gap: review freezing used the business source cutoff
  for Eval attempts, which can exclude assessments run after that cutoff. New
  `agc.metrics-review.v2` retains the source cutoff and adds evaluation_cutoff
  (default current UTC). HTML methods expose both; human feedback must follow
  both. Reader retains v1 compatibility, which keeps its original single cutoff.
- Reds: source-plan module (`f9f71c`), missing evaluation cutoff (`98c819`). Final
  related tests: 34 passed in 5.60 s (`7547ea`), including old schema compatibility
  and future results excluded by an earlier Eval cutoff. No actual model calls.
- Still open: fixed host ledger, production source/gateway construction and CLI
  evaluate/freeze orchestration, explicit retry grants, other source kinds,
  managed invalidation and complete acceptance. No production writes/install/push.

## Latest continuation: bounded plan runner and shared send reservations

- `metrics_runner.run_plan` composes verified same-directory reuse, fresh safe
  source resolution, dependency ordering, single-step execution and persisted
  result verification. Existing invalid/insufficient attempts do not silently
  retry. Changed evidence prevents reuse. Keyboard interrupts remain interrupts.
- A gateway wrapper reserves each plan/entry before sending in a shared private
  ledger; exclusive files arbitrate concurrent output directories. Failed calls
  consume their reservation. No automatic slot refund or retry authorization.
- Red missing runner (`436043`). Final related execution/reader/freeze tests:
  35 passed in 4.38 s (`2ca930`), including concurrent output roots sharing one
  ledger and changed-source cache invalidation. Synthetic gateway only.
- Still an internal API: a trusted production host must bind the stable ledger
  path and actual user consent. Selecting a fresh ledger must not become a bypass.
  Explicit reauthorization/retry history, CLI evaluate, other source bridges,
  full acceptance and production installation remain open. Skill correctly still
  says no evaluate CLI. No live model, installation, memory writes or push.

## Latest continuation: explicit metrics review Skill

- Added `skills/agc-metrics-review/` with SKILL.md, explicit-only openai.yaml,
  and a self-contained command/feedback reference. Current implemented commands
  are prepare/plan/render/review. The Skill explicitly reports missing evaluate
  orchestration instead of calling internal executor functions as a workaround.
- Tests execute documented review -> render commands using synthetic frozen
  artifacts and assert the original review is untouched. The initial example
  exposed relative revisions-dir rejection; CLI now makes it absolute without
  resolving away reparse points before the private-root checks.
- Red: missing Skill (`e307a6`); workflow failure (`9eb4f0`). Final relevant tests:
  22 passed in 3.70 s and quick_validate valid (`46a794`). Validator requires
  Python UTF-8 mode on this Windows host; no global encoding changes made.
- This is repository source, not an installed/discoverable production Skill.
  No independent agent behavioral test, real user review, model call, installation
  or push performed. Full executor/source/authorization and acceptance work remains.

## Latest continuation: append-only human feedback and rerender

- `metrics_review.py` binds feedback to frozen report/case/result digests with
  accepted/corrected/disputed, timestamp and opaque feedback provenance. Strict
  controlled corrections are projected separately; original Judge data stays
  unchanged. Sequential exclusive JSON files preserve revision links; gaps,
  tampering and reversed timestamps reject further appends. A partial write
  remains an explicit invalid history, not silently repaired.
- CLI `review` consumes an explicit feedback JSON and existing private revisions
  directory. `render --review ... --revisions-dir ...` displays initial judgments
  separately from latest human status and corrected M2/M5 arithmetic. The report
  revision digest binds the human history. No model, memory writes or production
  changes. Caller provenance is not authentication or proof of user consent.
- TDD reds: missing module (`a047ea`), CLI (`3d519c`), rerender (`28108f`). Related
  final regression: 26 passed in 4.07 s (`6703fc`), synthetic cases only. No browser
  visual acceptance or real user-feedback acceptance yet.
- Still open: explicit Skill, executor orchestration/global consent accounting,
  remaining evidence sources/invalidation and full real acceptance. Full goal
  not complete. Human sidecar CLI does not automatically create a rendered file;
  the explicit workflow must invoke render with a fresh output path.

## Latest continuation: frozen review HTML and render CLI

- `metrics_report.render_report(..., review=...)` validates a same-batch annex
  and displays M2 collected/zero strata, stage/subject-specific fractions and
  uncertainty; M4 planned cases vs steps and usable-case coverage; M5 misleading
  risk before relevance, with separate unreviewed status. Five method sections
  remain, now describing the frozen assessment source and limitations.
- `render --review` reads bounded strict JSON, rejects duplicate keys and invalid
  annexes before output creation, and retains exclusive output/no-model behavior.
- TDD red: four missing-interface failures (`422877`). Focused initial green:
  16 passed (`74a69a`). No production reads, real Judge, installation or push.
- Final metrics regression: 186 passed, 1 skipped (`f303bc`); optional local
  cross-repository adapter integration was not loaded in this run. No browser
  visual acceptance performed. Research two-axis rendering is asserted as well.
- Full goal remains open: explicit review Skill/human revisions, complete CLI
  orchestration/authorization consumption, remaining evidence sources and real
  acceptance. Frozen projections are not current source-validity attestations.

## Latest continuation: content-minimized frozen review data

- `metrics_review_batch.freeze_review` binds validated batch/plan/cutoff and
  verified execution projections; `validate_review` checks exact fields/case
  identities/schema/digest; `review_metrics` recomputes M2/M4/M5 offline.
- Frozen rows contain controlled labels, result digests, stage/subject identity
  and unreviewed status, not source statements, claim text or Judge reasons.
  M2 strata and subject identities stay separate; null denominator is not success.
  M5 relevance/misleading/human status remain distinct. Hashes are not signatures.
- Source status is frozen observation, not permanently live validity. Re-render
  must not imply current revocation verification; managed invalidation still open.
- Red: missing module 4 failures (`f51e53`). Final all metrics and existing Capture
  resolver regression: 195 passed in 10.86 s (`c2fa46`), synthetic temporary
  executions and simulated model, local Runtime sources available.
- Data layer only: HTML/CLI annex consumption, method charts, case drilldown and
  human corrections still pending. M4 detailed histories remain in execution
  artifacts; frozen history visualization not yet done. Full goal remains open.

## Latest continuation: persisted execution verification to M4

- `metrics_result_reader.py` bounds/strictly reads existing files, rejects linked
  paths and duplicate JSON keys, checks start/terminal identity and domain result,
  reconstructs authorized input from a resolver, checks receipt configuration,
  usage, input/result digest and dependent result. No files are modified.
- M2 dependency must have completed before alignment began. Current source
  unavailable/changed/revoked is unchecked; invalid saved output/receipt is an
  evaluation error. No receipt or orphan result can establish usability.
- `summarize_execution_directory` wires this verifier into M4. It still needs a
  caller-owned safe source resolver; no model call, source repair or cache rewrite.
  File consistency is not proof of authenticity or Judge semantic accuracy.
- Reds: missing module 9 failures (`b15189`); temporal mismatch test exposed
  false acceptance (`e04119`). Final all metrics plus existing capture resolver
  suite: 189 passed in 8.98 s (`b62691`), local Runtime source, synthetic gateway
  and temporary artifacts, no production execution.
- Remaining: frozen report integration, human revisions/Skill, other source types,
  managed derived invalidation, authorization consumption and P2/P5 acceptance.

## Latest continuation: Capture source bridge

- `CaptureMetricsSource` reuses actual AGCCaptureEvidenceResolver; it projects
  verified capsule and candidate observations into separately bound documents,
  stage/version/role subject and collected/zero case. Native source digest is
  rechecked. Bundles are private in-memory material, not report/Trace payloads.
- `resolve` re-reads and compares frozen identity; `revoked_refs` invalidates both
  derived refs on missing/changed/unavailable input, without asserting the cause
  was intentional forgetting. No positive liveness cache. Call on reuse as well.
- Red: 6 missing-module tests (`63d1f5`). Final metrics plus existing Capture
  resolver tests: 178 passed in 7.40 s (`c1b396`), local Runtime source available,
  all synthetic source adapters/temporary MemoryStore, no real model.
- Integration covers Capture resolver -> input -> execution; unavailable source
  blocks a second invocation before gateway and before output creation. Changed
  capsule hash invalidates both refs. No source scan, Census rebuild or production
  reads. Existing resolver snapshot cost retained; not optimized speculatively.
- Remaining: preview/formal-memory/research evidence sources, managed derived
  artifact invalidation, consent consumption, attempt/result reader+verifier,
  report/Skill/human-review integration and production acceptance. Goal not done.

## Latest continuation: explicit Codex gateway binding

- `MetricsGateway` now defaults to the real optional CodexStructuredJudge and
  accepts explicit absolute command file paths only. Command file content,
  adapter source/loaded method fields and gateway source identify the binding;
  before/after checks reject detected changes. No PATH fallback or auto-discovery.
- Independent default gpt-6-astra/medium/120s passes explicitly to the adapter.
  Observed configuration is copied only from its receipt, never fabricated.
- TDD: 6 missing-module failures (`7955d1`). Real adapter integration caught
  unstable marshal serialization after first method execution (`9d0a32`): bytecode
  stayed equal while serialization changed. Replaced it with explicit stable code
  fields, retaining source/command hashes. This is identification, not atomic OS
  attestation or signature verification.
- Final all metrics regression: 158 passed, 3.29s (`7cbaa1`), local Runtime source
  imported with contracts bootstrap. Real adapter/executor integration included;
  only subprocess.run mocked, no model invoked. Tests under fresh tmp_test.
- Still pending: safe resolver, consent consumption scope, attempt reader/verifier,
  reports and remaining P2/P4/P5. No production install/config change or push.

## Latest continuation: single-step execution artifacts

- Added `metrics_execution.execute_entry`: checks plan consent digest, trusted
  gateway configuration, input bindings and revocation callback, then reserves an
  exclusive entry directory and fsyncs started.json before invoking the gateway.
  Result/receipt/finished are separate exclusive files; no automatic retry.
- Domain output is checked against actually sent refs, then frozen. Requested and
  observed configuration remain separate; usage is validated. Post-call revocation
  prevents assessment persistence. KeyboardInterrupt leaves only the start.
- Fixed error metadata never copies exceptions. A receipt write failure may leave
  an orphan result file but terminal is evaluation_error with no result digest;
  readers must not accept an orphan as success. Failed start write means no call.
- TDD red: 8 missing-module failures (`01606c`). Latest all metrics tests:
  151 passed in 3.31 s (`3afd1f`), synthetic gateway, no cache, fresh tmp_test.
- Gateway is a trusted injected interface, not the real Codex binding yet. Root
  exclusivity prevents repeats only within that chosen root; host-wide consent
  consumption, real adapter/binary identity, safe resolver and result verifier
  remain pending. No production execution or installation is enabled.
- Next: real gateway binding, attempt reader/verifier and report integration;
  preserve remaining P2/P4/P5 requirements. No commit or push.

## Latest continuation: M4 plan/attempt summary

- `metrics_eval_summary.py` separates planned cases/model steps, builds scenario
  statuses and preserves first, last finished and unfinished attempt histories.
  Exact retransmissions deduplicate; conflicting attempts do not use last-wins.
  Cutoff, future and invalid records remain visible; empty plan ratio is null.
- Stored completion is unchecked without a result verifier. The verifier must
  check actual schema/identity, execution receipt and live evidence. Synthetic
  injected verdicts in tests prove arithmetic only, not real technical usability.
- Both M2 steps must be usable and selected alignment must bind the selected
  required-claims digest, else conflict. Retry success does not erase prior error.
- Red: missing module (`1c9470`), dependency contract (`f4fd13`). Final all metrics
  regression: 139 passed in 3.03 s (`1971a0`), no cache, fresh tmp_test directory.
- Pending: real attempts/verifier/executor, report consumption, remaining P2/P4/P5.
  No production access, model call, installation, commit or push.

## Latest continuation: step-specific Judge inputs

- Added `metrics_judge_input.py`: built-in v1.1 profiles/instructions/schema
  identities and `build_input`. Stage/version/evidence roles bind subject_digest;
  resolved documents bind exact ref/version/role/content digest. Duplicate,
  missing, modified, revoked or foreign inputs are rejected.
- Required-claims payload contains only safe_input evidence and refs; no candidate
  content/refs, stage, version or collected/zero tag. Alignment requires a valid
  same-plan frozen reference that cites only the prior safe input. Research
  payload never fills missing historical background and requires delivered output.
- Missing candidate artifact is not zero. A valid empty candidate artifact must
  still exist. Hash/role checks do not establish authenticity or source authority;
  caller must resolve authorized safe material and supply fresh revocation state.
- Initial red: 11 missing-module failures (`1c3e6c`); later missing-candidate
  test caught acceptance (`981561`). Full metrics suite: 129 passed in 2.76 s
  (`a8d052`), synthetic cases, no cache and fresh tmp_test basetemp.
- Pending: executor binds actual executable/adapter identity, authorization,
  resolver, attempts/outcomes and persistence; M4/report consumption; remaining
  P2/P4/P5. No real Judge, production changes, install, commit or push.

## Latest continuation: generic structured Judge adapter

- Dependency repository now exports CodexStructuredJudge/StructuredJudgeOutcome.
  It shares existing process transport and host checks, accepts caller-owned
  schema/instruction, binds configuration identity, rejects schema references,
  and preserves old CodexJsonJudge scoring behavior. No core schema/DB changes.
- Local schema keeps uniqueItems, while the host-facing copy omits it based on
  existing response-format compatibility evidence. Actual host acceptance remains
  unverified; private-text guard is retained and may constrain domain phrasing.
- New structured receipts require completed lifecycle, reject item errors and
  duplicate JSON fields. Output is structured data, not JSON stuffed into strings.
- Runtime adapter suite: 34 passed (`853245`), synthetic process fixtures, no
  real Judge. Windows venv timeout-fixture orphan was specifically cleaned up;
  final run used base Python for fixture children and passed in 4.51 seconds.
- AGC has NOT yet bound this adapter to authorized execution, evidence resolver,
  result storage/M4 or reports. That is the next integration step. P2/P4/P5 remain
  incomplete. No production settings, installation, commit or push.

## Latest continuation: AGC domain assessments

- Added `metrics_assessment.py`: strict schemas for required_claims,
  align_candidates and research_relevance; case citation membership, unique claim
  IDs, complete required-claim alignment, uncertain-reference exclusion, M2
  single-case counts and M5 misleading-first label. Semantic deduplication and
  truth remain Judge/human judgments, not claims of this validator.
- Domain result binding records plan/case/entry, schema identity, execution key,
  dependency result digest, result digest and detached content. Wrong plan/step,
  schema or modified dependency is rejected. Unresolved evidence stays unchecked,
  execution receipt absent, human review unreviewed. These records alone MUST NOT
  be counted as usable judgments. Content is private derived data, not Trace data.
- Declared jsonschema runtime dependency rather than relying on incidental test
  environment packages. No installation performed.
- Red: 13 missing-module failures (`1b233a`); then 6 missing-binding/dependency
  failures (`6dfd8d`). All metrics regression: 114 passed (`b2815e`), repository
  Python, `tests/test_metrics_*.py`, no cache, fresh tmp_test basetemp.
- Still pending: real adapter structured output, step-specific blind inputs,
  authorized execution/receipts/resolver and live revocation checks, M4 outcomes,
  report aggregation/integration and human revision UI. Not a complete P3.
- No production access, model call, install, branch change, commit or push.

## Latest continuation: offline evaluation plan CLI

- `metrics_cli plan` consumes explicit frozen batch/cases/judge/rules files and
  writes an exclusive new plan directory. No execution or production access.
- Input validation rejects duplicate JSON fields, oversized inputs and tampered
  batches before creating output. Existing output is preserved.
- Red: missing command (`7584ed`); boundary tests then caught duplicate/oversized
  acceptance (`25c8e4`). Green: all `tests/test_metrics_*.py`, 95 passed (`88ef55`),
  pytest with no cache and fresh tmp_test basetemp. Synthetic agent-local only.
- Runtime adapter regression: 22 passed (`ced4c4`), including absent host effort
  remaining unknown. Local contracts source bootstrapped without installation.
- P3 remains partial: structured output, evidence resolution, actual adapter binding
  and execution are not done. Remaining P2 bindings and P4/P5 also remain open.
- No install, real Judge, commit or push. Next: structured domain assessment path.

## Latest: service-boundary metadata and frozen report

- `metrics_business.py` wraps read/write/admin dispatchers for fixed operations
  when `AGC_METRICS_EVIDENCE_DIR` is present. Real response content is preserved;
  metadata failure adds a fixed warning. Capture and normal service files are
  separated using a business child directory.
- Records preserve opaque returned IDs/representation hashes, observation linkage,
  response state and separate write/review-receipt outcomes. Actual use, preview
  delivery, task/confirmation/Trace/configuration identity and saved file versions
  remain unknown. This is not completion of all P2 evidence requirements.
- Explicit `--business-dir` freezes records in v3/p2.2; v1/v2 remain supported.
  M1 service groups are separate from the Capture cohort and never summed as
  Capture successes. No production reads, installation, Judge, commit or push.
- TDD: initial 6 expected failures (`9fe0ce`), then two real-shape/status failures
  (`729a39`) before fixes; report integration two failures (`f748d4`) before wiring.
- Service command: repository Python `-B -m pytest tests/test_metrics_business.py`
  `tests/test_catalog_and_read.py tests/test_write_service.py tests/test_admin_service.py`
  `tests/test_capture_review.py tests/test_capture_review_notification.py`
  `tests/test_recall_activation_gate.py -q --tb=short -p no:cacheprovider`, fresh
  tmp_test basetemp. `b575d3`: 77 passed, exit 0.
- Metrics command: same flags, suites metrics_business_report, metrics_business,
  metrics_attempts, metrics_batch, metrics_compute, metrics_collect, metrics_report,
  metrics_evidence. `29cdab`: 76 passed, exit 0. These overlap; do not add counts.
- Agent-local synthetic verification: actual temporary MemoryStore write/get and
  real files included; injected handlers test failures. No model/provider acceptance.
- P3 source inspection (`2304af`) confirms CodexJsonJudge lacks effort and domain
  structured output. Runtime worktree has pre-existing edits; none changed here.
  Next: independent Judge/config/plan identity, bounded generic adapter extension,
  domain assessment, explicit review artifacts and remaining P2 bindings.

## Latest continuation: independent attempt reports

- `prepare --attempts-dir` now freezes content-minimized independent operation
  rows as `agc.metrics-batch.v2` / `agc.metrics-p2.1`. No argument keeps v1.
- M1 uses a business start cohort, retaining Trace cohort diagnostics separately.
  M3 samples at most ten independent attempts and checks identity/start/terminal;
  missing input is unchecked, absent matching events in a readable snapshot are
  not_observed, and contradictions are conflicts. No full coverage percentage.
- New assertions failed before implementation (`eefb2b`, five failing tests).
  Expanded missing-source field test caught a false absence label (`79021a`);
  corrected it to unchecked without weakening the assertion.
- Final command: repository virtualenv Python `-B -m pytest`
  `tests/test_metrics_attempts.py tests/test_metrics_batch.py tests/test_metrics_compute.py`
  `tests/test_metrics_collect.py tests/test_metrics_report.py tests/test_metrics_evidence.py`
  `-q --tb=short -p no:cacheprovider` with a fresh tmp_test basetemp.
  Output `3de631`: 63 passed, exit 0. `git diff --check` exit 0 (`7218b5`).
- Trust remains agent-local, synthetic inputs, no Judge/provider/production run.
  Source metadata and actual file bytes were tested, not mocked collector counts.
- Full objective remains active. Remaining: review/save/Recall and independent task
  evidence, safe resolver/forget linkage, independent Judge/profile/plan/assessment,
  explicit review Skill and human revisions, full HTML presentation and authorized
  production acceptance. Do not mark completion based on this Capture-only slice.

## P2 Capture boundary continuation — 2026-09-11

- Implemented `metrics_evidence.py`; integrated opt-in independent attempts at
  `capture_cli._run_runner`; Trace now accepts matching preallocated IDs. Existing
  no-opt-in response behavior and optional Trace semantics remain unchanged.
- Scope and exclusions are in the requirement's P2 section and
  `../../docs/metrics-review.md`. No production enablement, Judge, install,
  commit or push. Reporting ingestion and review/save/Recall evidence remain next.
- Test-first evidence: 11 new recorder tests failed for missing module; then all
  11 passed (`4f35ba`). Five integration tests failed before wiring (`057637`).
  New duplicate-field test failed before strict JSON parsing (`b2a8ed`).
- First regression command: repository virtualenv Python, `-B -m pytest`
  `tests/test_metrics_evidence.py tests/test_capture_trace.py tests/test_capture_cli.py`
  `tests/test_metrics_batch.py tests/test_metrics_collect.py tests/test_metrics_compute.py`
  `tests/test_metrics_report.py -q --tb=short -p no:cacheprovider`, isolated tmp_test
  basetemp; 89 passed, exit 0 (`9cf193`).
- After duplicate-field rejection and portable reparse-point check, reran the three
  evidence/Capture suites with `-k 'not scan and not census and not probe and not
  activation and not exclusion and not junction and not configured'`: 45 passed,
  12 deselected, exit 0 (`c96795`). Deselected scanner/configuration tests passed
  in the earlier full regression; this is not an additional 45 unique tests.
- Executor/trust: local assistant execution, isolated synthetic fixtures, no CI or
  independent reviewer acceptance. Existing assertions were retained. New recorder
  tests use real files; CLI tests replace Runner/model execution, Trace contract
  tests use the existing fake provider. No actual model or deployed Trace tested.
- Unknowns: production overhead (two fsynced files per opted-in invocation),
  source/configuration identity, all-process completeness and source-file tamper
  authenticity. Not claimed as accepted limitations or verified coverage.


- flow_id: agc-metrics-upgrade-v1
- updated: 2026-09-11
- trust_level: agent-local; no CI or independent reviewer acceptance
- scope: P1 offline implementation, not the complete metrics upgrade

## Changed

Five standalone metrics modules implement allowlisted metadata projection,
timezone-aware windows, content-minimized digest-bound batches, visible Capture
status/conflict accounting, current-receipt/Trace linkage, stored Eval metadata,
and offline HTML with methods. `agc-metrics` entry point added to pyproject.
Source paths are explicit; no Capture/Recall/production configuration changes.

## Verification provenance

Executor: current development agent through local command tools, Python 3.13
repository venv / pytest 9.1.1. All fixtures synthetic and tmp files under the
user-designated common test root. No real model or production memory calls.

- RED: 22 tests failed because modules did not exist, before implementation.
- Boundary RED: 7 failed / 27 passed; caught missing strict loaded-schema checks,
  empty-state distinctions, receipt conflicts, source identity and demo labeling.
- Further RED: 2 failed / 10 passed; caught missing failure-code aggregation and
  malformed-only input being called an empty healthy source.
- Final command: `python -B -m pytest tests/test_metrics_batch.py tests/test_metrics_compute.py tests/test_metrics_collect.py tests/test_metrics_report.py tests/test_cli_contract.py tests/test_capture_trace.py tests/test_eval_cli.py -q -ra --tb=short -p no:cacheprovider --basetemp <isolated-test-directory>`.
- Raw execution result: tool command chunk `093577`, exit 0, **64 passed in 3.70s**.
- Test integrity: new functions and synthetic fixtures changed together. Tests
  assert counts, digest rejection, source isolation, raw-text absence, conflict
  handling and deterministic re-rendering against real temporary SQLite/files.
  No mocked Judge/store was used to declare content or production success.
- Headless Edge check: 1280px and 375px layouts had no horizontal overflow;
  five method expanders, zero page errors, zero external page requests. Tool
  chunk `b79d03`. Initial bundled Chromium was absent; used installed Edge in an
  isolated temporary profile, without installing a browser or using user profile.

## Limits / next gate

The report copied into the collaboration workspace is explicitly **synthetic**,
not a new production baseline. Source permissions were not bypassed. Existing
historical baseline was not regenerated; unit scenarios cover its cross-window
and item-versus-run denominator distinctions, not all historical inputs.

P1 metadata-only limitations: no complete Trace digest validation, no independent
historical business manifest, no planned Eval denominator or content evaluation,
no M5 task population, and no automatic revocation update for exported static
metadata. No large-store performance or production activation acceptance.
These are disclosed implementation boundaries, not user-accepted proof of value.

Next: user review of P1 and explicitly scoped production read acceptance if
desired; then P2 business evidence linkage. No installation, commit or push of
these new changes yet. Do not resume old RSI experiments or the blocked review
automation as part of metrics development.
