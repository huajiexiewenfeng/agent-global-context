# AGC metrics: P1 offline report

## M3 implementation-version comparison

New AGC Capture root-start events include the AGC implementation version. The
metrics projection retains only a validated version label and uses a versioned
transform suffix `.trace-version1`. Existing frozen transforms remain readable;
their missing version is not replaced with today's installed version.

The field matrix compares the version only when the single Trace start matches
the independent business attempt's start time. A differing version is a conflict;
a missing label is unchecked. This is metadata consistency, not proof of the
executed binary or source authenticity. Configuration and result-reference
verification remain unavailable without additional bound evidence, and no full
coverage percentage is claimed. HTML displays the field states directly.

## Managed report retention and unfinished attempts (implemented, not installed)

Quality evaluation, classification export and evidence export now register their
fixed report files in the host's `report-registry`, bound to the plan's source
receipts and original output-directory identity. Live source validation and
publication share the existing root write lock with Capture forget. Missing or
revoked sources, or absent source bindings, stop a new managed export; no fallback
to a newly published stale snapshot. Offline `render` remains an unmanaged static
copy, does not check live access and must not be presented as current evidence.

Reports are built in memory without source bodies. Registered internal
`.<filename>.agc-pending` files are written and synced, hash-checked, then published
with an exclusive same-directory hard link. This requires filesystem hard-link
support; failure is explicit, with no overwrite fallback. Incomplete staging
files can be removed by the existing committed forget intent. Final report files
must still match their registered hashes; user edits cause deferred cleanup, not
silent deletion. Other files and externally copied reports are not removed.
The whole related report bundle is removed when any bound source is forgotten;
it is not partially recomputed into a new quality claim. Content-free dependency
metadata remains for audit. No arbitrary directory scan or recursive deletion.

Evaluation/classification holds an OS-owned `.attempt.lock` from before started
metadata until all terminal/error writes finish. An unfinished attempt becomes
cleanable only with a valid, exclusively acquirable lock. Active locks and legacy
missing/invalid locks remain pending. Cleanup holds that lock and revalidates
files; it never fabricates completion or usage. Recovery still occurs on a later
explicit `capture_forget`, not a new background scheduler.

These guarantees cover registered host outputs and cooperating writers, not
malicious external file mutation or recalled user copies. Production rollout,
original P1–P4 end-to-end acceptance and an authorized real Judge trial remain
separate from synthetic test success.

## Capture forget integration (implemented, not installed)

The existing explicitly authorized `capture_forget` operation now writes a
content-free cleanup intent in the same transaction as source invalidation.
Only after that transaction commits, while still holding both existing locks,
does it remove bound external metric results. The original rollback boundary
remains inside Memory Root; no external path is added to the transaction.

If cleanup fails or is interrupted, the intent survives. A later explicit
`capture_forget` first resumes those committed intents, validating the same host
ledger identity and the redacted receipt or suppression tombstone. No model or
source session is read during cleanup. Source invalidation is not rolled back
after commit merely because external deletion failed.

An incomplete cleanup returns `status=deferred`, code
`capture_metrics_cleanup_pending`, and `source_forget_committed` /
`current_request_applied` describing the current request. False means previous
cleanup blocked this request before its source transaction; it does not imply
that an earlier request was rolled back. Active/unknown attempts and unbound
inventory remain deferred, not treated as completed or safe to delete.

Before actual model sends, the host records its ledger identity in the Capture
runtime's `metrics-host.json`. A missing or changed host/configuration/ledger
cannot silently become "metrics was never enabled". This marker is metadata-only,
is not a formal memory and is not included in managed backups. The cleanup path
does not construct a model client. Production installation and live acceptance
remain outstanding; current attempt/report handling is described above.

## Restricted cleanup executor (not a production entry point)

The internal `apply_cleanup` API now accepts an explicit-user-request assertion,
the trusted host ledger/commit guard and a previously inspected candidate snapshot.
Under the guard it rebuilds the exact snapshot and rejects pending/unbound records
or changes before deleting anything. Each selected fixed file is checked again
against directory, source/dependency, full terminal digest and file hash/identity.
It unlinks only those result files, retaining directories, registrations, send
reservations and other files. A final snapshot confirms the expected absence.

`selected_artifacts_removed` describes this selected snapshot only, not full
forget. An observed mid-operation failure returns `cleanup_incomplete`, a fixed
error and the exact successful unlink list; deletions are not rolled back. This
response is not a durable crash-recovery journal. An authorization string is a
host assertion, not authentication. Capture forget now calls this internal API
through the transaction/intent coordination above; there is no separate cleanup
CLI. It is not the same as a completed production rollout or complete retention
coverage of every report artifact.

## Result commit coordination (development boundary)

Host quality and classification commands now use the existing Memory Root write
lock during final source/configuration checks, registration verification and
result/receipt writes. Model calls run outside the lock. Busy locks or failed
final checks preserve a failed attempt without a new result or automatic retry.
Standalone library callers default to no host lock and must supply their own
coordination; that default is not a production guarantee.

`cleanup_candidates` only reads the fixed artifact inventory and selects exact
receipt/subject matches with bound directory identity and fixed artifact names.
It returns hashes and metadata, not contents. Missing terminal records are
reported separately as pending, not assumed to be running or safe to delete;
unbound records cannot establish source ownership. This is not delete authority.
Source invalidation, registered result cleanup and partial-cleanup recovery now
connect to authorized Capture forget. Pending-attempt reconciliation and remaining
report dependencies are not yet covered by that integration.

## External execution directory inventory (development boundary)

Host execution also records `send-ledger/source-bindings/<plan_id>.json`, joining
each evaluated subject to its original Capture receipt identity. Native research
and classification references use `receipt_id_for(RevisionRef.key)`; the record
contains only controlled IDs and a native-reference digest, never source text or
locators. Classification retains duplicate/ambiguous manifest membership but
registers only ready inputs. Identical registration is idempotent; conflicting
content cannot overwrite it. Source joins are metadata; live source verification
still happens separately. Failed attempts can have inventory records too.

Directory registrations v2 now bind the source inventory's binding_id and verify
subject membership. Missing/changed inventories invalidate formerly bound results.
Host sending, reuse, review freezing and both export paths require non-null source
binding, including recursive and final checks. Standalone library calls may retain
null bindings, but host exports do not accept them. Old v1 records are not silently
migrated. Registration alone remains unrelated to delete authority; the explicit
forget request and verified source invalidation supply the cleanup scope above.

The fixed metrics host send ledger now has an `artifact-registry` containing
content-free registrations of exact Eval/classification execution directories,
their filesystem identities and source/config dependency manifests. New model
calls through the Runner/classifier require successful registration first.
Runner reuse and classification-result reading reject missing or changed records.
Host CLI review freezing and evidence export also bind this ledger through
recursive result verification. Evidence export rechecks registration after its
last source reads; unavailable registrations cannot produce available cases.
This is not deletion authorization, tamper-proof provenance or completed forget
integration. Library callers omitting the optional ledger perform only lower-level
file/live-source checks, not host registration verification.
No automatic cleanup, old-result migration or production installation is included.

## Human review queue

Rendering a frozen review includes a presentation-only case queue. All flagged
cases precede normal spotchecks: non-usable execution states, M2 retention,
omission or uncertainty labels, M5 risk/unsupported/uncertain or non-specific
connection labels, and latest human disputes/corrections. Each group is sorted
by case ID. At most two unflagged initial judgments are selected across all
scenarios; omitted spotcheck counts remain visible. This is not random sampling
and must not estimate overall Judge accuracy. Metric denominators and the full
metadata remain unchanged.

The queue labels program states, original LLM labels and human feedback
separately. Human acceptance never erases an original risk label. The human
revision panel and queue use the same validated revision snapshot. No source
body or model free-text reason is included, and rendering never calls a Judge.
Managed external-result cleanup and on-demand sensitive evidence viewing remain
separate unfinished work; this queue does not establish production readiness.

## M5 independent task cohort (development interface)

`agc-metrics research-cohort --batch batch.json --tasks tasks.json
--classifier classifier.json --output NEW_PRIVATE_DIRECTORY` freezes supplied
frontend-task metadata. It does not scan sessions, classify content, call a Judge,
or use Recall logs. The output parent must already exist; output is never replaced.

Each task has exactly `task_ref` (opaque ID), `revision` (SHA-256), `delivered_at`
(timezone-aware timestamp), `decision`, `reason`, and `evidence_status`.
Decisions/reasons: include/research_connection_request;
exclude/not_research_connection|background_task|not_delivered;
ambiguous/task_boundary_unclear|intent_unclear. Evidence status is
available/unavailable/unknown. Task IDs must be unique across revisions.

Classifier fields: method llm|human, rule_version, configuration_digest and
authorization_ref. LLM classification requires a configuration hash and opaque
authorization reference; human classification uses null for both. These are
caller-supplied metadata, not proof of consent or verified classification.

Method `delivered_at_then_task_ref_first_5_v1`: use the batch's half-open business
window, sort by delivery time and task ID, select at most five included tasks with
available evidence. Keep all supplied rows, including exclusions, ambiguity,
unavailable evidence, outside-window and sample-cap cases. The cohort is only a
selected frontend-task sample, never a full-population denominator. A zero selected
count is not evidence that no research tasks occurred. No quality score is computed.

The cohort interface does not yet produce classifications from authorized session
content. Selected rows can now connect to historical input/final evidence using
the research plan and execution commands below; automatic classification remains
required implementation work.

### Research plan adapter boundary

`metrics_research_plan.prepare_research_plan(batch, cohort, source=..., judge=...)`
now maps only selected tasks to one research_relevance step each. A source adapter
implements `prepare({task_ref, revision})`, returning exactly task_ref, revision,
and documents with ref/version/role/content fields. It must resolve authorized
historical evidence and fail on missing, revoked or changed source material.
The native input/final adapter and research CLI are implemented in source. Richer
historical background/source roles and production installation/acceptance remain
pending; synthetic verification is not production evidence.

The plan/source map contains references and digests, never content. Input/output
roles are required, historical background/source roles optional; current_memory
is forbidden. Missing historical background cannot be filled using today's data.
`research_plan_resolver` binds the batch/cohort/task map and re-resolves each case
on execution and cached-result verification. Changed content invalidates the old
plan; hashes and role declarations alone are not source-authenticity evidence.
Synthetic integration covers execute, reuse, frozen review, HTML and unavailable
source refusal. It is not evidence of live M5 benefit or production source coverage.

### Codex historical input/final source (not production-wired)

`CodexResearchSource(adapter, native_references, policy=CapsulePolicy(...),
access=CaptureResearchAccess(paths))` now
implements the research source protocol for explicitly bound Codex main-task
revisions. `describe_task(ref)` returns opaque task identity, content/policy-bound
revision, delivery time and availability. The adapter does not discover all tasks
or classify research intent. Multiple revisions of one task must be resolved by
the sampling layer first; duplicate task bindings are rejected.

It reuses native source identity, completion and settled-file validation. Only
user messages and one unambiguous explicit final answer are projected; commentary,
analysis, reasoning/tool records and subagent-marked messages are excluded. It
does not infer background or paper content from arbitrary tool output. Missing
finals, post-delivery timestamps, conflicting finals, known secrets/private paths
or oversized messages cause unavailability rather than silent truncation. These
checks do not guarantee detection of every possible sensitive passage.

The revision binds source records, native reference, policy and transform version.
Each prepare rereads and checks it; no private content is cached in plan metadata.
The source now requires live CaptureResearchAccess checks before reading, after
loading and before returning. It rejects matching Capture suppression tombstones,
redacted/excluded/quarantined receipts, source quarantine/conflict and degraded
Capture integrity. Existing configuration and Capture namespaces must be readable;
missing configuration never falls back to defaults. Task exclusions apply before
source reading; project exclusions are checked once session project metadata is
available, with unknown project rejected when project exclusions exist. A receipt
is not required: an uncaptured task can still be sampled. These checks read current
Capture snapshots; they do not create or repair control files, grant user consent,
or claim managed cleanup of already generated reports. Production host wiring must
still enforce the explicit authorized source scope. Historical background/source-role
extraction and task classification integration remain open.

Unsupported input/final message shapes (including unhandled images) are unavailable,
not silently omitted from an otherwise scoreable task. Explicit foreign turn IDs
are rejected; conflicting analysis/commentary phase or channel is never projected
as final output merely because an is_final flag is also present.

### Research CLI

The internal research classification contract now binds one intent label to each
ready preparation input (task reference, revision and input digest). It rejects
missing, duplicate, foreign or version-mismatched labels and quality-score fields.
Only task input is provided, never the answer. Controlled include/exclude/ambiguous
reasons feed the existing first-five cohort rule; the complete preparation manifest
is retained separately, including unavailable and over-budget entries. These
entries are not fabricated as classified exclusions. Supplied labels/configuration
remain caller-supplied and unverified. A structured payload now uses the existing
MetricsGateway interface, with an exact-length labels array and no extra fields.
Output validation checks both JSON structure and the bound label semantics.
The contract alone does not invoke the classifier; execution must check live
access, reserve the fixed send ledger and obtain
explicit consent before sending any content. A payload is not a send grant.

The internal classification executor now freezes the payload, preparation and
requested model configuration into a one-call plan (zero calls for no ready
inputs). It checks the exact consent digest before resolving live inputs, reserves
the host-supplied ledger exclusively, and rechecks live preparation/configuration
before and after the call. Failure consumes the slot; switching output folders
does not enable a retry. It stores metadata, controlled labels and receipts, not
input bodies or arbitrary exception text. An unfinished/failed attempt is not a
usable classification. prepare-classification-plan and classify-research now
bind this executor to the fixed host configuration and send-ledger. Preparation
writes only plan.json and preparation-manifest.json to a new directory. Execution
requires the exact approved --consent digest and an existing private output
directory outside source/host roots. Its classification_status distinguishes
completed, classification_error and no_ready_inputs; top-level status=ok means
the command returned, not that classification succeeded. A caller-chosen
replacement ledger is not authorization, and a matching digest is not proof of
human consent. This executor has only synthetic/mock-model test evidence.

The internal read_classification verifier now reconstructs the plan from live
inputs, checks the fixed reservation plus start/finish/result/receipt records,
validates labels, requested/observed configuration, usage and time ordering, and
rejects missing, failed, conflicting or changed artifacts. It rechecks sources
and artifacts before returning without model calls or writes. Its verification
means local consistency and currently available source evidence, not authenticity
of files, consent or classifier correctness. This is not an atomic snapshot.
export-classification now exposes this verifier through the fixed host and ledger,
writing research-cohort.json and classification-verification.json to a new private
directory. The latter retains the full preparation manifest and verification
time; it is not a permanent source authorization. The cohort can feed
prepare-research-plan with only its selected native references (at most five).
Preparing the quality-evaluation plan invokes no model, and executing it requires
its own authorization. Classification export never retries a model call.

Offline render optionally accepts --research-cohort research-cohort.json. It
validates the frozen cohort against the batch and displays selection counts,
per-task decision/reason/evidence state, classifier method and sampling limits.
These are independent cohort metadata, not M5 quality denominators or whole-window
task counts. Rendering does not verify the cohort's per-case association with a
quality review or live source validity. Preparation-stage unavailable/over-budget
inputs are absent from the cohort and remain in the preparation manifest; this
section alone must not be presented as full capture/classification coverage.

render also accepts --research-preparation preparation-manifest.json, displaying
the five preparation states and per-reference metadata without reading input
bodies. Its denominator is explicitly supplied native reference entries, not
independent tasks. Ready means input was prepared at that time, not classified or
evaluated. Budget exclusions follow deterministic ordering, not random sampling.
Metadata validation does not validate document content or current permission;
model-call paths still require complete digest-bound inputs and live source checks.

### Explicit private evidence annex (internal API)

freeze_evidence can prepare an opt-in review-evidence annex containing the full
frozen model assessments and their version-bound safe documents. The default
review/report remains content-minimized. Each usable review case is reverified
against saved execution records and live source access; unavailable cases retain
only an unavailable marker. Offline validation binds the annex to the exact review,
result digests, subjects and documents. Maximum canonical size is 16 MiB; overflow
fails rather than truncating evidence. No model is called and no file is written
by this API. Do not persist its content-bearing return value while managed cleanup
is unavailable. export-review-evidence generates only evidence-index.json and
content-free report.html
in a new private directory, using fixed host roots and the source map for the
review's plan. Research plans require matching cohort and selected native
references; Capture plans use their Capture source map. Mixed-source plans are
not supported by this command. Generation performs live reads and verification,
but never calls a Judge or overwrites a prior output. Response case counts retain
unavailable evidence rather than treating export success as evidence completeness.
Offline render now
accepts an existing --evidence with a matching --review, validates the annex but
displays only case states, result references and document identifiers. It never
embeds source bodies or unchecked model reasons, even when explicitly supplied.
Raw evidence viewing must remain on-demand via a local resolver, not bulk HTML.

This annex contains private source and model-derived text, not proven facts or
hidden model reasoning. Do not commit or publish it. Frozen validation does not
recheck access, and managed forget cleanup of exported artifacts is still pending;
the annex must not be represented as automatically revocable or production-ready.
Earlier content-bearing annex/HTML export was removed to honor the approved design
section 10; the private label alone did not satisfy that boundary. Existing files
are not automatically deleted. Model-derived execution-result retention is a
separate remaining implementation requirement, not solved by this export change.

### Local derived-result dependency records

Evaluation and classification attempts now write dependencies.json before the
model call. It identifies exact case/input references, configuration/rule identity,
dependent result (where applicable) and fixed result/receipt filenames, without
source bodies. Failure to write it prevents that call. Readers require the exact
record and recheck it before reuse; older results without registration are not
silently accepted or backfilled. This is local dependency recording, not a global
directory registry or completed integration with hard forget. Existing hard forget
manages Memory Root namespaces, while metrics outputs may reside outside them;
external-result discovery and cleanup still need implementation before production
content retention can be considered compliant with the approved design.

`research-inputs --batch batch.json --references native-revisions.json` prepares
classification material from at most 100 explicit native references. It performs
no model invocation or file write. JSON stdout contains research_preparation:
a content-free manifest with digest-bound ready input references and preserved
outside_window/ambiguous_revision/evidence_unavailable entries, plus private safe
task-input documents. Answers are not returned to the classification layer.
Inputs are private content: do not publish stdout, commit it or send it to a
classifier outside authorized scope. This is not full-window task discovery or
semantic classification; classification_status remains not_classified. Duplicate
tasks within the window are left ambiguous; the command does not silently choose
a revision. The canonical UTF-8 inputs array is bounded to 2 MiB without
truncation. In completion-time/task/reference order, an input that does not fit
is omitted and its manifest entry retains input_budget_exceeded and its version
and digest references. Later smaller inputs may still fit. All manifest entries
and status counts remain available; this partial return is not a random sample.

`prepare-research-plan --batch batch.json --cohort research-cohort.json
--references native-revisions.json --output NEW_DIRECTORY` uses the fixed metrics
host binding and resolves only the cohort's selected tasks. References are native
RevisionRef mappings, at most five, with no duplicate task bindings. Source roots
must be configured in host.json; selected IDs and delivery timestamps must match
the native references. The command reads authorized historical inputs/finals but
does not call a model. It writes only plan.json and source-map.json.

`evaluate-research --batch batch.json --cohort research-cohort.json
--references native-revisions.json --plan PLAN_DIR/plan.json
--source-map PLAN_DIR/source-map.json --consent APPROVED_DIGEST
--output EXISTING_EXECUTION_DIRECTORY` uses the same fixed send-ledger as Capture
evaluation. Consent is checked before research evidence resolution. Source and
Capture access policy are checked live during execution and reuse; output includes
unique run/review/report artifacts, per-entry status and model-call attempts.
The consent string binds scope but is not proof of human consent. Classifications
and native references must come from the user's authorized review workflow.

CLI tests use real host/source/runner/report code with synthetic JSONL and a mocked
Judge. They prove integration and reuse, not live model quality or AGC benefit.

## P2 Capture evidence (source implementation; not production-enabled)

The instrumented `agc-capture run` and Runner `cycle --once --max-items N`
boundaries can now record independent, content-free attempt metadata. Scanner-only
cycles, manual backfill, review delivery, memory writes and Recall are not yet
instrumented by this feature.

Opt-in is `AGC_METRICS_EVIDENCE_DIR`, pointing at an existing absolute private
directory with no symlink/junction ancestors. No default path or automatic
directory creation is provided. Use a dedicated directory per Memory Root;
this version does not record a root fingerprint or verify configuration identity.
No production environment variable has been set by this implementation.

Each invocation allocates random attempt/Trace/span IDs before configuration
loading and writes `<attempt_id>.started.json`. The normal return path writes a
separate `.finished.json` after the optional Trace attempt. Files are exclusive,
flushed and fsynced; repeated terminal writes cannot replace earlier outcomes.
The CLI adds `data.metrics_evidence` only when opted in, with separate start and
finish recording diagnostics. Missing directories, invalid inputs or I/O failures
do not change business return codes. Record creation failure means the business
inventory itself may be incomplete; there is no all-process coverage claim.

Trace uses the same preallocated IDs. `recorded`, `disabled`, `suppressed` and
`unavailable` are delivery statuses, not reference verification. A business
`completed` cycle may still contain failed items or zero observations: it is not
a memory-quality result. If interruption occurs before the terminal write,
including while Trace is being emitted, only the start may remain.

`agc_runtime.metrics_evidence.read_capture_attempts(directory)` is a read-only
inspection API. It reports completed/failed, terminal_unobserved, orphan_terminal,
state_conflict, and invalid record counts. Duplicate JSON fields, unknown fields,
bad IDs, mismatched filenames and oversized/changed records are rejected without
echoing content. It does not repair files, call models, or independently validate
Trace delivery. The snapshot is not a cross-file transaction or a frozen report.

Only cycle-level IDs, timestamps, implementation/recorder versions, a small
count allowlist and fixed status/error enums are stored. Configuration identity
is explicitly unknown. No source/receipt IDs, task text, Capsule, raw error,
memory content or model output is copied. These are still private metadata;
deletion of external report copies is not guaranteed. Local file tampering and
concurrent filesystem path replacement are not authenticated by this feature.

Supply `--attempts-dir <private-directory>` to `prepare` to consume these receipts.
The resulting v2 batch preserves independent business rows and read diagnostics.
M1 uses window-started attempts and shows the Trace start cohort separately.
M3 samples up to ten business attempts, ordered by start time and opaque ID;
it checks identity/start/terminal agreement. Missing Trace source is unchecked,
whereas a complete readable Trace snapshot with no match is not_observed.
Configuration, implementation binding and content references are still unchecked,
so even matching attempts are only partial, not fully traceable.

Without `--attempts-dir`, prepare retains the original v1 format and interpretation.
Both formats render offline. Output within the attempt source directory is refused.
Actual disk overhead and production compatibility still require installation-stage
verification. Full review/save/Recall evidence bindings and Judge remain pending;
the implemented service-boundary metadata is described below.

## Service-boundary evidence

With the same opt-in environment variable, read/write/notice dispatchers append
metadata under its `business/` child directory. The root must already exist;
recording failure adds only `metrics_evidence_unavailable`, without altering the
business decision, returned content, or permission checks. Disabled mode returns
the original response unchanged.

Recall records opaque object IDs and hashes of the exact returned representation,
not memory text or authoritative historical file versions. Search `results/items`
are recorded once. Actual use is unknown. Formal-memory write acceptance and
Capture review-receipt success/failure are distinct fields; acceptance also covers
idempotent duplicate-source responses and does not by itself prove a new mutation.
Notice records do not assert preview delivery. Task, confirmation, Trace and
configuration bindings remain unknown unless a later implementation verifies them.

`prepare --business-dir <metrics-root>/business` includes the records in a v3
frozen batch and displays separate M1 service-stage statuses. Both v1 and v2
batches remain supported. This source is explicit; supplying an attempts directory
does not silently read its business child. Frozen rendering never rereads live
memory. Results are metadata, not memory quality or task benefit measurements.

P1 implements explicitly requested metadata collection, frozen batches and a
self-contained HTML report. It is not a production activation, content Judge,
scheduled job, or memory write workflow. There are no default production paths.

## Commands

From a source checkout, use `python -m agc_runtime.metrics_cli`. A future package
installation exposes the same interface as `agc-metrics`.

```powershell
python -m agc_runtime.metrics_cli prepare --start 2026-09-03T00:00:00+08:00 --end 2026-09-10T00:00:00+08:00 --output D:/tmp_test/agc-report-20260911
```

With no source arguments, the command produces an honest unavailable-data report,
not a report about the user's production system. Supply explicitly authorized
paths with `--trace-db`, `--eval-db`, and `--receipts-dir` to read their metadata.
SQLite connections use `mode=ro` and `query_only`; they never initialize a store.
The receipt directory is the directory of individual receipt JSON files, not the
Memory Root. It is read as a current metadata snapshot, without Census rebuilding.

`--cutoff` defaults to `--end`; a later explicit cutoff allows observing terminal
events after the business window. Dates must include a timezone. The window is
left-closed/right-open. `--synthetic` labels caller-supplied fixtures as synthetic;
it does not fabricate input data. Do not use it to relabel production evidence.

The new output directory contains `batch.json`, `metrics.json`, and `report.html`.
Existing destinations are refused. A partial filesystem failure may leave an
incomplete new directory; use another destination after inspecting the error.

```powershell
python -m agc_runtime.metrics_cli render --batch D:/tmp_test/agc-report-20260911/batch.json --output D:/tmp_test/agc-report-20260911/reopened.html
```

Render verifies the frozen batch and uses no live source, network or model.
The same batch and renderer reproduce the same HTML. Changed evidence requires
a new batch; changing a file without its matching digest is rejected. Digests
are integrity checks, not signatures or proof that supplied evidence is truthful.

## What the report can say

### Offline evaluation plan (P3 partial)

`agc-metrics plan --batch batch.json --cases cases.json --judge judge.json
--rules rules.json --output new-plan-directory` validates a frozen batch and
writes `plan.json`. It reads only these four explicit files, rejects duplicate
JSON keys and inputs larger than 32 MiB, and refuses an existing output directory.
No model, Capture configuration, production store or automatic scheduler is used.

Judge configuration is independent: provider, model, reasoning_effort (low or
medium), timeout_seconds, executable_identity and adapter_identity are required.
Identities are SHA-256 digests; caller-provided identities are not proof that
an executable or host actually used those settings. observed_judge stays null.

Cases contain an opaque case_id, scenario (collected/zero/research), subject_digest
and versioned evidence_refs. Each scenario is limited to five cases. M2 cases
have required_claims then align_candidates steps; research cases have one
research_relevance step. Rules bind each step's profile/prompt/schema digests.
The plan records its maximum call count and authorization_digest. This digest
identifies what must be reviewed; generating it does not grant authorization.

The current command is planning only. Resolving live evidence, checking revocation,
binding the real adapter, validating structured domain assessments and executing
authorized steps remain pending. It does not establish M2/M5 results or M4 coverage.

`metrics_assessment` now defines the three domain schemas and validates case
citations, unique claim IDs and complete alignment. M2 counting keeps uncertain
reference claims outside determinate matching denominators and reports them
separately. No candidates yields a null retention ratio, not perfect quality.
M5 preserves relevance and misleading independently, displaying misleading first.

`freeze_assessment` / `validate_record` bind derived results to the exact plan,
entry, schema and preceding required-claims result. They do not execute a Judge
or verify live source resolution. Records retain unchecked evidence, no execution
receipt and unreviewed human status. Claim text and reasons are private derived
content; do not publish them or copy them into Trace metadata. Report integration
and the authorized execution path are still pending.

`metrics_judge_input.rule_identities()` supplies built-in v1.1 profile/prompt/schema
digests for a plan. Its `build_input` validates the subject's stage/version/role
mapping and exact supplied document digests, then constructs a detached in-memory
payload. `required_claims` receives safe input only; candidate content/references
and outcome stratum are hidden. Alignment takes the previously frozen reference.
Even zero requires an explicit candidate artifact; missing is not empty.

Research input requires task input/output; historical background may be missing
but is never replaced with current memory. These functions neither read source
stores nor prove role provenance. The executor must enforce consent, resolve safe
evidence and check current revocations. No CLI execution path is enabled yet.

`metrics_eval_summary.summarize_evaluations` computes M4 from an explicit plan and
attempt metadata at a cutoff. It preserves first/last finished attempts, unfinished
retries, duplicates, conflicts and invalid records. Planned cases and steps are
separate; M2 needs both steps with matching dependency result identity. It never
selects a best score. A completed row without external verification is unchecked,
not usable. The verifier must validate actual result/receipt/evidence; a supplied
status alone is not proof. This summary is not yet wired into CLI reports or a
production attempt store.

`metrics_execution.execute_entry` now writes exclusive started/result/receipt/
finished artifacts around one trusted gateway invocation. A start write failure
prevents calling; interruption retains the start; exceptions produce fixed error
metadata. Result-write or receipt-write failures cannot claim completed, even if
an orphan result file remains. Readers must require consistent terminal/receipt.
Insufficient evidence stays in the assessment, separate from execution success.

This is an injected execution API, not a production CLI. It checks the plan digest
and configured gateway contract but does not yet bind the actual Codex binary or
manage host-wide consent consumption. Duplicate protection is local to the chosen
report directory. Real gateway/resolver/verifier integration is still pending.

The Codex gateway is now implemented as `MetricsGateway`: it binds explicit
absolute executable/wrapper file paths, hashes file content and adapter/gateway
implementation, and checks for changes before and after calls. Model/effort are
independent (default gpt-6-astra/medium). Missing optional structured adapter fails
explicitly; it does not substitute another model or discover an executable.
Integration tests use the real local adapter with simulated subprocess output,
not an actual provider call. Resolver, consent consumption and report integration
remain pending. Fingerprints are not provenance signatures or atomic attestation.

`CaptureMetricsSource(AGCCaptureEvidenceResolver(...))` bridges existing safe
Capture evidence into metrics cases. `prepare(reference)` creates a private,
in-memory bundle; `resolve(bundle)` re-reads its native source and checks exact
identity; `revoked_refs(bundle)` invalidates derived refs if unavailable or changed.
Use the latter callback before/after execution and on reuse. It does not claim
whether invalidation was caused by deliberate forgetting or temporary failure.
The existing resolver's read-only snapshot behavior is preserved; no rescanning
or Census repair occurs. Other evidence types and managed artifact invalidation
are not yet connected. Static exported copies are not automatically revoked.

`metrics_result_reader.summarize_execution_directory(plan, directory, cutoff=...,
resolve_case=...)` now reads saved attempts and verifies results before M4 counting.
The source callback must provide current subject/documents/revoked_refs from a
safe resolver. It checks source binding, actual sent citations, schema, receipt,
configuration, usage, input/result digests, and reference-before-alignment timing.
No model call or file repair occurs. Missing live evidence is unchecked; invalid
saved artifacts are errors. File consistency does not authenticate a fabricated
local ledger or prove the Judge's semantic correctness. Frozen HTML consumption
and human revisions remain pending.

`metrics_review_batch.freeze_review` now creates content-minimized frozen analysis
rows from verified executions; `validate_review` and `review_metrics` validate and
recompute M2/M4/M5 without live reads or model calls. Rows retain controlled labels,
stage/subject identity, result digests and unreviewed human status. No source text,
claim text or Judge reasons are exported. M2 strata/subject identities are kept
separate; research relevance and misleading are separate axes. Hash integrity
does not authenticate the source or make old evidence permanently valid.
HTML/CLI integration and human revisions are not yet implemented.

## Current report interpretation

| Metric | P1 behavior |
|---|---|
| M1 | Visible Capture root start-cohort states, conflicts, terminal/item event counts and error-code tags. No global success rate. |
| M2 | Not measured: no private content/Judge execution. Zero output is not a quality verdict. |
| M3 | Up to 10 current receipts, sorted by update time/opaque ID, matched to item Trace IDs. All full evidence checks remain unchecked; conflicts are visible. No complete traceability rate. |
| M4 | Stored AGC Capture Eval result metadata by status. No planned coverage, technical usability or Judge accuracy claim. |
| M5 | Not measured: no independent task/background cohort or content evaluation. |

All five sections have per-metric methods, limitations and counts. Empty data,
missing sources, malformed records and unperformed evaluation are distinct.
Capture emits useful-cycle Trace records at completion and suppresses some idle
cycles: these events cannot serve as a complete business-request denominator.
Review/save/Recall historical adapters and full digest resolution are not part
of this P1 metadata implementation.

## Privacy and limits

- Persist only allowlisted metadata; no statements, Capsules, recommendations,
  error messages, original Session content, or absolute source paths.
- IDs/source paths become stable opaque digests; this does not make reports
  anonymous. Treat all reports as private artifacts outside version control.
- Receipts explicitly marked forgotten are excluded. P1 never exports source
  text. Frozen static reports do not automatically refresh when a source is
  revoked; do not use old reports as live memory or authorization evidence.
- Sources have separate read times, not a cross-store transaction. A concurrent
  receipt rewrite detected during reading is an invalid record, not a good empty
  result. Source authenticity and global store health are not established.
- Collection scans selected stores' metadata before time projection. Large-store
  performance and production workload acceptance remain unverified.
- No Judge call, automatic schedule, formal-memory change, install or Git push
  occurs through these commands. Content evaluation and human correction come in
  later phases.
# Frozen review annex rendering

Review v3 additionally freezes content-free `execution_history`. M4 displays
each step's first attempt, latest finished attempt and unfinished/total counts.
These are observations from the supplied execution directory, not a claim that
all historical retries were discovered. Selection follows start time and attempt
ID, never the highest score. Readers keep v1/v2 support; absent history is not
invented when rendering older reports.

New `agc.metrics-review.v2` annexes distinguish the business source `cutoff` from
`evaluation_cutoff`. `freeze_review` defaults the latter to the current UTC time,
or accepts an explicit observation cutoff. Evaluations after the source cutoff
can therefore be included without changing the frozen business population.
Per-metric methods show both times. Legacy v1 annexes retain their single-cutoff
meaning; reading them does not silently re-freeze or backfill results.

## Human feedback sidecars

Use an existing empty private directory dedicated to one frozen review. After
actual explicit user feedback, `agc-metrics review --batch batch.json --review
review.json --feedback feedback.json --revisions-dir human` appends a revision.
The feedback object has exactly `case_id`, `decision` (accepted/corrected/disputed),
`correction`, `feedback_ref` (opaque `id_` SHA-256), and an offset-aware `timestamp`.
Provenance references are not proof of consent; the caller must obtain feedback.
Accepted/disputed require null correction. Corrected requires the controlled
`candidate_verdicts`, `required_matches`, `research` projection matching that case.
No free-form source or explanation text belongs in this content-minimized file.

Then use `render --batch batch.json --review review.json --revisions-dir human
--output report-revision.html` with a new output path. Original initial judgments
remain visible; human status and corrected arithmetic are separate. No response
means unreviewed. History gaps/corruption reject rather than silently skipping.
Do not edit sidecars in place; append another explicit feedback revision.

`agc-metrics render --batch batch.json --review review.json --output report.html`
renders a validated same-batch review annex without source reads or model calls.
The output path must not exist. Omitting `--review` retains the metadata-only
report. Both input files use bounded strict JSON; duplicate keys are rejected.

M2 retains collected/zero strata, stage and subject-version grouping, explicit
numerators/denominators and uncertainty. M4 uses planned **cases** as coverage
denominator, with steps separately displayed. M5 shows misleading risk before
relevance and keeps human review separate. These are frozen initial assessments,
not proof of causal benefit or current source validity. Per-card methods explain
the distinction; source text and Judge explanations are not embedded.
