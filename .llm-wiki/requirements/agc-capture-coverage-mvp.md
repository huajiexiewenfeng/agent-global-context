# Change Brief: agc-capture-coverage-mvp

## Summary

- title: AGC Codex Task Revision Capture Coverage MVP
- status: planned
- flow_id: agc-capture-coverage-mvp
- why: AGC can govern and recall formal memories, but it cannot prove that completed Codex task revisions were checked for durable signals. The system currently cannot distinguish no useful signal from capture not running or failing.
- changes: Add a failure-open side-channel capture plane that discovers every in-scope main-task revision, records a truthful Capture Receipt, stores zero to eight safe classified Collected Observations, and exposes read-only capture coverage views. Capture data never enters ordinary Recall; pre-existing Recall lifecycle and budget defects are corrected as an activation gate.
- does_not_change: The AGC North Star, three-tool public MCP surface, formal-memory semantics, formal-memory-only Recall model, sensitive persistence boundary, project-local LLM Wiki ownership, and current task success behavior remain unchanged.

## Sources

- `docs/superpowers/specs/2026-07-28-agent-global-context-v2-design.md`
- `docs/superpowers/specs/2026-08-13-agent-global-context-high-coverage-capture-design.md`
- User confirmation on 2026-08-13: the next milestone is provable capture coverage, not the complete automatic-learning loop.
- User confirmation on 2026-08-13: capture is global for in-scope main tasks in the active Codex profile, heavy processing stays outside the foreground task, and checking every task does not mean saving or recalling every task.
- Current Runtime and deployed-host inspection on 2026-08-13: no Capture Runner or global Hook is enabled; project-local v1 routing and global v2 routing can coexist; overview can exceed its declared budget before adding cards; source-level idempotency cannot represent multiple observations from one revision.

## Scope

- active:
  - one diagnosable v2 Skill/MCP/Memory Root route for the active Codex profile
  - ordinary Recall contract gates required before capture: lifecycle-safe Catalog/Search and a hard overview token budget
  - Codex main-task discovery, revision identity, dirty marking, reconciliation scanning, watermarks, and recovery
  - Capture Receipt schema, state machine, storage, validation, and read-only coverage reporting
  - Collected Observation schema, classification, provenance, lifecycle, storage, safety filtering, and read-only search
  - two-level idempotency and atomic commit across observations, receipt state, and watermark progression
  - Capture-aware backup, restore, and user-authorized Hard Forget across all AGC-managed copies
  - a versioned semantic Extractor Adapter with a safe isolated Codex non-interactive reference implementation
  - recent seven-day bounded backfill and continuous incremental processing
  - failure-open execution, bounded concurrency, backpressure, token accounting, and foreground-latency verification
- reference-only:
  - current formal-memory schema, write lifecycle, migration, and three-tool MCP contracts
  - current Codex local task/session sources and official Hooks behavior
  - existing v1 rollback material until v2 routing consistency is verified
- excluded:
  - Observation aggregation, Candidate creation, Candidate adjudication, or automatic Formal Memory mutation
  - Recall ranking, embeddings, vector databases, knowledge graphs, Trace Runtime, Eval Runtime, or Loop Runtime
  - TencentDB Agent Memory or any other external memory engine
  - full historical transcript replay, raw transcript storage, code/Diff/log storage, or project LLM Wiki replacement
  - subagent transcripts as independent capture units
  - UI dashboard, multi-user/team ACL, cross-device sync, or remote capture service

## Acceptance

1. The active Codex profile can report exactly one effective AGC Skill, MCP Runtime version, Memory Root, configured Codex source roots, Extractor boundary, background budget, and capture enabled/paused state; capture remains off until explicitly enabled.
2. Ordinary `agc.read overview` never exceeds its configured hard response budget; ordinary overview/search exclude non-recallable lifecycle states by default.
3. Every settled main-task revision in the frozen recent seven-day backfill census has one truthful Capture Receipt or user-authorized content-free suppression tombstone, including zero-observation, deferred, retryable, failed, and quarantined outcomes; unkeyed source anomalies degrade Source Health and cannot be hidden by the coverage percentage.
4. After the initial watermark is established, every newly settled or continued main-task revision is eventually represented by a Receipt, explicit coalesced relationship, or user-authorized suppression tombstone; no revision disappears without state.
5. Foreground Hooks only mark a source revision dirty or enqueue a source reference. They do not read full transcripts, build Task Capsules, call a model or network, classify content, or mutate formal memory.
6. Capture model calls and semantic work run in a background Runner. A reconciliation Scanner, not Hook delivery alone, guarantees eventual coverage.
7. A completed extraction stores zero to eight Collected Observations, each with a stable observation id, short atomic statement, primary category, kind, scopes, project scope when applicable, observed time, short source locator, schema/extractor versions, and processing state.
8. Capture idempotency is keyed at task-revision level, while Observation idempotency is keyed at observation level. One task revision can safely create multiple observations; exact replay creates no duplicates.
9. Observation writes, final Receipt transition, and watermark progression are crash-consistent. Partial work can be retried without silent loss or duplicate observations.
10. Secret and sensitive content is discarded before any AGC-managed persistent object. Task Capsules, full transcripts, thoughts, tool logs, long code, Diffs, and terminal output are never persisted by Capture.
11. Collected Observations are absent from the formal Catalog and ordinary Recall. Users can inspect them only through explicit read-only capture overview/search actions.
12. Capture failure, backlog, model unavailability, source corruption, or budget exhaustion never changes the original Codex task result, triggers a task retry, or claims a successful capture.
13. The foreground latency gate measures Hook contribution separately from background processing. Target added latency is `p95 < 100 ms`; if the host/process combination cannot meet it, Capture operates Scanner-only rather than weakening the foreground gate.
14. Runner concurrency defaults to one, supports pause/backpressure, and reports discovered, complete, zero-observation, deferred, retryable, failed, quarantined, coalesced, token, and duplicate-suppression counts.
15. The active profile supports global pause plus explicit project/task exclusions. Exclusion decisions create metadata-only state and do not persist excluded task content.
16. Re-running the seven-day backfill stays within the confirmed `100,000` total model-token ceiling and does not expand to older history without a new user decision.
17. Capture backup/restore preserves schema, references, idempotency, and Recall isolation. Every Capture-capable Runtime rejects unsupported Capture schema; once Capture data exists, host rollback keeps a Capture-capable Runtime and blocks binary downgrade to the pre-Capture 0.2.0 Runtime.
18. User-authorized Capture Hard Forget removes Observation content and content-derived summaries from every AGC-managed copy. Observation-level forget transactionally redacts its Receipt; Revision-level forget leaves only a content-free suppression tombstone. Both leave the original Codex task unchanged.

## Plan

- active_plan:
  - `docs/superpowers/plans/2026-08-13-agent-global-context-capture-core.md`
  - `docs/superpowers/plans/2026-08-13-agent-global-context-codex-source-census.md`
  - `docs/superpowers/plans/2026-08-13-agent-global-context-capture-extractor-runner.md`
  - `docs/superpowers/plans/2026-08-13-agent-global-context-capture-host-rollout.md`
- status: confirmed
- execution: Subagent-Driven Development in the current session, directly on `main`
- evidence: On 2026-08-13 the user selected option 1, then explicitly directed implementation on `main` after the isolation prompt.

## External Dependencies

- project-id: codex-host
- edge_id: none
- dependency_type: lifecycle-hooks-and-local-task-source
- required_contract: Background-capable `Stop` notification, synchronous and advisory `SessionEnd`, main-thread identity, transcript/source references, and active config-root discovery. Scanner reconciliation must tolerate missed/cancelled Hook delivery and source-format evolution.
- evidence: Official OpenAI Codex Hooks documentation plus read-only inspection of the active Codex profile and local task metadata.
- verification_status: source-verified
- derived_staleness: fresh
- impact_on_change: Hook behavior shapes the low-latency wake-up path; local source discovery and adapter tests remain the correctness path.
- fallback_or_handoff: If Hook behavior or transcript format changes, disable Hook wake-up and continue Scanner-only discovery through a versioned Source Adapter.

## Flow Record

| Step | Status | Evidence | Updated |
|---|---|---|---|
| source | done | confirmed v2 North Star, current Runtime evidence, and 2026-08-13 user decisions | 2026-08-13 |
| design | done | approved written specification in `docs/superpowers/specs/2026-08-13-agent-global-context-high-coverage-capture-design.md` | 2026-08-13 |
| plan | done | four dependency-ordered TDD plans with AC-01 through AC-20 traceability | 2026-08-13 |
| development | in progress | Capture Core and Codex Source Census Tasks 1-6 are implemented on `main`; the Source Census Task 6 E2E required one narrow replay fix for the existing single-slot Source Quarantine, while Extractor/Runner and Host rollout remain unimplemented and inactive | 2026-08-19 |
| testing | in progress | Source Census Task 6 focused: `3 passed`; ordered adjacent: `99 passed`; complete suite: `647 passed`, one intentional duplicate-ZIP warning; clean installed-wheel `agc-capture` and exactly-three-MCP-tools gate: `2 passed` | 2026-08-19 |
| archive | pending |  | 2026-08-13 |

## Capture Core Task 6 Evidence

- Scope: `agc_runtime/cli.py`, `tests/test_cli_contract.py`,
  `tests/test_capture_core_end_to_end.py`, and
  `tests/test_runtime_end_to_end.py`; the production delta is only a version
  alias. No Source, model, Runner, Hook, provider, network, scheduler, host, or
  deployed-profile behavior changed.
- RED: the new E2E scaffold was run before its proof was implemented and
  failed with exit `1`, `1 failed`, at the intentional
  `disabled Capture core E2E proof is not implemented` assertion.
- Review RED/GREEN: `agc --version` first failed with exit `2`/`invalid_tool`;
  after the minimal alias change both version forms passed. The final scoped
  CLI and E2E command exited `0` with `11 passed in 11.59s`.
- Complete suite: the final venv-first run with the documented bundled build
  backend available only as fallback exited `0` with `514 passed, 1 warning in
  318.80s`. The warning is the intentional duplicate-name ZIP attack case.
- Production/test/mocks: the production delta is the version alias only. The test uses the real
  `CaptureStore`, admin/read/write dispatchers, filesystem backup/restore, and
  both hard-forget transactions. Monkeypatching is limited to fail-fast guards
  before init for subprocess, planned Source/model/provider imports,
  source-root enumeration, socket, and URL APIs; no
  persistence, hashing, read routing, backup, restore, or forget behavior is
  mocked.
- Assertions/actual behavior: a synthetic root initializes and validates;
  Capture is disabled with configured source count `0` and no configured
  model; two synthetic observations commit once and exact replay creates `0`
  duplicates; only explicit Capture actions can read them; a third
  post-backup Observation makes restore prove a `3` to `2` state change;
  exact Observation forget, and exact Revision forget succeed; the revision
  forget leaves one content-free suppression tombstone and does not delete the
  source task. An outside-root source sentinel remains byte-exact through both
  forget types. The Formal Catalog byte hash and memory count `0` remain
  identical at every boundary, and every boundary guard records `0` calls.
- Ordinary Recall: the Runtime E2E now proves the overview stays at or below
  the configured `250`-token default, only active lifecycle items appear, and
  validate succeeds both before and after formal forget.
- Package evidence: a clean disposable source copy built a wheel offline with
  the documented no-isolation backend and installed it into a disposable
  environment. Installed `agc --version` and `agc version` both reported
  Runtime `0.2.0`, installed
  admin validation returned `accepted`, and the installed artifact exposed
  exactly `agc.admin`, `agc.read`, and `agc.write`.
- Text/package gates: strict UTF-8/no-BOM covered `132` tracked text files,
  `compileall` covered `agc_runtime` and `tests`, and `git diff --check` ran on
  the final scoped diff; all exited `0`.
- Backward-restore residual risk: Capture archives declare Capture schema `1`
  and the current Runtime rejects unknown Capture schema, but the package still
  reports `0.2.0`. A pre-Capture binary with the same version cannot safely
  restore or govern Capture data, and host-level binary downgrade prevention
  remains deferred. Capture is not usable or activated by this evidence.

## Codex Source Census Task 6 Evidence

- Scope: a synthetic-only E2E in `tests/test_capture_census_end_to_end.py`,
  lifecycle evidence, and a narrowly authorized replay correction in
  `CaptureStore.record_source_quarantine` / `CaptureScanner`. No live profile,
  Extractor, Runner, model/provider, host route, scheduler, service, or formal
  write path was enabled.
- Corpus: one configured Codex root with `10` final JSONL files / `3297` bytes
  covers ordinary main completion, two continued revisions, exact
  active/archive replay plus archive move, subagent, incomplete/aborted and
  partial tails, unknown source shape, one configured exclusion, one transient
  sharing failure, and one late/out-of-order completion. A separate configured
  marker and a failed/missed Hook delivery prove that dirty state is only a
  hint and Scanner reconciliation is correctness authority.
- Accounting: cycle 1 records `5/5` known/accounted keys while the locked key's
  marker remains durable. Cycle 2 converges to `7/7`, `0` silent loss,
  `6` discovered plus `1` excluded Receipt, `7` Ledger entries, `0`
  tombstones, `1` content-free Source Quarantine, and `0` dirty markers. The
  marker unlink guard observes matching durable Receipt/Ledger accounting
  before acknowledgement.
- Replay: the third exact cycle creates `0` Receipts and replays `7`; Census
  key membership and correctness metadata, Receipts, Ledger, tombstones,
  quarantines, conflicts, and scan-state correctness remain unchanged except
  allowed run/timestamp/version bookkeeping. Active/archive locator movement
  remains non-identity metadata and continued turn ids remain distinct.
- Authentic product RED: after the intentional scaffold RED, the completed E2E
  failed because exact replay refreshed Source Quarantine `created_at`. The
  minimal fix preserves same-binding/same-code quarantine bytes, permits the
  existing different-code single-slot replacement contract, fails closed on a
  malformed existing quarantine, and persists only the deterministic final
  diagnostic for one binding/batch.
- Isolation: ordinary Recall remains empty, Capture Observation count is `0`,
  Candidate/Formal Memory/Event counts and the Formal Catalog hash remain
  unchanged, response and Capture persistence contain none of the synthetic
  content/path/exception sentinels, and every model/provider/network,
  subprocess, extractor, Task Capsule, target-turn load, Observation write,
  formal write, Hook-install, service/scheduler, and unconfigured-root guard
  remains `0`.
- Verification: focused `3 passed in 3.70s`; disabled-boundary-first adjacent
  `99 passed in 35.04s`; natural-order complete suite `647 passed, 1 warning in
  301.09s`; clean copied-source wheel install plus installed `agc-capture`
  probe and exact `agc.admin`/`agc.read`/`agc.write` surface `2 passed in
  10.93s`. The warning is the intentional duplicate-name ZIP adversarial case.
- Remaining gates: Extractor/Runner behavior, token-budget and model-call
  evidence, real-profile shadow backfill, continuous hosting, Hook trust and
  foreground p95 latency, host route activation, and binary downgrade
  prevention remain pending explicit gates. This does not complete or activate
  the overall Capture Coverage MVP.

## Open Questions

- Extractor/Runner enablement, real-profile Scanner shadow backfill, Hook
  trust/foreground latency, continuous hosting, host route activation, and
  binary downgrade prevention remain separate explicit human gates.

## Notes

- “Global” means all in-scope main tasks under the configured active Codex profile, not every Windows user, every Codex home, or independent subagent execution.
- “Every task is checked” means every in-scope settled revision receives truthful state. It does not mean every revision creates an Observation, Candidate, Formal Memory, or Prompt injection.
- Capture coverage metrics are correctness telemetry for this subsystem, not the deferred Trace/Eval/Loop Runtime.
