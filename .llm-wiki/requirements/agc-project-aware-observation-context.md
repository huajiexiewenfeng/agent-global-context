# Change Brief: agc-project-aware-observation-context

## Summary

- title: AGC project-aware Observation context and review aggregation
- flow_id: agc-project-aware-observation-context
- status: executing
- change: Preserve a stable, opaque project scope during Codex Capture and use it to aggregate related atomic Observations during quality-first review.
- why: Production backfill produced correct but fragmented statements with `project_scope: null`, forcing the user to explain that observations from multiple Sessions referred to one X-publishing open-source project.

## Sources

- User-confirmed production case on 2026-08-24/25: three extracted statements about article-roadmap planning, per-article summaries, and open-source participation all referred to one X-publishing open-source project.
- `agc_runtime/capture_runner.py`: constructs `CapsulePolicy` without `project_scope`.
- `agc_runtime/codex_source_adapter.py`: loads `session_meta` but does not resolve a project binding for the Capsule.
- `agc_runtime/capture_capsule.py`: already carries `TaskCapsule.project_scope`.
- `agc_runtime/capture_extractor.py` and `agc_runtime/schemas/capture-extractor-v1.schema.json`: Observation drafts already carry `project_scope`.
- `agc_runtime/capture_read_service.py`: already exposes and filters `project_scope`.
- `skills/agent-global-context/references/formalization-workflow.md`: quality-first review can aggregate related Observations without reopening raw Sessions or launching another extractor.
- Existing Capture boundary: `.llm-wiki/requirements/agc-capture-coverage-mvp.md`.

## Confirmed Design

### 1. Keep atomic Observations

Collected Observations remain short, atomic evidence units. The extractor must not pack a project description, workflow, goal, and preference into one compound Observation. Existing persistence safety, fingerprinting, receipt identity, backup/restore, Hard Forget, and read contracts remain schema version 1.

### 2. Resolve one opaque project scope upstream

The Codex adapter derives a stable project scope from the target Session's validated `session_meta.cwd` when present.

- Normalize the cwd deterministically without accessing that directory.
- Reject empty, relative, control-bearing, or unreasonably long values.
- Hash the normalized value and emit only an opaque identifier with the `project:cwd:` prefix followed by 64 lowercase hexadecimal characters.
- Never persist, log, return, or include the absolute cwd itself in a Capsule, Observation, error, diagnostic, or test artifact.
- The same normalized cwd produces the same scope across Sessions; different cwd values produce different scopes.
- Missing or unsafe metadata produces `None` and preserves current conservative behavior.

The resolved scope is applied to the per-revision `CapsulePolicy` before Capsule construction. Extractor drafts must preserve the exact Capsule scope, as already required by the persistence gate.

### 3. Require self-contained project wording when evidence supports it

The extractor instruction should prefer an atomic statement that includes the bounded project referent visible in the safe Capsule title or user signal. For example, prefer `用户需要先规划 X 发文项目的文章整体路线` over `用户需要先规划文章的整体路线` when the project referent is actually supported.

The extractor must not invent a project name, expand an opaque scope into a name, or turn a project fact into a personal global fact. If the safe Capsule lacks a supported referent, it keeps the shorter atomic statement and tentative confidence.

### 4. Aggregate automatically at review time

Quality-first formalization remains the synthesis boundary.

- Group observations from the same receipt before drafting.
- When a selected Observation has a non-null `project_scope`, automatically query additional unreviewed Observations for that exact scope through the existing Capture search filter.
- Review at most 20 observations for one project in one pass; paginate explicitly rather than silently truncating.
- Synthesize the minimum number of self-contained Memory Item proposals from the group and list every contributing Observation id.
- Do not merge observations with different non-null scopes.
- A null scope does not authorize cross-Session semantic merging. It may only use same-receipt grouping or explicit user confirmation.
- Semantic similarity alone may propose `needs_context`; it must not silently merge or promote.

This makes the normal review path automatic for strongly linked project work while preserving human confirmation only for genuinely ambiguous cross-project cases.

### 5. Existing production observations

This change does not rewrite Observation ids, fingerprints, receipts, or historical `project_scope: null` records. The user-confirmed X-publishing case may be synthesized during a separately confirmed formalization operation using its existing Observation ids. No migration or replay is part of this change.

## Scope

- active:
  - `agc_runtime/codex_source_adapter.py`
  - `agc_runtime/capture_project_scope.py`
  - `agc_runtime/codex_extractor.py`
  - focused Capture contract/safety/runner/extractor tests
  - `skills/agent-global-context/references/formalization-workflow.md`
  - focused Skill adapter tests
  - this Change Brief and a linked working-context/plan after approval
- reference-only:
  - `agc_runtime/capture_runner.py`
  - `agc_runtime/capture_capsule.py`
  - `agc_runtime/capture_extractor.py`
  - `agc_runtime/capture_read_service.py`
  - `agc_runtime/capture_contracts.py`
  - `agc_runtime/capture_schema.py`
  - `.llm-wiki/requirements/agc-capture-coverage-mvp.md`
- excluded:
  - Observation schema v2 or migration
  - vector embeddings, graph databases, or fuzzy cross-project clustering
  - automatic Formal Memory promotion
  - rewriting existing production Observations or receipts
  - reopening production raw Sessions during review
  - additional model calls, production backfill, installation, release, or GitHub push
  - filesystem or Git inspection of a Session cwd during scope derivation

## Acceptance

1. Two Codex Sessions whose valid metadata cwd normalizes identically produce the same opaque `project_scope` in their Task Capsules and accepted Observations.
2. Different valid cwd values produce different scopes; absent, relative, malformed, control-bearing, or oversized cwd values produce `None` without failing Capture.
3. No absolute cwd appears in persisted Capture objects, public read results, logs, exceptions, diagnostics, repr output, or test artifacts.
4. Runner ranking and extraction use the per-revision resolved scope without changing Census identity, Receipt identity, source fingerprint semantics, concurrency, budget accounting, or authorization digest boundaries beyond the expected Capsule hash change.
5. Extractor instructions require supported, self-contained project wording but preserve atomicity, evidence grounding, tentative inference rules, and the existing persistence gate.
6. Formalization review automatically expands a selected non-null project scope through the existing `project` filter, groups same-receipt observations, and presents coherent proposals with all contributing ids.
7. Review never silently merges different scopes or cross-Session null-scope observations and never auto-promotes a proposal.
8. A regression fixture representing the X-publishing case demonstrates that three atomic Observations from two Sessions under one scope are reviewed as one coherent project proposal rather than three unrelated memories.
9. Focused tests, adjacent Capture tests, Skill contract tests, strict UTF-8/no-BOM checks, `compileall`, and `git diff --check` pass with all test artifacts routed to the operator-configured centralized temporary root.

## Non-Goals

- Maximizing candidate count or recall rate.
- Guessing project identity from semantic similarity alone.
- Combining unrelated durable facts merely because they share a cwd.
- Turning project-specific work into a global preference or identity claim.
- Solving the separate task-aware backfill ranking performance bottleneck.

## Risks And Controls

- cwd aliases or project moves can create different scopes: accept as a conservative false negative in this MVP; do not add filesystem access or a registry migration.
- Multiple unrelated tasks can share one cwd: scope is a candidate set boundary, not proof that every Observation becomes one Memory Item; synthesis still checks compatible meaning and evidence.
- Task titles can be vague or adversarial: use them only after the existing Capsule safety gate and never as sole evidence for a direct assertion.
- Changing Capsule scope changes Capsule hashes for newly processed revisions: preserve frozen historical receipts and do not reopen completed revisions automatically.

## Verification Plan

- TDD RED/GREEN tests for deterministic safe scope derivation and adapter-to-Capsule propagation.
- TDD tests proving exact scope preservation through extraction and persistence filtering.
- Skill contract regression for same-receipt grouping, exact-project expansion, the 20-item bound, null-scope conservatism, and no automatic promotion.
- Focused and adjacent Capture regression suites using only synthetic Session fixtures.
- No production Session, model, Memory Root mutation, or external network use during development verification.

## Plan

- active_plan: `.llm-wiki/working-context/agc-project-aware-observation-context.md`
- status: verified
- evidence: Tasks 1–4 implemented with TDD; focused adjacent suite reports 582 passed

## External Dependencies

- none

## Context Handoff

- lifecycle_session: project-develop / agc-project-aware-observation-context
- user_intent: stop requiring manual user explanation when related Capture observations belong to one project
- active_sources: current Runtime source/tests, confirmed production symptom, existing formalization workflow
- active_scope: project-scope derivation, propagation, extractor wording, review aggregation, focused tests/docs
- read_only_scope: existing Observation/Capsule/read contracts and Capture Coverage requirement
- candidate_scope: none
- excluded_scope: schema migration, fuzzy clustering, production replay/model/install/release
- current_gate: project-finish review
- requested_stage_or_bridge: finishing-a-development-branch
- constraints: correctness and low noise over capture volume; no auto-promotion; no raw Session reopening during review

## Flow Record

| Step | Status | Evidence | Updated |
|---|---|---|---|
| source | done | user-confirmed production case and current source inspection | 2026-08-25 |
| design | done | confirmed design recorded in this Change Brief | 2026-08-25 |
| plan | done | `.llm-wiki/working-context/agc-project-aware-observation-context.md` | 2026-08-25 |
| development | done | `f7b4c86`, `6ee4b04`, `ce54a93`, `bb24171` | 2026-08-25 |
| testing | done | focused adjacent suite: 582 passed; compileall/diff/UTF-8 gates passed | 2026-08-25 |
| archive | pending |  | 2026-08-25 |

## Open Questions

- none

## Notes

- Documentation mode: new Change Brief, because the prior Capture Coverage MVP is implemented and this adds a new observable project-linking and review behavior.
- The design deliberately reuses `project_scope` and the existing Capture project filter instead of introducing a new Observation contract.
- Planning reduced the production-code scope: per-revision resolution belongs inside the Source Adapter, so `capture_runner.py` remains reference-only.
- Verification touched no production Memory Root, scheduler, installer, release, configuration, or raw Session content.
- Residual risks remain conservative false negatives after project moves/path aliases and same-cwd unrelated work; review semantics, not scope alone, decide whether to synthesize memory.
