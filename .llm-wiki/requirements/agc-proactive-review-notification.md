# Change Brief: agc-proactive-review-notification

## Summary

- title: AGC Proactive Capture Review Notification
- status: ready
- flow_id: `agc-proactive-review-notification`
- why: Automatic Capture currently stops after storing observations, so useful evidence can accumulate without reaching the existing complete-preview and explicit-confirmation workflow.

## Sources

- User-confirmed design decision: use Codex App as the notification and review surface.
- `agc_runtime/capture_read_service.py`
- `agc_runtime/admin_service.py`
- `skills/agent-global-context/references/formalization-workflow.md`
- `docs/superpowers/specs/2026-08-23-agc-quality-first-formalization-design.md`
- Official Codex Scheduled Tasks and Notifications documentation reviewed on 2026-08-31.

## Active Scope

- A deterministic, content-safe Capture review-readiness view.
- A content-free local notice cache that suppresses repeated alerts for 24 hours.
- Exact `agc.read` and `agc.admin` actions for scheduled Codex App review runs.
- A bounded scheduled-review Skill workflow that produces complete, non-mutating Memory Item previews.
- Focused tests, operator documentation, and Runtime 0.4.5 release metadata.

## Read-Only Scope

- Existing Capture observations and terminal review receipts.
- Existing quality-first formalization and formal-memory write contracts.
- Existing Capture Runner, Trace bridge, Eval Pilot, and production Memory Root.

## Excluded Scope

- Capture extraction, taxonomy, project-scope, Recall, Trace, or Eval behavior changes.
- Automatic formal-memory promotion, update, reinforcement, discard, or `needs_context` writes.
- Persisting preview text, raw Session content, Capsule content, model output, or reasoning.
- Windows-native toast integration or a new notification daemon.
- Production installation and Codex App automation creation before a separate deployment confirmation.

## Acceptance Criteria

1. `agc.read capture_review_status` reports unreviewed count, oldest age, a bounded oldest-first batch of at most 10 observation IDs, safe category/kind aggregates, and a deterministic batch digest.
2. Readiness is true when at least 10 unreviewed observations exist or the oldest unreviewed observation is at least 24 hours old; degraded Capture integrity fails closed.
3. `should_notify` is false for an empty/not-ready queue and for 24 hours after the same local review queue was notified.
4. `agc.admin capture_review_notice` accepts only an exact SHA-256 batch digest and stores only schema version, digest, and UTC notification time in an operational cache.
5. Cache loss may cause a repeat notification but cannot lose or mutate Capture observations, review receipts, or formal memories.
6. The scheduled Codex App workflow remains quiet when `should_notify` is false. When true, it reads only the returned safe observation IDs, generates at most three complete Memory Item previews, records the notice, and waits for explicit user confirmation.
7. Preview generation never calls a formal-memory write. Only a later explicit user confirmation may use the existing `confirm`, `update`, or reinforce-compatible `observe` path with `capture_observation_ids`.
8. Existing Capture, formalization, backup/restore, Hard Forget, Trace, and Eval tests remain green.

## Verification Plan

- Follow the TDD checkpoints in `.llm-wiki/working-context/agc-proactive-review-notification.md`.
- Run focused review-status, read/admin dispatch, MCP, Skill adapter, and documentation contract tests.
- Run the complete pytest suite under the user-designated centralized test root.
- Run compile, package, CLI/MCP version, strict UTF-8/no-BOM, and `git diff --check` gates.
- After separate deployment confirmation, install without replacing the production Memory Root or Trace database, create the Codex App scheduled review, and run one manual readiness cycle.

## Plan

- active_plan: `.llm-wiki/working-context/agc-proactive-review-notification.md`
- status: confirmed
- execution_mode: inline on the current `main` branch, as confirmed by the user

## External Dependencies

- project_id: Codex App host capability
- edge_id: not applicable; host-owned product surface rather than a repository contract
- dependency_type: scheduled task and desktop notification surface
- required_contract: a local scheduled task can return to a Codex App task and surface a run that needs user input
- evidence: official Codex Scheduled Tasks and Notifications documentation
- verification_status: source-verified
- impact_on_change: AGC owns readiness and content safety; Codex App owns scheduling, notification delivery, preview rendering, and user interaction
- fallback_or_handoff: the existing manual formalization workflow remains available when scheduled tasks are unavailable

## Flow Record

| Step | Status | Evidence | Updated |
|---|---|---|---|
| source | done | current Runtime/Skill source plus confirmed user request | 2026-08-31 |
| design | done | confirmed AGC readiness plus Codex App notification boundary | 2026-08-31 |
| plan | done | `.llm-wiki/working-context/agc-proactive-review-notification.md` | 2026-08-31 |
| development | pending |  | 2026-08-31 |
| testing | pending |  | 2026-08-31 |
| archive | pending |  | 2026-08-31 |

## Open Questions

- Production installation and scheduled-task creation remain a later explicit deployment gate after local verification.
