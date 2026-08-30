# Working Context: agc-capture-eval-pilot

- lifecycle_session: `agc-capture-eval-pilot`
- user_intent: Execute the confirmed AGC Capture Eval Pilot after the generic Eval Runtime is locally implemented and verified.
- active_sources:
  - `../requirements/agc-capture-eval-pilot.md`
  - `../../docs/superpowers/plans/2026-08-30-agc-capture-eval-pilot.md`
- active_scope: safe Capture evidence, completed-item Trace events, AGC evidence resolution, EvalCase sampling, Profile, manual authorization CLI, and local verification.
- read_only_scope: Capture truth, Trace database, and source-verified Agent Runtime Modules public APIs.
- candidate_scope: preparation-only read of installed production Trace after all synthetic checks pass.
- excluded_scope: live Judge calls, automatic scheduling, memory mutation, production installation, publishing, tags, and push.
- current_gate: blocked-on-runtime-dependency
- requested_stage_or_bridge: test-driven implementation after Eval Runtime verification
- constraints:
  - Trace stays generic; AGC defines domain evidence
  - one immutable complete receipt yields at most one item event and case
  - all integration imports are optional and failure-open
  - preparation never resolves semantic evidence or calls a model
  - use only the user-designated global test root for temporary artifacts

## Verification State

- Repository clean before implementation.
- Full pre-change test baseline: 1372 passed with one existing duplicate-name warning.
- A long Windows test path produced environmental failures; the same representative tests and full suite passed with the required short path under the designated test root.
