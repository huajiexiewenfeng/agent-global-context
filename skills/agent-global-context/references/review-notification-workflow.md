# Proactive Capture Review Notification

Use this workflow only from a Codex App scheduled review task or when the user explicitly asks to check whether Capture review is ready. Codex App owns scheduling and notification delivery. AGC owns readiness, safe observation selection, formalization rules, and memory-domain writes.

1. Call `agc.read` with `{"action":"capture_review_status"}`.
2. If `should_notify` is false, produce no user-facing result. Do not call a model-facing formalization step, `capture_get`, or `capture_review_notice`.
3. If `should_notify` is true, read only the returned `batch_observation_ids`. Call `capture_get` once per selected id. Never reopen a raw Codex Session, transcript, or Capsule.
4. Follow `formalization-workflow.md` for grouping, relevant formal-memory comparison, deduplication, and the grounded/self-contained/decision-relevant/bounded/policy-valid quality gates. Different or null project scopes retain the conservative rules in that workflow.
5. Prepare at most three proposals. For every usable proposal, show the complete Memory Item, whether it is new/update/reinforce, and every contributing observation id. A batch may produce zero proposals when the evidence is noise or needs context.
6. Keep `needs_context` and `discard` classifications separate from formal-memory confirmation. When the batch produces zero proposals, record every observation's non-memory outcome with `agc.write` action `capture_review` (`discard` for clear noise or transient actions; `needs_context` when the evidence is not self-contained). This closes the reviewed batch but does not create or update formal memory. When the batch has any proposal, wait for the user's decision before recording its contributing observations or any adjacent non-memory outcomes.
7. After the complete preview result is ready to show, call `agc.admin` with `{"action":"capture_review_notice","batch_digest":"<the exact batch_digest returned by capture_review_status>"}`. This records only content-free delivery state.
8. End with the task waiting for explicit user confirmation. Never write formal memory from the scheduled run. Only a later user confirmation may call `confirm`, `update`, or reinforce-compatible `observe` with the exact contributing `capture_observation_ids`.

If readiness or exact observation reads fail, report a short safe operational error and do not record a notice. If preview generation succeeds but `capture_review_notice` fails, show the preview and state that the reminder may repeat; formal memory remains unchanged.
