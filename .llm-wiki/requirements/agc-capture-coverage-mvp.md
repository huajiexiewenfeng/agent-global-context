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
- status: proposed
- execution: awaiting user selection between Subagent-Driven Development and Inline Execution
- evidence: The user approved continuation after written-spec review; four dependency-ordered TDD plans now map AC-01 through AC-20 to independently runnable gates.

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
| development | pending |  | 2026-08-13 |
| testing | pending |  | 2026-08-13 |
| archive | pending |  | 2026-08-13 |

## Open Questions

- Execution mode is not yet selected. Real-profile Scanner enablement, Hook trust, Shadow Backfill, and continuous Runner activation remain separate explicit human gates even after implementation.

## Notes

- “Global” means all in-scope main tasks under the configured active Codex profile, not every Windows user, every Codex home, or independent subagent execution.
- “Every task is checked” means every in-scope settled revision receives truthful state. It does not mean every revision creates an Observation, Candidate, Formal Memory, or Prompt injection.
- Capture coverage metrics are correctness telemetry for this subsystem, not the deferred Trace/Eval/Loop Runtime.
